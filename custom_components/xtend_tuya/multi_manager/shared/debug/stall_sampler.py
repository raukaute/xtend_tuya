"""Sample the event-loop thread's stack from a daemon thread.

Purpose: catch the setup-time CPU burn that makes the whole instance (and
every network path into it, including the supervisor log proxy) unreachable.
A separate OS thread keeps getting scheduled while the loop thread burns
(the GIL switches every ~5ms), so this works precisely when py-spy over the
network cannot.  Samples are appended and fsync'd to /config so they survive
the supervisor watchdog SIGKILLing the container.

Read afterwards via GET /api/xtend_tuya/stall_samples (authenticated).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView

from ....const import DOMAIN

SAMPLE_INTERVAL = 2.0
MAX_RUNTIME = 30 * 60  # ponytail: fixed 30-min window per boot; enough to cover setup
FILE_NAME = "xtend_stall_samples.log"

_STARTED = False


def start(hass: HomeAssistant) -> None:
    """Start the sampler thread and register the read-back view. Idempotent."""
    global _STARTED
    if _STARTED:
        return
    _STARTED = True

    hass.http.register_view(XTStallSamplesView())

    path = hass.config.path(FILE_NAME)
    main_id = threading.main_thread().ident
    thread = threading.Thread(
        target=_run, args=(path, main_id), name="xt_stall_sampler", daemon=True
    )
    thread.start()


def _run(path: str, main_id: int | None) -> None:
    deadline = time.monotonic() + MAX_RUNTIME
    idle = 0
    with open(path, "a") as fh:
        fh.write(f"=== sampler start {datetime.now().isoformat()} pid={os.getpid()} ===\n")
        fh.flush()
        while time.monotonic() < deadline:
            time.sleep(SAMPLE_INTERVAL)
            frame = sys._current_frames().get(main_id)  # type: ignore[arg-type]
            if frame is None:
                continue
            stack = traceback.format_stack(frame)
            # Idle loop = innermost frame waiting in the selector; don't spam.
            if stack and "selectors.py" in stack[-1].splitlines()[0]:
                idle += 1
                if idle % 30 == 0:
                    fh.write(f"--- {datetime.now():%H:%M:%S} idle x{idle} ---\n")
                    fh.flush()
                continue
            if idle:
                fh.write(f"--- idle x{idle} ---\n")
                idle = 0
            fh.write(f"--- {datetime.now():%H:%M:%S} ---\n{''.join(stack)}\n")
            fh.flush()
            os.fsync(fh.fileno())
        fh.write(f"=== sampler done {datetime.now().isoformat()} ===\n")


class XTStallSamplesView(HomeAssistantView):
    """Serve the sample log so it can be read without filesystem access."""

    url = f"/api/{DOMAIN}/stall_samples"
    name = f"api:{DOMAIN}:stall_samples"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        path = hass.config.path(FILE_NAME)

        def _read() -> str:
            try:
                with open(path) as fh:
                    return fh.read()
            except FileNotFoundError:
                return ""

        text: Any = await hass.async_add_executor_job(_read)
        return web.Response(text=text, content_type="text/plain")
