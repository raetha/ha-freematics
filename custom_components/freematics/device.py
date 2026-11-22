"""What Home Assistant knows about one dongle, kept up to date by its webhook."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .compact import Record
from .const import DOMAIN, EVENT_TRIP_STARTED, EVENT_TRIP_STOPPED

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 30  # seconds: batches arrive every couple of minutes at most


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
class TripEvent:
    """A trip start or stop, with the time the dongle recorded it."""

    event_type: str
    time: datetime
    latitude: float | None
    longitude: float | None


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
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.last_time = 0  # Unix time of the newest record taken
        self.position: Position | None = None
        self.position_time: datetime | None = None
        self.moving: bool | None = None
        self.battery_v: float | None = None
        self.batches = 0
        self.records = 0
        self.repeats = 0
        self.last_sequence: int | None = None
        self.sequence_gaps = 0
        self.kinds: Counter[str] = Counter()
        self.last_batch: BatchInfo | None = None
        self._unsaved = False
        self._update_listeners: set[CALLBACK_TYPE] = set()
        self._event_listeners: set[Callable[[TripEvent], None]] = set()

    @property
    def last_report(self) -> datetime | None:
        """When the dongle recorded its newest record."""
        return datetime.fromtimestamp(self.last_time, UTC) if self.last_time else None

    async def async_load(self) -> None:
        """Restore what was known before Home Assistant restarted."""
        data = await self._store.async_load()
        if not data:
            return
        self.last_time = data.get("last_time", 0)
        if (position := data.get("position")) is not None:
            self.position = Position(**position)
        if (position_time := data.get("position_time")) is not None:
            self.position_time = datetime.fromtimestamp(position_time, UTC)
        self.moving = data.get("moving")
        self.battery_v = data.get("battery_v")

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "last_time": self.last_time,
            "position": asdict(self.position) if self.position else None,
            "position_time": (
                self.position_time.timestamp() if self.position_time else None
            ),
            "moving": self.moving,
            "battery_v": self.battery_v,
        }

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call update after each batch; returns the remover."""
        self._update_listeners.add(update)
        return lambda: self._update_listeners.discard(update)

    @callback
    def async_add_event_listener(
        self, listener: Callable[[TripEvent], None]
    ) -> CALLBACK_TYPE:
        """Call listener with each trip start and stop; returns the remover."""
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
        events: list[TripEvent] = []
        taken = 0
        for record in records:
            if record.time <= self.last_time:
                # Sent again because the dongle missed our answer.
                self.repeats += 1
                _LOGGER.debug("%s: repeat of %s, skipped", self._name, record)
                continue
            taken += 1
            self.kinds[record.kind] += 1
            self.last_time = record.time
            when = datetime.fromtimestamp(record.time, UTC)
            _LOGGER.debug(
                "%s: %s, %d s old: %s",
                self._name,
                when.isoformat(),
                int((received - when).total_seconds()),
                record,
            )
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
            if record.kind == "start":
                self.moving = True
                events.append(self._trip_event(EVENT_TRIP_STARTED, when, record))
            elif record.kind == "stop":
                self.moving = False
                events.append(self._trip_event(EVENT_TRIP_STOPPED, when, record))
            elif record.kind == "heartbeat":
                self.moving = False
            else:
                self.moving = True
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
        for event in events:
            for event_listener in list(self._event_listeners):
                event_listener(event)
        for update in list(self._update_listeners):
            update()
        return taken

    @staticmethod
    def _trip_event(event_type: str, when: datetime, record: Record) -> TripEvent:
        return TripEvent(event_type, when, record.latitude, record.longitude)

    async def async_save(self) -> None:
        """Write what's new now (the entry is unloading or reloading)."""
        if self._unsaved:
            await self._store.async_save(self._data_to_save())
            self._unsaved = False

    async def async_remove(self) -> None:
        """Forget the stored state (the entry was deleted)."""
        await self._store.async_remove()
