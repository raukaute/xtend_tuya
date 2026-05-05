"""Force-poll the FDM5KW valve every second while it's open.

Tuya's MQTT push throttles cur_cap / cur_time updates while a cycle runs
(typically every several seconds), which leaves the watering history graph
showing a coarse staircase instead of the climbing curve the user expects.
This poller GETs the device status endpoint at 1Hz while switch=on, writes
fresh values into the integration's device cache, and dispatches the
existing per-device update signal so the related sensors re-read.

While the valve is closed the loop sleeps with no API traffic.

Lifecycle is anchored to Fdm5kwTimerRegistryEntity, which is created
exactly once per FDM5KW device and lives for the lifetime of the
integration's config entry.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...multi_manager.multi_manager import MultiManager, XTDevice

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL_RUNNING = 1.0
POLL_INTERVAL_IDLE = 5.0
SWITCH_DP = "switch"


class Fdm5kwActiveRunPoller:
    """Per-device poller that ticks at 1Hz while the valve is open."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: XTDevice,
        device_manager: MultiManager,
    ) -> None:
        self._hass = hass
        self._device = device
        self._device_manager = device_manager
        self._task: asyncio.Task[Any] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = self._hass.loop.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is None:
            return
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            interval = (
                POLL_INTERVAL_RUNNING if self._is_valve_on() else POLL_INTERVAL_IDLE
            )
            if self._is_valve_on():
                try:
                    await self._poll_once()
                except Exception:
                    _LOGGER.exception(
                        "fdm5kw active-run poll iteration failed for %s",
                        self._device.id,
                    )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def _is_valve_on(self) -> bool:
        return bool(self._device.status.get(SWITCH_DP))

    async def _poll_once(self) -> None:
        account = self._device_manager.get_account_by_name("tuya_iot")
        if account is None:
            return
        device_id = self._device.id
        try:
            response = await self._hass.async_add_executor_job(
                account.call_api, "GET", f"/v1.0/devices/{device_id}/status", None
            )
        except Exception:
            _LOGGER.debug(
                "fdm5kw poll: status fetch failed for %s", device_id, exc_info=True
            )
            return
        if not response or not response.get("success"):
            return
        status_list = response.get("result") or []
        updated: list[str] = []
        for item in status_list:
            code = item.get("code")
            if code is None:
                continue
            value = item.get("value")
            if self._device.status.get(code) != value:
                self._device.status[code] = value
                updated.append(code)
        if not updated:
            return
        try:
            self._device_manager.multi_device_listener.update_device(
                self._device, updated
            )
        except Exception:
            _LOGGER.debug(
                "fdm5kw poll: dispatch failed for %s", device_id, exc_info=True
            )
