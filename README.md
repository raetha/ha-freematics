# Freematics for Home Assistant

A Home Assistant integration for Freematics ONE+ GPS dongles running [ESPHome for Freematics](https://github.com/raetha/esphome-freematics). Each dongle posts compact batches of its positions and trips to a Home Assistant webhook, and the integration turns them into:

- a device tracker, with an accuracy estimated from the satellite fix;
- speed, heading, altitude, battery voltage and temperature sensors, and satellites, HDOP, cellular signal and last report as diagnostics;
- a moving sensor, on from a trip's start to its stop; a live tracking sensor, connected while a trip's batches keep arriving (off when parked, and when a trip's reports stop: out of coverage or unplugged); and a next-report-due time: the dongle is overdue once it has passed with no newer last report (awake, it reports at least every 15 minutes; before sleeping it says when it will report next), for an automation that warns of a dongle gone quiet;
- the dongle's model and firmware version on its device, as the dongle reports them once per boot;
- a trip event entity (trip started, trip stopped) to automate on, the stop carrying the trip's distance, duration, top and average speed, which also show as last-trip sensors (a trip whose stop never arrives, because the dongle restarted on the way, ends at its last point with `stop_missed: true`);
- an impact event entity, fired when the dongle's motion sensor measures a jolt beyond its threshold (4 g by default), with the peak and where it happened: an automation can tell the family or call for help.

No Traccar server is needed, and it uses little cellular data: a record is about 11 bytes (15 as the base64 text that goes over the air), sent in batches every 2 minutes and at once when a trip starts or stops. Home Assistant can't store back-dated positions, so records sent late (after a coverage gap) update the device to the newest one without a track history; for drive history and replay, run Traccar as well (the dongle can report to both).

Not released yet: it's being built and tested.

## Setup

1. Install the integration (below) and restart Home Assistant.
2. Settings → Devices & services → Add integration → Freematics, and name the dongle after its car. Home Assistant makes a webhook for it and shows its address: Home Assistant Cloud's when you subscribe, otherwise your Home Assistant's external HTTPS address (Settings → System → Network). The dongle reaches it from the internet, so nothing else at home needs opening. Reconfigure shows the address again.
3. In ESPHome Device Builder, add the address to Secrets under a name of its own for each dongle (such as `volvo_webhook_url`), set the device config's `ha_webhook_url: !secret volvo_webhook_url`, and install the dongle with [`examples/car-ha-integration.yaml`](https://github.com/raetha/esphome-freematics/blob/dev/examples/car-ha-integration.yaml) (or add `packages/uplink-ha-webhook.yaml` to the Traccar example to report to both).

The address is the dongle's only key: keep it private.

For a street address like Traccar's, add the [places](https://github.com/custom-components/places) integration (from HACS) with the dongle's device tracker: it looks positions up in OpenStreetMap, with no key. Home Assistant has no address lookup of its own.

## Example: a dongle that stopped reporting

Next report due is when a quiet dongle should have reported again: 45 minutes after an awake dongle's last report, or a little after the time a sleeping one said it would wake. Each report moves it later, so an automation that fires at that time only fires when the dongle missed it: unplugged, out of coverage for a long while, or broken. Replace `volvo` with the dongle's name and the notify action with yours:

```yaml
alias: Volvo's tracker stopped reporting
triggers:
  - trigger: time
    at: sensor.volvo_next_report_due
conditions:
  # Fires only if no report moved the time on in the meantime.
  - condition: template
    value_template: "{{ now() >= states('sensor.volvo_next_report_due') | as_datetime }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Volvo tracker
      message: >-
        No report since
        {{ as_timestamp(states('sensor.volvo_last_report')) | timestamp_custom('%-I:%M %p on %b %-d') }}.
mode: single
```

A car out of coverage for a long drive fires it too; the dongle keeps what it records and sends it all once back in coverage.

## Troubleshooting

Diagnostics (the device's ⋮ menu → Download diagnostics) are safe to post: they count the batches and records received, those missed or sent twice, and how late the newest one arrived, with the webhook ID redacted and no coordinates. For more, turn on debug logging (Settings → Devices & services → Freematics → ⋮ → Enable debug logging): each batch and every record in it is logged, coordinates included, so check a debug log before posting it.

## Test builds

Add this repository to Home Assistant's Marketplace (HACS on Home Assistant 2026.10 and older) as a custom repository of type Integration, turn on pre-releases for Freematics (its ⋮ menu, or its **Pre-release** switch), and install the newest test build.
