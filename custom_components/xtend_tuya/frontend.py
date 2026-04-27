"""Serve and auto-register bundled Lovelace cards for xtend_tuya.

The integration ships pre-built card JS in `cards/` so users don't need
a separate deployment for the irrigation timer card. Static files are
served under `/xtend_tuya_static/...` and registered as frontend module
URLs so HA loads them on every dashboard.
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


async def async_register_cards(hass: HomeAssistant) -> None:
    """Register bundled card JS as static paths + frontend resources."""
    cards_dir = Path(__file__).parent / "cards"
    if not cards_dir.is_dir():
        return

    static_paths: list[StaticPathConfig] = []
    new_urls: list[str] = []
    for card_file in sorted(cards_dir.glob("*.js")):
        url_path = f"{CARDS_URL_PREFIX}/{card_file.name}"
        if url_path in _REGISTERED_CARDS:
            continue
        static_paths.append(
            StaticPathConfig(url_path, str(card_file), cache_headers=False)
        )
        new_urls.append(url_path)
        _REGISTERED_CARDS.add(url_path)

    if static_paths:
        await hass.http.async_register_static_paths(static_paths)

    for url_path in new_urls:
        # Versioned with file mtime so HACS upgrades bust the browser cache.
        full_path = Path(__file__).parent / url_path.replace(
            f"{CARDS_URL_PREFIX}/", "cards/"
        )
        try:
            mtime = int(full_path.stat().st_mtime)
        except OSError:
            mtime = 0
        add_extra_js_url(hass, f"{url_path}?v={mtime}")
        _LOGGER.info("xtend_tuya: registered Lovelace card %s", url_path)
