"""Calendar platform for xtend_tuya.

Exposes two merged calendars for the fdm5kw irrigation valve family:

  - `calendar.irrigation_planned`   — every enabled timer slot on every
                                       valve, expanded as a weekly
                                       recurrence inside the [start,
                                       end] window HA queries.

  - `calendar.irrigation_completed` — historic watering runs sourced
                                       from the recorder (paired
                                       start_time / end_time states
                                       per device, with the matching
                                       watering_volume peak as totals).

Both calendars share the same title / description formatter:

    {valve} - {duration} m | {l/min} l | {total} l

The averages line in the description is a 30 s-cached "last 10 runs"
summary per device. Title `total` is the all-time lifetime liter sum
from the watering_volume sensor's current value (TOTAL_INCREASING
long-term statistic accumulator on each cycle reset).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from aiohttp import web

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN, DOMAIN_ORIG

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

REGISTRY_SUFFIX = "irrigation_timer_registry"
WATERING_VOLUME_TRANSLATION_KEY = "watering_volume"
START_TIME_TRANSLATION_KEY = "start_time"
END_TIME_TRANSLATION_KEY = "end_time"
CLOSE_TIME_TRANSLATION_KEY = "close_time"
# T3 valves have no start/end-time sensors; their completed runs come from
# the counter_custom last-run sensor instead (runs_store listens on it).
LAST_RUN_TRANSLATION_KEY = "last_watering_run"

# Entity-id suffix fallbacks for installs whose entities pre-date the
# translation_key bump in 4.4.150 (registry stores translation_key only
# at first registration). Mirrors the same pattern in the dashboard
# strategy so calendar + dashboard agree on which sibling is which.
_ENTITY_SUFFIX_TO_ROLE: tuple[tuple[str, str], ...] = (
    ("_last_watering_start", "start_entity"),
    ("_last_watering_end", "end_entity"),
    ("_watering_volume", "volume_entity"),
)

ICS_VIEW_REGISTERED_KEY = f"{DOMAIN}_ics_view_registered"
ICS_DEFAULT_FUTURE_DAYS = 30
ICS_DEFAULT_PAST_DAYS = 30

# Completed-calendar safety cap on the per-device recorder window so a
# 90-day Google Cal pull on a 48-valve fleet stays bounded.
COMPLETED_MAX_WINDOW = timedelta(days=90)
# Runs-store listener re-arm cadence (see async_setup_entry).
RUNS_STORE_REARM_INTERVAL = timedelta(minutes=15)
# Last-N runs we average per device for the description line.
LAST_N_FOR_AVERAGES = 10
# Cap on a single watering cycle. FDM5KW battery / typical tank means a
# real cycle never runs more than a few hours; anything longer is
# either a stale registry slot or a broken start/end recorder pairing
# and must not bleed into the calendar UI.
MAX_SANE_RUN_SECONDS = 6 * 3600
# Cap on liters delivered in one cycle. The QT-08W impeller tops out at
# 25 L/min, so even the longest sane run can't exceed 25 * (cap minutes).
# A derived per-run volume above this means the cur_cap delta is garbage
# (e.g. an odometer reset mid-run) and must be dropped, not shown.
MAX_SANE_RUN_LITERS = 25 * (MAX_SANE_RUN_SECONDS / 60)


def _run_volume(
    vol_series: list[tuple[datetime, float]],
    start_lu: datetime,
    end_lu: datetime,
    run_minutes: float | None = None,
) -> float | None:
    """Per-run liters = peak cur_cap in the run window, ignoring spikes.

    cur_cap resets to 0 at cycle start and ramps up as water flows, so the
    peak inside the run window is the liters delivered. But the DP glitches:
    it intermittently reports a garbage value (e.g. 15237, 177610 L —
    observed on ~2 of 488 samples, 2026-07-06) that sticks as the idle
    resting value between runs. A plain max() picks up that spike and shows
    an impossible per-run total. Dropping any sample above MAX_SANE_RUN_LITERS
    filters the spikes while keeping the real ramp.
    """
    # Scale the ceiling to the ACTUAL run duration, not the 6 h cap:
    # a 5-minute run physically tops out around 125 L, so a 2,000 L
    # sample inside it is garbage even though it clears the absolute
    # ceiling. 50 L/min = 2× the meter's 25 L/min spec — margin for
    # cur_cap's ~10 s update lag; 50 L floor keeps sub-minute runs from
    # rejecting their own real ramp. (Valve 824 emitted exactly this
    # class of sub-ceiling garbage, 2026-07-06.)
    # run_minutes is passed explicitly when the sampling window is wider
    # than the actual run (see the pairing loop) — the spike ceiling must
    # scale with the real watering duration, not the window size.
    if run_minutes is None:
        run_minutes = max((end_lu - start_lu).total_seconds() / 60, 0.0)
    sane_cap = min(MAX_SANE_RUN_LITERS, max(50.0, 50.0 * run_minutes))
    peak: float | None = None
    for ts, v in vol_series:
        if ts < start_lu or ts > end_lu:
            continue
        if v > sane_cap:
            continue  # glitch spike — not a real reading
        if peak is None or v > peak:
            peak = v
    return peak


async def async_setup_entry(
    hass: HomeAssistant,
    entry: "ConfigEntry",
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the merged calendars for this config entry.

    A single planned-calendar entity and a single completed-calendar
    entity cover every fdm5kw valve under every xtend_tuya config
    entry; HA collapses duplicates by unique_id when multiple entries
    call this. The entities read live state from `hass.states` and the
    recorder on each `async_get_events`, so adding/removing valves
    after setup is picked up automatically.
    """
    from .runs_store import async_get_store

    store = await async_get_store(hass)
    async_add_entities(
        [
            IrrigationPlannedCalendar(hass, store),
            IrrigationCompletedCalendar(hass, store),
        ]
    )

    # Arm the end-sensor listener for every valve known right now (devices
    # appearing later are picked up on each calendar render) and run the
    # one-time recorder backfill in the background — the ONLY recorder
    # scan left in the recording path, and it is off the request path.
    store.track_devices(_iter_fdm5kw_devices(hass))
    _maybe_start_backfill(hass, store)

    # Re-arm periodically. Relying on setup + renders alone broke live: the
    # 4.4.233 speedup made this platform set up before the valve sensors
    # exist, so the boot-time arm saw no devices — and with nobody opening
    # the calendar panel, NO runs were recorded fleet-wide (Aug 10-12).
    # track_devices is additive/idempotent and a state walk is cheap.
    async def _rearm(_now) -> None:
        store.track_devices(_iter_fdm5kw_devices(hass))

    entry.async_on_unload(
        async_track_time_interval(hass, _rearm, RUNS_STORE_REARM_INTERVAL)
    )

    # Register the ICS export view once across all xtend_tuya config
    # entries — the view resolves entities at request time, so a single
    # registration covers every fdm5kw calendar instance in the hass.
    if not hass.data.get(ICS_VIEW_REGISTERED_KEY):
        hass.http.register_view(XtendTuyaCalendarICSView())
        hass.http.register_view(XtendTuyaRunsExportView())
        hass.data[ICS_VIEW_REGISTERED_KEY] = True


