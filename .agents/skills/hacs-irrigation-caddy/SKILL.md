---
name: hacs-irrigation-caddy
description: Work on the hacs-irrigation-caddy HA custom integration.
---

# HACS Irrigation Caddy Skill

Guide for developing, testing, and releasing the Irrigation Caddy Home Assistant custom integration (KGControls Irrigation Caddy S1 / ICEthS1 ethernet sprinkler controller) in `D:\Code\hacs-irrigation-caddy`.

## When to Use

- Adding/changing entities, services, config flow, or the coordinator
- Debugging the reverse-engineered device HTTP API or firmware quirks
- Version bumps / releases validated by HACS action + hassfest CI

## Integration Architecture

Standard HA config-entry integration (`iot_class: local_polling`, no deps/requirements):

- **Config flow** (`config_flow.py`): user enters host/port; connection tested via `GET /status.json`. Unique ID is `host:port`. The options flow is a menu: zone selection, Run Now durations, plus a full schedule editor per program (days / 5 start times / per-zone run times) that POSTs straight to the device. Every zone-facing form lists only the selected zones. No UDP discovery — the device supports it (broadcast port 30303) but nothing wires it up.
- **Coordinator** (`coordinator.py`): `DataUpdateCoordinator[IrrigationCaddyData]`, 30s polling; gathers 5 GETs (`status.json`, `zoneNames.json`, `programData.json`, `settingsVars.json`, `js/indexVarsDyn.js?program=4`) with `return_exceptions=True` — only `status.json` failure raises `UpdateFailed`. Owns all control POSTs (run program/zone, stop, save schedule). See `references/api-and-quirks.md`.
- **Entities** (`switch.py`, `button.py`, `sensor.py`, `binary_sensor.py`, `number.py`): all `CoordinatorEntity`; unique IDs keyed on `entry.entry_id`. Zone switches and zone duration numbers are built from `coordinator.enabled_zones`, not `MAX_ZONES`. Zone switches read their ON state from `status.json` (`running` + `zoneNumber`) with a bounded optimistic hold; turning one off posts `stop=active`.
- **Devices** (`device_info.py`): three sub-devices — System, Run Now, Programs — under one entry (`via_device` hub pattern). The Run Now device keeps the legacy `_zones` identifier suffix so the rename preserves entity history.
- **Options** (`options.py`): Run Now zone durations live in `entry.options`, because the device cannot store a Run Now duration without also starting the run. So does the set of visible zones — the firmware reports nine outputs regardless of what is wired up. `derive_enabled_zones()` seeds that set on first setup from program durations plus non-placeholder zone names.
- **Service**: `irrigation_caddy.set_program` registered in `__init__.py::async_setup` (partial updates preserved from device state).

## Commands

```bash
# Lint/type-check locally (no repo lint config — use HA's tooling against the component dir)
python -m compileall custom_components/irrigation_caddy

# Validation done by CI (.github/workflows/validate.yml):
#   - hacs/action@main (category: integration)
#   - home-assistant/actions/hassfest@master
# Reproduce hassfest locally:
docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest:latest --validation integration /github/workspace/custom_components/irrigation_caddy

# Manual test: copy custom_components/irrigation_caddy into a dev HA instance and restart.
```

There are **no tests, ruff config, or pre-commit hooks** in this repo yet.

## Key Files

| File | Role |
|---|---|
| `custom_components/irrigation_caddy/manifest.json` | Domain, version (bump here), codeowner |
| `custom_components/irrigation_caddy/coordinator.py` | All API endpoints, payloads, quirks — read before touching API code |
| `custom_components/irrigation_caddy/const.py` | Endpoints, limits (MAX_ZONES=9, MAX_PROGRAMS=3), defaults |
| `custom_components/irrigation_caddy/__init__.py` | Setup/unload, `set_program` service schema |
| `strings.json` + `translations/en.json` | Config-flow/service strings (keep in sync) |
| `services.yaml` | Service UI definitions |
| `hacs.json` | HACS settings (min HA 2023.1.0, render_readme) |

## Release Process

1. Make changes on a branch off `main` (one change per PR).
2. Bump `version` in `custom_components/irrigation_caddy/manifest.json` per SemVer: patch = bug fix, minor = new entity/feature, major = breaking.
3. Ensure `strings.json`/`translations/en.json` match any new UI text.
4. Push → CI runs HACS validation + hassfest.
5. Tag the release on GitHub so HACS picks it up.

## Pitfalls

See `references/api-and-quirks.md` for full details. Top items:

- The device HTTP API is undocumented and firmware-version dependent; payloads were verified only against ICEthS1-2.0.x. Never "clean up" payload fields without a live device check.
- `stopSprinklers.htm`: `stop=active` halts watering but keeps system enabled; `stop=off` also disables the system (allowRun=false). Don't mix them up.
- Program save form quirks: unchecked days must be omitted, slot 0 start time has no enable checkbox (always armed when time set, and `isOn=false` in programData.json must be normalized), unset slots post empty `startTime{i}`, entry 10 of `zoneDuration` is a totals row that must not be echoed back, `everyNDays` must be read back from `js/indexVarsDyn.js` and echoed to avoid wiping interval schedules.
- Run-zone uses `pgmNum=4` ("Run Now") via `/program.htm`, not a dedicated endpoint; device reports that run as progNumber=4.
- `js/indexVarsDyn.js` MUST be fetched with `?program=N`; a bare fetch returns whichever program the device last had selected. See quirk 6.
- Zone durations capped at firmware `maxZRunTime` (default 40 min); service durations max 720 min.
- Options changes do NOT reload the entry, with one exception: `_async_update_listener` compares the selected zones against `coordinator.enabled_zones` and reloads only when they differ (which entities exist is fixed at platform setup). Everything else just calls `coordinator.async_update_listeners()` — entity values read `entry.options` live, and reloading made every entity flicker unavailable on each duration change.
- Deselecting a zone removes its registry entries (`__init__._purge_hidden_zone_entities`) so it disappears instead of lingering as "restored". The program editor still echoes hidden zones' durations back to the device unchanged — hiding a zone must never rewrite a schedule.
- Keep `strings.json` and `translations/en.json` in sync or hassfest fails.
