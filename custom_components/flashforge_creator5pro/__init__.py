"""FlashForge Creator 5 Pro.

Sensors, binary sensors and an MJPEG camera. Job commands, each off unless
enabled in the options: cancel (after arming), pause, resume. Starting a print
is not offered.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CreatorController
from .const import (
    CONF_CHECK_CODE,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_NUMBER,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import CreatorCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    # Create entities only when their option is enabled.
    Platform.SWITCH,
    Platform.BUTTON,
]

type CreatorConfigEntry = ConfigEntry[CreatorCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CreatorConfigEntry) -> bool:
    reader = CreatorController(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_SERIAL_NUMBER],
        entry.data[CONF_CHECK_CODE],
    )
    coordinator = CreatorCoordinator(
        hass,
        entry,
        reader,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    # Unreachable -> ConfigEntryNotReady (HA retries with backoff).
    # Refused -> ConfigEntryAuthFailed (no retry, re-authentication flow).
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    entry.async_on_unload(coordinator.arming.disarm)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CreatorConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options(hass: HomeAssistant, entry: CreatorConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
