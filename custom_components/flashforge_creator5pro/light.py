"""Chamber light. Created unless disabled in the options."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CreatorConfigEntry
from . import values as v
from .api import PrinterAuthRefused, PrinterError, PrinterUnreachable
from .const import CONF_ENABLE_LIGHT, DOMAIN
from .coordinator import CreatorCoordinator
from .entity import CreatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.options.get(CONF_ENABLE_LIGHT, True):
        async_add_entities([ChamberLight(entry.runtime_data)])


class ChamberLight(CreatorEntity, LightEntity):
    """State comes from the next status poll, which is requested right after a command."""

    _attr_translation_key = "light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, coordinator: CreatorCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return v.light_on(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        try:
            await self.coordinator.reader.async_set_light(on)
        except PrinterUnreachable as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_no_answer",
                translation_placeholders={"error": str(err)},
            ) from None
        except PrinterAuthRefused as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_refused",
                translation_placeholders={"error": str(err)},
            ) from None
        except PrinterError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from None
        finally:
            await self.coordinator.async_request_refresh()
