"""Freematics: GPS trackers running ESPHome, reporting through a webhook."""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_flow

from .compact import CompactError, decode_body
from .const import CONF_WEBHOOK_ID, DOMAIN, MAX_BODY
from .device import FreematicsDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SENSOR,
]

type FreematicsConfigEntry = ConfigEntry[FreematicsDevice]


async def async_setup_entry(hass: HomeAssistant, entry: FreematicsConfigEntry) -> bool:
    """Set up a dongle: restore its state and listen on its webhook."""
    device = FreematicsDevice(hass, entry.entry_id)
    await device.async_load()
    entry.runtime_data = device

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        body = await request.content.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            return web.Response(status=413)
        try:
            sequence, records = decode_body(body)
        except CompactError as err:
            _LOGGER.warning("%s sent a batch that can't be read: %s", entry.title, err)
            return web.Response(status=400)
        device.async_apply(sequence, records)
        # An empty answer: it's what the dongle pays for over the air.
        return web.Response(status=200)

    webhook.async_register(
        hass,
        DOMAIN,
        entry.title,
        entry.data[CONF_WEBHOOK_ID],
        handle_webhook,
        allowed_methods=["POST"],
    )
    entry.async_on_unload(
        lambda: webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FreematicsConfigEntry) -> bool:
    """Stop listening, remove the entities and save the state now."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: FreematicsConfigEntry) -> None:
    """Delete the cloud webhook and the stored state."""
    await config_entry_flow.webhook_async_remove_entry(hass, entry)
    await FreematicsDevice(hass, entry.entry_id).async_remove()
