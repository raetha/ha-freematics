"""Whether the car is on a trip."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FreematicsConfigEntry
from .entity import FreematicsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The moving sensor."""
    async_add_entities([FreematicsMoving(entry, "moving")])


class FreematicsMoving(FreematicsEntity, BinarySensorEntity):
    """On from a trip's start to its stop, as the dongle decides them."""

    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_translation_key = "moving"

    @property
    @override
    def is_on(self) -> bool | None:
        """Whether a trip is under way."""
        return self.device.moving
