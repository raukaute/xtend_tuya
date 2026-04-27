"""Single-watering (one_control) services for fdm5kw irrigation valve.

The one_control DP is a 6-byte payload:

    [mode, value(4 bytes uint32 BE), flag]

Modes:
    0 = idle (stops a running cycle)
    1 = duration  (value = seconds)
    3 = volume    (value = liters)

Byte 5 ("flag") is not yet fully understood; observed state writes use
zero, which matches what the device pushes back when idle. We use zero
for both writes; if the firmware needs a non-zero trigger we can revisit
once we have a captured packet from SmartLife in active mode.

This is the proper fix for the "duration ignored on second start" bug:
the existing valve switch + duration number entity decouples target from
trigger, so the device may use a stale value. Writing one_control directly
sends mode + value + start atomically.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from ...multi_manager.shared.threading import XTEventLoopProtector
from ...util import get_all_multi_managers

_LOGGER = logging.getLogger(__name__)

ONE_CONTROL_CODE = "one_control"

MODE_IDLE = 0
MODE_DURATION = 1
MODE_VOLUME = 3


def _mode_to_int(mode: str) -> int:
    if mode == "duration":
        return MODE_DURATION
    if mode == "volume":
        return MODE_VOLUME
    if mode == "idle" or mode == "stop":
        return MODE_IDLE
    raise ValueError(f"mode must be 'duration', 'volume', or 'idle', got {mode!r}")


def build_one_control_payload(mode: int, value: int, start: bool = True) -> str:
    """Build base64-encoded 6-byte one_control DP payload.

    The 6th byte is a "trigger" flag: 1 = start watering now, 0 = idle.
    Captured idle frames from SmartLife show byte 5 = 0; writing mode+value
    alone with byte 5 = 0 doesn't actually fire a cycle on the device, so
    the start flag is required.
    """
    if mode not in (MODE_IDLE, MODE_DURATION, MODE_VOLUME):
        raise ValueError(f"unknown mode {mode}")
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"value out of range: {value}")
    flag = 1 if (start and mode != MODE_IDLE) else 0
    payload = bytes(
        [
            mode & 0xFF,
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
            flag,
        ]
    )
    return base64.b64encode(payload).decode("ascii")


def _find_account(hass, device_id: str, source: str) -> Any:
    for mm in get_all_multi_managers(hass):
        if mm.device_map.get(device_id):
            return mm.get_account_by_name(source)
    return None


async def _write_one_control(account, device_id: str, b64_value: str) -> bool:
    body = json.dumps(
        {"commands": [{"code": ONE_CONTROL_CODE, "value": b64_value}]}
    )
    url = f"/v1.0/devices/{device_id}/commands"
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "POST", url, body
        )
    except Exception:
        _LOGGER.exception("one_control DP write failed for %s", device_id)
        return False
    if not resp or not resp.get("success"):
        _LOGGER.warning("one_control DP write rejected for %s: %s", device_id, resp)
        return False
    return True


async def start_watering(hass, data: dict) -> bool:
    """Start a single watering cycle by duration (sec) or volume (L)."""
    device_id: str = data["device_id"]
    mode_int = _mode_to_int(data.get("mode", "duration"))
    value: int = int(data["value"])
    if mode_int == MODE_IDLE:
        raise ValueError("Use stop_watering for mode=idle/stop")

    account = _find_account(hass, device_id, "tuya_iot")
    if account is None:
        _LOGGER.error("No tuya_iot account found for device %s", device_id)
        return False

    b64 = build_one_control_payload(mode_int, value)
    return await _write_one_control(account, device_id, b64)


async def stop_watering(hass, data: dict) -> bool:
    """Stop an active watering cycle (writes one_control idle)."""
    device_id: str = data["device_id"]

    account = _find_account(hass, device_id, "tuya_iot")
    if account is None:
        _LOGGER.error("No tuya_iot account found for device %s", device_id)
        return False

    b64 = build_one_control_payload(MODE_IDLE, 0)
    return await _write_one_control(account, device_id, b64)
