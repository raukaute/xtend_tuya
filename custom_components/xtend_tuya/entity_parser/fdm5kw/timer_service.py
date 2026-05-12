"""Dual-write timer services for fdm5kw irrigation valve.

The device-side `time_task` DP executes locally and is offline-safe, but
empirical testing on 2026-05-12 with the Mavronero fleet showed that
Tuya's cloud rewrites the device DP from the cloud timer registry ~10s
after a direct DP write. To make HA → SmartLife mutations durable we
write both: the DP for immediate local execution, then the cloud timer
registry (via OpenAPI) so the cloud doesn't roll back our change.

Cost: 1–2 OpenAPI calls per user-initiated timer mutation (set/delete).
Negligible compared to the historical periodic-poll regressions —
mutations are interactive, not on a timer.
"""

from __future__ import annotations

import base64
import json
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


def _find_multi_manager(hass, device_id: str) -> MultiManager | None:
    for mm in get_all_multi_managers(hass):
        if mm.device_map.get(device_id):
            return mm
    return None


def _find_iot_account(hass, device_id: str) -> Any:
    """Return the OpenAPI (tuya_iot) account for the device, or None."""
    for mm in get_all_multi_managers(hass):
        if mm.device_map.get(device_id):
            return mm.get_account_by_name("tuya_iot")
    return None


def _get_prior_slot(hass, device_id: str, slot: int) -> dict | None:
    """Look up the current slot data from the registry entity so we can
    match it against the cloud timer registry when deleting/overwriting.
    Returns None if the entity isn't loaded yet or the slot is empty."""
    # Local import avoids a circular import at module load time.
    from .sensor import Fdm5kwTimerRegistryEntity, DPCodeTimeTaskRegistryWrapper

    entity = Fdm5kwTimerRegistryEntity.INSTANCES.get(device_id)
    if entity is None:
        return None
    wrapper = entity._dpcode_wrapper
    if not isinstance(wrapper, DPCodeTimeTaskRegistryWrapper):
        return None
    return wrapper.slots.get(slot)


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


def _ha_timezone(hass) -> tuple[str, str]:
    """Return (timezone_id, '+H:MM' utc offset) for HA's configured TZ."""
    from datetime import datetime
    try:
        import zoneinfo
    except ImportError:  # pragma: no cover
        from backports import zoneinfo  # type: ignore

    tz_name = getattr(hass.config, "time_zone", None) or "UTC"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    offset = datetime.now(tz).utcoffset()
    if offset is None:
        return tz_name, "+0:00"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return tz_name, f"{sign}{total_minutes // 60}:{total_minutes % 60:02d}"


async def _post_cloud_timer(
    hass,
    account,
    device_id: str,
    hour: int,
    minute: int,
    days_mask: int,
    mode: int,
    value: int,
    enabled: bool,
) -> None:
    """Cloud timer create so the cloud doesn't roll back our DP write.
    Schema (verified 2026-05-12 against Mavronero fleet, fdm5kw category):
    - top-level: category, loops, timezone_id, time_zone, instruct
    - each instruct[]: time (HH:mm), functions [{code, value}]
    The GET response renders the same data with a different layout
    (timer rows nested under groups). Do NOT mirror the GET shape on POST.
    """
    time_str = f"{hour:02d}:{minute:02d}"
    loops = _mask_to_loops(days_mask)
    start_time_sec = hour * 3600 + minute * 60
    # SmartLife's scheduler UI requires the rich `value` shape — verified
    # against the Mavronero account on 2026-05-12. A minimal body still
    # gets stored, but SL renders it as a half-broken "Single watering"
    # entry and its edit flow hangs.
    func_value = {
        "startTimeStr": time_str,
        "loops": loops,
        "duration": value if mode == MODE_DURATION else 0,
        "capacity": value if mode == MODE_VOLUME else 0,
        "startTime": start_time_sec,
        "start": True,
        "current": 0,
    }
    timezone_id, time_zone = _ha_timezone(hass)
    body = json.dumps(
        {
            "category": "timer",
            "loops": loops,
            "timezone_id": timezone_id,
            "time_zone": time_zone,
            "instruct": [
                {
                    "time": time_str,
                    "date": "00000000",
                    "functions": [{"code": TIME_TASK_CODE, "value": func_value}],
                }
            ],
        }
    )
    url = f"/v1.0/devices/{device_id}/timers"
    _LOGGER.warning(
        "Cloud timer POST -> %s body=%s account_type=%s",
        url,
        body,
        type(account).__name__,
    )
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "POST", url, body
        )
    except Exception:
        _LOGGER.warning(
            "Cloud timer POST raised for %s (non-fatal)", device_id, exc_info=True
        )
        return
    _LOGGER.warning("Cloud timer POST response for %s: %s", device_id, resp)
    if not resp or not resp.get("success"):
        _LOGGER.warning(
            "Cloud timer POST returned no success for %s: %s", device_id, resp
        )


