"""Irrigation valve (fdm5kw) data parser for raw Tuya DP codes."""

from __future__ import annotations
import logging
import struct
from dataclasses import dataclass
from typing import Any, Mapping
from tuya_device_handlers.definition.sensor import (
    TuyaSensorDefinition,
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
    restoration. The device DP is the single source of truth — no cloud
    timer registry is consulted.
    """

    NUM_SLOTS = 7

    def __init__(self, dpcode: str, type_information: TuyaRawTypeInformation) -> None:
        super().__init__(dpcode, type_information)
        self.slots: dict[int, dict | None] = {i: None for i in range(self.NUM_SLOTS)}
        # The DP is a sliding window that shows the last write/delete. Apply
        # each unique payload to slots once; without this guard, every state
        # read would re-apply the last delete and wipe a previously restored
        # slot.
        self._last_applied_payload: bytes | None = None

    def read_device_status(self, device: TuyaCustomerDevice) -> str | None:
        """Parse DP, apply once per unique payload, return active count."""
        raw = super().read_device_status(device)
        payload = bytes(raw) if isinstance(raw, (bytes, bytearray)) else None
        if payload is not None and payload != self._last_applied_payload:
            self.update_data(device)
            if self.timer is not None:
                idx = self.timer["slot"]
                if 0 <= idx < self.NUM_SLOTS:
                    self.slots[idx] = dict(self.timer)
            elif self.slot_index is not None and 0 <= self.slot_index < self.NUM_SLOTS:
                # count=0 means slot was deleted
                self.slots[self.slot_index] = None
            self._last_applied_payload = payload
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


# ---------------------------------------------------------------------------
# Custom Entity for Timer Registry
# ---------------------------------------------------------------------------


class Fdm5kwTimerRegistryEntity(XTSensorEntity):
    """Sensor that exposes all 7 timer slots as attributes.

    State value = count of active (enabled) timers.
    Attributes contain the full slot registry for the irrigation-timer-card.
    Slots accumulate from the device's time_task DP push events; the
    registry survives HA restarts via state restoration.
    """

    # device_id → live entity instance
    INSTANCES: dict[str, "Fdm5kwTimerRegistryEntity"] = {}

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        wrapper = self._dpcode_wrapper
        if not isinstance(wrapper, DPCodeTimeTaskRegistryWrapper):
            return None
        slots = wrapper.get_slots_dict()
        active = sum(1 for s in slots.values() if s and s.get("enabled"))
        return {
            "slots": slots,
            "active_count": active,
            "valve_name": self.device.name,
            "device_id": self.device.id,
            "product_name": getattr(self.device, "product_name", None),
        }

    async def async_added_to_hass(self) -> None:
        """Restore slot registry from previous HA state."""
        await super().async_added_to_hass()
        Fdm5kwTimerRegistryEntity.INSTANCES[self.device.id] = self
        wrapper = self._dpcode_wrapper
        if not isinstance(wrapper, DPCodeTimeTaskRegistryWrapper):
            return

        # Prime the idempotency guard with the device's current DP payload
        # before restoring slots; otherwise the next state read would re-apply
        # the last DP push (often a delete) and trample the restored data.
        try:
            wrapper.read_device_status(self.device)
        except Exception:
            _LOGGER.debug(
                "fdm5kw: priming read_device_status for %s failed",
                self.entity_id,
                exc_info=True,
            )

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

        # Force a state write so attributes (valve_name, slots, etc.) reach
        # the frontend immediately. Without this, devices that haven't seen
        # a fresh DP push since boot keep the prior boot's attributes — the
        # dashboard strategy then falls back to device_id for the tile name.
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        Fdm5kwTimerRegistryEntity.INSTANCES.pop(self.device.id, None)
        await super().async_will_remove_from_hass()


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
