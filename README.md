# Freematics for Home Assistant

A Home Assistant integration for Freematics ONE+ GPS dongles running [ESPHome for Freematics](https://github.com/raetha/esphome-freematics). Each dongle posts compact batches of its positions and trips to a Home Assistant webhook, and the integration turns them into:

- a device tracker, with an accuracy estimated from the satellite fix;
- speed, heading, altitude, battery voltage and temperature sensors, and satellites, HDOP, cellular signal and last report as diagnostics;
- a moving sensor, on from a trip's start to its stop, and a reporting sensor, off when the dongle has gone quiet for longer than it should (it says before sleeping when it will report next);
- a trip event entity (trip started, trip stopped) to automate on, the stop carrying the trip's distance, duration, top and average speed, which also show as last-trip sensors;
- an impact event entity, fired when the dongle's motion sensor measures a jolt beyond its threshold (4 g by default), with the peak and where it happened: an automation can tell the family or call for help.

No Traccar server is needed, and it uses little cellular data: a record is about 11 bytes (15 as the base64 text that goes over the air), sent in batches every 2 minutes and at once when a trip starts or stops. Home Assistant can't store back-dated positions, so records sent late (after a coverage gap) update the device to the newest one without a track history; for drive history and replay, run Traccar as well (the dongle can report to both).

Not released yet: it's being built and tested.

## Setup

1. Install the integration (below) and restart Home Assistant.
2. Settings → Devices & services → Add integration → Freematics, and name the dongle after its car. Home Assistant makes a webhook for it and shows its address: Home Assistant Cloud's when you subscribe, otherwise your Home Assistant's external HTTPS address (Settings → System → Network). The dongle reaches it from the internet, so nothing else at home needs opening. Reconfigure shows the address again.
3. In ESPHome Device Builder, add the address to Secrets under a name of its own for each dongle (such as `volvo_webhook_url`), set the device config's `ha_webhook_url: !secret volvo_webhook_url`, and install the dongle with [`examples/car-ha-integration.yaml`](https://github.com/raetha/esphome-freematics/blob/dev/examples/car-ha-integration.yaml) (or add `packages/uplink-ha-webhook.yaml` to the Traccar example to report to both).

The address is the dongle's only key: keep it private.

## Troubleshooting

Diagnostics (the device's ⋮ menu → Download diagnostics) are safe to post: they count the batches and records received, those missed or sent twice, and how late the newest one arrived, with the webhook ID redacted and no coordinates. For more, turn on debug logging (Settings → Devices & services → Freematics → ⋮ → Enable debug logging): each batch and every record in it is logged, coordinates included, so check a debug log before posting it.

## Test builds

Add this repository to Home Assistant's Marketplace (HACS on Home Assistant 2026.10 and older) as a custom repository of type Integration, turn on pre-releases for Freematics (its ⋮ menu, or its **Pre-release** switch), and install the newest test build.
