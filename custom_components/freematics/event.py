"""Trip starts and stops, as events to automate on."""

from __future__ import annotations

from typing import override

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FreematicsConfigEntry
from .const import EVENT_TRIP_STARTED, EVENT_TRIP_STOPPED
from .device import TripEvent
from .entity import FreematicsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The trip event."""
    async_add_entities([FreematicsTripEvent(entry, "trip")])


class FreematicsTripEvent(FreematicsEntity, EventEntity):
    """Fired when the dongle reports a trip starting or stopping.

    A trip reported late (after a coverage gap) still fires, with the time the
    dongle recorded it in the event's attributes.
    """

    _attr_event_types = [EVENT_TRIP_STARTED, EVENT_TRIP_STOPPED]
    _attr_translation_key = "trip"

    @override
    async def async_added_to_hass(self) -> None:
        """Listen for trip starts and stops."""
        await super().async_added_to_hass()
        self.async_on_remove(self.device.async_add_event_listener(self._handle_trip))

    @callback
    def _handle_trip(self, event: TripEvent) -> None:
        self._trigger_event(
            event.event_type,
            {
                "recorded_at": event.time.isoformat(),
                "latitude": event.latitude,
                "longitude": event.longitude,
            },
        )
        self.async_write_ha_state()
