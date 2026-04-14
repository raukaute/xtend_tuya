"""Irrigation valve (fdm5kw) data parser for raw Tuya DP codes."""

from __future__ import annotations
import logging
import struct
from dataclasses import dataclass
from typing import Any, Mapping
from tuya_device_handlers.definition.sensor import (
    TuyaSensorDefinition,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
)
from ...sensor import (
    XTSensorEntity,
    XTSensorEntityDescription,
)
from ...multi_manager.multi_manager import (
    XTDevice,
    MultiManager,
)
from ...ha_tuya_integration.tuya_integration_imports import (
    TuyaCustomerDevice,
    TuyaDPCodeRawWrapper,
    TuyaRawTypeInformation,
)
from ...const import XTDPCode

_LOGGER = logging.getLogger(__name__)

# DP codes not yet in XTDPCode — use string literals until PR is merged
DP_ONE_CONTROL = "one_control"
DP_TIME_TASK = "time_task"
from .const import DEVICE_CATEGORY, DAYS_OF_WEEK


# ---------------------------------------------------------------------------
# Raw DP Wrappers
# ---------------------------------------------------------------------------


class DPCodeTimestampWrapper(TuyaDPCodeRawWrapper):
    """Decodes start_time / close_time: 6 bytes [year_offset, month, day, hour, minute, second]."""

    def read_device_status(self, device: TuyaCustomerDevice) -> str | None:
        if decoded := super().read_device_status(device):
            if len(decoded) == 6:
                y, mo, d, h, mi, s = struct.unpack("BBBBBB", decoded)
                # 0xFF bytes = no data / unset
                if y == 255 or mo == 0 or mo > 12 or d == 0 or d > 31:
                    return None
                return f"20{y:02d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
        return None


class DPCodeOneControlWrapper(TuyaDPCodeRawWrapper):
    """Decodes one_control: 6 bytes [mode, param_hi, param_mid_hi, param_mid_lo, param_lo, ?]."""

    def __init__(self, dpcode: str, type_information: TuyaRawTypeInformation) -> None:
        super().__init__(dpcode, type_information)
        self.mode: int | None = None
        self.value: int | None = None

    def update_data(self, device: TuyaCustomerDevice) -> None:
        if decoded := super().read_device_status(device):
            if len(decoded) >= 6:
                self.mode = decoded[0]
                self.value = int.from_bytes(decoded[1:5], byteorder="big")


class DPCodeOneControlModeWrapper(DPCodeOneControlWrapper):
    """Returns the one_control mode: 1=duration, 3=volume (hypothesis)."""

    def read_device_status(self, device: TuyaCustomerDevice) -> str | None:
        self.update_data(device)
        if self.mode is not None:
            modes = {0: "idle", 1: "duration", 3: "volume"}
            return modes.get(self.mode, f"unknown ({self.mode})")
        return None


class DPCodeOneControlValueWrapper(DPCodeOneControlWrapper):
    """Returns the one_control parameter value (duration in sec or volume in L)."""

    def read_device_status(self, device: TuyaCustomerDevice) -> int | None:
        self.update_data(device)
        return self.value


class DPCodeTimeTaskWrapper(TuyaDPCodeRawWrapper):
    """Decodes time_task: 2-byte header + 9-byte timer entry.

    Confirmed layout (validated against S 809 with 3 known timers):
    Header: [slot_index, count (always 1)]
    Timer entry (9 bytes): [mode, value(4 bytes uint32 BE), hour, minute, days_bitmask, enabled]

    The DP acts as a sliding window — only shows the last-written timer slot.
    The device stores all timers internally. Each edit pushes that slot's data.

    Mode: 0=duration (value in seconds), 1=volume (value in liters)
    Days bitmask: bit0=Mon, bit1=Tue, ..., bit6=Sun
    """

    def __init__(self, dpcode: str, type_information: TuyaRawTypeInformation) -> None:
        super().__init__(dpcode, type_information)
        self.slot_index: int = 0
        self.timer: dict | None = None

    def update_data(self, device: TuyaCustomerDevice) -> None:
        if decoded := super().read_device_status(device):
            if len(decoded) < 11:
                return
            self.slot_index = decoded[0]
            count = decoded[1]
            if count == 0:
                self.timer = None
                return
            entry = decoded[2:11]
            mode = entry[0]
            value = int.from_bytes(entry[1:5], byteorder="big")
            hour = entry[5]
            minute = entry[6]
            days_mask = entry[7]
            enabled = entry[8]
            days = [
                DAYS_OF_WEEK[i] for i in range(7) if days_mask & (1 << i)
            ]
            self.timer = {
                "slot": self.slot_index,
                "hour": hour,
                "minute": minute,
                "mode": "duration" if mode == 0 else "volume",
                "value": value,
                "value_unit": "s" if mode == 0 else "L",
                "days": days,
                "days_mask": days_mask,
                "enabled": bool(enabled),
            }


