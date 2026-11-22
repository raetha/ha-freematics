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
    assert data["kinds"] == {"start": 1, "fix": 1}
    assert data["sequence_gaps"] == 0
    last = data["last_batch"]
    assert last["sequence"] == 42 and last["records"] == 2 and last["taken"] == 2
    assert last["size"] > 0 and last["delay_s"] is not None
    assert data["battery_v"] == 14.1 and data["position_time"] is not None
    assert "latitude" not in str(data)
