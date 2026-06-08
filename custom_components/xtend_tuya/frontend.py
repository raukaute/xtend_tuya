"""Serve and auto-register bundled Lovelace cards for xtend_tuya.

The integration ships pre-built card JS in `cards/` so users don't need
a separate deployment for the irrigation cards. The files are served
under `/xtend_tuya_static/cards/...` via `async_register_static_paths`
(the supported way to add file routes from a config entry — a plain
`HomeAssistantView` can't be registered this late, the aiohttp router is
already frozen) and registered as frontend module URLs (`add_extra_js_url`)
so HA loads them on every dashboard.

Caching: the static paths are registered with `cache_headers=False`. The
previous `cache_headers=True` tagged every bundle `Cache-Control: public,
max-age=2678400` (31 days, immutable) — so after a HACS update the browser
and the HA workbox service worker kept serving the OLD bundle for weeks
unless the SW was manually cleared. That surfaced as "Configuration error"
cards and stale card code that survived reloads. With `cache_headers=False`
aiohttp serves only `Last-Modified` (no long-lived `Cache-Control`), so the
client revalidates quickly and a HACS-pushed change is picked up promptly;
the `?v=<mtime>` query on the module URL changes whenever a release bumps the
file mtime, giving each new bundle a fresh URL on top of that.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import (
    add_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARDS_URL_PREFIX = "/xtend_tuya_static/cards"
_REGISTERED_CARDS: set[str] = set()


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
    """Register bundled card JS as static paths + frontend module URLs."""
    cards_dir = Path(__file__).parent / "cards"
    entries = await hass.async_add_executor_job(_enumerate_card_files)
    if not entries:
        return

    static_paths: list[StaticPathConfig] = []
    new_urls: list[tuple[str, int]] = []
    for name, mtime in entries:
        url_path = f"{CARDS_URL_PREFIX}/{name}"
        if url_path in _REGISTERED_CARDS:
            continue
        # cache_headers=False -> no long-lived Cache-Control, so the browser /
        # service worker revalidate instead of pinning a stale bundle for weeks
        # after a HACS update (the cause of the recurring "Configuration error"
        # cards). Last-Modified still gives cheap 304s on unchanged files.
        static_paths.append(
            StaticPathConfig(url_path, str(cards_dir / name), cache_headers=False)
        )
        new_urls.append((url_path, mtime))
        _REGISTERED_CARDS.add(url_path)

    if static_paths:
        await hass.http.async_register_static_paths(static_paths)

    for url_path, mtime in new_urls:
        # Register every bundle as a module URL (es5=False). HA's
        # `add_extra_js_url(..., es5=True)` does NOT mean "blocking classic
        # script" — it routes the URL to the ES5-legacy-only bucket, served
        # solely to browsers that can't run ES modules. Modern browsers load
        # only the module bucket, so es5=True would make them never fetch the
        # file → the strategy custom element never registers → "Timeout
        # waiting for strategy element". The strategy bundle is an IIFE, which
        # runs fine inside a `type=module` script (it executes and defines the
        # element). The `?v=<mtime>` query busts the cache on every release.
        add_extra_js_url(hass, f"{url_path}?v={mtime}")
        _LOGGER.info("xtend_tuya: registered Lovelace card %s", url_path)