class DPCodeTimeTaskSlotWrapper(DPCodeTimeTaskWrapper):
    """Returns the slot index of the last-modified timer."""

    def read_device_status(self, device: TuyaCustomerDevice) -> int | None:
        self.update_data(device)
        return self.slot_index if self.timer else None


class DPCodeTimeTaskSummaryWrapper(DPCodeTimeTaskWrapper):
    """Returns a human-readable summary of the last-modified timer."""

    def read_device_status(self, device: TuyaCustomerDevice) -> str | None:
        self.update_data(device)
        if not self.timer:
            return "No timer data"
        t = self.timer
        status = "ON" if t["enabled"] else "OFF"
        days_str = ",".join(t["days"]) if t["days"] else "none"
        if t["mode"] == "duration":
            duration_min = t["value"] // 60
            return (
                f"Slot {t['slot']}: {t['hour']:02d}:{t['minute']:02d} "
                f"{duration_min}min {days_str} [{status}]"
            )
        return (
            f"Slot {t['slot']}: {t['hour']:02d}:{t['minute']:02d} "
            f"{t['value']}L {days_str} [{status}]"
        )


class DPCodeTimeTaskRegistryWrapper(DPCodeTimeTaskWrapper):
    """Accumulates all 7 timer slots across DP updates.

    The device's time_task DP is a sliding window that only shows the
    last-written slot. This wrapper maintains a dict of all 7 slots,
    updating each slot as its data comes through the DP. The registry
    persists across HA restarts via the companion entity's state
    restoration.
    """

    NUM_SLOTS = 7

    def __init__(self, dpcode: str, type_information: TuyaRawTypeInformation) -> None:
        super().__init__(dpcode, type_information)
        self.slots: dict[int, dict | None] = {i: None for i in range(self.NUM_SLOTS)}

    def read_device_status(self, device: TuyaCustomerDevice) -> str | None:
        """Parse DP, update the corresponding slot, return active count."""
        self.update_data(device)
        if self.timer is not None:
            idx = self.timer["slot"]
            if 0 <= idx < self.NUM_SLOTS:
                self.slots[idx] = dict(self.timer)
        elif self.slot_index is not None and 0 <= self.slot_index < self.NUM_SLOTS:
            # count=0 means slot was deleted
            self.slots[self.slot_index] = None
        active = sum(1 for s in self.slots.values() if s and s.get("enabled"))
        return str(active)

    def get_slots_dict(self) -> dict[str, dict | None]:
        """Return slots keyed by string index (for JSON-safe HA attributes)."""
        return {str(k): v for k, v in self.slots.items()}

    def restore_slots(self, data: dict) -> None:
        """Hydrate slots from HA state restoration."""
        for i in range(self.NUM_SLOTS):
            slot_data = data.get(str(i)) or data.get(i)
            if isinstance(slot_data, dict):
                self.slots[i] = slot_data
            else:
                self.slots[i] = None

    def merge_cloud_timers(self, cloud_timers: list[dict]) -> int:
        """Merge cloud timer entries into empty registry slots.

        Cloud timers don't carry a slot index, so we assign them to
        the first available empty slot (or match by time+days if a
        slot already has identical data). Returns number of slots populated.
        """
        merged = 0
        for ct in cloud_timers:
            timer_data = self._parse_cloud_timer(ct)
            if timer_data is None:
                continue
            # Check if this timer already exists in a slot (match by time + days)
            existing_slot = self._find_matching_slot(timer_data)
            if existing_slot is not None:
                # Update existing slot with cloud data (source of truth for SmartLife timers)
                timer_data["slot"] = existing_slot
                self.slots[existing_slot] = timer_data
                merged += 1
                continue
            # Assign to first empty slot
            for i in range(self.NUM_SLOTS):
                if self.slots[i] is None:
                    timer_data["slot"] = i
                    self.slots[i] = timer_data
                    merged += 1
                    break
        return merged

    def _find_matching_slot(self, timer_data: dict) -> int | None:
        """Find a slot with matching hour, minute, and days_mask."""
        for i, slot in self.slots.items():
            if slot is None:
                continue
            if (
                slot.get("hour") == timer_data.get("hour")
                and slot.get("minute") == timer_data.get("minute")
                and slot.get("days_mask") == timer_data.get("days_mask")
            ):
                return i
        return None

    @staticmethod
    def _parse_cloud_timer(cloud_timer: dict) -> dict | None:
        """Convert a Tuya cloud timer entry to our slot format.

        Cloud timer format (from GET /v1.0/devices/{id}/timers):
          groups[].timers[].functions[0].value = {
            duration: int (seconds), capacity: int (liters),
            loops: str ("1111111"), startTimeStr: "HH:MM", ...
          }
          groups[].timers[].status: 1=enabled, 0=disabled
        """
        funcs = cloud_timer.get("functions", [])
        if not funcs:
            return None
        value = funcs[0].get("value", {})
        if not isinstance(value, dict):
            return None

        # Parse time
        time_str = value.get("startTimeStr", "")
        if ":" not in time_str:
            return None
        parts = time_str.split(":")
        hour, minute = int(parts[0]), int(parts[1])

        # Parse mode and value
        capacity = value.get("capacity", 0)
        duration = value.get("duration", 0)
        if capacity and capacity > 0:
            mode = "volume"
            timer_value = capacity
            value_unit = "L"
        else:
            mode = "duration"
            timer_value = duration
            value_unit = "s"

        # Parse days bitmask from loops string ("1111111" → 0x7F)
        loops = value.get("loops", "0000000")
        days_mask = 0
        for i, ch in enumerate(loops):
            if ch == "1":
                days_mask |= (1 << i)
        days = [DAYS_OF_WEEK[i] for i in range(7) if days_mask & (1 << i)]

        enabled = cloud_timer.get("status", 0) == 1

        return {
            "slot": -1,  # assigned by caller
            "hour": hour,
            "minute": minute,
            "mode": mode,
            "value": timer_value,
            "value_unit": value_unit,
            "days": days,
            "days_mask": days_mask,
            "enabled": enabled,
            "cloud_timer_id": cloud_timer.get("timer_id"),
        }


