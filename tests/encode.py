"""An encoder for test batches, mirroring components/tracker_uplink/compact.h in
raetha/esphome-freematics (whose tests check the real encoder against
custom_components/freematics/compact.py's decoder)."""

from __future__ import annotations

KINDS = {"fix": 0, "start": 1, "stop": 2, "heartbeat": 3}


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def batch(records: list[dict], sequence: int = 1) -> bytes:
    """Encode records: dicts with kind, time and optionally lat, lon, speed,
    course, sats, hdop (x10), alt, battery (volts), and the extras temperature
    (deg C), signal (dBm), impact (g), next_report (minutes)."""
    base = records[0]["time"] if records else 0
    out = bytearray([1]) + sequence.to_bytes(2, "little") + base.to_bytes(4, "little")
    time, lat, lon, alt = base, 0, 0, 0
    for r in records:
        flags = KINDS[r["kind"]]
        body = bytearray(_varint(max(0, r["time"] - time)))
        time = max(time, r["time"])
        if "lat" in r:
            flags |= 0x04
            la, lo = round(r["lat"] * 1e6), round(r["lon"] * 1e6)
            body += _varint(_zigzag(la - lat)) + _varint(_zigzag(lo - lon))
            lat, lon = la, lo
            body += bytes(
                [
                    r.get("speed", 0),
                    r.get("course", 0) // 2,
                    r.get("sats", 9),
                    r.get("hdop", 10),
                ]
            )
            if "alt" in r:
                flags |= 0x08
                body += _varint(_zigzag(r["alt"] - alt))
                alt = r["alt"]
        if "battery" in r:
            flags |= 0x10
            body.append(round(r["battery"] * 10))
        extras = bytearray()
        count = 0
        if "temperature" in r:
            extras += bytes([0x01]) + r["temperature"].to_bytes(
                1, "little", signed=True
            )
            count += 1
        if "signal" in r:
            extras += bytes([0x02]) + r["signal"].to_bytes(1, "little", signed=True)
            count += 1
        if "impact" in r:
            extras += bytes([0x03, round(r["impact"] * 10)])
            count += 1
        if "next_report" in r:
            extras += bytes([0x44]) + r["next_report"].to_bytes(2, "little")
            count += 1
        if count:
            flags |= 0x20
            body += bytes([count]) + extras
        out += bytes([flags]) + body
    return bytes(out)
