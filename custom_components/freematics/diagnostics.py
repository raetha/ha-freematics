"""Diagnostics, safe to post publicly: the webhook ID is the dongle's only key."""

from __future__ import annotations

from dataclasses import asdict
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
        "kinds": dict(device.kinds),
        "last_sequence": device.last_sequence,
        "sequence_gaps": device.sequence_gaps,
        "last_batch": (
            {
                "received": batch.received.isoformat(),
                "sequence": batch.sequence,
                "size": batch.size,
                "records": batch.records,
                "taken": batch.taken,
                "delay_s": batch.delay_s,
            }
            if (batch := device.last_batch)
            else None
        ),
        "last_report": device.last_report.isoformat() if device.last_report else None,
        "model": device.model,
        "firmware": device.firmware,
        "moving": device.moving,
        "has_position": device.position is not None,
        "position_time": (
            device.position_time.isoformat() if device.position_time else None
        ),
        "battery_v": device.battery_v,
        "temperature": device.temperature,
        "signal": device.signal,
        "sleeping_until": device.sleeping_until,
        "report_due": device.report_due.isoformat() if device.report_due else None,
        "on_a_trip": device.trip is not None,
        "last_trip": asdict(device.last_trip) if device.last_trip else None,
    }
