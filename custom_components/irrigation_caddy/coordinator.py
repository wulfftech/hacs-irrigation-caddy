"""DataUpdateCoordinator for Irrigation Caddy."""
from __future__ import annotations

import asyncio
import logging
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
    MAX_PROGRAMS,
    MAX_ZONES,
)

_LOGGER = logging.getLogger(__name__)


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
            status, zone_names_raw, programs_raw, settings_raw = await asyncio.gather(
                self._get(ENDPOINT_STATUS),
                self._get(ENDPOINT_ZONE_NAMES),
                self._get(ENDPOINT_PROGRAM_DATA),
                self._get(ENDPOINT_SETTINGS),
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

            # settingsVars.json — firmware version and max run time per zone
            if not isinstance(settings_raw, Exception) and isinstance(settings_raw, dict):
                data.firmware_version = settings_raw.get("icVersion", "")
                data.max_zone_run_time = int(settings_raw.get("maxZRunTime", 40))

            return data

        except UpdateFailed:
            raise
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot connect to Irrigation Caddy at {self.host}:{self.port}: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    # --- Control methods ---

    async def async_run_program(self, program: int) -> None:
        """Trigger an immediate run of a saved program (1–3)."""
        await self._post(ENDPOINT_RUN_PROGRAM, {
            "pgmNum": str(program),
            "doProgram": "1",
            "runNow": "true",
            "time": str(int(time.time() * 1000)),
        })
        await self.async_request_refresh()

    async def async_run_zone(self, zone: int, duration_minutes: int) -> None:
        """Run a single zone via the Run Now mechanism (pgmNum=4).

        Sets the target zone's duration and zeroes all others, matching
        exactly what the web UI does for a Run Now submission.
        """
        max_zones = self.data.max_zone_run_time if self.data else 40
        duration_minutes = min(duration_minutes, self.data.max_zone_run_time if self.data else 40)

        payload: dict[str, str] = {
            "pgmNum": "4",   # 4 = Run Now (maxProgs + 1)
            "runNow": "1",
        }
        for z in range(1, MAX_ZONES + 1):
            payload[f"z{z}durHr"] = "0"
            payload[f"z{z}durMin"] = str(duration_minutes) if z == zone else "0"

        await self._post(ENDPOINT_SAVE_PROGRAM, payload)
        await self.async_request_refresh()

    async def async_stop_zone(self) -> None:
        """Stop the currently active zone (advances program to next zone).

        Uses stop=active per the firmware JS: stopSprinklers.htm?stop=active
        """
        await self._post(ENDPOINT_STOP_SPRINKLERS, {"stop": "active"})
        await self.async_request_refresh()

    async def async_stop_all(self) -> None:
        """Stop all activity and disable the system.

        Uses stop=off per the firmware JS: stopSprinklers.htm?stop=off
        """
        await self._post(ENDPOINT_STOP_SPRINKLERS, {"stop": "off"})
        await self.async_request_refresh()

    async def async_enable_system(self) -> None:
        """Re-enable the system (System ON button in web UI)."""
        await self._post(ENDPOINT_RUN_SPRINKLERS, {"run": "run"})
        await self.async_request_refresh()

    async def async_close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
