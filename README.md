# Irrigation Caddy — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **KGControls Irrigation Caddy S1** (ICEthS1) ethernet-connected sprinkler controller.

## Features

- **Zone switches** — turn individual zones on/off directly from HA (runs for a configurable duration)
- **Program switches** — trigger any of the 3 scheduled programs on demand
- **Sensors** — active zone name, active program number, remaining watering time
- **Binary sensors** — currently watering, controller enabled/disabled
- **Number entity** — set the default zone run duration (1–120 minutes) from the HA UI
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

- **Zone run duration** — how long a zone runs when you flip its switch on (default 10 minutes)

## Entities Created

For a controller named "Irrigation Caddy (icaddy.local)":

| Entity | Type | Description |
|---|---|---|
| `switch.zone_1` … `switch.zone_9` | Switch | Run/stop individual zones |
| `switch.program_1` … `switch.program_3` | Switch | Run/stop programs |
| `sensor.active_zone` | Sensor | Name of currently active zone |
| `sensor.active_program` | Sensor | Active program number (0 = none) |
| `sensor.remaining_time` | Sensor | Seconds remaining in current run |
| `binary_sensor.watering` | Binary Sensor | True when any zone is running |
| `binary_sensor.enabled` | Binary Sensor | True when controller is enabled |
| `number.zone_run_duration` | Number | Default zone run duration (minutes) |

## Automations Example

```yaml
# Water the veggie garden for 15 min every morning
automation:
  trigger:
    platform: time
    at: "06:30:00"
  action:
    - service: number.set_value
      target:
        entity_id: number.irrigation_caddy_zone_run_duration
      data:
        value: 15
    - service: switch.turn_on
      target:
        entity_id: switch.irrigation_caddy_veggie_garden
```

## API Notes

The Irrigation Caddy uses an undocumented HTTP/JSON API (reverse-engineered by the community):

- `GET /status.json` — zone and program status
- `GET /zoneNames.json` — zone names
- `GET /programData.json` — schedule data
- `POST /runProgram.htm` — run a program now
- `POST /stopSprinklers.htm` — stop all activity
- `POST /runZ.htm` — run a single zone

UDP discovery on port 30303: broadcast `"Discovery: Who is out there?"` to find devices.

## Contributing

PRs welcome! The API has quirks across firmware versions — if your device behaves differently, please open an issue with your firmware version and the raw JSON from `/status.json`.

## License

MIT
