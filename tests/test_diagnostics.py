"""Diagnostics hide the webhook ID and carry no coordinates."""

from __future__ import annotations

import base64

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freematics.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .encode import batch
from .test_init import URL, trip


async def test_diagnostics(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    data = await async_get_config_entry_diagnostics(hass, loaded)
    assert data["entry"]["webhook_id"] == "**REDACTED**"
    assert data["last_report"] is None
    client = await hass_client_no_auth()
    await client.post(URL, data=base64.b64encode(batch(trip(), sequence=42)))
    data = await async_get_config_entry_diagnostics(hass, loaded)
    assert data["batches"] == 1 and data["records"] == 2 and data["last_sequence"] == 42
    assert data["has_position"] is True
    assert "latitude" not in str(data)
