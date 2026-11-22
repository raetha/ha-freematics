"""Speed, heading, altitude, battery voltage, temperature, the last trip, and
the fix's and the cellular signal's quality."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FreematicsConfigEntry
from .device import FreematicsDevice
from .entity import FreematicsEntity


@dataclass(frozen=True, kw_only=True)
class FreematicsSensorDescription(SensorEntityDescription):
    """A sensor and where its value comes from."""

    value: Callable[[FreematicsDevice], float | int | datetime | None]


SENSORS: tuple[FreematicsSensorDescription, ...] = (
    FreematicsSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value=lambda d: d.position.speed_kmh if d.position else None,
    ),
    FreematicsSensorDescription(
        key="heading",
        translation_key="heading",
        native_unit_of_measurement=DEGREE,
        value=lambda d: d.position.course if d.position else None,
    ),
    FreematicsSensorDescription(
        key="altitude",
        translation_key="altitude",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        value=lambda d: d.position.altitude if d.position else None,
    ),
    FreematicsSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value=lambda d: d.battery_v,
    ),
    FreematicsSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda d: d.temperature,
    ),
    FreematicsSensorDescription(
        key="last_trip_distance",
        translation_key="last_trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value=lambda d: d.last_trip.distance_km if d.last_trip else None,
    ),
    FreematicsSensorDescription(
        key="last_trip_duration",
        translation_key="last_trip_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value=lambda d: d.last_trip.duration_min if d.last_trip else None,
    ),
    FreematicsSensorDescription(
        key="last_trip_max_speed",
        translation_key="last_trip_max_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value=lambda d: d.last_trip.max_speed_kmh if d.last_trip else None,
    ),
    FreematicsSensorDescription(
        key="last_trip_average_speed",
        translation_key="last_trip_average_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=0,
        value=lambda d: d.last_trip.average_speed_kmh if d.last_trip else None,
    ),
    FreematicsSensorDescription(
        key="signal",
        translation_key="signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.signal,
    ),
    FreematicsSensorDescription(
        key="satellites",
        translation_key="satellites",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.position.satellites if d.position else None,
    ),
    FreematicsSensorDescription(
        key="hdop",
        translation_key="hdop",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda d: d.position.hdop if d.position else None,
    ),
    FreematicsSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.last_report,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The dongle's sensors."""
    async_add_entities(FreematicsSensor(entry, description) for description in SENSORS)


class FreematicsSensor(FreematicsEntity, SensorEntity):
    """A value from the dongle's newest record."""

    entity_description: FreematicsSensorDescription

    def __init__(
        self, entry: FreematicsConfigEntry, description: FreematicsSensorDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> float | int | datetime | None:
        """The value."""
        return self.entity_description.value(self.device)