async def _delete_cloud_timer_by_match(
    account, device_id: str, hour: int, minute: int, days_mask: int
) -> None:
    """List cloud timers, delete the one matching time+days. Best-effort."""
    list_url = f"/v1.0/devices/{device_id}/timers"
    _LOGGER.warning(
        "Cloud timer GET -> %s (match %02d:%02d mask=%d)",
        list_url,
        hour,
        minute,
        days_mask,
    )
    try:
        resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
            account.call_api, "GET", list_url, None
        )
    except Exception:
        _LOGGER.warning(
            "Cloud timer list raised for %s (non-fatal)", device_id, exc_info=True
        )
        return
    _LOGGER.warning("Cloud timer GET response for %s: %s", device_id, resp)
    if not resp or not resp.get("success"):
        _LOGGER.warning(
            "Cloud timer GET non-success for %s, skipping delete", device_id
        )
        return
    time_str = f"{hour:02d}:{minute:02d}"
    loops = _mask_to_loops(days_mask)
    matched = False
    for category in resp.get("result", []):
        for group in category.get("groups", []):
            for timer in group.get("timers", []):
                funcs = timer.get("functions") or []
                v = funcs[0].get("value", {}) if funcs else {}
                if v.get("startTimeStr") == time_str and v.get("loops") == loops:
                    # Tuya's selective timer delete takes the timer-group
                    # id as a *query-string* parameter; both path-style
                    # variants (/timers/{group_id}, /timer/group/{id}, …)
                    # return 1108 "uri path invalid". Verified against the
                    # Mavronero account on 2026-05-12 with a throwaway
                    # group: DELETE /timers?group_id=<gid> succeeds and
                    # only removes that group.
                    group_id = group.get("id")
                    if not group_id:
                        continue
                    matched = True
                    del_url = f"/v1.0/devices/{device_id}/timers?group_id={group_id}"
                    _LOGGER.warning("Cloud timer DELETE -> %s", del_url)
                    try:
                        del_resp = await XTEventLoopProtector.execute_out_of_event_loop_and_return(
                            account.call_api, "DELETE", del_url, None
                        )
                        _LOGGER.warning(
                            "Cloud timer DELETE response for %s: %s",
                            device_id,
                            del_resp,
                        )
                    except Exception:
                        _LOGGER.warning(
                            "Cloud timer DELETE raised for %s (non-fatal)",
                            device_id,
                            exc_info=True,
                        )
    if not matched:
        _LOGGER.warning(
            "Cloud timer no entries matched %s for %s", time_str, device_id
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

    multi_manager = _find_multi_manager(hass, device_id)
    if multi_manager is None:
        _LOGGER.error("No multi_manager found for device %s", device_id)
        return False

    # When this is an edit (not a create), look up the prior slot state so
    # we can delete the cloud entry that's about to be replaced. Avoids
    # duplicate SmartLife timer entries after time/day changes.
    prior = _get_prior_slot(hass, device_id, slot)
    b64 = build_time_task_payload(slot, mode, value, hour, minute, days_mask, enabled)
    if not await _write_time_task(multi_manager, device_id, b64):
        return False

    account = _find_iot_account(hass, device_id)
    if account is None:
        _LOGGER.warning(
            "set_timer: no tuya_iot account for %s (DP write only, cloud may roll back)",
            device_id,
        )
        return True
    _LOGGER.warning(
        "set_timer: tuya_iot account found for %s (type=%s), proceeding to cloud write",
        device_id,
        type(account).__name__,
    )

    if prior is not None:
        _LOGGER.warning(
            "set_timer: prior slot %d for %s = %s, deleting cloud match first",
            slot,
            device_id,
            prior,
        )
        await _delete_cloud_timer_by_match(
            account,
            device_id,
            int(prior.get("hour", hour)),
            int(prior.get("minute", minute)),
            int(prior.get("days_mask", days_mask)),
        )

    # Tuya's OpenAPI has no per-timer enable/disable toggle (PUT
    # /timers/groups/{gid}/status is rejected with 1108; PUT on the
    # group body ignores `status` and resets it to 1). The closest
    # equivalent: when HA marks the timer disabled, leave it out of
    # the cloud registry entirely so the cloud can't fire it. The
    # device DP still carries the disabled bit for offline execution.
    # Net effect in SmartLife: the entry disappears from the schedule
    # tab when disabled and reappears on re-enable. Verified
    # 2026-05-12.
    if not enabled:
        _LOGGER.warning(
            "set_timer: enabled=False for slot %d on %s — skipping cloud POST "
            "so SmartLife schedule doesn't fire (no API to keep a disabled entry)",
            slot,
            device_id,
        )
        return True

    await _post_cloud_timer(
        hass, account, device_id, hour, minute, days_mask, mode, value, enabled
    )
    return True


async def delete_timer(hass, data: dict) -> bool:
    device_id: str = data["device_id"]
    slot: int = int(data["slot"])

    multi_manager = _find_multi_manager(hass, device_id)
    if multi_manager is None:
        _LOGGER.error("No multi_manager found for device %s", device_id)
        return False

    # Capture the slot's current time/days BEFORE we wipe the DP so we can
    # match the cloud timer entry on the way out.
    prior = _get_prior_slot(hass, device_id, slot)
    _LOGGER.warning(
        "delete_timer: device=%s slot=%d prior=%s", device_id, slot, prior
    )

    b64 = build_delete_payload(slot)
    if not await _write_time_task(multi_manager, device_id, b64):
        return False

    account = _find_iot_account(hass, device_id)
    if account is None:
        _LOGGER.warning(
            "delete_timer: no tuya_iot account for %s (DP-only delete)", device_id
        )
        return True
    if prior is None:
        _LOGGER.warning(
            "delete_timer: no prior slot data for %s slot %d — cannot match cloud entry",
            device_id,
            slot,
        )
        return True

    await _delete_cloud_timer_by_match(
        account,
        device_id,
        int(prior.get("hour", 0)),
        int(prior.get("minute", 0)),
        int(prior.get("days_mask", 0)),
    )
    return True
