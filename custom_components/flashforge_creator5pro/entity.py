"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import CreatorCoordinator


def build_device_info(coordinator: CreatorCoordinator) -> DeviceInfo:
    """Device card. The serial number is deliberately left out."""
    entry = coordinator.config_entry
    data = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL,
        sw_version=(data.firmware_version or None) if data else None,
    )


class CreatorEntity(CoordinatorEntity[CreatorCoordinator]):
    """Unavailable whenever the last poll failed; back as soon as one succeeds."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CreatorCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = build_device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
