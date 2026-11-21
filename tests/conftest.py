"""Shared fixtures for the Freematics integration's tests."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freematics.const import CONF_CLOUDHOOK, CONF_WEBHOOK_ID, DOMAIN

WEBHOOK_ID = "0123456789abcdef"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components/."""
    return enable_custom_integrations


@pytest.fixture
def entry() -> MockConfigEntry:
    """A dongle's config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Volvo",
        data={CONF_WEBHOOK_ID: WEBHOOK_ID, CONF_CLOUDHOOK: False},
    )


@pytest.fixture
async def loaded(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """The entry, set up, with Home Assistant's HTTP server running."""
    await async_setup_component(hass, "http", {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def cloud() -> MagicMock:
    """Home Assistant Cloud, faked: the real one pulls in half of Home Assistant."""
    module = ModuleType("homeassistant.components.cloud")
    fake = MagicMock()
    fake.async_active_subscription.return_value = True
    fake.async_is_connected.return_value = True
    fake.async_get_or_create_cloudhook = AsyncMock(
        return_value="https://hooks.nabu.casa/abc"
    )
    fake.async_delete_cloudhook = AsyncMock()
    for name in (
        "async_active_subscription",
        "async_is_connected",
        "async_get_or_create_cloudhook",
        "async_delete_cloudhook",
    ):
        setattr(module, name, getattr(fake, name))
    with patch.dict(sys.modules, {"homeassistant.components.cloud": module}):
        yield fake
