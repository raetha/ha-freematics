# Freematics for Home Assistant

A Home Assistant integration for Freematics ONE+ GPS trackers running [ESPHome for Freematics](https://github.com/raetha/esphome-freematics): each dongle posts compact batches of positions and trip events to a Home Assistant webhook, and the integration turns them into a device tracker and sensors. No Traccar server needed, and far less cellular data than ESPHome's native API.

Not released yet: it's being built and tested.

## Test builds

Add this repository to Home Assistant's Marketplace (HACS on Home Assistant 2026.10 and older) as a custom repository of type Integration, turn on pre-releases for Freematics (its ⋮ menu, or its **Pre-release** switch), and install the newest test build.
