# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

First release: Freematics ONE+ GPS dongles running ESPHome for Freematics, in Home Assistant through a webhook.

### Added

- Each dongle is added with a name and gets its own webhook: Home Assistant Cloud's address when you subscribe, otherwise Home Assistant's external HTTPS address; Reconfigure shows it again.
- A device tracker per dongle, with an accuracy estimated from the fix's HDOP, and speed, heading, altitude, battery voltage, satellites, HDOP and last report sensors.
- A moving sensor (on from a trip's start to its stop) and a trip event entity (trip started, trip stopped, with the time the dongle recorded it), so late reports still fire.
- Each trip added up from all its points when it stops: distance, duration, top and average speed, on the trip-stopped event and as last-trip sensors (kept across restarts, including a trip under way).
- An impact event entity, fired with the peak (in g) and position when the dongle reports an impact, and temperature and cellular signal sensors from the values the dongle sends with trip starts, stops and heartbeats.
- A reporting sensor (connectivity, diagnostic): off once the dongle has been silent for 45 minutes while awake, or 15 minutes past the time it said, before sleeping, it would report again. It costs the dongle nothing.
- Batches are compact (about 11 bytes a record, with extras in tagged fields that older versions skip, sent as base64 text so they pass through Home Assistant Cloud) and answered with an empty 200, keeping the dongle's cellular data low; a batch sent again because its answer was lost is taken once.
- The last state survives restarts. Diagnostics are safe to post (the webhook ID is redacted and no coordinates are included) and show the batches and records received, batches missed, repeats, and how late the newest batch arrived; debug logging logs every batch and record.

[Unreleased]: https://github.com/raetha/ha-freematics/commits/dev

### Internal

- The license names the copyright holder as Elias Hunt (raetha).
