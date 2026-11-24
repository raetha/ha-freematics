"""Setup, the webhook, the entities it updates, and what survives a restart."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
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
            "live_tracking",
            "trip",
            "impact",
            "temperature",
            "signal",
            "last_trip_distance",
            "last_trip_duration",
            "last_trip_max_speed",
            "last_trip_average_speed",
            "speed",
            "heading",
            "altitude",
            "battery_voltage",
            "satellites",
            "hdop",
            "last_report",
            "next_report",
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


async def test_a_trip_is_summed_up_at_its_stop(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    await post(hass_client_no_auth, batch(trip()))
    stop = [
        {"kind": "fix", "time": T + 40},  # no fix for a moment (a tunnel)
        {"kind": "fix", "time": T + 70, "lat": 43.8250, "lon": -72.2770, "speed": 90},
        {"kind": "stop", "time": T + 370, "lat": 43.8250, "lon": -72.2700},
    ]
    await post(hass_client_no_auth, batch(stop, sequence=2))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    assert event["event_type"] == "trip_stopped"
    # Along the points: 0.15 km, then 0.67 km north, then 0.56 km east
    assert event["distance_km"] == pytest.approx(1.38, abs=0.02)
    assert event["duration_min"] == 6.2
    assert event["max_speed_kmh"] == 90
    assert event["average_speed_kmh"] == pytest.approx(13.4, abs=0.3)
    assert (
        float(hass.states.get("sensor.volvo_last_trip_distance").state)
        == (event["distance_km"])
    )
    assert hass.states.get("sensor.volvo_last_trip_duration").state == "6.2"
    assert hass.states.get("sensor.volvo_last_trip_top_speed").state == "90"
    # The last trip is still there after a restart.
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.volvo_last_trip_top_speed").state == "90"


async def test_a_stop_without_its_start_has_no_summary(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    stop = {"kind": "stop", "time": T, "lat": 43.8, "lon": -72.3}
    await post(hass_client_no_auth, batch([stop]))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    assert event["event_type"] == "trip_stopped" and "distance_km" not in event
    assert hass.states.get("sensor.volvo_last_trip_distance").state == "unknown"


async def test_a_trip_survives_a_restart(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    await post(hass_client_no_auth, batch(trip()))
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    stop = {"kind": "stop", "time": T + 70, "lat": 43.8190, "lon": -72.2700}
    await post(hass_client_no_auth, batch([stop], sequence=2))
    await hass.async_block_till_done()
    assert hass.states.get("event.volvo_trip").attributes["duration_min"] == 1.2


async def test_extras_and_an_impact(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    records = [
        {
            "kind": "start",
            "time": T,
            "lat": 43.8,
            "lon": -72.3,
            "temperature": -7,
            "signal": -85,
        },
        {"kind": "fix", "time": T + 4, "lat": 43.8001, "lon": -72.3, "impact": 6.4},
    ]
    await post(hass_client_no_auth, batch(records))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.volvo_temperature").state == "-7"
    assert hass.states.get("sensor.volvo_cellular_signal").state == "-85"
    impact = hass.states.get("event.volvo_impact").attributes
    assert impact["event_type"] == "impact" and impact["peak_g"] == 6.4
    assert impact["latitude"] == 43.8001
    # The impact doesn't fire the trip event, nor the trip the impact event.
    assert hass.states.get("event.volvo_trip").attributes["event_type"] == (
        "trip_started"
    )


async def test_next_report_due_follows_what_the_dongle_said(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    def due() -> str:
        return hass.states.get("sensor.volvo_next_report_due").state

    assert due() == "unknown"
    await post(hass_client_no_auth, batch([{"kind": "heartbeat", "time": T}]))
    await hass.async_block_till_done()
    # Awake, it reports at least every 15 minutes: 45 without one is overdue.
    assert due() == dt_util.utc_from_timestamp(T + 45 * 60).isoformat()
    # Off to sleep for 6 hours: due then, and a bit.
    note = {"kind": "heartbeat", "time": T + 60, "next_report": 361}
    await post(hass_client_no_auth, batch([note], sequence=2))
    await hass.async_block_till_done()
    assert due() == dt_util.utc_from_timestamp(T + 60 + (361 + 15) * 60).isoformat()


async def test_live_tracking_is_on_while_a_trip_streams(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth, freezer
) -> None:
    def live() -> str:
        return hass.states.get("binary_sensor.volvo_live_tracking").state

    start = dt_util.utcnow()
    assert live() == "off"
    # Parked heartbeats aren't a trip streaming.
    await post(hass_client_no_auth, batch([{"kind": "heartbeat", "time": T}]))
    await hass.async_block_till_done()
    assert live() == "off"
    await post(hass_client_no_auth, batch(trip(), sequence=2))
    await hass.async_block_till_done()
    assert live() == "on"
    # Batches every 5 minutes keep it on; 10 minutes without one turn it off.
    freezer.move_to(start + timedelta(minutes=9))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert live() == "on"
    freezer.move_to(start + timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert live() == "off"
    # Back in coverage, then the stop: off.
    fix = {"kind": "fix", "time": T + 400, "lat": 43.82, "lon": -72.27, "speed": 50}
    await post(hass_client_no_auth, batch([fix], sequence=3))
    await hass.async_block_till_done()
    assert live() == "on"
    stop = {"kind": "stop", "time": T + 500, "lat": 43.83, "lon": -72.27}
    await post(hass_client_no_auth, batch([stop], sequence=4))
    await hass.async_block_till_done()
    assert live() == "off"
    # Unloading cancels the timer.
    await post(
        hass_client_no_auth,
        batch([{**r, "time": r["time"] + 1000} for r in trip()], sequence=5),
    )
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(loaded.entry_id)


async def test_the_dongle_names_its_model_and_firmware(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    hass_client_no_auth,
    device_registry: dr.DeviceRegistry,
) -> None:
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, loaded.entry_id), loaded.entry_id
    )
    assert device.model == "ONE+" and device.sw_version is None
    hello = {
        "kind": "heartbeat",
        "time": T,
        "model": "ONE+ Model B",
        "firmware": "0.1.0+ff6a429",
    }
    await post(hass_client_no_auth, batch([hello]))
    await hass.async_block_till_done()
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, loaded.entry_id), loaded.entry_id
    )
    assert (device.model, device.sw_version) == ("ONE+ Model B", "0.1.0+ff6a429")
    # Kept across restarts, and set at setup.
    await hass.config_entries.async_reload(loaded.entry_id)
    await hass.async_block_till_done()
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, loaded.entry_id), loaded.entry_id
    )
    assert (device.model, device.sw_version) == ("ONE+ Model B", "0.1.0+ff6a429")
    # The same again changes nothing.
    await post(hass_client_no_auth, batch([{**hello, "time": T + 60}], sequence=2))
    await hass.async_block_till_done()


async def test_a_heartbeat_ends_a_trip_whose_stop_never_came(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    # The dongle restarted on the trip (unplugged): no stop, then a heartbeat.
    await post(hass_client_no_auth, batch(trip()))
    heartbeat = {"kind": "heartbeat", "time": T + 300, "battery": 4.6}
    await post(hass_client_no_auth, batch([heartbeat], sequence=500))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    assert event["event_type"] == "trip_stopped"
    assert event["stop_missed"] is True
    # It ends at the trip's last record, where that record was.
    assert event["recorded_at"] == datetime.fromtimestamp(T + 10, UTC).isoformat()
    assert event["latitude"] == 43.8190
    assert event["duration_min"] == 0.2
    assert hass.states.get("sensor.volvo_last_trip_top_speed").state == "48"
    assert hass.states.get("binary_sensor.volvo_moving").state == "off"


async def test_a_new_start_ends_a_trip_whose_stop_never_came(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    await post(hass_client_no_auth, batch(trip()))
    later = [{**record, "time": record["time"] + 3600} for record in trip()]
    await post(hass_client_no_auth, batch(later, sequence=900))
    await hass.async_block_till_done()
    # The first trip was summed up; the second is under way.
    assert hass.states.get("sensor.volvo_last_trip_top_speed").state == "48"
    assert hass.states.get("event.volvo_trip").attributes["event_type"] == (
        "trip_started"
    )


async def test_a_trip_saved_without_its_end_ends_at_the_last_position(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    entry: MockConfigEntry,
    hass_client_no_auth,
) -> None:
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "last_time": T + 60,
            "position_time": T + 60,
            "trip": {"start": T, "distance_m": 1500.0, "max_speed_kmh": 70},
        },
    }
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    heartbeat = {"kind": "heartbeat", "time": T + 600}
    await post(hass_client_no_auth, batch([heartbeat]))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    assert event["duration_min"] == 1.0
    assert event["distance_km"] == 1.5


async def test_a_start_dated_before_a_record_already_taken(
    hass: HomeAssistant, loaded: MockConfigEntry, hass_client_no_auth
) -> None:
    # On waking, the dongle reported a heartbeat where it was parked; its GPS
    # found a fix only once the car was under way, and the trip is dated when
    # the motion sensor first felt it, before that heartbeat.
    parked = {"kind": "heartbeat", "time": T + 30, "lat": 43.8185, "lon": -72.2787}
    await post(hass_client_no_auth, batch([parked]))
    started = [
        {"kind": "start", "time": T + 20, "battery": 14.1},
        {"kind": "fix", "time": T + 200, "lat": 43.8275, "lon": -72.2787, "speed": 50},
    ]
    await post(hass_client_no_auth, batch(started, sequence=2))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    # From where the car was parked, when the motion sensor first felt it
    assert event["event_type"] == "trip_started"
    assert event["recorded_at"] == datetime.fromtimestamp(T + 20, UTC).isoformat()
    assert event["latitude"] == 43.8185
    # The newest record shows where the car is
    assert hass.states.get("device_tracker.volvo").attributes["latitude"] == 43.8275
    stop = {"kind": "stop", "time": T + 500, "lat": 43.8275, "lon": -72.2787}
    await post(hass_client_no_auth, batch([stop], sequence=3))
    await hass.async_block_till_done()
    event = hass.states.get("event.volvo_trip").attributes
    assert event["event_type"] == "trip_stopped"
    assert event["duration_min"] == 8.0
    assert event["distance_km"] == pytest.approx(1.0, abs=0.02)
    # Sent again (the dongle missed the answer): not a second trip
    await post(hass_client_no_auth, batch(started, sequence=4))
    await hass.async_block_till_done()
    assert hass.states.get("event.volvo_trip").attributes["event_type"] == (
        "trip_stopped"
    )
    assert hass.states.get("binary_sensor.volvo_moving").state == "off"
