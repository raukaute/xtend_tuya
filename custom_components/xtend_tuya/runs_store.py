"""Materialized store of completed irrigation runs.

A watering run is immutable once it closes, but the calendar used to
re-derive every run on every render by scanning the recorder's raw
cur_cap series (~500 rows per run × 107 valves — millions of rows).
Even batched, that scan blew past Nabu Casa's 60 s proxy timeout and the
Calendar panel rendered empty (ticket 9W8FXA4l).

This module records each run exactly once, event-driven:

  - A state listener watches every fdm5kw end_time/close_time sensor.
  - The firmware pre-reports the SCHEDULED close time the moment a run
    starts; that value lies in the future and is skipped. The real close
    report lies in the (immediate) past and triggers recording.
  - Liters are read from the LIVE watering_volume state at close — the
    cur_cap counter rests at the run's final total, so no history scan
    is needed at all.

Persistence: homeassistant.helpers.storage.Store (JSON in .storage/),
debounced saves. Rows survive HA restarts AND the recorder's ~30-day
retention, so the calendar can show full-season history.

A one-time backfill (guarded by a flag in the store) imports the last
30 days from the recorder in the background at first setup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORE_KEY = "xtend_tuya.irrigation_runs"
STORE_VERSION = 1
SAVE_DELAY_SEC = 30

# Keep roughly two seasons; prune beyond that on save.
RETENTION_DAYS = 730

# A close report is "real" (not the pre-reported schedule) when its value
# is at most this far in the future. Clock skew margin.
MAX_FUTURE_SLACK_SEC = 120

# Physical plausibility cap for liters at close: 50 L/min (2× meter spec)
# times the run duration, floored at 50 L for sub-minute runs.
MAX_LPM_CAP = 50.0

# T3 counter_custom rows above this duration are stuck-open/garbage records,
# not real watering cycles (mirrors calendar.MAX_SANE_RUN_SECONDS).
T3_MAX_RUN_SECONDS = 6 * 3600

DOMAIN_KEY = "xtend_tuya_runs_store"


class RunsStore:
    """In-memory runs table with JSON persistence.

    runs[device_id] = list of
      {"start": iso, "end": iso, "duration_seconds": float,
       "total_l": float | None}
    sorted by end ascending.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORE_VERSION, STORE_KEY)
        self.runs: dict[str, list[dict[str, Any]]] = {}
        self.backfilled = False
        self._backfill_started = False
        self._unsub: list[Callable[[], None]] = []
        # entity_id -> device record (end sensor routing table)
        self._end_entity_to_device: dict[str, dict[str, Any]] = {}
        # entity_id -> device record for T3 counter_custom last-run sensors
        self._counter_entity_to_device: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------- load/save

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.runs = data.get("runs", {})
        self.backfilled = bool(data.get("backfilled"))

    def _data(self) -> dict[str, Any]:
        return {"runs": self.runs, "backfilled": self.backfilled}

    def async_schedule_save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY_SEC)

    def _prune(self, device_id: str) -> None:
        cutoff = (
            datetime.now().astimezone() - timedelta(days=RETENTION_DAYS)
        ).isoformat()
        rows = self.runs.get(device_id)
        if rows and rows[0]["end"] < cutoff:
            self.runs[device_id] = [r for r in rows if r["end"] >= cutoff]

    # ------------------------------------------------------------- recording

    def add_run(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        total_l: float | None,
    ) -> bool:
        """Insert a closed run, deduped by end timestamp. Returns True if new."""
        if end <= start:
            return False
        rows = self.runs.setdefault(device_id, [])
        end_iso = end.isoformat()
        # Dedupe: DP redelivers and backfill overlaps land on the same end.
        for r in reversed(rows[-20:]):
            if r["end"] == end_iso:
                # Prefer a row that has liters over one that doesn't.
                if r.get("total_l") is None and total_l is not None:
                    r["total_l"] = total_l
                    return True
                return False
        rows.append(
            {
                "start": start.isoformat(),
                "end": end_iso,
                "duration_seconds": (end - start).total_seconds(),
                "total_l": total_l,
            }
        )
        rows.sort(key=lambda r: r["end"])
        self._prune(device_id)
        return True

    # ------------------------------------------------------------- queries

    def runs_in_window(
        self, device_id: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        out = []
        for r in self.runs.get(device_id, []):
            try:
                r_end = datetime.fromisoformat(r["end"])
                r_start = datetime.fromisoformat(r["start"])
            except ValueError:
                continue
            if start <= r_end <= end:
                out.append(
                    {
                        "start": r_start,
                        "end": r_end,
                        "duration_seconds": r["duration_seconds"],
                        "total_l": r.get("total_l"),
                        "open": False,
                    }
                )
        return out

    def last_runs(self, device_id: str, n: int) -> list[dict[str, Any]]:
        rows = self.runs.get(device_id, [])[-n:]
        return [
            {
                "start": datetime.fromisoformat(r["start"]),
                "end": datetime.fromisoformat(r["end"]),
                "duration_seconds": r["duration_seconds"],
                "total_l": r.get("total_l"),
                "open": False,
            }
            for r in rows
        ]

    # ------------------------------------------------------------- listener

    def track_devices(self, devices: list[dict[str, Any]]) -> None:
        """(Re)arm the end-sensor listener for the given device records
        (as produced by calendar._iter_fdm5kw_devices)."""
        new_map: dict[str, dict[str, Any]] = {}
        for d in devices:
            if d.get("end_entity") and d.get("start_entity"):
                new_map[d["end_entity"]] = d
        added = set(new_map) - set(self._end_entity_to_device)
        self._end_entity_to_device.update(new_map)
        if added:
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, list(added), self._on_end_change
                )
            )
        # T3 valves: no start/end sensors — record from the counter_custom
        # last-run sensor (the device's own completed-run record).
        counter_map: dict[str, dict[str, Any]] = {}
        for d in devices:
            if d.get("counter_entity"):
                counter_map[d["counter_entity"]] = d
        c_added = set(counter_map) - set(self._counter_entity_to_device)
        self._counter_entity_to_device.update(counter_map)
        if c_added:
            self._unsub.append(
                async_track_state_change_event(
                    self.hass, list(c_added), self._on_counter_change
                )
            )
            # The counter DP retains the last completed run, so seed it on
            # first arm — covers runs finished while no listener was armed
            # (boot race, HA downtime). add_run's end-timestamp dedupe makes
            # the replay idempotent.
            for entity_id in c_added:
                if state := self.hass.states.get(entity_id):
                    self._record_counter_csv(counter_map[entity_id], state.state)

    @callback
    def _on_end_change(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        d = self._end_entity_to_device.get(entity_id)
        if d is None or new_state is None:
            return
        end = _parse_iso(new_state.state)
        if end is None:
            return
        now = datetime.now().astimezone()
        # Pre-reported SCHEDULED close (arrives at run start, lies in the
        # future) — ignore; the real close report follows at actual close.
        if (end - now).total_seconds() > MAX_FUTURE_SLACK_SEC:
            return
        start_state = self.hass.states.get(d["start_entity"])
        start = _parse_iso(start_state.state) if start_state else None
        if start is None or end <= start:
            return
        duration_min = (end - start).total_seconds() / 60.0
        total_l: float | None = None
        vol_entity = d.get("volume_entity")
        if vol_entity and (vs := self.hass.states.get(vol_entity)):
            try:
                v = float(vs.state)
            except (TypeError, ValueError):
                v = None
            # cur_cap rests at the run total at close; reject garbage
            # spikes above the physical ceiling.
            if v is not None and 0 <= v <= max(50.0, MAX_LPM_CAP * duration_min):
                total_l = v
        if self.add_run(d["tuya_device_id"], start, end, total_l):
            self.async_schedule_save()
            _LOGGER.debug(
                "runs_store: recorded run %s %s→%s %.0f L",
                d["tuya_device_id"],
                start,
                end,
                total_l if total_l is not None else -1,
            )

    @callback
    def _on_counter_change(self, event: Event) -> None:
        """T3 counter_custom CSV: 'mode,flag,duration_s,volume_L,YYYYMMDDHHMMSS'.
        The timestamp is the run's END in device-local time (== HA local time,
        the HA box sits on the farm). Reported once per completed run; the DP
        retains the last run, so a restart replays it and the end-timestamp
        dedupe in add_run absorbs the redelivery."""
        new_state = event.data.get("new_state")
        d = self._counter_entity_to_device.get(event.data.get("entity_id"))
        if d is None or new_state is None:
            return
        self._record_counter_csv(d, new_state.state)

    def _record_counter_csv(self, d: dict[str, Any], raw: Any) -> None:
        parts = str(raw).split(",")
        if len(parts) < 5:
            return
        try:
            duration = int(parts[2])
            volume = float(parts[3])
            end = datetime.strptime(parts[4], "%Y%m%d%H%M%S").astimezone()
        except ValueError:
            return
        # 0xFFFE = aborted sentinel; beyond 6 h = stuck-open/garbage record
        # (real T3 anomalies seen: 40650 s and 65471 s, both 0 L).
        if duration <= 0 or duration == 65534 or duration > T3_MAX_RUN_SECONDS:
            return
        total_l = volume if 0 <= volume <= MAX_LPM_CAP * (duration / 60.0) + 50 else None
        if self.add_run(
            d["tuya_device_id"], end - timedelta(seconds=duration), end, total_l
        ):
            self.async_schedule_save()
            _LOGGER.debug(
                "runs_store: recorded T3 run %s end=%s %.0f L",
                d["tuya_device_id"],
                end,
                total_l if total_l is not None else -1,
            )

    # ------------------------------------------------------------- backfill

    def merge_backfill(
        self, device_id: str, runs: list[dict[str, Any]]
    ) -> int:
        added = 0
        for r in runs:
            if r.get("open") or not r.get("end"):
                continue
            if self.add_run(
                device_id, r["start"], r["end"], r.get("total_l")
            ):
                added += 1
        return added


def _parse_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


async def async_get_store(hass: HomeAssistant) -> RunsStore:
    """Process-wide singleton, loaded on first use."""
    store = hass.data.get(DOMAIN_KEY)
    if store is None:
        store = RunsStore(hass)
        await store.async_load()
        hass.data[DOMAIN_KEY] = store
    return store
