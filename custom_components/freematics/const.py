"""Constants for the Freematics integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "freematics"

CONF_WEBHOOK_ID: Final = "webhook_id"
CONF_CLOUDHOOK: Final = "cloudhook"

# A dongle's largest batch is about 1.4 KB as base64; anything far bigger isn't one.
MAX_BODY: Final = 8192

# HDOP times the error of one satellite range (about 5 m for a consumer
# receiver): the usual estimate of horizontal accuracy.
METRES_PER_HDOP: Final = 5.0

EVENT_TRIP_STARTED: Final = "trip_started"
EVENT_TRIP_STOPPED: Final = "trip_stopped"
EVENT_IMPACT: Final = "impact"

# A dongle that's awake reports at least every heartbeat (15 minutes by
# default), so a longer silence means it's out of coverage or off. Before it
# sleeps it says when it reports next; it gets this much longer than that.
AWAKE_SILENCE: Final = 45 * 60  # seconds
SLEEP_GRACE: Final = 15 * 60  # seconds