def _maybe_start_backfill(hass: HomeAssistant, store) -> None:
    """Kick the one-time backfill when valves are actually visible.

    Calendar platform setup can run before the valve entities exist, so
    this is also called from each render — first call that sees devices
    starts the job; the in-flight guard keeps it single."""
    if store.backfilled or getattr(store, "_backfill_started", False):
        return
    if not any(
        d["start_entity"] and d["end_entity"] and d["volume_entity"]
        for d in _iter_fdm5kw_devices(hass)
    ):
        return
    store._backfill_started = True
    hass.async_create_task(_async_backfill_runs(hass, store))


async def _async_backfill_runs(hass: HomeAssistant, store) -> None:
    """One-time import of the last 30 days of runs from the recorder into
    the runs store. Slow (minutes on a 107-valve fleet) but runs in the
    background — never on a request path."""
    try:
        devices = [
            d
            for d in _iter_fdm5kw_devices(hass)
            if d["start_entity"] and d["end_entity"] and d["volume_entity"]
        ]
        w_end = datetime.now().astimezone()
        w_start = w_end - timedelta(days=30)
        added = 0
        # Chunk to keep individual recorder queries bounded.
        for i in range(0, len(devices), 15):
            chunk = devices[i : i + 15]
            states = await _batch_significant_states(
                hass,
                [
                    e
                    for d in chunk
                    for e in (
                        d["start_entity"],
                        d["end_entity"],
                        d["volume_entity"],
                    )
                ],
                w_start,
                w_end,
            )
            for d in chunk:
                runs = _pair_runs(
                    states.get(d["start_entity"], []),
                    states.get(d["end_entity"], []),
                    states.get(d["volume_entity"], []),
                    window_start=w_start,
                    window_end=w_end,
                )
                added += store.merge_backfill(d["tuya_device_id"], runs)
        store.backfilled = True
        store.async_schedule_save()
        _LOGGER.info(
            "irrigation runs backfill complete: %d runs from %d valves",
            added,
            len(devices),
        )
    except Exception:  # noqa: BLE001 — backfill must never break setup
        _LOGGER.warning("irrigation runs backfill failed", exc_info=True)


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------


def _format_lpm(l_per_min: float | int | str | None) -> str:
    if l_per_min is None or l_per_min == "?" or l_per_min == "—":
        return "—"
    if isinstance(l_per_min, float):
        return f"{l_per_min:.1f}".rstrip("0").rstrip(".") + " L/min"
    return f"{l_per_min} L/min"


def _format_volume(volume_l: float | int | None) -> str:
    if volume_l is None:
        return "—"
    if isinstance(volume_l, float):
        return f"{volume_l:.1f}".rstrip("0").rstrip(".") + " L"
    return f"{volume_l} L"


def _format_completed_title(
    valve_name: str,
    duration_min: int,
    l_per_min: float | int | None,
    cycle_l: float | int | None,
) -> str:
    """Title for completed runs. cycle_l is delivered volume that run."""
    return (
        f"{valve_name} · {duration_min} min · "
        f"{_format_lpm(l_per_min)} · {_format_volume(cycle_l)}"
    )


def _format_planned_title(
    valve_name: str,
    duration_min: int,
    avg_lpm: float | None,
    estimated_l: float | None,
) -> str:
    """Title for planned slots. Values prefixed with ~ to mark them as
    estimates from historical averages, not committed values."""
    lpm_part = (
        f"~{_format_lpm(avg_lpm)}" if avg_lpm is not None else "—"
    )
    vol_part = (
        f"~{_format_volume(estimated_l)}" if estimated_l is not None else "—"
    )
    return f"{valve_name} · {duration_min} min · {lpm_part} · {vol_part}"


def _format_description(
    valve_name: str,
    registry_entity_id: str,
    duration_min: int,
    l_per_min: float | int | str,
    lifetime_l: int | None,
    event_type: str,
    avg_lpm: float | None,
    avg_per_cycle: float | None,
) -> str:
    lifetime_str = str(lifetime_l) if lifetime_l is not None else "?"
    lpm_str = (
        f"{l_per_min:.1f}".rstrip("0").rstrip(".")
        if isinstance(l_per_min, float)
        else str(l_per_min)
    )
    avg_lpm_str = f"{avg_lpm:.1f}" if avg_lpm is not None else "?"
    avg_cycle_str = f"{avg_per_cycle:.1f}" if avg_per_cycle is not None else "?"
    return (
        f"Valve: {valve_name} ({registry_entity_id})\n"
        f"Duration: {duration_min} min\n"
        f"Water rate: {lpm_str} L/min\n"
        f"Lifetime total: {lifetime_str} L\n"
        f"\n"
        f"Last {LAST_N_FOR_AVERAGES} waterings (averages):\n"
        f"  Water rate: {avg_lpm_str} L/min\n"
        f"  Per cycle: {avg_cycle_str} L\n"
        f"\n"
        f"Type: {event_type}"
    )


