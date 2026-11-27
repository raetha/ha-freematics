# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

First release: Freematics ONE+ GPS dongles running ESPHome for Freematics, in Home Assistant through a webhook.

### Added

- Each dongle is added with a name and gets its own webhook: Home Assistant Cloud's address when you subscribe, otherwise Home Assistant's external HTTPS address; Reconfigure shows it again.
- A device tracker per dongle, with an accuracy estimated from the fix's HDOP, and speed, heading, altitude, battery voltage, satellites, HDOP and last report sensors.
- A moving sensor (on from a trip's start to its stop) and a trip event entity (trip started, trip stopped, with the time the dongle recorded it), so late reports still fire.
- Each trip added up from all its points when it stops: distance, duration, top and average speed, on the trip-stopped event and as last-trip sensors (kept across restarts, including a trip under way). A trip whose stop never arrives (the dongle restarted on the way, for one) ends at its last record when the dongle next reports parked or starts another trip; its trip-stopped event says so with `stop_missed: true`.
- An impact event entity, fired with the peak (in g) and position when the dongle reports an impact, and temperature and cellular signal sensors from the values the dongle sends with trip starts, stops and heartbeats.
- A live tracking sensor (connectivity, diagnostic), connected while a trip streams: on a trip, with a batch at least every 10 minutes (the dongle sends one every 5). A next report due sensor (a time): 45 minutes after an awake dongle's last report, or 15 minutes past the time it said, before sleeping, it would report again; once it has passed with no newer last report, the dongle is overdue (out of coverage, unplugged or broken). Neither costs the dongle anything. The README has an example automation for a dongle that stopped reporting.
- A trip's start is dated when the car started moving, which the dongle can only work out once its GPS has a fix: a start older than records already shown is still taken (once), and a start sent without a position begins at where the car was parked.
- A trip that ended while the dongle had no power (the car parked, then the dongle unplugged or the power cut) gets its real stop, which the dongle reports once powered again, dated at the trip's last fix at moving speed, even though that's older than the slow fixes it sent while parking.
- The dongle's model (ONE+ Model B) and firmware version on its device, as it reports them once per boot; ONE+ until it does.
- Batches are compact (about 11 bytes a record, with extras in tagged fields that older versions skip, sent as base64 text so they pass through Home Assistant Cloud) and answered with an empty 200, keeping the dongle's cellular data low; a batch sent again because its answer was lost is taken once.
- The last state survives restarts. Diagnostics are safe to post (the webhook ID is redacted and no coordinates are included) and show the batches and records received, batches missed, repeats, and how late the newest batch arrived; debug logging logs every batch and record.

[Unreleased]: https://github.com/raetha/ha-freematics/commits/dev

### Internal

- The README suggests the places integration for street addresses.
- The license names the copyright holder as Elias Hunt (raetha).
- A review checklist and log (`docs/audits.md`).
- Lint settings trimmed to the rules the project uses (unused imports and import order are checked in the tests too); ruff 0.17.6.
