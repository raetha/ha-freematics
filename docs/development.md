# Development

## Layout

| Path | What |
| --- | --- |
| `custom_components/freematics/` | The integration: `compact.py` (the batch format), `device.py` (one dongle's state, restored across restarts), `config_flow.py` (name a dongle, get its webhook address), the entity platforms |
| `tests/` | pytest with Home Assistant's test harness (100% line coverage); `tests/encode.py` builds test batches |
| `scripts/release.py` | Changelog checks, test-build versions, release notes and the release zip, for CI |

## How a batch flows

The dongle posts `application/octet-stream` to `/api/webhook/<id>` (or Home Assistant Cloud's cloudhook address for it). `__init__.py` reads at most 8 KB, decodes it (`compact.py`, documented at the top of that file and of the encoder, `components/traccar_uplink/compact.h` in esphome-freematics), hands the records to the dongle's `FreematicsDevice`, and answers an empty 200, which the dongle takes as the batch's acknowledgement (400 for a batch it can't read, so the dongle's log shows something's wrong). The device takes records newer than the last it took, in order, updates its state, fires trip events, tells its entities to write their states once, and saves its state 30 seconds later (at once on unload).

## Branches and releases

`main` holds releases only: one squash-merged pull request per release from `dev`. Work lands on `dev`; experiments on `try/<topic>` branches. CI (`.github/workflows/build.yml`) runs on every push and pull request: hassfest and HACS validation, the changelog and Markdown checks, ruff, mypy and the tests. A push to `dev` that changes what ships publishes a test build as a GitHub pre-release (`<version>-dev.<n>`, its zip's manifest stamped with that version); a push to `main` publishes the release when its version has no tag yet (not while `DRAFT` exists) and resets `dev` to `main`.

Repository settings for the owner: a ruleset on `main` (no deletion or force pushes, pull requests, squash only, the `CI passed` check required), squash merging only with head branches deleted automatically, a classic protection rule on `dev` that allows force pushes (for the reset) and forbids deletion.
