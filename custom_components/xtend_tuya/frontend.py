"""Serve and auto-register bundled Lovelace cards for xtend_tuya.

The integration ships pre-built card JS in `cards/` so users don't need
a separate deployment for the irrigation cards. The files are served
under `/xtend_tuya_static/cards/...` and registered as frontend module
URLs (`add_extra_js_url`) so HA loads them on every dashboard.

Caching: the bundles are served with `Cache-Control: no-cache`, so the
browser (and the HA workbox service worker) MUST revalidate them on every
load instead of trusting a stale copy. Without this, a HACS update left the
SW serving the previous bundle until it was manually cleared — which showed
up as "Configuration error" cards and stale card code that survived reloads.
`no-cache` is not `no-store`: the view answers conditional requests with a
cheap `304 Not Modified` (via Last-Modified/ETag) when the file is unchanged,
so warm loads stay fast; only a changed bundle transfers a fresh body. The
`?v=<mtime>` query on the module URL is kept as a second cache-bust signal,
but correctness no longer depends on it — the view ignores the query and
always serves the current on-disk file.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiohttp import web

from homeassistant.components.frontend import (
    add_extra_js_url,
)
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARDS_URL_PREFIX = "/xtend_tuya_static/cards"
_REGISTERED_CARDS: set[str] = set()
_VIEW_REGISTERED = False

# Only bare `<name>.js` filenames are servable — no path separators, no
# traversal, nothing but the bundled cards.
_SAFE_CARD_NAME = re.compile(r"^[A-Za-z0-9._-]+\.js$")


class XTCardsView(HomeAssistantView):
    """Serve the bundled card JS with `Cache-Control: no-cache`.

    Unauthenticated (module scripts can't carry an HA token), read-only, and
    locked to `<name>.js` files inside the cards dir.
    """

    url = CARDS_URL_PREFIX + "/{filename}"
    name = "xtend_tuya:cards"
    requires_auth = False
    cors_allowed = True

    def __init__(self, cards_dir: Path) -> None:
        self._cards_dir = cards_dir.resolve()

    async def get(
        self, request: web.Request, filename: str
    ) -> web.StreamResponse:
        if not _SAFE_CARD_NAME.match(filename):
            return web.Response(status=404)
        path = (self._cards_dir / filename).resolve()
        try:
            path.relative_to(self._cards_dir)
        except ValueError:
            return web.Response(status=404)  # traversal attempt
        if not path.is_file():
            return web.Response(status=404)
        # FileResponse handles range + conditional (If-Modified-Since /
        # If-None-Match -> 304) requests; we only override Cache-Control so the
        # client always revalidates instead of trusting a stale cached body.
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})


def _enumerate_card_files() -> list[tuple[str, int]]:
    """Sync helper — list (filename, mtime) for every .js in the cards
    dir. Called via `async_add_executor_job` so the directory scan
    doesn't block the event loop on slow disks (e.g. SD-card HA OS
    installs); HA's loop-detector flagged the previous in-loop scandir."""
    cards_dir = Path(__file__).parent / "cards"
    if not cards_dir.is_dir():
        return []
    entries: list[tuple[str, int]] = []
    for card_file in sorted(cards_dir.glob("*.js")):
        try:
            mtime = int(card_file.stat().st_mtime)
        except OSError:
            mtime = 0
        entries.append((card_file.name, mtime))
    return entries


async def async_register_cards(hass: HomeAssistant) -> None:
    """Register the card-serving view + each bundle as a frontend module URL."""
    global _VIEW_REGISTERED
    cards_dir = Path(__file__).parent / "cards"
    entries = await hass.async_add_executor_job(_enumerate_card_files)
    if not entries:
        return

    if not _VIEW_REGISTERED:
        hass.http.register_view(XTCardsView(cards_dir))
        _VIEW_REGISTERED = True

    for name, mtime in entries:
        url_path = f"{CARDS_URL_PREFIX}/{name}"
        if url_path in _REGISTERED_CARDS:
            continue
        _REGISTERED_CARDS.add(url_path)
        # Register every bundle as a module URL (es5=False). HA's
        # `add_extra_js_url(..., es5=True)` does NOT mean "blocking classic
        # script" — it routes the URL to the ES5-legacy-only bucket, served
        # solely to browsers that can't run ES modules. Modern browsers load
        # only the module bucket, so es5=True would make them never fetch the
        # file → the strategy custom element never registers → "Timeout
        # waiting for strategy element". The strategy bundle is an IIFE, which
        # runs fine inside a `type=module` script (it executes and defines the
        # element). The `?v=<mtime>` query is a secondary cache-bust; the view
        # serves no-cache so correctness no longer relies on it.
        add_extra_js_url(hass, f"{url_path}?v={mtime}")
        _LOGGER.info("xtend_tuya: registered Lovelace card %s", url_path)
