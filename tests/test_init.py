"""Setup, the webhook, the entities it updates, and what survives a restart."""

from __future__ import annotations

import base64

from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.freematics.const import CONF_CLOUDHOOK, DOMAIN

from .conftest import WEBHOOK_ID
from .encode import batch

URL = f"/api/webhook/{WEBHOOK_ID}"
T = 1_763_700_000


async def post(hass_client_no_auth, batch_bytes: bytes, raw: bool = False) -> int:
    """Post a batch as the dongle does: base64 text (raw: the body as given)."""
    client = await hass_client_no_auth()
    body = batch_bytes if raw else base64.b64encode(batch_bytes)
    response = await client.post(URL, data=body)
    return response.status


def trip() -> list[dict[str, Any]]:
    return [
        {
            "kind": "start",
            "time": T,
            "lat": 43.8185,
            "lon": -72.2787,
            "speed": 20,
            "course": 90,
            "sats": 9,
            "hdop": 12,
            "alt": 237,
            "battery": 14.1,
        },
        {
            "kind": "fix",
            "time": T + 10,
            "lat": 43.8190,
            "lon": -72.2770,
            "speed": 48,
            "course": 44,
            "sats": 10,
            "hdop": 9,
            "alt": 241,
        },
    ]


async def test_a_batch_updates_every_entity(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    assert loaded.state is ConfigEntryState.LOADED
    assert hass.states.get("device_tracker.volvo").state == "unknown"
    assert await post(hass_client_no_auth, batch(trip())) == 200
    await hass.async_block_till_done()

    tracker = hass.states.get("device_tracker.volvo")
    assert tracker.attributes["latitude"] == 43.819
    assert tracker.attributes["longitude"] == -72.277
    assert tracker.attributes["gps_accuracy"] == 4.5
    assert tracker.attributes["source_type"] == "gps"
    assert hass.states.get("binary_sensor.volvo_moving").state == "on"
    assert hass.states.get("sensor.volvo_speed").state == "48"
    assert hass.states.get("sensor.volvo_heading").state == "44"
    assert hass.states.get("sensor.volvo_altitude").state == "241"
    assert hass.states.get("sensor.volvo_satellites").state == "10"
    assert hass.states.get("sensor.volvo_battery_voltage").state == "14.1"
    assert hass.states.get("sensor.volvo_last_report").state.startswith("2025-11-21")
    trip_event = hass.states.get("event.volvo_trip")
    assert trip_event.attributes["event_type"] == "trip_started"
    assert trip_event.attributes["latitude"] == 43.8185


async def test_a_stop_and_a_late_batch(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    await post(hass_client_no_auth, batch(trip()))
    stop = [
        {
            "kind": "stop",
            "time": T + 400,
            "lat": 43.8217,
            "lon": -72.2701,
            "alt": 230,
            "battery": 12.6,
        },
        {"kind": "heartbeat", "time": T + 1300, "battery": 12.5},
    ]
    assert await post(hass_client_no_auth, batch(stop)) == 200
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.volvo_moving").state == "off"
    assert hass.states.get("event.volvo_trip").attributes["event_type"] == (
        "trip_stopped"
    )
    # The heartbeat had no fix: the stop's position stays.
    assert hass.states.get("device_tracker.volvo").attributes["latitude"] == 43.8217
    assert hass.states.get("sensor.volvo_battery_voltage").state == "12.5"


async def test_a_batch_sent_again_is_taken_once(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    events: list[Event] = async_capture_events(hass, "state_changed")
    await post(hass_client_no_auth, batch(trip(), sequence=7))
    await hass.async_block_till_done()
    count = len(events)
    # The dongle missed the answer and sends the same records again.
    assert await post(hass_client_no_auth, batch(trip(), sequence=8)) == 200
    await hass.async_block_till_done()
    assert len(events) == count
    assert loaded.runtime_data.repeats == 2
    assert loaded.runtime_data.records == 2


async def test_missing_batches_are_counted(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth, caplog
) -> None:
    caplog.set_level("DEBUG", "custom_components.freematics")
    first, second = trip()
    await post(hass_client_no_auth, batch([first], sequence=0xFFFF))
    # The sequence wraps: no gap.
    await post(hass_client_no_auth, batch([second], sequence=0))
    assert loaded.runtime_data.sequence_gaps == 0
    third = {**second, "time": T + 20}
    await post(hass_client_no_auth, batch([third], sequence=5))
    assert loaded.runtime_data.sequence_gaps == 1
    assert "batch 5 after 0" in caplog.text
    assert "batch 0, 1 records" in caplog.text
    # A repeat taken nothing: the last batch says so.
    await post(hass_client_no_auth, batch([third], sequence=6))
    assert "repeat of" in caplog.text
    last = loaded.runtime_data.last_batch
    assert last is not None and last.taken == 0 and last.delay_s is None


async def test_rejects_what_isnt_a_batch(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth, caplog
) -> None:
    assert await post(hass_client_no_auth, b"hello!", raw=True) == 400
    assert "Volvo sent a batch that can't be read" in caplog.text
    # Binary isn't accepted: Home Assistant Cloud would have mangled it.
    assert await post(hass_client_no_auth, batch(trip()), raw=True) == 400
    assert await post(hass_client_no_auth, bytes(9000), raw=True) == 413


async def test_state_survives_a_restart(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth, hass_storage
) -> None:
    await post(hass_client_no_auth, batch(trip()))
    await hass.async_block_till_done()
    # Unloading writes at once what the delayed save would write later.
    await hass.config_entries.async_unload(loaded.entry_id)
    assert hass_storage[f"{DOMAIN}.{loaded.entry_id}"]["data"]["last_time"] == T + 10
    assert await hass.config_entries.async_setup(loaded.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.volvo").attributes["latitude"] == 43.819
    assert hass.states.get("binary_sensor.volvo_moving").state == "on"
    assert hass.states.get("sensor.volvo_battery_voltage").state == "14.1"
    # Records the dongle already sent before the restart are still recognised.
    assert loaded.runtime_data.last_time == T + 10


async def test_unload_stops_the_webhook(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert loaded.state is ConfigEntryState.NOT_LOADED
    assert (
        await post(hass_client_no_auth, batch(trip())) == 200
    )  # webhook: unknown ids answer 200
    assert hass.states.get("device_tracker.volvo").state == "unavailable"


async def test_remove_deletes_the_cloud_webhook_and_storage(
    hass: HomeAssistant, hass_storage, cloud
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Subaru",
        data={"webhook_id": WEBHOOK_ID, CONF_CLOUDHOOK: True},
    )
    entry.add_to_hass(hass)
    hass.config.components.add("cloud")
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"last_time": 5},
    }
    assert await hass.config_entries.async_remove(entry.entry_id)
    cloud.async_delete_cloudhook.assert_called_once_with(hass, WEBHOOK_ID)
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage


async def test_entities_have_stable_ids(
    hass: HomeAssistant, loaded: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, loaded.entry_id)
    }
    assert ids == {
        f"{loaded.entry_id}_{key}"
        for key in (
            "location",
            "moving",
            "trip",
            "speed",
            "heading",
            "altitude",
            "battery_voltage",
            "satellites",
            "hdop",
            "last_report",
        )
    }


async def test_accuracy_unknown_without_hdop(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    record = {"kind": "heartbeat", "time": T, "lat": 43.8, "lon": -72.2, "hdop": 0}
    await post(hass_client_no_auth, batch([record]))
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.volvo").attributes["gps_accuracy"] == 0
    assert hass.states.get("binary_sensor.volvo_moving").state == "off"
