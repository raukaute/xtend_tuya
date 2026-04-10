"""Irrigation valve (fdm5kw) data parser for raw Tuya DP codes."""

from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Any
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


# ---------------------------------------------------------------------------
# Entity Descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fdm5kwSensorEntityDescription(XTSensorEntityDescription):
    """Describes fdm5kw irrigation valve sensor entity."""

    pass


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
        ]

        Fdm5kwSensor.FDM5KW_SENSORS = {
            DEVICE_CATEGORY: tuple(sensors),
        }

    @staticmethod
    def get_descriptors_to_merge() -> (
        dict[str, tuple[XTSensorEntityDescription, ...]] | None
    ):
        return Fdm5kwSensor.FDM5KW_SENSORS
