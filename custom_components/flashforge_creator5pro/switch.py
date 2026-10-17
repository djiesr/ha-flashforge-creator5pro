"""Arming switch for the cancel button. Created only when the option is on."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CreatorConfigEntry
from .const import CONF_ENABLE_CANCEL
from .entity import CreatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.options.get(CONF_ENABLE_CANCEL, False):
        async_add_entities([CancelArmSwitch(entry.runtime_data)])


class CancelArmSwitch(CreatorEntity, SwitchEntity):
    """On for 30 seconds, then off on its own. Starts off after every restart."""

    _attr_translation_key = "arm_cancel"
    _attr_icon = "mdi:shield-alert-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "arm_cancel")

    @property
    def is_on(self) -> bool:
        return self.coordinator.arming.armed

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.arming.add_listener(self._on_arming_change))

    @callback
    def _on_arming_change(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.arming.arm()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.arming.disarm()
