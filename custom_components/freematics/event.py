"""Trip starts and stops, and impacts, as events to automate on."""

from __future__ import annotations

from typing import override

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FreematicsConfigEntry
from .const import EVENT_IMPACT, EVENT_TRIP_STARTED, EVENT_TRIP_STOPPED
from .device import DeviceEvent
from .entity import FreematicsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The trip and impact events."""
    async_add_entities(
        [
            FreematicsEvent(entry, "trip", [EVENT_TRIP_STARTED, EVENT_TRIP_STOPPED]),
            FreematicsEvent(entry, "impact", [EVENT_IMPACT]),
        ]
    )


class FreematicsEvent(FreematicsEntity, EventEntity):
    """Fired when the dongle reports one of its event types.

    An event reported late (after a coverage gap) still fires, with the time the
    dongle recorded it in the event's attributes. A trip's stop carries what
    the trip added up to; an impact, its peak in g beyond gravity.
    """

    def __init__(
        self, entry: FreematicsConfigEntry, key: str, event_types: list[str]
    ) -> None:
        super().__init__(entry, key)
        self._attr_translation_key = key
        self._attr_event_types = event_types

    @override
    async def async_added_to_hass(self) -> None:
        """Listen for the dongle's events."""
        await super().async_added_to_hass()
        self.async_on_remove(self.device.async_add_event_listener(self._handle))

    @callback
    def _handle(self, event: DeviceEvent) -> None:
        if event.event_type not in self.event_types:
            return
        self._trigger_event(
            event.event_type,
            {
                "recorded_at": event.time.isoformat(),
                "latitude": event.latitude,
                "longitude": event.longitude,
                **event.data,
            },
        )
        self.async_write_ha_state()
