"""Diagnostics, safe to post publicly: the webhook ID is the dongle's only key."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import FreematicsConfigEntry
from .const import CONF_WEBHOOK_ID


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FreematicsConfigEntry
) -> dict[str, Any]:
    """The entry (webhook ID redacted) and what the dongle has sent since start."""
    device = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_WEBHOOK_ID}),
        "batches": device.batches,
        "records": device.records,
        "repeats": device.repeats,
        "last_sequence": device.last_sequence,
        "last_report": device.last_report.isoformat() if device.last_report else None,
        "moving": device.moving,
        "has_position": device.position is not None,
    }
