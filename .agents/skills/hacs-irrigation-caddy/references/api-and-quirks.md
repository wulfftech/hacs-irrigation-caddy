# Irrigation Caddy Device API — Endpoints, Payloads, Firmware Quirks

All payloads verified against live firmware **ICEthS1-2.0.197** by capturing the device web UI's own POSTs (`js/program.js`, `js/status.js`) and round-trip testing. The API is undocumented and community reverse-engineered; behaviour may differ across firmware versions — always confirm against a real device before changing payloads.

## Read endpoints (polled every 30s by coordinator)

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /status.json` | object | `zoneNumber` (0=none), `progNumber` (0=none; 4 = Run Now), `allowRun`, `running`, `useSensor1`, `isRaining`, `zoneSecLeft`, `progSecLeft`, `maxZones`, `zoneLog`, per-zone `zones: [{hr,min,isRun}]` |
| `GET /zoneNames.json` | bare array | Up to 9 names |
| `GET /programData.json` | bare array of programs | `daysToRun`, `startTimes: [{hr,min,isOn}]`, `zoneDuration` (10 entries — entry 10 is a totals row), `allowRun` |
| `GET /settingsVars.json` | object | `icVersion` (firmware), `maxZRunTime` (minutes cap) |
| `GET /js/indexVarsDyn.js?program=N` | JS text | Regex `everyNDays\s*:\s*(\d+)` to recover interval schedules before saving |

Add cache-buster `?rand=<unix time>` to GETs.

## Write endpoints (POST, form-urlencoded)

- `POST /runProgram.htm` — Run Now for saved program: `pgmNum`, `doProgram=1`, `runNow=true`, `time=<ms epoch>`.
- `POST /program.htm` — dual purpose:
  - **Save schedule**: full form payload (see quirks below). `doProgram=1` required or POST is ignored.
  - **Run single zone** (`async_run_zone`): `pgmNum=4` (= maxProgs+1 "Run Now"), target zone gets its duration, all others zeroed.
- `POST /stopSprinklers.htm`:
  - `stop=active` → stops current watering only, system stays enabled (used by zone/program switch off).
  - `stop=off` → stops AND disables system, `allowRun=false` (System OFF button).
- `POST /runSprinklers.htm` with `run=run` → System ON (re-enable).

## Program save form schema (`_build_program_payload`)

- `doProgram=1`, `pgmNum` (1–3), `allowRun=yes|no` (radio strings, not numeric).
- Day checkboxes `day_Mon..day_Sun`: sent ONLY when checked; omit unchecked days entirely.
- Start times (5 slots): `stHr{i}` (12-hour), `stMin{i}`, `merid{i}` (am/pm), `startTime{i}` (`HH:MM am` string when armed, empty string to clear slot), `stStat{i}=1` for slots 1–4 when armed.
- Zone durations: `z{n}durHr` / `z{n}durMin`, n=1..9.
- Omit `evenOdd` fields so firmware keeps existing values; echo `everyNDays` back from `indexVarsDyn.js` (fetch returns None → omit).

## Firmware quirks

1. **Slot 0 start time**: no checkbox in web UI — always armed whenever its time is set, yet `programData.json` reports `isOn=false`. Coordinator normalizes slot 0 `isOn` from hr/min after each poll; partial saves would otherwise wipe it.
2. **Run Now reported as progNumber=4** in status.json even though only programs 1–3 exist.
3. **`zoneDuration` entry 10 is a totals row** — never echo back on save.
4. **Firmware-enforced zone run cap**: `maxZRunTime` (default 40 min) — clamp manual durations.
5. **API varies across firmware versions**; if new behaviour appears, capture firmware version + raw JSON and document it in the PR.

## Testing without hardware

No test suite exists. Manual verification path: copy `custom_components/irrigation_caddy/` into an HA dev container's `custom_components/`, add integration pointing at a reachable controller (or mock the HTTP endpoints with something like pytest-aiohttp/aioresponses if adding tests). UDP discovery broadcast: `"Discovery: Who is out there?"` to port 30303 finds devices on the LAN.
