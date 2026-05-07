"""Dual-write timer services for fdm5kw irrigation valve.

Handlers called by ServiceManager. The device DP write is the source of
truth (offline-safe); the cloud timer write is best-effort for SmartLife
UI visibility — a cloud failure is logged but does not fail the service.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

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


def _mask_to_loops(mask: int) -> str:
    return "".join("1" if mask & (1 << i) else "0" for i in range(7))


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


def _find_account(hass, device_id: str, source: str) -> Any:
    for mm in get_all_multi_managers(hass):
        if mm.device_map.get(device_id):
            return mm.get_account_by_name(source)
    return None


async def _write_device_dp(account, device_id: str, b64_value: str) -> bool:
    body = json.dumps({"commands": [{"code": TIME_TASK_CODE, "value": b64_value}]})
    url = f"/v1.0/devices/{device_id}/commands"
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "POST", url, body
        )
    except Exception:
        _LOGGER.exception("time_task DP write failed for %s", device_id)
        return False
    if not resp or not resp.get("success"):
        _LOGGER.warning("time_task DP write rejected for %s: %s", device_id, resp)
        return False
    return True


async def _post_cloud_timer(
    account,
    device_id: str,
    hour: int,
    minute: int,
    days_mask: int,
    mode: int,
    value: int,
    enabled: bool,
) -> None:
    """Best-effort cloud timer create for SmartLife visibility.

    Tuya cloud timer POST body is inferred from the read shape — the exact
    schema is not formally documented for this device category. Failures
    are logged and swallowed; the DP write is authoritative.
    """
    time_str = f"{hour:02d}:{minute:02d}"
    loops = _mask_to_loops(days_mask)
    func_value = {
        "startTimeStr": time_str,
        "loops": loops,
        "duration": value if mode == MODE_DURATION else 0,
        "capacity": value if mode == MODE_VOLUME else 0,
    }
    body = json.dumps(
        {
            "time": time_str,
            "loops": loops,
            "category": TIME_TASK_CODE,
            "is_app_push": False,
            "status": 1 if enabled else 0,
            "functions": [{"code": TIME_TASK_CODE, "value": func_value}],
        }
    )
    url = f"/v1.0/devices/{device_id}/timers"
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "POST", url, body
        )
    except Exception:
        _LOGGER.warning(
            "Cloud timer POST failed for %s (non-fatal)", device_id, exc_info=True
        )
        return
    if not resp or not resp.get("success"):
        _LOGGER.info(
            "Cloud timer POST returned no success for %s: %s", device_id, resp
        )


async def _delete_cloud_timer_by_match(
    account, device_id: str, hour: int, minute: int, days_mask: int
) -> None:
    """List cloud timers, delete the one matching time+days. Best-effort."""
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "GET", f"/v1.0/devices/{device_id}/timers", None
        )
    except Exception:
        _LOGGER.warning(
            "Cloud timer list failed for %s (non-fatal)", device_id, exc_info=True
        )
        return
    if not resp or not resp.get("success"):
        return
    time_str = f"{hour:02d}:{minute:02d}"
    loops = _mask_to_loops(days_mask)
    for category in resp.get("result", []):
        for group in category.get("groups", []):
            for timer in group.get("timers", []):
                funcs = timer.get("functions") or []
                v = funcs[0].get("value", {}) if funcs else {}
                if v.get("startTimeStr") == time_str and v.get("loops") == loops:
                    timer_id = timer.get("timer_id")
                    if not timer_id:
                        continue
                    try:
                        await XTEventLoopProtector.execute_out_of_event_loop_and_return(
                            account.call_api,
                            "DELETE",
                            f"/v1.0/devices/{device_id}/timers/{timer_id}",
                            None,
                        )
                    except Exception:
                        _LOGGER.warning(
                            "Cloud timer delete failed for %s (non-fatal)",
                            device_id,
                            exc_info=True,
                        )


async def set_timer(hass, data: dict) -> bool:
    device_id: str = data["device_id"]
    slot: int = int(data["slot"])
    hour: int = int(data["hour"])
    minute: int = int(data["minute"])
    mode: int = _mode_to_int(data.get("mode", "duration"))
    value: int = int(data["value"])
    days_mask: int = _days_to_mask(data.get("days"))
    enabled: bool = bool(data.get("enabled", True))

    account = _find_account(hass, device_id, "tuya_iot")
    if account is None:
        _LOGGER.error("No tuya_iot account found for device %s", device_id)
        return False

    b64 = build_time_task_payload(slot, mode, value, hour, minute, days_mask, enabled)
    ok = await _write_device_dp(account, device_id, b64)
    if not ok:
        return False

    await _post_cloud_timer(
        account, device_id, hour, minute, days_mask, mode, value, enabled
    )
    return True


async def delete_timer(hass, data: dict) -> bool:
    device_id: str = data["device_id"]
    slot: int = int(data["slot"])

    account = _find_account(hass, device_id, "tuya_iot")
    if account is None:
        _LOGGER.error("No tuya_iot account found for device %s", device_id)
        return False

    b64 = build_delete_payload(slot)
    ok = await _write_device_dp(account, device_id, b64)
    if not ok:
        return False

    # Cloud cleanup is best-effort and only runs when the caller (e.g. the
    # irrigation-timer-card) supplies enough to match a cloud timer entry.
    # The card has the slot's current time/days; the service doesn't need
    # to recover them from the registry.
    hour = data.get("hour")
    minute = data.get("minute")
    if hour is not None and minute is not None:
        days_mask = _days_to_mask(data.get("days"))
        await _delete_cloud_timer_by_match(
            account, device_id, int(hour), int(minute), days_mask
        )
    return True
