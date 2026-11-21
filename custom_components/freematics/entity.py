"""The base entity: one device per dongle, updated after each batch."""

from __future__ import annotations

from typing import override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from . import FreematicsConfigEntry
from .const import DOMAIN
from .device import FreematicsDevice


class FreematicsEntity(Entity):
    """An entity of one dongle."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: FreematicsConfigEntry, key: str) -> None:
        self.device: FreematicsDevice = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Freematics",
            model="ONE+ (ESPHome)",
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Update with each batch."""
        await super().async_added_to_hass()
        self.async_on_remove(self.device.async_add_listener(self.async_write_ha_state))
