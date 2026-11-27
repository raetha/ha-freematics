"""The batch decoder (custom_components/freematics/compact.py)."""

from __future__ import annotations

import base64

import pytest

from custom_components.freematics.compact import CompactError, decode, decode_body

from .encode import batch


def test_decodes_kinds_positions_and_deltas():
    body = batch(
        [
            {
                "kind": "start",
                "time": 1000,
                "lat": 43.818481,
                "lon": -72.278662,
                "speed": 12,
                "course": 91,
                "sats": 9,
                "hdop": 12,
                "alt": 237,
                "battery": 14.1,
            },
            {
                "kind": "fix",
                "time": 1010,
                "lat": 43.819001,
                "lon": -72.277001,
                "speed": 49,
                "course": 358,
                "alt": 241,
            },
            {"kind": "fix", "time": 1020, "lat": 43.821777, "lon": -72.27},
            {
                "kind": "stop",
                "time": 1400,
                "lat": 43.8217,
                "lon": -72.2701,
                "alt": 230,
                "battery": 12.6,
            },
            {"kind": "heartbeat", "time": 2300, "battery": 12.5},
        ],
        sequence=513,
    )
    sequence, records = decode(body)
    assert sequence == 513
    assert [r.kind for r in records] == ["start", "fix", "fix", "stop", "heartbeat"]
    assert [r.time for r in records] == [1000, 1010, 1020, 1400, 2300]
    assert records[0].latitude == pytest.approx(43.818481)
    assert records[0].longitude == pytest.approx(-72.278662)
    assert records[2].latitude == pytest.approx(43.821777)
    assert records[0].course == 90 and records[1].course == 358
    assert records[0].hdop == pytest.approx(1.2)
    assert [r.altitude for r in records] == [237, 241, None, 230, None]
    assert [r.battery_v for r in records] == [14.1, None, None, 12.6, 12.5]
    assert records[4].latitude is None


def test_an_empty_batch_is_valid():
    assert decode(bytes([1, 5, 0, 0, 0, 0, 0])) == (5, [])


@pytest.mark.parametrize(
    "body",
    [
        b"",
        bytes([2, 0, 0, 0, 0, 0, 0]),  # another version
        bytes([1, 0, 0, 0, 0, 0, 0, 0x40, 0]),  # unknown flag
        bytes([1, 0, 0, 0, 0, 0, 0, 0x20, 0, 1, 0x41, 7]),  # extra cut short
        bytes([1, 0, 0, 0, 0, 0, 0, 0x04, 0]),  # position cut short
        bytes([1, 0, 0, 0, 0, 0, 0, 0x08, 0]),  # altitude without a position
        bytes([1, 0, 0, 0, 0, 0, 0, 0x00, 0x80]),  # varint cut short
        bytes([1, 0, 0, 0, 0, 0, 0, 0x00]) + b"\xff" * 6,  # oversized varint
        bytes([1, 0, 0, 0, 0, 0, 0, 0x10, 0]),  # battery missing
    ],
)
def test_rejects_what_isnt_a_batch(body):
    with pytest.raises(CompactError):
        decode(body)


def test_bodies_are_base64():
    body = batch([{"kind": "heartbeat", "time": 5, "battery": 12.5}], sequence=3)
    assert decode_body(base64.b64encode(body)) == decode(body)
    with pytest.raises(CompactError):
        decode_body(b"not base64!")
    with pytest.raises(CompactError):
        decode_body(body)  # raw binary


def test_unknown_extras_are_skipped():
    # A heartbeat with an unknown 2-byte extra (id 9), an unknown
    # length-prefixed one (id 10), then a temperature: newer dongles' extras
    # don't stop an older integration.
    header = bytes([1, 0, 0, 0, 0, 0, 0])
    record = bytes([0x23, 0, 3, 0x49, 1, 2, 0xCA, 2, 7, 7, 0x01, 21])
    (got,) = decode(header + record)[1]
    assert got.kind == "heartbeat" and got.temperature == 21
