"""Binary sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flashforge.models import FFMachineInfo

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CreatorConfigEntry
from . import values as v
from .coordinator import CreatorCoordinator
from .entity import CreatorEntity


@dataclass(frozen=True, kw_only=True)
class CreatorBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[FFMachineInfo], bool | None]


BINARY_SENSORS: tuple[CreatorBinarySensorDescription, ...] = (
    CreatorBinarySensorDescription(
        key="printing",
        translation_key="printing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=v.is_printing,
    ),
    CreatorBinarySensorDescription(
        key="paused",
        translation_key="paused",
        icon="mdi:pause-circle",
        value_fn=v.is_paused,
    ),
    CreatorBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=v.has_problem,
    ),
    CreatorBinarySensorDescription(
        key="door",
        translation_key="door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=v.door_open,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            OnlineBinarySensor(coordinator),
            *(CreatorBinarySensor(coordinator, d) for d in BINARY_SENSORS),
        ]
    )


class CreatorBinarySensor(CreatorEntity, BinarySensorEntity):
    entity_description: CreatorBinarySensorDescription

    def __init__(
        self, coordinator: CreatorCoordinator, description: CreatorBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class OnlineBinarySensor(CreatorEntity, BinarySensorEntity):
    """On when the last poll worked. Never unavailable, so it can drive automations.

    ``reason`` says why it is off (unreachable, refused, unreadable) and
    ``last_seen`` when the printer last answered.
    """

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: CreatorCoordinator) -> None:
        super().__init__(coordinator, "online")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_seen = self.coordinator.last_seen
        return {
            "reason": self.coordinator.connection_state,
            "last_seen": last_seen.isoformat() if last_seen else None,
        }
