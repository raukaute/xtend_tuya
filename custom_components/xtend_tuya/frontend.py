"""Serve and auto-register bundled Lovelace cards for xtend_tuya.

The integration ships pre-built card JS in `cards/` so users don't need
a separate deployment for the irrigation timer card. Static files are
served under `/xtend_tuya_static/...` and registered as frontend module
URLs so HA loads them on every dashboard.

The cards URL carries a `?v=<file-mtime>` query string so the browser
caches the bundle aggressively (one-day max-age) but still picks up
HACS-pushed updates the next time a release bumps the on-disk mtime.
This matters because the dashboard panel only waits ~5 s for the
custom strategy element (`ll-strategy-dashboard-irrigation-valves`) to
register; a cold fetch over the Nabu Casa relay can blow past that
budget intermittently, leaving Simon with a "Timeout waiting for
strategy element" error that resolves on refresh. Caching makes
repeat loads instant.
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
    """Register bundled card JS as static paths + frontend resources."""
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
        static_paths.append(
            # Browser-cache the JS bundle. The `?v=<mtime>` cache-bust
            # below means a new release (= new file mtime) gets a fresh
            # URL, so an aggressive cache here is safe.
            StaticPathConfig(url_path, str(cards_dir / name), cache_headers=True)
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
        # element). The `?v=<mtime>` cache-bust keeps warm loads instant to
        # stay inside the panel's ~5 s element-registration budget.
        add_extra_js_url(hass, f"{url_path}?v={mtime}")
        _LOGGER.info("xtend_tuya: registered Lovelace card %s", url_path)