def _iter_fdm5kw_devices(
    hass: HomeAssistant,
) -> list[dict[str, Any]]:
    """Walk every registry sensor and return one record per device with
    its registry entity, valve name and sibling watering_volume /
    start_time / end_time entity_ids. Used by both calendar entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    out: list[dict[str, Any]] = []

    for state in hass.states.async_all("sensor"):
        if not state.entity_id.endswith(REGISTRY_SUFFIX):
            continue
        tuya_device_id = state.attributes.get("device_id")
        if not tuya_device_id:
            continue
        ha_device = dev_reg.async_get_device(
            identifiers={
                (DOMAIN, tuya_device_id),
                (DOMAIN_ORIG, tuya_device_id),
            }
        )
        if ha_device is None:
            continue

        roles: dict[str, str] = {}
        for ent in er.async_entries_for_device(ent_reg, ha_device.id):
            tk = ent.translation_key
            if tk == START_TIME_TRANSLATION_KEY:
                roles.setdefault("start_entity", ent.entity_id)
            elif tk in (END_TIME_TRANSLATION_KEY, CLOSE_TIME_TRANSLATION_KEY):
                roles.setdefault("end_entity", ent.entity_id)
            elif tk == WATERING_VOLUME_TRANSLATION_KEY:
                roles.setdefault("volume_entity", ent.entity_id)
            elif tk == LAST_RUN_TRANSLATION_KEY:
                roles.setdefault("counter_entity", ent.entity_id)
        # Fallback for legacy installs whose entities have no
        # translation_key — match by entity-id suffix.
        for ent in er.async_entries_for_device(ent_reg, ha_device.id):
            for suffix, role in _ENTITY_SUFFIX_TO_ROLE:
                if ent.entity_id.endswith(suffix):
                    roles.setdefault(role, ent.entity_id)
                    break

        # When the registry sensor is unavailable HA strips its custom
        # attributes, so fall back to the device-registry name.
        valve_name = (
            state.attributes.get("valve_name")
            or ha_device.name_by_user
            or ha_device.name
            or state.attributes.get("friendly_name")
            or state.entity_id
        )
        out.append(
            {
                "tuya_device_id": tuya_device_id,
                "registry_entity_id": state.entity_id,
                "registry_state": state,
                "valve_name": str(valve_name),
                "volume_entity": roles.get("volume_entity"),
                "start_entity": roles.get("start_entity"),
                "end_entity": roles.get("end_entity"),
                "counter_entity": roles.get("counter_entity"),
            }
        )
    return out


# volume_entity -> (monotonic stamp, lifetime liters). Lifetime totals move
# slowly; caching avoids a statistics query per valve per render.
_LIFETIME_CACHE: dict[str, tuple[float, int | None]] = {}
LIFETIME_CACHE_TTL_SEC = 1800.0


async def _warm_lifetime(
    hass: HomeAssistant, volume_entities: list[str | None]
) -> None:
    """Fill the lifetime cache for every stale entity with ONE statistics
    query (statistics_during_period accepts a set of ids)."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistics_during_period,
    )

    now = time.monotonic()
    stale = {
        v
        for v in volume_entities
        if v
        and not (
            (c := _LIFETIME_CACHE.get(v))
            and (now - c[0]) < LIFETIME_CACHE_TTL_SEC
        )
    }
    if not stale:
        return
    very_old = datetime(2020, 1, 1, tzinfo=timezone.utc)

    def _query():
        return statistics_during_period(
            hass, very_old, None, stale, "month", None, {"sum"}
        )

    try:
        stats = await get_instance(hass).async_add_executor_job(_query)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Bulk lifetime stats query failed", exc_info=True)
        return
    for v in stale:
        rows = stats.get(v) or []
        val: int | None = None
        if rows and rows[-1].get("sum") is not None:
            try:
                val = int(rows[-1]["sum"])
            except (TypeError, ValueError):
                val = None
        _LIFETIME_CACHE[v] = (now, val)


async def _lifetime_liters(
    hass: HomeAssistant, volume_entity: str | None
) -> int | None:
    """Return the all-time cumulative liters through this valve.

    The watering_volume sensor (cur_cap DP) resets to 0 each cycle and
    accumulates during the run, so its live state is *not* a lifetime
    figure — it's the current run's accumulator. The lifetime number
    lives in the recorder's long-term `sum` statistic (cur_cap declares
    `state_class=TOTAL_INCREASING`, so HA treats each per-cycle reset
    as a new accumulator window and the running `sum` is the lifetime
    total).
    """
    if not volume_entity:
        return None
    cached = _LIFETIME_CACHE.get(volume_entity)
    if cached and (time.monotonic() - cached[0]) < LIFETIME_CACHE_TTL_SEC:
        return cached[1]
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import (
        statistics_during_period,
    )

    instance = get_instance(hass)
    # Pull a single month-period bucket from the dawn of recording — the
    # last row's `sum` is the lifetime cumulative. Month period keeps the
    # query cheap regardless of recorder retention.
    very_old = datetime(2020, 1, 1, tzinfo=timezone.utc)

    def _query():
        return statistics_during_period(
            hass,
            very_old,
            None,
            {volume_entity},
            "month",
            None,
            {"sum"},
        )

    try:
        stats = await instance.async_add_executor_job(_query)
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "Lifetime stats query failed for %s", volume_entity, exc_info=True
        )
        return None
    rows = stats.get(volume_entity) or []
    val: int | None = None
    if rows and rows[-1].get("sum") is not None:
        try:
            val = int(rows[-1]["sum"])
        except (TypeError, ValueError):
            val = None
    _LIFETIME_CACHE[volume_entity] = (time.monotonic(), val)
    return val


