"""Calendar platform for xtend_tuya.

Currently exposes a single merged calendar for the fdm5kw irrigation
valve family: `calendar.irrigation_planned`. Each enabled timer slot
on each valve expands into a weekly recurrence; events fall in the
[start, end] window HA hands to `async_get_events`.

Completed-runs calendar is planned for Phase 2 (recorder query on
`start_time` / `close_time` per device).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DOMAIN_ORIG

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

REGISTRY_SUFFIX = "irrigation_timer_registry"
WATERING_VOLUME_TRANSLATION_KEY = "watering_volume"

# Mon=0 .. Sun=6 → Python weekday() matches Mon=0 .. Sun=6 too.
_DAYS_MASK_BITS = 7


async def async_setup_entry(
    hass: HomeAssistant,
    entry: "ConfigEntry",
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the merged calendars for this config entry.

    A single planned-calendar entity covers every fdm5kw valve under
    every xtend_tuya config entry; HA collapses duplicates by unique_id
    when multiple entries call this. The entity reads live state from
    `hass.states` on each `async_get_events`, so adding/removing valves
    after setup is picked up automatically.
    """
    async_add_entities([IrrigationPlannedCalendar(hass)])


class IrrigationPlannedCalendar(CalendarEntity):
    """Merged calendar of every enabled fdm5kw timer slot."""

    _attr_has_entity_name = False
    _attr_name = "Irrigation Planned"
    _attr_icon = "mdi:water-pump-outline"
    _attr_unique_id = "xtend_tuya_irrigation_planned"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @property
    def event(self) -> CalendarEvent | None:
        """Next upcoming event, used for the calendar entity's state.
        HA UI shows this in the entity tile; full agenda comes from
        async_get_events when the calendar view queries a range.
        """
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
        return self._build_events(start_date, end_date)

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _build_events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tzinfo = start.tzinfo or datetime.now().astimezone().tzinfo

        for state in self.hass.states.async_all("sensor"):
            if not state.entity_id.endswith(REGISTRY_SUFFIX):
                continue
            slots = state.attributes.get("slots")
            if not isinstance(slots, dict):
                continue
            valve_name = (
                state.attributes.get("valve_name")
                or state.attributes.get("friendly_name")
                or state.entity_id
            )
            lifetime_l = self._lifetime_liters(state)
            for slot in slots.values():
                if not isinstance(slot, dict):
                    continue
                if not slot.get("enabled"):
                    continue
                events.extend(
                    self._expand_slot(
                        slot=slot,
                        valve_name=str(valve_name),
                        registry_entity_id=state.entity_id,
                        lifetime_l=lifetime_l,
                        window_start=start,
                        window_end=end,
                        tzinfo=tzinfo,
                    )
                )
        return events

    def _lifetime_liters(self, registry_state) -> int | None:
        """Pair the registry entity with its sibling watering_volume sensor
        via device_registry instead of friendly-name heuristics. Identifier
        layout: xtend_tuya stores ({DOMAIN}, tuya_id) and ({DOMAIN_ORIG},
        tuya_id) on the HA device entry."""
        tuya_device_id = registry_state.attributes.get("device_id")
        if not tuya_device_id:
            return None
        dev_reg = dr.async_get(self.hass)
        ha_device = dev_reg.async_get_device(
            identifiers={(DOMAIN, tuya_device_id), (DOMAIN_ORIG, tuya_device_id)}
        )
        if ha_device is None:
            return None
        ent_reg = er.async_get(self.hass)
        for ent in er.async_entries_for_device(ent_reg, ha_device.id):
            if ent.translation_key != WATERING_VOLUME_TRANSLATION_KEY:
                continue
            state = self.hass.states.get(ent.entity_id)
            if state is None:
                return None
            try:
                return int(float(state.state))
            except (TypeError, ValueError):
                return None
        return None

    def _expand_slot(
        self,
        slot: dict,
        valve_name: str,
        registry_entity_id: str,
        lifetime_l: int | None,
        window_start: datetime,
        window_end: datetime,
        tzinfo,
    ) -> list[CalendarEvent]:
        hour = int(slot.get("hour", 0))
        minute = int(slot.get("minute", 0))
        days_mask = int(slot.get("days_mask", 0))
        mode = slot.get("mode", "duration")
        value = int(slot.get("value", 0))
        if mode == "duration":
            duration_min = max(1, value // 60) if value < 60 else value // 60
            duration_seconds = value
            l_per_min = "?"
        else:
            duration_min = 0
            duration_seconds = 0
            l_per_min = "?"

        title = self._format_title(valve_name, duration_min, l_per_min, lifetime_l)
        description = self._format_description(
            valve_name=valve_name,
            registry_entity_id=registry_entity_id,
            duration_min=duration_min,
            l_per_min=l_per_min,
            lifetime_l=lifetime_l,
            event_type="Planned",
        )

        events: list[CalendarEvent] = []
        day = window_start.date()
        end_day = window_end.date()
        while day <= end_day:
            weekday = day.weekday()  # Mon=0..Sun=6, matches our bitmask
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

    @staticmethod
    def _format_title(
        valve_name: str,
        duration_min: int,
        l_per_min: int | str,
        lifetime_l: int | None,
    ) -> str:
        lifetime_str = str(lifetime_l) if lifetime_l is not None else "?"
        return (
            f"{valve_name} - {duration_min} m | {l_per_min} l | {lifetime_str} l"
        )

    @staticmethod
    def _format_description(
        valve_name: str,
        registry_entity_id: str,
        duration_min: int,
        l_per_min: int | str,
        lifetime_l: int | None,
        event_type: str,
    ) -> str:
        lifetime_str = str(lifetime_l) if lifetime_l is not None else "?"
        return (
            f"Valve: {valve_name} ({registry_entity_id})\n"
            f"Duration: {duration_min} minutes\n"
            f"Water per minute: {l_per_min} l\n"
            f"Total watering: {lifetime_str} l\n"
            f"\n"
            f"Type: {event_type}"
        )
