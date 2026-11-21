"""Where the dongle is."""

from __future__ import annotations

from typing import override

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FreematicsConfigEntry
from .const import METRES_PER_HDOP
from .entity import FreematicsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One tracker per dongle."""
    async_add_entities([FreematicsTracker(entry, "location")])


class FreematicsTracker(FreematicsEntity, TrackerEntity):
    """The newest position the dongle reported."""

    _attr_name = None  # the device's own name
    _attr_translation_key = "location"

    @property
    @override
    def source_type(self) -> SourceType:
        """A GPS receiver."""
        return SourceType.GPS

    @property
    @override
    def latitude(self) -> float | None:
        """Latitude of the newest position."""
        return self.device.position.latitude if self.device.position else None

    @property
    @override
    def longitude(self) -> float | None:
        """Longitude of the newest position."""
        return self.device.position.longitude if self.device.position else None

    @property
    @override
    def location_accuracy(self) -> float:
        """Metres, estimated from the fix's HDOP (0 when unknown)."""
        position = self.device.position
        if position is None or not position.hdop:
            return 0
        return round(position.hdop * METRES_PER_HDOP, 1)
