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
    """On while the dongle reports when it should: off once it has been silent
    longer than an awake dongle ever is, or past the time it said, before
    sleeping, it would report again. Off means out of coverage, unplugged or
    broken; costs the dongle nothing."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "reporting"
    _unsub_timer: CALLBACK_TYPE | None = None

    @property
    @override
    def is_on(self) -> bool | None:
        """Whether the dongle is reporting as it should."""
        due = self.device.report_due
        return None if due is None else dt_util.utcnow() < due

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
        due = self.device.report_due
        if due is not None and due > dt_util.utcnow():
            self._unsub_timer = async_track_point_in_utc_time(
                self.hass, self._overdue, due
            )

    @callback
    def _overdue(self, now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
