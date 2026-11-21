"""Add a dongle: name it, and get the webhook URL for its ESPHome config."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_CLOUDHOOK, CONF_WEBHOOK_ID, DOMAIN


def _form(schema: Any) -> Any:
    """A schema in whatever type this Home Assistant takes.

    From 2026.10 Home Assistant validates with probatio and makes `import
    voluptuous` load it, so at run time this already is a probatio schema; only
    the static types differ.
    """
    return schema


class FreematicsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per dongle, each with its own webhook."""

    VERSION = 1

    async def _async_webhook_url(self, webhook_id: str) -> tuple[str, bool] | None:
        """The address the dongle posts to, and whether it's a cloud one.

        The dongle is out on the internet and only speaks HTTPS: Home Assistant
        Cloud's address when there's a subscription, otherwise Home
        Assistant's own external HTTPS address; None when there's neither.
        """
        if "cloud" in self.hass.config.components:
            # Imported only when it's loaded: cloud pulls in much of Home Assistant.
            from homeassistant.components import cloud  # noqa: PLC0415

            if cloud.async_active_subscription(self.hass) and cloud.async_is_connected(
                self.hass
            ):
                url = await cloud.async_get_or_create_cloudhook(self.hass, webhook_id)
                return url, True
        try:
            base = get_url(
                self.hass,
                allow_internal=False,
                allow_ip=False,
                require_ssl=True,
                allow_cloud=False,
            )
        except NoURLAvailableError:
            return None
        return f"{base}{webhook.async_generate_path(webhook_id)}", False

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the dongle (the car it's in)."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_form(vol.Schema({vol.Required(CONF_NAME): str})),
            )
        webhook_id = webhook.async_generate_id()
        found = await self._async_webhook_url(webhook_id)
        if found is None:
            return self.async_abort(reason="no_https_url")
        url, cloudhook = found
        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data={CONF_WEBHOOK_ID: webhook_id, CONF_CLOUDHOOK: cloudhook},
            description_placeholders={"webhook_url": url},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the webhook URL again (and switch to the cloud one if it's new)."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self.async_show_form(step_id="reconfigure")
        found = await self._async_webhook_url(entry.data[CONF_WEBHOOK_ID])
        if found is None:
            return self.async_abort(reason="no_https_url")
        url, cloudhook = found
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CLOUDHOOK: cloudhook}
        )
        return self.async_abort(
            reason="webhook_url", description_placeholders={"webhook_url": url}
        )