# ---------------------------------------------------------------------------
# Custom Entity for Timer Registry
# ---------------------------------------------------------------------------


class Fdm5kwTimerRegistryEntity(XTSensorEntity):
    """Sensor that exposes all 7 timer slots as attributes.

    State value = count of active (enabled) timers.
    Attributes contain the full slot registry for the irrigation-timer-card.
    """

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        wrapper = self._dpcode_wrapper
        if not isinstance(wrapper, DPCodeTimeTaskRegistryWrapper):
            return None
        slots = wrapper.get_slots_dict()
        active = sum(1 for s in slots.values() if s and s.get("enabled"))
        return {"slots": slots, "active_count": active}

    async def async_added_to_hass(self) -> None:
        """Restore slot registry from previous HA state, then sync cloud timers."""
        await super().async_added_to_hass()
        wrapper = self._dpcode_wrapper
        if not isinstance(wrapper, DPCodeTimeTaskRegistryWrapper):
            return

        # Step 1: Restore from HA state (fast, local)
        last_state = await self.async_get_last_state()
        if last_state is not None:
            slots_data = last_state.attributes.get("slots")
            if isinstance(slots_data, dict):
                wrapper.restore_slots(slots_data)
                _LOGGER.debug(
                    "Restored timer registry for %s: %s",
                    self.entity_id,
                    slots_data,
                )

        # Step 2: Sync cloud timers (discovers SmartLife-created timers)
        await self._sync_cloud_timers(wrapper)

    async def _sync_cloud_timers(self, wrapper: DPCodeTimeTaskRegistryWrapper) -> None:
        """Fetch cloud timer entries and merge into registry."""
        device_id = self.device.id
        account = self.device_manager.get_account_by_name("tuya_iot")
        if account is None:
            _LOGGER.debug("No tuya_iot account — skipping cloud timer sync for %s", device_id)
            return

        url = f"/v1.0/devices/{device_id}/timers"
        try:
            response = await self.hass.async_add_executor_job(
                account.call_api, "GET", url, None
            )
        except Exception:
            _LOGGER.warning("Cloud timer sync failed for %s", device_id, exc_info=True)
            return

        if not response or not response.get("success"):
            _LOGGER.debug("Cloud timer API returned no data for %s", device_id)
            return

        # Extract individual timer entries from nested groups structure
        cloud_timers: list[dict] = []
        for category in response.get("result", []):
            for group in category.get("groups", []):
                for timer in group.get("timers", []):
                    cloud_timers.append(timer)

        if not cloud_timers:
            return

        merged = wrapper.merge_cloud_timers(cloud_timers)
        if merged > 0:
            _LOGGER.info(
                "Synced %d cloud timer(s) into registry for %s",
                merged,
                self.entity_id,
            )
            self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Entity Descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fdm5kwSensorEntityDescription(XTSensorEntityDescription):
    """Describes fdm5kw irrigation valve sensor entity."""

    pass


