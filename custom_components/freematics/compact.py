"""The compact batches the dongles post to the webhook, as base64 text.

The encoder is components/tracker_uplink/compact.h in raetha/esphome-freematics,
whose tests carry a copy of this decoder: keep the two the same.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

VERSION = 1
KINDS = ("fix", "start", "stop", "heartbeat")
POSITION, ALTITUDE, BATTERY = 0x04, 0x08, 0x10


class CompactError(ValueError):
    """A batch that isn't a valid compact batch."""


@dataclass
class Record:
    kind: str
    time: int
    latitude: float | None = None
    longitude: float | None = None
    speed_kmh: int | None = None
    course: int | None = None
    satellites: int | None = None
    hdop: float | None = None
    altitude: int | None = None
    battery_v: float | None = None


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data) or shift > 28:
            raise CompactError("truncated or oversized varint")
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _byte(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise CompactError("truncated record")
    return data[pos], pos + 1


def decode(data: bytes) -> tuple[int, list[Record]]:
    """Return the batch's sequence number and its records, oldest first."""
    if len(data) < 7 or data[0] != VERSION:
        raise CompactError("not a version 1 batch")
    sequence = int.from_bytes(data[1:3], "little")
    time = int.from_bytes(data[3:7], "little")
    lat = lon = alt = 0
    records = []
    pos = 7
    while pos < len(data):
        flags = data[pos]
        pos += 1
        if flags & ~0x1F:
            raise CompactError(f"unknown flags {flags:#04x}")
        dt, pos = _varint(data, pos)
        time += dt
        rec = Record(kind=KINDS[flags & 0x03], time=time)
        if flags & POSITION:
            d, pos = _varint(data, pos)
            lat += _zigzag(d)
            d, pos = _varint(data, pos)
            lon += _zigzag(d)
            rec.latitude, rec.longitude = lat / 1e6, lon / 1e6
            rec.speed_kmh, pos = _byte(data, pos)
            course, pos = _byte(data, pos)
            rec.course = course * 2
            rec.satellites, pos = _byte(data, pos)
            hdop, pos = _byte(data, pos)
            rec.hdop = hdop / 10
            if flags & ALTITUDE:
                d, pos = _varint(data, pos)
                alt += _zigzag(d)
                rec.altitude = alt
        elif flags & ALTITUDE:
            raise CompactError("altitude without a position")
        if flags & BATTERY:
            battery, pos = _byte(data, pos)
            rec.battery_v = battery / 10
        records.append(rec)
    return sequence, records


def decode_body(body: bytes) -> tuple[int, list[Record]]:
    """A webhook body: a batch as base64 text (Home Assistant Cloud relays bodies
    as UTF-8 text, which binary wouldn't survive)."""
    try:
        data = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as err:
        raise CompactError("not base64") from err
    return decode(data)