def _build_in_progress_event(
    run: dict[str, Any],
    *,
    valve_name: str,
    registry_entity_id: str,
    lifetime_l: int | None,
    avg_lpm: float | None,
    avg_cycle: float | None,
    now: datetime,
) -> CalendarEvent:
    """Render an open (currently-running) cycle as a calendar event.
    End is estimated from the historical avg duration so the event has
    a non-zero span in the calendar UI; description marks it as
    in-progress and shows the running liters so Simon's team can spot
    a stuck valve."""
    elapsed_seconds = max((now - run["start"]).total_seconds(), 60.0)
    # Estimate remaining run length from historical avg per-cycle
    # liters minus the current cur_cap, divided by avg flow. Fall back
    # to "now + elapsed" so the event always has a bounded end.
    estimated_end = now + timedelta(seconds=60)
    if avg_cycle and avg_lpm and avg_lpm > 0 and run.get("total_l") is not None:
        remaining_l = max(0.0, avg_cycle - float(run["total_l"]))
        remaining_seconds = (remaining_l / avg_lpm) * 60.0
        estimated_end = now + timedelta(seconds=max(60.0, remaining_seconds))
    elif avg_cycle and avg_lpm and avg_lpm > 0:
        # No cur_cap reading yet — use the average total duration.
        estimated_end = run["start"] + timedelta(
            seconds=(avg_cycle / avg_lpm) * 60.0
        )

    current_l = run.get("total_l")
    current_str = f"{current_l:.1f}" if isinstance(current_l, (int, float)) else "—"
    elapsed_min = int(elapsed_seconds // 60)
    current_part = f"{current_str} L" if current_str != "—" else "—"
    title = f"{valve_name} · running · {elapsed_min} min · {current_part} so far"
    description = (
        f"Valve: {valve_name} ({registry_entity_id})\n"
        f"Running since: {run['start'].isoformat()}\n"
        f"Elapsed: {elapsed_min} min\n"
        f"Liters so far: {current_str} L\n"
        f"Estimated end (from last-10 averages): {estimated_end.isoformat()}\n"
        f"Lifetime total: {lifetime_l if lifetime_l is not None else '?'} L\n"
        f"\n"
        f"Type: In progress"
    )
    return CalendarEvent(
        start=run["start"],
        end=estimated_end,
        summary=title,
        description=description,
    )


def _live_open_run(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, Any] | None:
    """Detect an in-progress run from live states: the start_time DP is
    newer than the last real close and recent enough to be plausible.
    Liters-so-far come from the live cur_cap accumulator."""
    start_state = hass.states.get(d["start_entity"]) if d["start_entity"] else None
    end_state = hass.states.get(d["end_entity"]) if d["end_entity"] else None
    start = _parse_dt(start_state.state) if start_state else None
    if start is None:
        return None
    end = _parse_dt(end_state.state) if end_state else None
    now = datetime.now().astimezone()
    # Closed: a REAL close report lies between start and (roughly) now.
    # During a run the pre-report firmware writes the SCHEDULED close —
    # a FUTURE value — so end > now means the run is still in progress;
    # end < start is a stale value from the previous run.
    if end is not None and start < end <= now + timedelta(seconds=120):
        return None
    if not (0 <= (now - start).total_seconds() <= MAX_SANE_RUN_SECONDS):
        return None
    total_l: float | None = None
    vol = d.get("volume_entity")
    if vol and (vs := hass.states.get(vol)):
        try:
            v = float(vs.state)
        except (TypeError, ValueError):
            v = None
        run_min = max((now - start).total_seconds() / 60.0, 1.0)
        if v is not None and 0 <= v <= max(50.0, 50.0 * run_min):
            total_l = v
    return {
        "start": start,
        "end": None,
        "duration_seconds": 0,
        "total_l": total_l,
        "open": True,
    }


def _parse_dt(raw: Any) -> datetime | None:
    """Parse a recorder/state value that should be an ISO timestamp.

    Some xtend_tuya sensors emit naive ISO strings (e.g.
    `"2026-05-27 10:00:00"` without a TZ offset). Comparing those with
    the tz-aware window bounds used by `_query_recent_runs` raises
    `TypeError: can't compare offset-naive and offset-aware datetimes`,
    so attach the local TZ when the parsed value is naive.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.astimezone()
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # `astimezone()` on a naive datetime treats it as local time.
        parsed = parsed.astimezone()
    return parsed


def _compute_averages(
    runs: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    lpms = []
    totals = []
    for r in runs:
        dur_min = r["duration_seconds"] / 60.0
        if r["total_l"] is None or dur_min <= 0:
            continue
        lpms.append(r["total_l"] / dur_min)
        totals.append(r["total_l"])
    avg_lpm = sum(lpms) / len(lpms) if lpms else None
    avg_cycle = sum(totals) / len(totals) if totals else None
    return avg_lpm, avg_cycle


# ----------------------------------------------------------------------
# Recorder query for completed cycles
# ----------------------------------------------------------------------


async def _batch_significant_states(
    hass: HomeAssistant,
    entity_ids: list[str],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, list]:
    """ONE recorder query for many entities.

    Per-device queries (3 entities each × 107 valves) serialized on the
    recorder executor took minutes on a cold render — the Calendar
    panel's HTTP request timed out and the grid rendered empty in every
    view (ticket 9W8FXA4l). A single multi-entity query is one SQL pass.
    """
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states

    if not entity_ids:
        return {}

    def _query() -> dict[str, list]:
        return get_significant_states(
            hass,
            window_start,
            window_end,
            entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=True,
        )

    return await get_instance(hass).async_add_executor_job(_query)


async def _query_recent_runs(
    hass: HomeAssistant,
    start_entity: str,
    end_entity: str,
    volume_entity: str,
    *,
    limit: int | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    include_open: bool = False,
) -> list[dict[str, Any]]:
    """Single-device convenience wrapper: batch-fetch this device's three
    entities and pair them. Bulk callers use `_batch_significant_states`
    once + `_pair_runs` per device instead."""
    if window_end is None:
        window_end = datetime.now().astimezone()
    if window_start is None:
        window_start = window_end - COMPLETED_MAX_WINDOW

    states_by_entity = await _batch_significant_states(
        hass, [start_entity, end_entity, volume_entity], window_start, window_end
    )
    return _pair_runs(
        states_by_entity.get(start_entity, []),
        states_by_entity.get(end_entity, []),
        states_by_entity.get(volume_entity, []),
        limit=limit,
        window_start=window_start,
        window_end=window_end,
        include_open=include_open,
    )


def _pair_runs(
    start_states: list,
    end_states: list,
    vol_states: list,
    *,
    limit: int | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    include_open: bool = False,
) -> list[dict[str, Any]]:
    """Pair start_time and end_time state rows for one device and compute
    the watering_volume peak per pair.

    `limit` truncates to the most recent N closed runs (used by the
    averages helper). If `window_start`/`window_end` are given, only
    runs whose end falls inside that window are returned (used by the
    Completed calendar).

    Edge cases handled:
      - Repeated identical start timestamps (DP redeliver) are deduped
        so a single cycle isn't counted twice.
      - Interrupted cycles (start without a later matching end) are
        either dropped (default) or surfaced as open runs with
        `end=None` and `open=True` when `include_open=True`. The
        Completed calendar uses this to render the "running now" event.
    """

    # Build sorted lists of (last_updated, parsed-state-value) for the
    # two timestamp entities. Skip rows where the state isn't a parseable
    # ISO datetime (HA may have "unknown"/"unavailable" placeholders).
    # Dedupe by parsed value: when the DP republishes the same timestamp
    # the recorder stores another row, but it's the same logical event.
    def _dedupe(states) -> list[tuple[datetime, datetime]]:
        seen: set[datetime] = set()
        rows: list[tuple[datetime, datetime]] = []
        for s in states:
            parsed = _parse_dt(s.state)
            if parsed is None or parsed in seen:
                continue
            seen.add(parsed)
            rows.append((s.last_updated, parsed))
        rows.sort()
        return rows

    start_events = _dedupe(start_states)
    end_events = _dedupe(end_states)

    vol_series = []
    for s in vol_states:
        try:
            vol_series.append((s.last_updated, float(s.state)))
        except (TypeError, ValueError):
            continue
    vol_series.sort()

    runs: list[dict[str, Any]] = []
    j = 0  # cursor into end_events
    for idx, (s_last_updated, s_value) in enumerate(start_events):
        # Find the first end-event chronologically after the start, by
        # the time the state row was recorded — that's the cycle close.
        while j < len(end_events) and end_events[j][0] <= s_last_updated:
            j += 1
        is_last_start = idx + 1 >= len(start_events)
        next_start_lu = None if is_last_start else start_events[idx + 1][0]

        if j >= len(end_events) or (
            next_start_lu is not None and next_start_lu < end_events[j][0]
        ):
            # No end report belonging to THIS cycle: either none exists at
            # all, or the next recorder event after this start is another
            # start — meaning this cycle's end report was lost. Pairing it
            # with the next cycle's end would merge two runs into one event
            # with a wrong completion time (e.g. 06:00→10:45 spanning a
            # lost 06:00 run and a real 10:30 one), so drop it instead.
            # Surface the newest start as in-progress when requested.
            if include_open and is_last_start and j >= len(end_events):
                run_start = s_value or s_last_updated
                # Running liters so far = cur_cap delta since run start.
                total_l = _run_volume(
                    vol_series, s_last_updated, datetime.now().astimezone()
                )
                runs.append(
                    {
                        "start": run_start,
                        "end": None,
                        "duration_seconds": 0,
                        "total_l": total_l,
                        "open": True,
                    }
                )
            continue
        e_last_updated, e_value = end_events[j]
        j += 1

        # Use the device-reported timestamps as event bounds; they're
        # what Simon actually wants to see in the calendar.
        run_start = s_value or s_last_updated
        run_end = e_value or e_last_updated
        if run_end <= run_start:
            # Garbage row (clock skew or repeated DP) — skip.
            continue

        duration_seconds = (run_end - run_start).total_seconds()
        if duration_seconds > MAX_SANE_RUN_SECONDS:
            _LOGGER.debug(
                "skipping run %s→%s (%.0fs): exceeds sane cap %ds",
                run_start, run_end, duration_seconds, MAX_SANE_RUN_SECONDS,
            )
            continue

        # Per-run liters = peak cur_cap between THIS cycle start and the
        # NEXT cycle start (or now). The end-row time can't bound the
        # window: most firmwares pre-report the SCHEDULED close time the
        # moment the run starts, so the end row lands ~1 s after the start
        # row while the cur_cap ramp arrives over the following minutes —
        # a [start_row, end_row] window contains no samples and every
        # event showed "—" liters (ticket 9W8FXA4l, "liters missing in
        # most entries"). Between cycles cur_cap rests at the final run
        # total, so extending to the next start stays exact; the spike
        # ceiling is scaled by the real run duration.
        total_l = _run_volume(
            vol_series,
            s_last_updated,
            next_start_lu or datetime.now().astimezone(),
            run_minutes=duration_seconds / 60,
        )

        runs.append(
            {
                "start": run_start,
                "end": run_end,
                "duration_seconds": duration_seconds,
                "total_l": total_l,
                "open": False,
            }
        )

    if window_start is not None and window_end is not None:
        runs = [
            r
            for r in runs
            if r.get("open") or (r["end"] and window_start <= r["end"] <= window_end)
        ]

    if limit is not None and len(runs) > limit:
        # Closed runs only when limiting (averages don't use open runs).
        closed = [r for r in runs if not r.get("open")]
        runs = sorted(closed, key=lambda r: r["end"], reverse=True)[:limit]

    return runs


# ----------------------------------------------------------------------
# Planned calendar
# ----------------------------------------------------------------------


class IrrigationPlannedCalendar(CalendarEntity):
    """Merged calendar of every enabled fdm5kw timer slot."""

    _attr_has_entity_name = False
    _attr_name = "Irrigation Planned"
    # NB: must be a real MDI name — the earlier "mdi:water-pump-outline"
    # does not exist in MDI, so the planned calendar rendered no icon at
    # all while the completed one (valid mdi:water-check) had one.
    _attr_icon = "mdi:water-pump"
    _attr_unique_id = "xtend_tuya_irrigation_planned"

    def __init__(self, hass: HomeAssistant, store) -> None:
        self.hass = hass
        self._runs_store = store

    @property
    def event(self) -> CalendarEvent | None:
        now = datetime.now().astimezone()
        upcoming = self._build_events(now, now + timedelta(days=7))
        upcoming.sort(key=lambda e: e.start)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        # Everything here reads memory: slots from registry states,
        # averages from the runs store. The only awaited call is the
        # lifetime statistics batch, one query cached for 30 min.
        devices = _iter_fdm5kw_devices(self.hass)
        self._runs_store.track_devices(devices)
        _maybe_start_backfill(self.hass, self._runs_store)
        await _warm_lifetime(self.hass, [d["volume_entity"] for d in devices])
        averages_by_device: dict[str, tuple[float | None, float | None]] = {}
        lifetime_by_device: dict[str, int | None] = {}
        for d in devices:
            averages_by_device[d["tuya_device_id"]] = _compute_averages(
                self._runs_store.last_runs(
                    d["tuya_device_id"], LAST_N_FOR_AVERAGES
                )
            )
            lifetime_by_device[d["tuya_device_id"]] = await _lifetime_liters(
                self.hass, d["volume_entity"]
            )
        return self._build_events(
            start_date, end_date, averages_by_device, lifetime_by_device
        )

    def _build_events(
        self,
        start: datetime,
        end: datetime,
        averages_by_device: dict[str, tuple[float | None, float | None]]
        | None = None,
        lifetime_by_device: dict[str, int | None] | None = None,
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tzinfo = start.tzinfo or datetime.now().astimezone().tzinfo

        for d in _iter_fdm5kw_devices(self.hass):
            slots = d["registry_state"].attributes.get("slots")
            if not isinstance(slots, dict):
                continue
            lifetime_l = (
                lifetime_by_device.get(d["tuya_device_id"])
                if lifetime_by_device
                else None
            )
            avg_lpm, avg_cycle = (
                averages_by_device.get(d["tuya_device_id"], (None, None))
                if averages_by_device
                else (None, None)
            )
            for slot in slots.values():
                if not isinstance(slot, dict):
                    continue
                if not slot.get("enabled"):
                    continue
                events.extend(
                    self._expand_slot(
                        slot=slot,
                        valve_name=d["valve_name"],
                        registry_entity_id=d["registry_entity_id"],
                        lifetime_l=lifetime_l,
                        avg_lpm=avg_lpm,
                        avg_cycle=avg_cycle,
                        window_start=start,
                        window_end=end,
                        tzinfo=tzinfo,
                    )
                )
        return events

    def _expand_slot(
        self,
        slot: dict,
        valve_name: str,
        registry_entity_id: str,
        lifetime_l: int | None,
        avg_lpm: float | None,
        avg_cycle: float | None,
        window_start: datetime,
        window_end: datetime,
        tzinfo,
    ) -> list[CalendarEvent]:
        hour = int(slot.get("hour", 0))
        minute = int(slot.get("minute", 0))
        days_mask = int(slot.get("days_mask", 0))
        mode = slot.get("mode", "duration")
        value = int(slot.get("value", 0))
        volume_target_l: int | None = None
        if mode == "duration":
            if value > MAX_SANE_RUN_SECONDS:
                _LOGGER.debug(
                    "skipping planned slot for %s: duration %ds exceeds cap",
                    valve_name, value,
                )
                return []
            duration_min = max(1, value // 60) if value < 60 else value // 60
            duration_seconds = value
        else:
            # Volume-mode: `value` is the target liters. The actual run
            # length depends on flow, which we can only know historically.
            # Use the last-10 avg l/min to estimate; if no history exists
            # yet (first run on a fresh valve), leave the event as a
            # zero-length marker at the start time.
            volume_target_l = value
            if avg_lpm and avg_lpm > 0:
                duration_seconds = int((value / avg_lpm) * 60)
                duration_min = max(1, duration_seconds // 60)
            else:
                duration_seconds = 0
                duration_min = 0
        # Estimated cycle volume for the title. Prefer avg_lpm × THIS slot's
        # duration — avg_cycle averages over runs of any length, so a 5-min
        # slot next to 10-min ones showed "5 min · ~15 L/min · ~126 L".
        # avg_cycle stays as fallback when only per-cycle history exists.
        estimated_l: float | None = None
        if avg_lpm is not None and duration_min > 0:
            estimated_l = avg_lpm * duration_min
        elif avg_cycle is not None:
            estimated_l = avg_cycle

        title = _format_planned_title(
            valve_name, duration_min, avg_lpm, estimated_l
        )
        description = _format_description(
            valve_name=valve_name,
            registry_entity_id=registry_entity_id,
            duration_min=duration_min,
            l_per_min=avg_lpm if avg_lpm is not None else "?",
            lifetime_l=lifetime_l,
            event_type="Planned",
            avg_lpm=avg_lpm,
            avg_per_cycle=avg_cycle,
        )
        if volume_target_l is not None:
            description += (
                f"\n\nVolume-mode timer: target {volume_target_l} l "
                "(duration estimated from last-10 average flow)."
            )

        events: list[CalendarEvent] = []
        day = window_start.date()
        end_day = window_end.date()
        while day <= end_day:
            weekday = day.weekday()
            if days_mask & (1 << weekday):
                start_dt = datetime(
                    day.year, day.month, day.day, hour, minute, tzinfo=tzinfo
                )
                end_dt = start_dt + timedelta(
                    seconds=duration_seconds if duration_seconds > 0 else 60
                )
                if window_start <= start_dt <= window_end:
                    events.append(
                        CalendarEvent(
                            start=start_dt,
                            end=end_dt,
                            summary=title,
                            description=description,
                        )
                    )
            day += timedelta(days=1)
        return events


# ----------------------------------------------------------------------
# Completed calendar
# ----------------------------------------------------------------------


class IrrigationCompletedCalendar(CalendarEntity):
    """Merged calendar of every historical fdm5kw watering cycle."""

    _attr_has_entity_name = False
    _attr_name = "Irrigation Completed"
    _attr_icon = "mdi:water-check"
    _attr_unique_id = "xtend_tuya_irrigation_completed"

    def __init__(self, hass: HomeAssistant, store) -> None:
        self.hass = hass
        self._runs_store = store
        self._last_event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        # Cheap: return the most recent completed run we've rendered.
        # The full agenda comes from async_get_events on demand.
        return self._last_event

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        # Cap the window so a 1-year Google Cal pull doesn't blow up
        # the recorder.
        effective_start = max(
            start_date, datetime.now().astimezone() - COMPLETED_MAX_WINDOW
        )
        effective_end = min(
            end_date, datetime.now().astimezone() + timedelta(seconds=1)
        )
        if effective_start >= effective_end:
            return []

        events: list[CalendarEvent] = []
        now = datetime.now().astimezone()
        # T3 valves have no start/end sensors — their runs land in the store
        # via the counter_custom listener, so counter-only devices render too.
        devices = [
            d
            for d in _iter_fdm5kw_devices(self.hass)
            if (d["start_entity"] and d["end_entity"]) or d.get("counter_entity")
        ]
        self._runs_store.track_devices(devices)
        _maybe_start_backfill(self.hass, self._runs_store)
        # NO recorder work on the request path: closed runs come from the
        # materialized runs store (event-driven, real-time), the open
        # "running now" run from live states. The recorder-scan approach —
        # even batched — blew past Nabu Casa's 60 s proxy timeout on a
        # 107-valve fleet and the Calendar panel rendered empty (9W8FXA4l).
        await _warm_lifetime(
            self.hass, [d["volume_entity"] for d in devices if d["volume_entity"]]
        )
        for d in devices:
            runs = self._runs_store.runs_in_window(
                d["tuya_device_id"], effective_start, effective_end
            )
            open_run = _live_open_run(self.hass, d)
            if open_run is not None:
                runs.append(open_run)
            if not runs:
                continue
            lifetime_l = await _lifetime_liters(self.hass, d["volume_entity"])
            avg_lpm, avg_cycle = _compute_averages(
                self._runs_store.last_runs(
                    d["tuya_device_id"], LAST_N_FOR_AVERAGES
                )
            )
            for r in runs:
                if r.get("open"):
                    # Skip stale opens: the start_time DP is far enough in
                    # the past that an in-progress event would be obvious
                    # garbage (the valve isn't actually running for hours).
                    if (now - r["start"]).total_seconds() > MAX_SANE_RUN_SECONDS:
                        _LOGGER.debug(
                            "skipping stale open run for %s: started %s",
                            d["valve_name"], r["start"],
                        )
                        continue
                    events.append(
                        _build_in_progress_event(
                            r,
                            valve_name=d["valve_name"],
                            registry_entity_id=d["registry_entity_id"],
                            lifetime_l=lifetime_l,
                            avg_lpm=avg_lpm,
                            avg_cycle=avg_cycle,
                            now=now,
                        )
                    )
                    continue
                duration_min = int(r["duration_seconds"] // 60)
                # Sub-minute runs (manual open/close blips): "0 min" with a
                # rate extrapolated from a few seconds reads as garbage
                # ("0 min · 30 L/min · 1 L") — show no rate for those.
                if (
                    r["total_l"] is not None
                    and r["duration_seconds"] >= 60
                ):
                    l_per_min: float | None = r["total_l"] / (
                        r["duration_seconds"] / 60.0
                    )
                else:
                    l_per_min = None
                title = _format_completed_title(
                    d["valve_name"],
                    duration_min,
                    l_per_min,
                    r["total_l"],
                )
                description = _format_description(
                    valve_name=d["valve_name"],
                    registry_entity_id=d["registry_entity_id"],
                    duration_min=duration_min,
                    l_per_min=l_per_min,
                    lifetime_l=lifetime_l,
                    event_type="Completed",
                    avg_lpm=avg_lpm,
                    avg_per_cycle=avg_cycle,
                )
                events.append(
                    CalendarEvent(
                        start=r["start"],
                        end=r["end"],
                        summary=title,
                        description=description,
                    )
                )

        if events:
            self._last_event = max(events, key=lambda e: e.end)
        return events


# ----------------------------------------------------------------------
# ICS export (Phase 3) — Google Calendar subscription endpoint
# ----------------------------------------------------------------------


class XtendTuyaRunsExportView(HomeAssistantView):
    """JSON export of the materialized runs store for external sync.

    URL: `/api/xtend_tuya/runs?since=<iso>` (standard HA bearer auth).

    STABLE CONTRACT — consumed in production by the SquidWeb `HA_SYNC`
    cron (backend PR #3104, ticket 1LbpcoJD) since 2026-08-25. Frozen:
    the response shape `generated/count/runs[{device_id, name, start,
    end, duration_seconds, liters}]`, `since` filtering on run END,
    and the 400 (bad since) / 401 (no auth) behavior. The consumer's
    freshness alert catches silence but NOT shape drift — coordinate
    any breaking change through the ticket.

    The consumer pulls with an overlap window and upserts on
    (device_id, end), so re-serving rows across calls is expected and
    harmless. Serves purely from the in-memory store — never touches
    the recorder.
    """

    url = "/api/xtend_tuya/runs"
    name = f"api:{DOMAIN}:runs"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        from .runs_store import _parse_iso, async_get_store

        since = None
        if raw := request.query.get("since"):
            since = _parse_iso(raw)
            if since is None:
                raise web.HTTPBadRequest(text="since must be ISO 8601")
        device_filter = request.query.get("device_id")

        store = await async_get_store(hass)

        # tuya device_id -> display name, via the device registry.
        dev_reg = dr.async_get(hass)
        names: dict[str, str] = {}
        for device in dev_reg.devices.values():
            for dom, ident in device.identifiers:
                if dom in (DOMAIN, DOMAIN_ORIG):
                    names[ident] = device.name_by_user or device.name or ident

        out: list[dict[str, Any]] = []
        for device_id, rows in store.runs.items():
            if device_filter and device_id != device_filter:
                continue
            name = names.get(device_id)
            for r in rows:
                if since is not None:
                    r_end = _parse_iso(r["end"])
                    if r_end is None or r_end < since:
                        continue
                out.append(
                    {
                        "device_id": device_id,
                        "name": name,
                        "start": r["start"],
                        "end": r["end"],
                        "duration_seconds": r["duration_seconds"],
                        "liters": r.get("total_l"),
                    }
                )
        out.sort(key=lambda r: r["end"])
        return self.json(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "count": len(out),
                "runs": out,
            }
        )


class XtendTuyaCalendarICSView(HomeAssistantView):
    """Serve any xtend_tuya calendar entity as an iCalendar feed.

    URL: `/api/xtend_tuya/calendar/{entity_id}.ics`

    Google Calendar can't send Authorization headers when polling a
    subscribed URL, so this view also accepts a `?token=<bearer>` query
    parameter validated against HA's auth manager. `requires_auth` is
    disabled here and we enforce the bearer manually in `get`.
    """

    url = "/api/xtend_tuya/calendar/{entity_id}.ics"
    name = f"api:{DOMAIN}:calendar:ics"
    requires_auth = False

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        token = await _extract_bearer_token(request)
        if not token or not await _validate_token(hass, token):
            raise web.HTTPUnauthorized

        component = hass.data.get("calendar")
        if component is None:
            raise web.HTTPNotFound
        entity = component.get_entity(entity_id)
        if entity is None or not isinstance(entity, CalendarEntity):
            raise web.HTTPNotFound

        # Window is configurable via query params so Simon can pull a
        # wider history if needed; defaults stay tight to keep the
        # recorder query cheap on the 48-valve fleet.
        try:
            past = int(
                request.query.get("past_days", str(ICS_DEFAULT_PAST_DAYS))
            )
            future = int(
                request.query.get("future_days", str(ICS_DEFAULT_FUTURE_DAYS))
            )
        except ValueError:
            raise web.HTTPBadRequest

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(0, past))
        end = now + timedelta(days=max(0, future))

        events = await entity.async_get_events(hass, start, end)
        body = _render_ics(entity_id, events)
        return web.Response(
            body=body,
            content_type="text/calendar",
            charset="utf-8",
            headers={"Cache-Control": "max-age=300"},
        )


async def _extract_bearer_token(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.query.get("token")


async def _validate_token(hass: HomeAssistant, token: str) -> bool:
    # Long-lived access tokens and short-lived ones both validate
    # through `async_validate_access_token`; if it returns a refresh
    # token the bearer is valid.
    try:
        refresh = await hass.auth.async_validate_access_token(token)
    except Exception:  # noqa: BLE001 — keep the auth path permissive
        return False
    return refresh is not None


def _render_ics(entity_id: str, events: list[CalendarEvent]) -> bytes:
    """Render a list of CalendarEvent into an iCalendar 2.0 byte
    string. Uses the `icalendar` library, already a transitive HA
    dependency via the caldav integration; we add it to manifest
    requirements anyway so a stripped-down install still has it."""
    from icalendar import Calendar, Event

    cal = Calendar()
    cal.add("prodid", f"-//raukaute//{DOMAIN}//irrigation-calendar//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", entity_id)
    for ev in events:
        ie = Event()
        ie.add("summary", ev.summary or "")
        if ev.description:
            ie.add("description", ev.description)
        ie.add("dtstart", ev.start)
        ie.add("dtend", ev.end)
        uid = f"{entity_id}:{_dt_to_uid(ev.start)}@{DOMAIN}"
        ie.add("uid", uid)
        cal.add_component(ie)
    return cal.to_ical()


def _dt_to_uid(dt: datetime) -> str:
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return str(dt)
