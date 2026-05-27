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
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN, DOMAIN_ORIG

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

REGISTRY_SUFFIX = "irrigation_timer_registry"
WATERING_VOLUME_TRANSLATION_KEY = "watering_volume"
START_TIME_TRANSLATION_KEY = "start_time"
END_TIME_TRANSLATION_KEY = "end_time"

ICS_VIEW_REGISTERED_KEY = f"{DOMAIN}_ics_view_registered"
ICS_DEFAULT_FUTURE_DAYS = 30
ICS_DEFAULT_PAST_DAYS = 30

# Completed-calendar safety cap on the per-device recorder window so a
# 90-day Google Cal pull on a 48-valve fleet stays bounded.
COMPLETED_MAX_WINDOW = timedelta(days=90)
# Last-N runs we average per device for the description line.
LAST_N_FOR_AVERAGES = 10
# Cache TTL for the averages helper; both calendars hit it on the same
# render pass so 30 s deduplicates the recorder hammer.
AVERAGES_CACHE_TTL_SEC = 30.0


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
    averages = _AveragesCache(hass)
    async_add_entities(
        [
            IrrigationPlannedCalendar(hass, averages),
            IrrigationCompletedCalendar(hass, averages),
        ]
    )

    # Register the ICS export view once across all xtend_tuya config
    # entries — the view resolves entities at request time, so a single
    # registration covers every fdm5kw calendar instance in the hass.
    if not hass.data.get(ICS_VIEW_REGISTERED_KEY):
        hass.http.register_view(XtendTuyaCalendarICSView())
        hass.data[ICS_VIEW_REGISTERED_KEY] = True


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------


def _format_title(
    valve_name: str,
    duration_min: int,
    l_per_min: float | int | str,
    lifetime_l: int | None,
) -> str:
    lifetime_str = str(lifetime_l) if lifetime_l is not None else "?"
    lpm_str = (
        f"{l_per_min:.1f}".rstrip("0").rstrip(".")
        if isinstance(l_per_min, float)
        else str(l_per_min)
    )
    return f"{valve_name} - {duration_min} m | {lpm_str} l | {lifetime_str} l"


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
        f"Duration: {duration_min} minutes\n"
        f"Water per minute: {lpm_str} l\n"
        f"Total watering: {lifetime_str} l\n"
        f"\n"
        f"Last {LAST_N_FOR_AVERAGES} waterings (averages):\n"
        f"  Water per minute: {avg_lpm_str} l\n"
        f"  Per cycle: {avg_cycle_str} l\n"
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

        sibling: dict[str, str] = {}
        for ent in er.async_entries_for_device(ent_reg, ha_device.id):
            tk = ent.translation_key
            if tk in (
                WATERING_VOLUME_TRANSLATION_KEY,
                START_TIME_TRANSLATION_KEY,
                END_TIME_TRANSLATION_KEY,
            ):
                sibling[tk] = ent.entity_id

        valve_name = (
            state.attributes.get("valve_name")
            or state.attributes.get("friendly_name")
            or state.entity_id
        )
        out.append(
            {
                "tuya_device_id": tuya_device_id,
                "registry_entity_id": state.entity_id,
                "registry_state": state,
                "valve_name": str(valve_name),
                "volume_entity": sibling.get(WATERING_VOLUME_TRANSLATION_KEY),
                "start_entity": sibling.get(START_TIME_TRANSLATION_KEY),
                "end_entity": sibling.get(END_TIME_TRANSLATION_KEY),
            }
        )
    return out


