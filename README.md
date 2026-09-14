# Irrigation Caddy — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **KGControls Irrigation Caddy S1** (ICEthS1) ethernet-connected sprinkler controller.

## Features

- **Zone switches** — one per zone on a **Run Now** device, mirroring the controller's own
  Run Now page. Turn one on to water that zone; it stays on for the whole run and turning
  it off stops it, without disabling the controller
- **Zone selection** — the controller always reports nine outputs; pick the ones that are
  actually wired up and the rest get no entities at all
- **Per-zone run durations** — a 1–30 minute slider per zone, plus a default for zones you
  haven't set
- **Schedule editor** — edit each program's days, start times and per-zone run times from the
  integration's **Configure** dialog
- **Program buttons** — momentary "run program now" pushbuttons for each of the 3 programs
- **Stop Watering button** — halts whatever is watering without disabling the system
- **Program enable switches** — arm/disarm any program's schedule (real persisted device state)
- **Program state sensors** — per-program `running` / `enabled` / `disabled`, with the full
  schedule (days, start times, per-zone durations) exposed as attributes
- **Sensors** — active zone name, active program number, remaining watering time
- **Binary sensors** — currently watering, controller enabled/disabled, rain sensor
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

## Configure

Click **Configure** on the integration card. You get a menu:

- **Zones** — which of the controller's nine outputs appear in Home Assistant
- **Run Now** — the run time for each selected zone, plus the fallback used by any zone
  that hasn't been given one. Sliders, 1–30 minutes (or the controller's `maxZRunTime`
  if that is lower)
- **Edit Program 1 / 2 / 3** — the full schedule editor (see below)

Zones you don't select get no switch, no duration slider, and no field in the program
editors — so to add a zone to a program, select it under **Zones** first. Deselecting a
zone never rewrites a saved schedule: the controller keeps whatever duration it already
had for that zone.

## Entities Created

For a controller named "Irrigation Caddy (icaddy.local)":

| Entity | Type | Description |
|---|---|---|
| `switch.run_now_<zone name>` | Switch | One per selected zone. Run that zone now; on while it waters, off to stop it |
| `number.run_now_<zone name>_duration` | Number | One per selected zone. How long it runs when switched on (1–30 min slider) |
| `number.run_now_default_run_duration` | Number | Fallback duration for zones with no duration of their own |
| `button.run_program_N_now` × 3 | Button | Trigger that program's schedule immediately |
| `button.stop_watering` | Button | Stop the active zone (system stays enabled) |
| `button.repeat_run_now` | Button | Replay the last manual watering's zone durations |
| `switch.system` | Switch | Master ON/OFF (disables all watering when off) |
| `switch.program_N_enabled` × 3 | Switch | Arm/disarm each program's schedule |
| `sensor.program_N_state` × 3 | Sensor | `running` / `enabled` / `disabled` + schedule attributes |
| `sensor.run_now_state` | Sensor | `running` while a manual run is active + stored Run Now durations |
| `sensor.active_zone` | Sensor | Name of currently active zone |
| `sensor.active_program` | Sensor | Active program number (0 = none, 4 = manual run) |
| `sensor.zone_time_remaining` / `_program_time_remaining` | Sensor | Seconds left in current run |
| `binary_sensor.watering` | Binary Sensor | True when any zone is running |
| `binary_sensor.system_enabled` | Binary Sensor | True when controller is enabled |
| `binary_sensor.rain_sensor_*` | Binary Sensor | Rain sensor wet/enabled state |

> **Upgrading to v1.5.0.** On first load the integration picks which zones to show:
> any zone watered by a program, plus any zone you've renamed on the controller. Zones
> still carrying the firmware's placeholder name (`Zone 6`, `Zone 7`…) and used by no
> program are hidden, and their switches and duration entities are removed from the
> registry. Change the selection under **Configure → Zones** at any time — saving reloads
> the integration. Run Now durations are now 1–30 minute sliders; a longer value set
> previously is clamped to 30.
>
> **Upgrading to v1.4.0.** The "Zones" device is now called **Run Now**, matching the
> controller's own web UI. The `button.run_zone_N_now` buttons are gone — use the zone
> switches instead, and update any automation that pressed one. The old
> `number.zone_run_duration` keeps its entity id and history — it is now labelled
> *Default Run Duration*, and the new per-zone durations override it.
> HA will show the removed buttons as restored/unavailable — delete them from
> Settings → Devices & Services → Entities.
>
> Upgrading from ≤ v1.1.x as well: the original zone and program-run switches were replaced
> by buttons in v1.2.0, so those stale entities may also need deleting.

## Editing Schedules

Two routes, both writing straight to the controller.

### From the UI

**Settings → Devices & Services → Irrigation Caddy → Configure → Edit Program N.**
The form is pre-filled from the device and shows:

- **Program enabled** — arm or disarm the whole program
- **Days to run** — checkboxes, Monday through Sunday
- **Start time 1–5** — leave a slot blank to clear it
- **Zone run time** — one box per selected zone; minutes, 0 to skip that zone. Capped at
  the controller's own zone limit (`maxZRunTime`, 40 minutes by default) — schedules are
  not held to the 30-minute Run Now slider limit

Submitting sends the whole schedule as one POST, which is exactly how the controller's
own web form behaves — so a partial edit can't leave it in a half-saved state.

### From an automation (`set_program` service)

The same edits are available as `irrigation_caddy.set_program`. Any field
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
    # Runs for whatever number.side_garden_beds_duration is set to
    - service: switch.turn_on
      target:
        entity_id: switch.side_garden_beds
```

```yaml
# Cut a run short if rain is forecast
automation:
  trigger:
    platform: state
    entity_id: binary_sensor.watering
    to: "on"
  condition: "{{ state_attr('weather.home', 'forecast')[0].precipitation > 5 }}"
  action:
    - service: button.press
      target:
        entity_id: button.stop_watering
```

## API Notes

The Irrigation Caddy uses an undocumented HTTP/JSON API. All write payloads in
this integration were captured from the device's own web UI (firmware
ICEthS1-2.0.197) and verified by round-trip testing against a live device:

- `GET /status.json` — zone and program status
- `GET /zoneNames.json` — zone names
- `GET /programData.json` — schedule data
- `GET /settingsVars.json` — firmware version, max zone run time
- `GET /js/indexVarsDyn.js?program=N` — per-program view variables. The `?program=`
  parameter is mandatory: without it the device returns whichever program it last had
  selected. `program=4` is the Run Now pseudo-program
- `POST /runProgram.htm` — run a program now (`pgmNum`, `doProgram=1`, `runNow=true`)
- `POST /program.htm` — save program schedule / run-now zone durations
- `POST /stopSprinklers.htm` — stop watering (`stop=active`) or disable system (`stop=off`)
- `POST /runSprinklers.htm` — re-enable the system (`run=run`)

The controller also answers UDP discovery on port 30303 (broadcast
`"Discovery: Who is out there?"`), though this integration doesn't use it — enter the
host manually.

## Contributing

PRs welcome! The API has quirks across firmware versions — if your device behaves differently, please open an issue with your firmware version and the raw JSON from `/status.json`.

## License

MIT
