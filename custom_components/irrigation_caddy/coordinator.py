"""DataUpdateCoordinator for Irrigation Caddy."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINT_PROGRAM_DATA,
    ENDPOINT_SETTINGS,
    ENDPOINT_STATUS,
    ENDPOINT_ZONE_NAMES,
    ENDPOINT_RUN_PROGRAM,
    ENDPOINT_SAVE_PROGRAM,
    ENDPOINT_RUN_SPRINKLERS,
    ENDPOINT_STOP_SPRINKLERS,
    ENDPOINT_RUN_NOW_VARS,
    MAX_ZONES,
)

_LOGGER = logging.getLogger(__name__)

_ZDUR_RE = re.compile(r"zDur\s*:\s*\[(.*?)\]", re.S)
_DUR_ITEM_RE = re.compile(r"\{\s*hr\s*:\s*(\d+)\s*,\s*min\s*:\s*(\d+)\s*\}")


def _parse_run_now_durations(text: str) -> list[dict]:
    """Extract the Run Now (pgmNum=4) zone durations from indexVarsDyn.js text.

    The file is a hand-generated JS object literal; zDur looks like:
        zDur : [{hr:0, min:5},{hr:0, min:0}, ...]
    Zone 1 first. Returns [] if the block can't be found.
    """
    match = _ZDUR_RE.search(text)
    if not match:
        return []
    return [
        {"hr": int(hr), "min": int(min)}
        for hr, min in _DUR_ITEM_RE.findall(match.group(1))
    ]


@dataclass
class IrrigationCaddyData:
    """Parsed state from the Irrigation Caddy.

    Field names match the actual JSON keys returned by the device firmware
    ICEthS1-2.0.x (verified against a live device via JS source inspection).
    """

    # status.json
    zone_number: int = 0          # active zone (0 = none, 1–9)
    prog_number: int = 0          # active program (0 = none, 1–3)
    allow_run: bool = True        # controller globally enabled (system ON/OFF)
    running: bool = False         # actively watering right now
    use_sensor1: bool = False     # rain sensor enabled
    is_raining: bool = False      # raw rain sensor state (only meaningful if use_sensor1)
    zone_sec_left: int = 0        # seconds remaining for current zone
    prog_sec_left: int = 0        # seconds remaining in whole program run
    max_zones: int = MAX_ZONES
    zone_log: list = field(default_factory=list)
    # Per-zone schedule data while running: [{hr, min, isRun}, ...]
    zones: list[dict] = field(default_factory=list)

    # zoneNames.json — bare array
    zone_names: list[str] = field(default_factory=lambda: [f"Zone {i+1}" for i in range(MAX_ZONES)])

    # programData.json — bare array
    programs: list[dict] = field(default_factory=list)

    # Run Now (pgmNum=4) stored zone durations, parsed from js/indexVarsDyn.js.
    # The firmware persists the last manual run's per-zone config here; a bare
    # list of {hr, min} dicts, zone 1 first. Empty if it couldn't be read.
    run_now_durations: list[dict] = field(default_factory=list)

    # settingsVars.json
    firmware_version: str = ""
    max_zone_run_time: int = 40   # minutes — enforced by firmware


class IrrigationCaddyCoordinator(DataUpdateCoordinator[IrrigationCaddyData]):
    """Coordinator that polls the Irrigation Caddy controller."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._base_url = f"http://{host}:{port}"
        self._session: aiohttp.ClientSession | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _url(self, endpoint: str) -> str:
        return f"{self._base_url}{endpoint}?rand={int(time.time())}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def _get(self, endpoint: str):
        session = await self._get_session()
        async with session.get(self._url(endpoint)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _get_text(self, endpoint: str) -> str:
        """GET an endpoint and return the raw body text (non-JSON resources)."""
        session = await self._get_session()
        async with session.get(self._url(endpoint)) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _post(self, endpoint: str, data: dict) -> None:
        session = await self._get_session()
        async with session.post(
            f"{self._base_url}{endpoint}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            resp.raise_for_status()

    async def _async_update_data(self) -> IrrigationCaddyData:
        try:
            status, zone_names_raw, programs_raw, settings_raw, run_now_raw = await asyncio.gather(
                self._get(ENDPOINT_STATUS),
                self._get(ENDPOINT_ZONE_NAMES),
                self._get(ENDPOINT_PROGRAM_DATA),
                self._get(ENDPOINT_SETTINGS),
                self._get_text(ENDPOINT_RUN_NOW_VARS),
                return_exceptions=True,
            )

            if isinstance(status, Exception):
                raise UpdateFailed(f"Error fetching status: {status}") from status

            data = IrrigationCaddyData()

            if isinstance(status, dict):
                data.zone_number = int(status.get("zoneNumber", 0))
                data.prog_number = int(status.get("progNumber", 0))
                data.allow_run = bool(status.get("allowRun", True))
                data.running = bool(status.get("running", False))
                data.use_sensor1 = bool(status.get("useSensor1", False))
                data.is_raining = bool(status.get("isRaining", False))
                data.zone_sec_left = int(status.get("zoneSecLeft", 0))
                data.prog_sec_left = int(status.get("progSecLeft", 0))
                data.max_zones = int(status.get("maxZones", MAX_ZONES))
                data.zone_log = status.get("zoneLog", [])
                data.zones = status.get("zones", [])

            # zoneNames.json returns a bare JSON array
            if not isinstance(zone_names_raw, Exception) and isinstance(zone_names_raw, list):
                for i, name in enumerate(zone_names_raw[:MAX_ZONES]):
                    data.zone_names[i] = name if name else f"Zone {i+1}"

            # programData.json returns a bare JSON array
            if not isinstance(programs_raw, Exception) and isinstance(programs_raw, list):
                data.programs = programs_raw
                # Firmware quirk (verified live): start slot 0 has no checkbox
                # in the web UI — it is always armed whenever its time is set,
                # yet programData.json always reports isOn=false for it. The
                # other slots' isOn flags are accurate. Normalise slot 0 here so
                # partial updates don't wipe its time and attribute displays
                # show it as active.
                for prog in data.programs:
                    if not isinstance(prog, dict):
                        continue
                    times = prog.get("startTimes")
                    if isinstance(times, list) and times and isinstance(times[0], dict):
                        first = times[0]
                        first["isOn"] = bool(first.get("hr", 0) or first.get("min", 0))

            # settingsVars.json — firmware version and max run time per zone
            if not isinstance(settings_raw, Exception) and isinstance(settings_raw, dict):
                data.firmware_version = settings_raw.get("icVersion", "")
                data.max_zone_run_time = int(settings_raw.get("maxZRunTime", 40))

            # js/indexVarsDyn.js — the stored Run Now (pgmNum=4) zone durations.
            # Plain JS object text; parse the zDur array out of it. Optional:
            # failure just leaves run_now_durations empty.
            if not isinstance(run_now_raw, Exception) and isinstance(run_now_raw, str):
                data.run_now_durations = _parse_run_now_durations(run_now_raw)

            return data

        except UpdateFailed:
            raise
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot connect to Irrigation Caddy at {self.host}:{self.port}: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    # --- Control methods ---
    #
    # All payloads below were verified against live firmware ICEthS1-2.0.197
    # by capturing the POSTs made by the device's own web UI (js/program.js,
    # js/status.js) and round-trip testing against the device.

    async def _refresh_now(self) -> None:
        """Bypass the coordinator throttle so entities reflect the command."""
        await self.async_refresh()

    @staticmethod
    def _to_12h(hour_24: int) -> tuple[int, str]:
        """Convert a 24-hour value to the (hour, meridiem) pair the form expects."""
        hour_24 %= 24
        meridiem = "am" if hour_24 < 12 else "pm"
        hour_12 = hour_24 % 12
        return (hour_12 if hour_12 else 12, meridiem)

    async def async_run_program(self, program: int) -> None:
        """Trigger an immediate run of a saved program (1–3).

        Verified payload from the web UI's Run Now button (js/program.js).
        The device reports this run as progNumber=4 in status.json.
        """
        await self._post(ENDPOINT_RUN_PROGRAM, {
            "pgmNum": str(program),
            "doProgram": "1",
            "runNow": "true",
            "time": str(int(time.time() * 1000)),
        })
        await self._refresh_now()

    async def async_run_zone(self, zone: int, duration_minutes: int) -> None:
        """Run a single zone via the Run Now mechanism (pgmNum=4).

        Sets the target zone's duration and zeroes all others, matching
        exactly what the web UI does for a Run Now submission.
        """
        max_run = self.data.max_zone_run_time if self.data else 40
        duration_minutes = min(duration_minutes, max_run)

        payload: dict[str, str] = {
            "doProgram": "1",
            "pgmNum": "4",   # 4 = Run Now (maxProgs + 1)
            "runNow": "1",
        }
        for z in range(1, MAX_ZONES + 1):
            payload[f"z{z}durHr"] = "0"
            payload[f"z{z}durMin"] = str(duration_minutes) if z == zone else "0"

        await self._post(ENDPOINT_SAVE_PROGRAM, payload)
        await self._refresh_now()

    async def async_run_now_repeat(self) -> None:
        """Re-run the stored Run Now (pgmNum=4) configuration.

        The firmware persists the last manual run's per-zone durations; this
        re-submits them unchanged with runNow=1, i.e. "repeat last manual
        watering". Raises UpdateFailed if no durations are known yet.
        """
        durations = (
            list(self.data.run_now_durations)
            if self.data and self.data.run_now_durations else []
        )
        if not any(d.get("hr", 0) or d.get("min", 0) for d in durations[:MAX_ZONES]):
            raise UpdateFailed(
                "No Run Now configuration stored on the device to repeat — "
                "run a zone or program first"
            )

        payload: dict[str, str] = {
            "doProgram": "1",
            "pgmNum": "4",
            "runNow": "1",
        }
        for z in range(1, MAX_ZONES + 1):
            dur = durations[z - 1] if z <= len(durations) else {}
            payload[f"z{z}durHr"] = str(int(dur.get("hr", 0)))
            payload[f"z{z}durMin"] = str(int(dur.get("min", 0)))

        await self._post(ENDPOINT_SAVE_PROGRAM, payload)
        await self._refresh_now()

    async def async_stop_zone(self) -> None:
        """Stop the currently active zone only (system stays enabled).

        Verified: stop=active stops watering but leaves allowRun=true.
        """
        await self._post(ENDPOINT_STOP_SPRINKLERS, {"stop": "active"})
        await self._refresh_now()

    async def async_stop_all(self) -> None:
        """Stop all activity AND disable the system (System OFF button).

        Verified: stop=off sets allowRun=false. Use async_stop_zone() to
        merely halt the current watering without disabling the system.
        """
        await self._post(ENDPOINT_STOP_SPRINKLERS, {"stop": "off"})
        await self._refresh_now()

    async def _get_every_n_days(self, program: int) -> int | None:
        """Fetch a program's everyNDays interval from its web UI variables.

        The save form always submits everyNDays, so to preserve an existing
        interval schedule we read the value the UI would display and echo it
        back. Returns None (meaning "omit from payload") if it can't be read.
        """
        try:
            session = await self._get_session()
            url = (
                f"{self._base_url}/js/indexVarsDyn.js"
                f"?program={program}&rand={int(time.time())}"
            )
            async with session.get(url) as resp:
                resp.raise_for_status()
                text = await resp.text()
            match = re.search(r"everyNDays\s*:\s*(\d+)", text)
            return int(match.group(1)) if match else None
        except Exception:
            return None

    def _build_program_payload(
        self,
        program: int,
        enabled: bool,
        days: dict[str, bool],
        start_times: list[dict],
        zone_durations: list[dict],
        every_n_days: int | None = None,
    ) -> dict[str, str]:
        """Build the /program.htm form payload for saving a schedule.

        Form schema (verified against live firmware):
        - doProgram=1 is required or the POST is ignored.
        - allowRun is yes/no radio, not a numeric flag.
        - Day checkboxes are only sent when checked; unchecked days must be
          OMITTED (sending day_X=0 corrupts nothing but is not what the UI does).
        - Start times are 12-hour with a separate meridiem field.
        - Slot 0 is always armed whenever its time is set; there is no stStat0
          checkbox in the web UI at all. Slots 1-4 are armed via stStat{i},
          which maps directly to startTimes[i] on POST.
        - An unset slot must post startTime{i}="" so the firmware clears it.
        - Zone durations are z{n}durHr/z{n}durMin for n=1..9. Entry 10 in
          programData.json is a totals row and must not be echoed back.
        - evenOdd fields are omitted so the firmware keeps whatever the web UI
          last saved for those settings. everyNDays is echoed from the device
          when known for the same reason.
        """
        payload: dict[str, str] = {
            "doProgram": "1",
            "pgmNum": str(program),
            "allowRun": "yes" if enabled else "no",
        }
        if every_n_days is not None:
            payload["everyNDays"] = str(every_n_days)

        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            if days.get(day):
                payload[f"day_{day.capitalize()}"] = "1"

        for i in range(5):
            if i < len(start_times):
                st = start_times[i]
                hour_24 = int(st.get("hr", 0))
                minute = int(st.get("min", 0))
                is_on = bool(st.get("isOn") or st.get("is_on", False))
            else:
                hour_24, minute, is_on = 0, 0, False
            hour_12, meridiem = self._to_12h(hour_24)
            payload[f"stHr{i}"] = str(hour_12)
            payload[f"stMin{i}"] = str(minute)
            payload[f"merid{i}"] = meridiem
            payload[f"startTime{i}"] = (
                f"{hour_12:02d}:{minute:02d} {meridiem}" if is_on else ""
            )
            if is_on and 1 <= i <= 4:
                payload[f"stStat{i}"] = "1"

        for z in range(1, MAX_ZONES + 1):
            dur = zone_durations[z - 1] if z <= len(zone_durations) else {}
            payload[f"z{z}durHr"] = str(int(dur.get("hr", 0)))
            payload[f"z{z}durMin"] = str(int(dur.get("min", 0)))

        return payload

    async def async_save_program_schedule(
        self,
        program: int,
        *,
        enabled: bool | None = None,
        days: dict[str, bool] | None = None,
        start_times: list[dict] | None = None,
        zone_durations: list[dict] | None = None,
    ) -> None:
        """Save a program's schedule (days, start times, durations, enabled).

        Any argument left as None is taken from the device's current state so
        partial updates don't wipe the rest of the schedule. Raises
        UpdateFailed if the device's current program data is unavailable.
        """
        current = self._current_program(program)

        if enabled is None:
            enabled = bool(current.get("allowRun", False))
        if days is None:
            days = {d: bool(v) for d, v in current.get("daysToRun", {}).items()}
        if start_times is None:
            start_times = list(current.get("startTimes", []))
        if zone_durations is None:
            # Drop the totals row (entry 10) — only zones 1..9 are editable
            zone_durations = list(current.get("zoneDuration", []))[:MAX_ZONES]

        payload = self._build_program_payload(
            program,
            enabled,
            days,
            start_times,
            zone_durations,
            every_n_days=await self._get_every_n_days(program),
        )
        await self._post(ENDPOINT_SAVE_PROGRAM, payload)
        await self._refresh_now()

    def _current_program(self, program: int) -> dict:
        """Return the device's current data for a program (1-based index)."""
        programs = self.data.programs if self.data else []
        if not 1 <= program <= len(programs):
            raise UpdateFailed(
                f"Program {program} not available on device "
                f"(device reports {len(programs)} programs)"
            )
        return programs[program - 1]

    async def async_set_program_enabled(self, program: int, enabled: bool) -> None:
        """Enable or disable a saved program, preserving its full schedule.

        Re-submits the whole schedule with allowRun changed, using the exact
        form schema the device's web UI uses (POST /program.htm).
        """
        await self.async_save_program_schedule(program, enabled=enabled)

    async def async_enable_system(self) -> None:
        """Re-enable the system (System ON button in web UI)."""
        await self._post(ENDPOINT_RUN_SPRINKLERS, {"run": "run"})
        await self._refresh_now()

    async def async_close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