@dataclass(frozen=True)
class Fdm5kwTimerRegistryDescription(Fdm5kwSensorEntityDescription):
    """Descriptor that returns a Fdm5kwTimerRegistryEntity instead of base XTSensorEntity."""

    def get_entity_instance(
        self,
        device: XTDevice,
        device_manager: MultiManager,
        description: XTSensorEntityDescription,
        definition: TuyaSensorDefinition,
        supported_descriptors: dict[str, tuple[XTSensorEntityDescription, ...]],
    ) -> Fdm5kwTimerRegistryEntity:
        return Fdm5kwTimerRegistryEntity(
            device=device,
            device_manager=device_manager,
            description=XTSensorEntityDescription(**description.__dict__),
            definition=definition,
            supported_descriptors=supported_descriptors,
        )


class Fdm5kwSensor:
    FDM5KW_SENSORS: dict[str, tuple[XTSensorEntityDescription, ...]] = {}

    @staticmethod
    def initialize_sensor() -> None:
        sensors: list[Fdm5kwSensorEntityDescription] = [
            # --- Timestamps ---
            Fdm5kwSensorEntityDescription(
                key=f"{XTDPCode.START_TIME}_timestamp",
                dpcode=XTDPCode.START_TIME,
                name="Last watering start",
                icon="mdi:clock-start",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeTimestampWrapper,),
            ),
            Fdm5kwSensorEntityDescription(
                key=f"{XTDPCode.CLOSE_TIME}_timestamp",
                dpcode=XTDPCode.CLOSE_TIME,
                name="Last watering end",
                icon="mdi:clock-end",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeTimestampWrapper,),
            ),
            # --- One-shot control status ---
            Fdm5kwSensorEntityDescription(
                key=f"{DP_ONE_CONTROL}_mode",
                dpcode=DP_ONE_CONTROL,
                name="Watering mode",
                icon="mdi:water-pump",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeOneControlModeWrapper,),
            ),
            Fdm5kwSensorEntityDescription(
                key=f"{DP_ONE_CONTROL}_value",
                dpcode=DP_ONE_CONTROL,
                name="Watering value",
                icon="mdi:water",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeOneControlValueWrapper,),
            ),
            # --- Timer schedule ---
            Fdm5kwSensorEntityDescription(
                key=f"{DP_TIME_TASK}_slot",
                dpcode=DP_TIME_TASK,
                name="Timer slot",
                icon="mdi:timer-outline",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeTimeTaskSlotWrapper,),
            ),
            Fdm5kwSensorEntityDescription(
                key=f"{DP_TIME_TASK}_summary",
                dpcode=DP_TIME_TASK,
                name="Timer schedule",
                icon="mdi:calendar-clock",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeTimeTaskSummaryWrapper,),
            ),
            # --- Timer registry (accumulates all 7 slots) ---
            Fdm5kwTimerRegistryDescription(
                key=f"{DP_TIME_TASK}_registry",
                dpcode=DP_TIME_TASK,
                name="Irrigation timer registry",
                icon="mdi:timer-cog",
                entity_registry_enabled_default=True,
                wrapper_class=(DPCodeTimeTaskRegistryWrapper,),
            ),
        ]

        Fdm5kwSensor.FDM5KW_SENSORS = {
            DEVICE_CATEGORY: tuple(sensors),
        }

    @staticmethod
    def get_descriptors_to_merge() -> (
        dict[str, tuple[XTSensorEntityDescription, ...]] | None
    ):
        return Fdm5kwSensor.FDM5KW_SENSORS
