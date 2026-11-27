# Audits

Quality, security and housekeeping reviews. Repeat when the owner asks for a full review, and before every release; record each one below, newest first.

## Checklist for a full review

1. **Open pull requests**, Dependabot's especially (`gh api "repos/raetha/ha-freematics/pulls?state=open"`; sessions have the REST API, not GraphQL): read each diff, check its CI, check action pins against their tags (`git ls-remote https://github.com/<owner>/<action> refs/tags/<tag>`).
2. **Pins:** pytest-homeassistant-custom-component (its newest release pins the Home Assistant version the tests run), ruff, mypy (the release Home Assistant core pins), the actions; hassfest's `master` pin moves only when its `hassfest/` folder changed. Check PyPI directly (`https://pypi.org/pypi/<package>/json`): `pip index` on the system Python hides releases that need Python 3.14.
3. **Security:** sessions can't read code scanning, Dependabot or secret scanning alerts: ask the owner. Run CodeQL locally (the `python-security-and-quality` and `actions-security-and-quality` suites) over a copy of the tracked files. The webhook ID never reaches a log, diagnostics redact it and carry no coordinates, and the webhook answers with an empty 200.
4. **Checks:** everything in `CLAUDE.md` → "Validate", with 100% coverage.
5. **The contract with the dongle:** `compact.py` here and `tests/compact.py` in raetha/esphome-freematics differ only in their docstrings.
6. **Entity model:** against Home Assistant's current developer guidance (state and attributes, naming, categories); every name through `strings.json`, identical to `translations/en.json`.
7. **Upstream:** Home Assistant releases since the last review (webhook, cloud, device_tracker, event platform changes), and the tests against the newest beta where the test harness allows it.
8. **Docs:** README and `docs/development.md` match the code (intervals, entity names, the automation example); the `[Unreleased]` section reads as release notes.
9. **Leftovers:** compatibility kept for test builds before the first release, settings for rules nobody selected, comments that tell history.
10. **Record it:** a dated section below, and changelog lines for anything users notice.

## 2026-11-27: full review (before an alpha release)

The whole integration on `dev` (0.1.0, DRAFT), after a week on the owner's dongle in the Volvo.

- **Pull requests and pins:** none open. pytest-homeassistant-custom-component 0.13.375 (Home Assistant 2026.10.4) is its newest release; mypy 2.4.1 is core's; ruff 0.17.5 → 0.17.6 (patch, taken). Actions at their latest tags, pins match; hassfest's folder hasn't changed since its pin.
- **Security:** CodeQL 2.27.6 (Python and Actions security-and-quality suites): one unused import in a test (removed), nothing else. Workflows: `contents: read` at the top, `persist-credentials: false` on every checkout that doesn't push, actions pinned to commit SHAs, one `CI passed` gate. The webhook ID appears in no log; diagnostics redact it.
- **Correctness:** ruff, mypy, 64 tests at 100% coverage, the markdown and release checks pass. `compact.py` matches the dongle repo's copy except for its docstring.
- **Upstream:** Home Assistant 2026.12.0b2 can't run the tests yet: the test harness pins 2026.10.4 and fails to import under the beta (an `httpx` alias clash in the harness, not this code). The only warnings in the suite come from Home Assistant's own `http` component.
- **Fixed:** the README said batches go every 2 minutes (the dongle's default is 5, `ha_send_interval`); the lint settings ignored unused imports and import order in the tests with a reason copied from another project, and listed ignores for rules never selected (now just the rules used; two import orders fixed); a trip restored from storage without its end time was handled for test builds from before 2026-11-23 (removed with its test: no compatibility before the first release).
- **Checked and fine:** entities follow Home Assistant's model (values that change on their own are entities, diagnostics categorised, names from translations, the tracker named after the device); `strings.json` and `translations/en.json` are identical; the quality scale isn't tracked (no `quality_scale.yaml`), which a HACS integration doesn't need.
