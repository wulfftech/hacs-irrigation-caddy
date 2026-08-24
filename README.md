# Irrigation Caddy — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **KGControls Irrigation Caddy S1** (ICEthS1) ethernet-connected sprinkler controller.

## Features

- **Program buttons** — momentary "run program now" pushbuttons for each of the 3 programs
- **Zone buttons** — "Run Zone N Now" buttons; each runs for the configurable zone run duration
- **Stop Watering button** — halts the current zone without disabling the system
- **Program enable switches** — arm/disarm any program's schedule (real persisted device state)
- **Program state sensors** — per-program `running` / `enabled` / `disabled`, with the full
  schedule (days, start times, per-zone durations) exposed as attributes
- **Sensors** — active zone name, active program number, remaining watering time
- **Binary sensors** — currently watering, controller enabled/disabled, rain sensor
- **Number entity** — set the default zone run duration from the HA UI
- **Config flow** — set up via the HA UI, no YAML required
- Local polling every 30 seconds — no cloud dependency

## Supported Hardware

| Model | Zones | Tested |
|---|---|---|
| ICEthS1 | Up to 9 | Yes |

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/wulfftech/hacs-irrigation-caddy` as an **Integration**
3. Search for "Irrigation Caddy" and install
4. Restart Home Assistant

### Manual

Copy `custom_components/irrigation_caddy/` into your HA `custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Irrigation Caddy**
3. Enter your controller's hostname or IP address (e.g. `icaddy.local` or `192.168.1.x`)
4. Click **Submit**

## Options

After setup, click **Configure** on the integration card to adjust:

- **Zone run duration** — how long a zone runs when you press its run button (default 10 minutes)

## Entities Created

For a controller named "Irrigation Caddy (icaddy.local)":

| Entity | Type | Description |
|---|---|---|
| `button.run_zone_N_now` × 9 | Button | Run that zone now for the configured duration |
| `button.run_program_N_now` × 3 | Button | Trigger that program's schedule immediately |
| `button.stop_watering` | Button | Stop the active zone (system stays enabled) |
| `switch.system` | Switch | Master ON/OFF (disables all watering when off) |
| `switch.program_N_enabled` × 3 | Switch | Arm/disarm each program's schedule |
| `sensor.program_N_state` × 3 | Sensor | `running` / `enabled` / `disabled` + schedule attributes |
| `sensor.active_zone` | Sensor | Name of currently active zone |
| `sensor.active_program` | Sensor | Active program number (0 = none, 4 = manual run) |
| `sensor.zone_time_remaining` / `_program_time_remaining` | Sensor | Seconds left in current run |
| `binary_sensor.watering` | Binary Sensor | True when any zone is running |
| `binary_sensor.system_enabled` | Binary Sensor | True when controller is enabled |
| `binary_sensor.rain_sensor_*` | Binary Sensor | Rain sensor wet/enabled state |
| `number.zone_run_duration` | Number | Default zone run duration (minutes) |

> Upgrading from ≤ v1.1.x: the old zone and program-run **switches** are gone
> (replaced by buttons). HA will show them as restored/unavailable — delete
> them from Settings → Devices & Services → Entities.

## Editing Schedules (`set_program` service)

Schedules are edited with the `irrigation_caddy.set_program` service. Any field
you omit keeps its current value on the device, so you can change just days,
just times, or just durations:

```yaml
# Example: Program 2 waters Mon/Wed/Fri at 06:00 and 18:30, zone 1 for 10 min
service: irrigation_caddy.set_program
data:
  program: 2
  enabled: true
  days: ["mon", "wed", "fri"]
  start_times: ["06:00", "18:30"]   # up to 5, 24-hour HH:MM; listed = armed
  zone_durations: {"1": 10}         # zones not listed are set to 0 (skipped)
```

Fields:

| Field | Type | Notes |
|---|---|---|
| `program` | int 1–3 | required |
| `enabled` | bool | arm/disarm the program |
| `days` | list | subset of mon/tue/wed/thu/fri/sat/sun |
| `start_times` | list of HH:MM | max 5; every listed time is armed; slots beyond the list are cleared |
| `zone_durations` | map zone→minutes | zones not listed are skipped |

The current schedule is always visible as attributes on `sensor.program_N_state`.

## Automations Example

```yaml
# Extra evening watering for the veggie garden in summer
automation:
  trigger:
    platform: time
    at: "18:30:00"
  action:
    - service: button.press
      target:
        entity_id: button.irrigation_caddy_run_zone_3_now
```

## API Notes

The Irrigation Caddy uses an undocumented HTTP/JSON API. All write payloads in
this integration were captured from the device's own web UI (firmware
ICEthS1-2.0.197) and verified by round-trip testing against a live device:

- `GET /status.json` — zone and program status
- `GET /zoneNames.json` — zone names
- `GET /programData.json` — schedule data
- `GET /settingsVars.json` — firmware version, max zone run time
- `POST /runProgram.htm` — run a program now (`pgmNum`, `doProgram=1`, `runNow=true`)
- `POST /program.htm` — save program schedule / run-now zone durations
- `POST /stopSprinklers.htm` — stop watering (`stop=active`) or disable system (`stop=off`)
- `POST /runSprinklers.htm` — re-enable the system (`run=run`)

UDP discovery on port 30303: broadcast `"Discovery: Who is out there?"` to find devices.

## Contributing

PRs welcome! The API has quirks across firmware versions — if your device behaves differently, please open an issue with your firmware version and the raw JSON from `/status.json`.

## License

MIT
