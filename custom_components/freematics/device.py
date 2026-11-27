"""What Home Assistant knows about one dongle, kept up to date by its webhook."""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .compact import Record
from .const import (
    AWAKE_SILENCE,
    DEFAULT_MODEL,
    DOMAIN,
    EVENT_IMPACT,
    EVENT_TRIP_STARTED,
    EVENT_TRIP_STOPPED,
    LIVE_WINDOW,
    SLEEP_GRACE,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 30  # seconds: batches close together are written once


@dataclass
class Position:
    """The newest position a dongle reported."""

    latitude: float
    longitude: float
    speed_kmh: int
    course: int
    satellites: int
    hdop: float
    altitude: int | None


@dataclass
class TripSummary:
    """A trip worked out from its records: every point the dongle sent."""

    distance_km: float
    duration_min: float
    max_speed_kmh: int
    average_speed_kmh: float | None  # None for a trip of no time


@dataclass
class Trip:
    """A trip under way: what's been added up since its start."""

    start: int  # Unix time
    end: int = 0  # Unix time of the last record added
    distance_m: float = 0.0
    max_speed_kmh: int = 0
    latitude: float | None = None  # the last point
    longitude: float | None = None

    def add(self, record: Record) -> None:
        """Add a record's leg from the last point."""
        self.end = max(self.end, record.time)
        if record.latitude is None or record.longitude is None:
            return
        if self.latitude is not None and self.longitude is not None:
            self.distance_m += _metres(
                self.latitude, self.longitude, record.latitude, record.longitude
            )
        self.latitude, self.longitude = record.latitude, record.longitude
        self.max_speed_kmh = max(self.max_speed_kmh, record.speed_kmh or 0)

    def summary(self, end: int) -> TripSummary:
        """The trip, ending at end (Unix time)."""
        seconds = max(0, end - self.start)
        return TripSummary(
            distance_km=round(self.distance_m / 1000, 2),
            duration_min=round(seconds / 60, 1),
            max_speed_kmh=self.max_speed_kmh,
            average_speed_kmh=(
                round(self.distance_m / seconds * 3.6, 1) if seconds else None
            ),
        )


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


@dataclass
class DeviceEvent:
    """A trip start or stop, or an impact, with the time the dongle recorded it."""

    event_type: str
    time: datetime
    latitude: float | None
    longitude: float | None
    data: dict[str, Any]


@dataclass
class BatchInfo:
    """The newest batch, for diagnostics: no coordinates."""

    received: datetime
    sequence: int
    size: int  # bytes of base64 text
    records: int
    taken: int
    delay_s: int | None  # from the newest record taken to its arrival


class FreematicsDevice:
    """The latest state of one dongle, restored across restarts.

    Records arrive in time order. Home Assistant keeps no back-dated states,
    so each batch moves the device to its newest record; trip starts and stops
    within it become events carrying their own times.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, name: str = "") -> None:
        self._name = name
        self._hass = hass
        self._entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.last_time = 0  # Unix time of the newest record taken
        # Unix time of the newest trip start taken: a start can be dated
        # before records already taken (below), and is taken only once.
        self.last_start = 0
        self.position: Position | None = None
        self.position_time: datetime | None = None
        self.moving: bool | None = None
        self.battery_v: float | None = None
        self.temperature: int | None = None
        self.signal: int | None = None
        # The dongle said, before sleeping, it reports again by then (Unix time)
        self.sleeping_until: int | None = None
        # What the dongle says it is, once per boot
        self.model: str | None = None
        self.firmware: str | None = None
        self.trip: Trip | None = None
        self.last_trip: TripSummary | None = None
        self.batches = 0
        self.records = 0
        self.repeats = 0
        self.last_sequence: int | None = None
        self.sequence_gaps = 0
        self.kinds: Counter[str] = Counter()
        self.last_batch: BatchInfo | None = None
        self._unsaved = False
        self._update_listeners: set[CALLBACK_TYPE] = set()
        self._event_listeners: set[Callable[[DeviceEvent], None]] = set()

    @property
    def last_report(self) -> datetime | None:
        """When the dongle recorded its newest record."""
        return datetime.fromtimestamp(self.last_time, UTC) if self.last_time else None

    @property
    def live_until(self) -> datetime | None:
        """While on a trip, when the dongle stops counting as reporting live
        unless another batch arrives (None: not on a trip, or no batch since
        Home Assistant started)."""
        if not self.moving or self.last_batch is None:
            return None
        return self.last_batch.received + timedelta(seconds=LIVE_WINDOW)

    @property
    def report_due(self) -> datetime | None:
        """When the dongle should have reported again by (None: no report yet)."""
        if not self.last_time:
            return None
        if self.sleeping_until is not None:
            due = self.sleeping_until + SLEEP_GRACE
        else:
            due = self.last_time + AWAKE_SILENCE
        return datetime.fromtimestamp(due, UTC)

    async def async_load(self) -> None:
        """Restore what was known before Home Assistant restarted."""
        data = await self._store.async_load()
        if not data:
            return
        self.last_time = data.get("last_time", 0)
        self.last_start = data.get("last_start", 0)
        if (position := data.get("position")) is not None:
            self.position = Position(**position)
        if (position_time := data.get("position_time")) is not None:
            self.position_time = datetime.fromtimestamp(position_time, UTC)
        self.moving = data.get("moving")
        self.battery_v = data.get("battery_v")
        self.temperature = data.get("temperature")
        self.signal = data.get("signal")
        self.sleeping_until = data.get("sleeping_until")
        self.model = data.get("model")
        self.firmware = data.get("firmware")
        if (trip := data.get("trip")) is not None:
            self.trip = Trip(**trip)
        if (last_trip := data.get("last_trip")) is not None:
            self.last_trip = TripSummary(**last_trip)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "last_time": self.last_time,
            "last_start": self.last_start,
            "position": asdict(self.position) if self.position else None,
            "position_time": (
                self.position_time.timestamp() if self.position_time else None
            ),
            "moving": self.moving,
            "battery_v": self.battery_v,
            "temperature": self.temperature,
            "signal": self.signal,
            "sleeping_until": self.sleeping_until,
            "model": self.model,
            "firmware": self.firmware,
            "trip": asdict(self.trip) if self.trip else None,
            "last_trip": asdict(self.last_trip) if self.last_trip else None,
        }

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call update after each batch; returns the remover."""
        self._update_listeners.add(update)
        return lambda: self._update_listeners.discard(update)

    @callback
    def async_add_event_listener(
        self, listener: Callable[[DeviceEvent], None]
    ) -> CALLBACK_TYPE:
        """Call listener with each trip start and stop and each impact; returns
        the remover."""
        self._event_listeners.add(listener)
        return lambda: self._event_listeners.discard(listener)

    @callback
    def async_apply(self, sequence: int, records: list[Record], size: int = 0) -> int:
        """Take a batch; returns how many of its records were new."""
        received = dt_util.utcnow()
        self.batches += 1
        if (
            self.last_sequence is not None
            and sequence != (self.last_sequence + 1) & 0xFFFF
        ):
            # A post that never arrived, or the dongle restarted (which picks
            # a new random sequence).
            self.sequence_gaps += 1
            _LOGGER.debug(
                "%s: batch %d after %d: a batch went missing or the dongle restarted",
                self._name,
                sequence,
                self.last_sequence,
            )
        self.last_sequence = sequence
        _LOGGER.debug(
            "%s: batch %d, %d records in %d bytes",
            self._name,
            sequence,
            len(records),
            size,
        )
        events: list[DeviceEvent] = []
        identity_changed = False
        taken = 0
        for record in records:
            # A trip's start is dated when the car started moving, which can
            # be before a record the dongle sent while its GPS was still
            # finding a fix (a heartbeat on waking): it's still news, once.
            # Likewise a stop dated at the trip's last fix at moving speed,
            # reported after a restart: the car parked, then the power went.
            late_trip = record.time <= self.last_time and (
                (record.kind == "start" and record.time > self.last_start)
                or (
                    record.kind == "stop"
                    and self.trip is not None
                    and record.time >= self.trip.start
                )
            )
            if record.time <= self.last_time and not late_trip:
                # Sent again because the dongle missed our answer.
                self.repeats += 1
                _LOGGER.debug("%s: repeat of %s, skipped", self._name, record)
                continue
            taken += 1
            self.kinds[record.kind] += 1
            when = datetime.fromtimestamp(record.time, UTC)
            _LOGGER.debug(
                "%s: %s, %d s old: %s",
                self._name,
                when.isoformat(),
                int((received - when).total_seconds()),
                record,
            )
            if late_trip:
                # Only the trip: the rest describes an earlier moment than
                # what's shown now.
                self._trip_record(record, when, events)
                continue
            self.last_time = record.time
            if record.latitude is not None and record.longitude is not None:
                self.position = Position(
                    latitude=record.latitude,
                    longitude=record.longitude,
                    speed_kmh=record.speed_kmh or 0,
                    course=record.course or 0,
                    satellites=record.satellites or 0,
                    hdop=record.hdop or 0.0,
                    altitude=record.altitude,
                )
                self.position_time = when
            if record.battery_v is not None:
                self.battery_v = record.battery_v
            if record.temperature is not None:
                self.temperature = record.temperature
            if record.signal is not None:
                self.signal = record.signal
            if record.model is not None and record.model != self.model:
                self.model = record.model
                identity_changed = True
            if record.firmware is not None and record.firmware != self.firmware:
                self.firmware = record.firmware
                identity_changed = True
            # Only the newest record says whether the dongle is asleep now.
            self.sleeping_until = (
                record.time + record.next_report_min * 60
                if record.next_report_min
                else None
            )
            self._trip_record(record, when, events)
            if record.impact_g is not None:
                events.append(
                    DeviceEvent(
                        EVENT_IMPACT,
                        when,
                        record.latitude,
                        record.longitude,
                        {"peak_g": record.impact_g},
                    )
                )
        self.records += taken
        self.last_batch = BatchInfo(
            received=received,
            sequence=sequence,
            size=size,
            records=len(records),
            taken=taken,
            delay_s=(int(received.timestamp() - self.last_time) if taken else None),
        )
        if not taken:
            return 0
        self._unsaved = True
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        if identity_changed:
            self._update_device_registry()
        for event in events:
            for event_listener in list(self._event_listeners):
                event_listener(event)
        for update in list(self._update_listeners):
            update()
        return taken

    def _trip_record(
        self, record: Record, when: datetime, events: list[DeviceEvent]
    ) -> None:
        """Follow trips: their starts and stops, and what they add up to."""
        if record.kind == "start":
            self._end_trip_without_stop(events)
            self.moving = True
            self.last_start = max(self.last_start, record.time)
            self.trip = Trip(start=record.time)
            if record.latitude is None and self.position is not None:
                # Dated before the GPS had a fix: the car was still where it
                # was parked, the last position known.
                self.trip.latitude = self.position.latitude
                self.trip.longitude = self.position.longitude
            self.trip.add(record)
            events.append(
                DeviceEvent(
                    EVENT_TRIP_STARTED,
                    when,
                    self.trip.latitude,
                    self.trip.longitude,
                    {},
                )
            )
        elif record.kind == "stop":
            self.moving = False
            data: dict[str, Any] = {}
            if self.trip is not None:
                self.trip.add(record)
                self.last_trip = self.trip.summary(record.time)
                data = asdict(self.last_trip)
            self.trip = None
            events.append(self._event(EVENT_TRIP_STOPPED, when, record, data))
        elif record.kind == "heartbeat":
            # A heartbeat comes only from a parked dongle
            self.moving = False
            self._end_trip_without_stop(events)
        else:
            self.moving = True
            if self.trip is not None:
                self.trip.add(record)

    def _update_device_registry(self) -> None:
        """Show the model and firmware the dongle reported on its device."""
        registry = dr.async_get(self._hass)
        if device := registry.async_get_device_by_identifier(
            (DOMAIN, self._entry_id), self._entry_id
        ):
            registry.async_update_device(
                device.id,
                model=self.model or DEFAULT_MODEL,
                sw_version=self.firmware,
            )

    def _end_trip_without_stop(self, events: list[DeviceEvent]) -> None:
        """End a trip whose stop never came, at its last record.

        A dongle that restarts on a trip (unplugged, or a crash) forgets it:
        its next record is a heartbeat or another trip's start, never the stop.
        """
        if self.trip is None:
            return
        _LOGGER.debug(
            "%s: the trip's stop never came; ending it at its last record",
            self._name,
        )
        end = self.trip.end
        self.last_trip = self.trip.summary(end)
        events.append(
            DeviceEvent(
                EVENT_TRIP_STOPPED,
                datetime.fromtimestamp(end, UTC),
                self.trip.latitude,
                self.trip.longitude,
                {**asdict(self.last_trip), "stop_missed": True},
            )
        )
        self.trip = None

    @staticmethod
    def _event(
        event_type: str, when: datetime, record: Record, data: dict[str, Any]
    ) -> DeviceEvent:
        return DeviceEvent(event_type, when, record.latitude, record.longitude, data)

    async def async_save(self) -> None:
        """Write what's new now (the entry is unloading or reloading)."""
        if self._unsaved:
            await self._store.async_save(self._data_to_save())
            self._unsaved = False

    async def async_remove(self) -> None:
        """Forget the stored state (the entry was deleted)."""
        await self._store.async_remove()
