"""Timer services for fdm5kw irrigation valve.

Writes the device-side `time_task` DP via the multi-manager (sharing channel
first; OpenAPI is no longer touched). The device DP is the single source
of truth — it executes locally and is mirrored back to HA via cloud push.
The Tuya cloud timer registry is not written or read; SmartLife schedule
display reads from the DP shadow, and editing schedules is owned by HA.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from ...multi_manager.multi_manager import MultiManager
from ...multi_manager.shared.threading import XTEventLoopProtector
from ...util import get_all_multi_managers
from .const import DAYS_OF_WEEK

_LOGGER = logging.getLogger(__name__)

TIME_TASK_CODE = "time_task"
MODE_DURATION = 0
MODE_VOLUME = 1


def _days_to_mask(days: list[str] | int | None) -> int:
    if days is None:
        return 0
    if isinstance(days, int):
        return days & 0x7F
    mask = 0
    for d in days:
        try:
            mask |= 1 << DAYS_OF_WEEK.index(d.capitalize())
        except ValueError:
            _LOGGER.warning("Unknown day %r (expected one of %s)", d, DAYS_OF_WEEK)
    return mask


def _mode_to_int(mode: str) -> int:
    if mode == "duration":
        return MODE_DURATION
    if mode == "volume":
        return MODE_VOLUME
    raise ValueError(f"mode must be 'duration' or 'volume', got {mode!r}")


def build_time_task_payload(
    slot: int,
    mode: int,
    value: int,
    hour: int,
    minute: int,
    days_mask: int,
    enabled: bool,
) -> str:
    """Build base64-encoded 11-byte time_task DP payload."""
    if not 0 <= slot <= 6:
        raise ValueError(f"slot must be 0–6, got {slot}")
    payload = bytes(
        [
            slot & 0xFF,
            1,
            mode & 0xFF,
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
            hour & 0xFF,
            minute & 0xFF,
            days_mask & 0x7F,
            1 if enabled else 0,
        ]
    )
    return base64.b64encode(payload).decode("ascii")


def build_delete_payload(slot: int) -> str:
    """Build base64 payload that clears a slot (count=0)."""
    if not 0 <= slot <= 6:
        raise ValueError(f"slot must be 0–6, got {slot}")
    return base64.b64encode(bytes([slot] + [0] * 10)).decode("ascii")


def _find_multi_manager(hass, device_id: str) -> MultiManager | None:
    for mm in get_all_multi_managers(hass):
        if mm.device_map.get(device_id):
            return mm
    return None


async def _write_time_task(
    multi_manager: MultiManager, device_id: str, b64_value: str
) -> bool:
    commands = [{"code": TIME_TASK_CODE, "value": b64_value}]
    try:
        ok = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            multi_manager.send_commands, device_id, commands
        )
    except Exception:
        _LOGGER.exception("time_task DP write failed for %s", device_id)
        return False
    if not ok:
        _LOGGER.warning("time_task DP write rejected for %s", device_id)
        return False
    return True


async def set_timer(hass, data: dict) -> bool:
    device_id: str = data["device_id"]
    slot: int = int(data["slot"])
    hour: int = int(data["hour"])
    minute: int = int(data["minute"])
    mode: int = _mode_to_int(data.get("mode", "duration"))
    value: int = int(data["value"])
    days_mask: int = _days_to_mask(data.get("days"))
    enabled: bool = bool(data.get("enabled", True))

    multi_manager = _find_multi_manager(hass, device_id)
    if multi_manager is None:
        _LOGGER.error("No multi_manager found for device %s", device_id)
        return False

    b64 = build_time_task_payload(slot, mode, value, hour, minute, days_mask, enabled)
    return await _write_time_task(multi_manager, device_id, b64)


async def delete_timer(hass, data: dict) -> bool:
    device_id: str = data["device_id"]
    slot: int = int(data["slot"])

    multi_manager = _find_multi_manager(hass, device_id)
    if multi_manager is None:
        _LOGGER.error("No multi_manager found for device %s", device_id)
        return False

    b64 = build_delete_payload(slot)
    return await _write_time_task(multi_manager, device_id, b64)
