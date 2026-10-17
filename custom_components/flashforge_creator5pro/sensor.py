"""Sensors. All values come from the ``/detail`` status (see values.py)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flashforge.models import FFMachineInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfLength,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CreatorConfigEntry
from . import values as v
from .coordinator import CreatorCoordinator
from .entity import CreatorEntity


@dataclass(frozen=True, kw_only=True)
class CreatorSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FFMachineInfo], Any]
    attrs_fn: Callable[[FFMachineInfo], dict[str, Any]] | None = None
    # When set, the sensor is created only once this returns True, so a
    # capability the printer does not have never shows up as a fake 0.
    exists_fn: Callable[[FFMachineInfo], bool] | None = None


def _temp(key: str, fn: Callable[[FFMachineInfo], Any], **kwargs: Any) -> CreatorSensorDescription:
    return CreatorSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=fn,
        **kwargs,
    )


def _tool_sensors() -> tuple[CreatorSensorDescription, ...]:
    out: list[CreatorSensorDescription] = []
    for i in range(v.TOOL_COUNT):
        out.append(_temp(f"tool_{i + 1}_temperature", lambda d, i=i: v.tool_temp(d, i)))
        out.append(
            _temp(
                f"tool_{i + 1}_target_temperature",
                lambda d, i=i: v.tool_temp(d, i, target=True),
                entity_registry_enabled_default=False,
            )
        )
    return tuple(out)


def _slot_sensors() -> tuple[CreatorSensorDescription, ...]:
    return tuple(
        CreatorSensorDescription(
            key=f"slot_{n}",
            translation_key=f"slot_{n}",
            icon="mdi:printer-3d-nozzle-heat-outline",
            value_fn=lambda d, n=n: v.slot_material(d, n),
            attrs_fn=lambda d, n=n: v.slot_attributes(d, n),
            exists_fn=lambda d: d.has_matl_station,
        )
        for n in range(1, v.SLOT_COUNT + 1)
    )


SENSORS: tuple[CreatorSensorDescription, ...] = (
    CreatorSensorDescription(
        key="machine_status",
        translation_key="machine_status",
        device_class=SensorDeviceClass.ENUM,
        options=v.MACHINE_STATE_OPTIONS,
        icon="mdi:printer-3d",
        value_fn=v.machine_state,
    ),
    CreatorSensorDescription(
        key="print_progress",
        translation_key="print_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent-circle",
        value_fn=v.progress,
    ),
    CreatorSensorDescription(
        key="current_file",
        translation_key="current_file",
        icon="mdi:file-outline",
        value_fn=v.current_file,
    ),
    CreatorSensorDescription(
        key="current_layer",
        translation_key="current_layer",
        icon="mdi:layers",
        value_fn=lambda d: d.current_print_layer,
    ),
    CreatorSensorDescription(
        key="total_layers",
        translation_key="total_layers",
        icon="mdi:layers-triple",
        value_fn=lambda d: d.total_print_layers,
    ),
    CreatorSensorDescription(
        key="elapsed_time",
        translation_key="elapsed_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
        value_fn=v.elapsed_seconds,
    ),
    CreatorSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
        value_fn=v.remaining_seconds,
    ),
    CreatorSensorDescription(
        key="print_completion_time",
        translation_key="print_completion_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda d: v.completion_time(d, dt_util.DEFAULT_TIME_ZONE),
    ),
    _temp("nozzle_temperature", v.nozzle_temp),
    _temp("nozzle_target_temperature", lambda d: v.nozzle_temp(d, target=True)),
    _temp("bed_temperature", v.bed_temp),
    _temp("bed_target_temperature", lambda d: v.bed_temp(d, target=True)),
    _temp("chamber_temperature", v.chamber_temp, exists_fn=v.has_chamber),
    _temp(
        "chamber_target_temperature",
        lambda d: v.chamber_temp(d, target=True),
        exists_fn=v.has_chamber,
    ),
    *_tool_sensors(),
    CreatorSensorDescription(
        key="job_filament_used_length",
        translation_key="job_filament_used_length",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_display_precision=2,
        icon="mdi:ruler",
        value_fn=lambda d: d.est_length,
    ),
    CreatorSensorDescription(
        key="job_filament_used_weight",
        translation_key="job_filament_used_weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1,
        icon="mdi:weight-gram",
        value_fn=lambda d: d.est_weight,
    ),
    CreatorSensorDescription(
        key="active_slot",
        translation_key="active_slot",
        icon="mdi:tray-full",
        value_fn=v.active_slot,
        exists_fn=lambda d: d.has_matl_station,
    ),
    *_slot_sensors(),
    CreatorSensorDescription(
        key="cooling_fan_speed",
        translation_key="cooling_fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan",
        value_fn=lambda d: d.cooling_fan_speed,
    ),
    CreatorSensorDescription(
        key="chamber_fan_speed",
        translation_key="chamber_fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan",
        value_fn=lambda d: d.chamber_fan_speed,
    ),
    CreatorSensorDescription(
        key="tvoc",
        translation_key="tvoc",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.tvoc,
    ),
    CreatorSensorDescription(
        key="lifetime_filament",
        translation_key="lifetime_filament",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        icon="mdi:counter",
        value_fn=lambda d: d.cumulative_filament,
    ),
    CreatorSensorDescription(
        key="error_code",
        translation_key="error_code",
        icon="mdi:alert-octagon",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.error_code or None,
    ),
    CreatorSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.firmware_version or None,
    ),
    CreatorSensorDescription(
        key="free_disk_space",
        translation_key="free_disk_space",
        device_class=SensorDeviceClass.DATA_SIZE,
        # Reported in GB (ff-5mp-hass, verified on hardware; ~10 on a Creator 5 Pro).
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:harddisk",
        value_fn=v.free_disk_space_gb,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    pending = list(SENSORS)

    @callback
    def _add_ready() -> None:
        data = coordinator.data
        if data is None:
            return
        ready = [d for d in pending if d.exists_fn is None or d.exists_fn(data)]
        if not ready:
            return
        for description in ready:
            pending.remove(description)
        async_add_entities(CreatorSensor(coordinator, d) for d in ready)

    _add_ready()
    if pending:
        # A capability (station, chamber) may only show up on a later poll.
        entry.async_on_unload(coordinator.async_add_listener(_add_ready))


class CreatorSensor(CreatorEntity, SensorEntity):
    entity_description: CreatorSensorDescription

    def __init__(self, coordinator: CreatorCoordinator, description: CreatorSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        if fn is None or self.coordinator.data is None:
            return None
        return fn(self.coordinator.data)
