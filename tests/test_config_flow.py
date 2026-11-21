"""Adding a dongle and showing its webhook address again."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.network import NoURLAvailableError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freematics.const import CONF_CLOUDHOOK, CONF_WEBHOOK_ID, DOMAIN

EXTERNAL = "https://ha.example.com"
GET_URL = "custom_components.freematics.config_flow.get_url"


@pytest.fixture(autouse=True)
def _no_setup():
    """The flow's tests stop at the entry; setting it up is test_init's."""
    with patch("custom_components.freematics.async_setup_entry", return_value=True):
        yield


async def start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_add_with_the_external_address(hass: HomeAssistant) -> None:
    result = await start(hass)
    with patch(GET_URL, return_value=EXTERNAL):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Volvo"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Volvo"
    webhook_id = result["data"][CONF_WEBHOOK_ID]
    assert result["data"][CONF_CLOUDHOOK] is False
    assert result["description_placeholders"] == {
        "webhook_url": f"{EXTERNAL}/api/webhook/{webhook_id}"
    }


async def test_add_with_home_assistant_cloud(hass: HomeAssistant, cloud) -> None:
    hass.config.components.add("cloud")
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Subaru"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CLOUDHOOK] is True
    assert result["description_placeholders"] == {
        "webhook_url": "https://hooks.nabu.casa/abc"
    }


async def test_cloud_not_connected_falls_back_to_the_external_address(
    hass: HomeAssistant, cloud
) -> None:
    hass.config.components.add("cloud")
    cloud.async_is_connected.return_value = False
    result = await start(hass)
    with patch(GET_URL, return_value=EXTERNAL):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Volvo"}
        )
    assert result["data"][CONF_CLOUDHOOK] is False


async def test_no_https_address(hass: HomeAssistant) -> None:
    result = await start(hass)
    with patch(GET_URL, side_effect=NoURLAvailableError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Volvo"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_https_url"


async def test_reconfigure_shows_the_address_again(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    with patch(GET_URL, return_value=EXTERNAL):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "webhook_url"
    assert result["description_placeholders"] == {
        "webhook_url": f"{EXTERNAL}/api/webhook/{entry.data[CONF_WEBHOOK_ID]}"
    }


async def test_reconfigure_without_an_address(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(GET_URL, side_effect=NoURLAvailableError):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "no_https_url"
