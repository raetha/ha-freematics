"""Whether the car is on a trip, and whether the dongle is reporting."""

from __future__ import annotations

from datetime import datetime
from typing import override

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from . import FreematicsConfigEntry
from .entity import FreematicsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreematicsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """The moving and reporting sensors."""
    async_add_entities(
        [FreematicsMoving(entry, "moving"), FreematicsReporting(entry, "reporting")]
    )


class FreematicsMoving(FreematicsEntity, BinarySensorEntity):
    """On from a trip's start to its stop, as the dongle decides them."""

    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_translation_key = "moving"

    @property
    @override
    def is_on(self) -> bool | None:
        """Whether a trip is under way."""
        return self.device.moving


class FreematicsReporting(FreematicsEntity, BinarySensorEntity):
    """On while the dongle streams a trip: on a trip, with a batch arriving at
    least every few minutes. Off when parked or asleep, and when a trip's
    batches stop coming (out of coverage, unplugged). Whether a quiet dongle is
    late is the Next report due sensor's: overdue once that time has passed
    with no newer Last report. Costs the dongle nothing."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "reporting"
    _unsub_timer: CALLBACK_TYPE | None = None

    @property
    @override
    def is_on(self) -> bool:
        """Whether the dongle is reporting a trip live."""
        until = self.device.live_until
        return until is not None and dt_util.utcnow() < until

    @override
    async def async_added_to_hass(self) -> None:
        """Turn off on time even when nothing arrives."""
        await super().async_added_to_hass()
        self.async_on_remove(self.device.async_add_listener(self._schedule))
        self.async_on_remove(self._cancel)
        self._schedule()

    @callback
    def _cancel(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _schedule(self) -> None:
        self._cancel()
        until = self.device.live_until
        if until is not None and until > dt_util.utcnow():
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._quiet, until
            )

    @callback
    def _quiet(self, now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