def _lifetime_liters(hass: HomeAssistant, volume_entity: str | None) -> int | None:
    if not volume_entity:
        return None
    state = hass.states.get(volume_entity)
    if state is None:
        return None
    try:
        return int(float(state.state))
    except (TypeError, ValueError):
        return None


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
    current_str = f"{current_l:.1f}" if isinstance(current_l, (int, float)) else "?"
    elapsed_min = int(elapsed_seconds // 60)
    title = f"{valve_name} — running ({elapsed_min} m, {current_str} l so far)"
    description = (
        f"Valve: {valve_name} ({registry_entity_id})\n"
        f"Running since: {run['start'].isoformat()}\n"
        f"Elapsed: {elapsed_min} minutes\n"
        f"Liters so far: {current_str}\n"
        f"Estimated end (from last-10 averages): {estimated_end.isoformat()}\n"
        f"Lifetime total: {lifetime_l if lifetime_l is not None else '?'} l\n"
        f"\n"
        f"Type: In progress"
    )
    return CalendarEvent(
        start=run["start"],
        end=estimated_end,
        summary=title,
        description=description,
    )


def _parse_dt(raw: Any) -> datetime | None:
    """Parse a recorder/state value that should be an ISO timestamp."""
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# ----------------------------------------------------------------------
# Last-N averages cache
# ----------------------------------------------------------------------


class _AveragesCache:
    """Per-device cache of the last-N completed runs' averages. Both
    calendar entities query this; we want a single recorder hit per
    render pass, not 2 × N_valves."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cache: dict[str, tuple[float, float | None, float | None]] = {}

    async def get(
        self,
        tuya_device_id: str,
        start_entity: str | None,
        end_entity: str | None,
        volume_entity: str | None,
    ) -> tuple[float | None, float | None]:
        """Return (avg_lpm, avg_per_cycle) for the last N completed
        cycles of this device. Cached for AVERAGES_CACHE_TTL_SEC."""
        now = time.monotonic()
        cached = self._cache.get(tuya_device_id)
        if cached and (now - cached[0]) < AVERAGES_CACHE_TTL_SEC:
            return cached[1], cached[2]
        if not (start_entity and end_entity and volume_entity):
            self._cache[tuya_device_id] = (now, None, None)
            return None, None

        runs = await _query_recent_runs(
            self.hass,
            start_entity,
            end_entity,
            volume_entity,
            limit=LAST_N_FOR_AVERAGES,
        )
        if not runs:
            self._cache[tuya_device_id] = (now, None, None)
            return None, None

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
        self._cache[tuya_device_id] = (now, avg_lpm, avg_cycle)
        return avg_lpm, avg_cycle


# ----------------------------------------------------------------------
# Recorder query for completed cycles
# ----------------------------------------------------------------------


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
    """Recorder query — pair start_time and end_time state changes for
    a device and compute the watering_volume peak between each pair.

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
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states

    if window_end is None:
        window_end = datetime.now().astimezone()
    if window_start is None:
        window_start = window_end - COMPLETED_MAX_WINDOW

    entity_ids = [start_entity, end_entity, volume_entity]

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

    instance = get_instance(hass)
    states_by_entity = await instance.async_add_executor_job(_query)

    start_states = states_by_entity.get(start_entity, [])
    end_states = states_by_entity.get(end_entity, [])
    vol_states = states_by_entity.get(volume_entity, [])

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
    for s_last_updated, s_value in start_events:
        # Find the first end-event chronologically after the start, by
        # the time the state row was recorded — that's the cycle close.
        while j < len(end_events) and end_events[j][0] <= s_last_updated:
            j += 1
        if j >= len(end_events):
            # Orphan start — no end after it. If this is the most recent
            # start and the caller wants in-progress events, surface it.
            if include_open:
                run_start = s_value or s_last_updated
                # Volume peak so far for the running cycle.
                total_l: float | None = None
                for ts, v in vol_series:
                    if ts < s_last_updated:
                        continue
                    if total_l is None or v > total_l:
                        total_l = v
                runs.append(
                    {
                        "start": run_start,
                        "end": None,
                        "duration_seconds": 0,
                        "total_l": total_l,
                        "open": True,
                    }
                )
            break
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

        # Volume peak between the two recorder timestamps; cur_cap
        # resets to 0 on cycle start and accumulates, so max(...) in
        # the window is the total liters delivered.
        total_l = None
        for ts, v in vol_series:
            if ts < s_last_updated:
                continue
            if ts > e_last_updated:
                break
            if total_l is None or v > total_l:
                total_l = v

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
    _attr_icon = "mdi:water-pump-outline"
    _attr_unique_id = "xtend_tuya_irrigation_planned"

    def __init__(self, hass: HomeAssistant, averages: _AveragesCache) -> None:
        self.hass = hass
        self._averages = averages

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
        # Pull averages for every device first so _expand_slot can use
        # them in description text without async calls.
        averages_by_device: dict[str, tuple[float | None, float | None]] = {}
        devices = _iter_fdm5kw_devices(self.hass)
        for d in devices:
            averages_by_device[d["tuya_device_id"]] = await self._averages.get(
                d["tuya_device_id"],
                d["start_entity"],
                d["end_entity"],
                d["volume_entity"],
            )
        return self._build_events(start_date, end_date, averages_by_device)

    def _build_events(
        self,
        start: datetime,
        end: datetime,
        averages_by_device: dict[str, tuple[float | None, float | None]]
        | None = None,
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tzinfo = start.tzinfo or datetime.now().astimezone().tzinfo

        for d in _iter_fdm5kw_devices(self.hass):
            slots = d["registry_state"].attributes.get("slots")
            if not isinstance(slots, dict):
                continue
            lifetime_l = _lifetime_liters(self.hass, d["volume_entity"])
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
        # For planned events the l/min comes from the historical average,
        # since we don't know the upcoming run's flow yet.
        l_per_min: float | str = avg_lpm if avg_lpm is not None else "?"

        title = _format_title(valve_name, duration_min, l_per_min, lifetime_l)
        description = _format_description(
            valve_name=valve_name,
            registry_entity_id=registry_entity_id,
            duration_min=duration_min,
            l_per_min=l_per_min,
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

    def __init__(self, hass: HomeAssistant, averages: _AveragesCache) -> None:
        self.hass = hass
        self._averages = averages
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
        for d in _iter_fdm5kw_devices(self.hass):
            if not (d["start_entity"] and d["end_entity"] and d["volume_entity"]):
                continue
            runs = await _query_recent_runs(
                self.hass,
                d["start_entity"],
                d["end_entity"],
                d["volume_entity"],
                window_start=effective_start,
                window_end=effective_end,
                include_open=True,
            )
            if not runs:
                continue
            lifetime_l = _lifetime_liters(self.hass, d["volume_entity"])
            avg_lpm, avg_cycle = await self._averages.get(
                d["tuya_device_id"],
                d["start_entity"],
                d["end_entity"],
                d["volume_entity"],
            )
            for r in runs:
                if r.get("open"):
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
                if r["total_l"] is not None and r["duration_seconds"] > 0:
                    l_per_min: float | str = r["total_l"] / (
                        r["duration_seconds"] / 60.0
                    )
                else:
                    l_per_min = "?"
                title = _format_title(
                    d["valve_name"],
                    duration_min,
                    l_per_min,
                    int(r["total_l"]) if r["total_l"] is not None else lifetime_l,
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
