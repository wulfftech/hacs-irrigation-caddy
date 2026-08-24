---
name: hacs-irrigation-caddy
description: Work on the hacs-irrigation-caddy HA custom integration.
---

# HACS Irrigation Caddy Skill

Guide for developing, testing, and releasing the Irrigation Caddy Home Assistant custom integration (KGControls Irrigation Caddy S1 / ICEthS1 ethernet sprinkler controller) in `/mnt/d/Code/hacs-irrigation-caddy`.

## When to Use

- Adding/changing entities, services, config flow, or the coordinator
- Debugging the reverse-engineered device HTTP API or firmware quirks
- Version bumps / releases validated by HACS action + hassfest CI

## Integration Architecture

Standard HA config-entry integration (`iot_class: local_polling`, no deps/requirements):

- **Config flow** (`config_flow.py`): user enters host/port; connection tested via `GET /status.json`. Unique ID is `host:port`. Options flow exposes zone run duration. UDP discovery helper exists (broadcast port 30303).
- **Coordinator** (`coordinator.py`): `DataUpdateCoordinator[IrrigationCaddyData]`, 30s polling; gathers 4 GETs (`status.json`, `zoneNames.json`, `programData.json`, `settingsVars.json`) with `return_exceptions=True` — only `status.json` failure raises `UpdateFailed`. Owns all control POSTs (run program/zone, stop, save schedule). See `references/api-and-quirks.md`.
- **Entities** (`switch.py`, `sensor.py`, `binary_sensor.py`, `number.py`): all `CoordinatorEntity`; unique IDs keyed on `entry.entry_id`.
- **Devices** (`device_info.py`): three sub-devices — System, Zones, Programs — under one entry (`via_device` hub pattern).
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
- Zone durations capped at firmware `maxZRunTime` (default 40 min); service durations max 720 min.
- Config entry reload on options change (`_async_update_listener`) — entity values come from `entry.options`, not stored state.
- Keep `strings.json` and `translations/en.json` in sync or hassfest fails.
