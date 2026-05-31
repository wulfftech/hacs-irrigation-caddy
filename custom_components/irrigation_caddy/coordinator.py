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
    ENDPOINT_STATUS,
    ENDPOINT_ZONE_NAMES,
    ENDPOINT_RUN_PROGRAM,
    ENDPOINT_RUN_ZONE,
    ENDPOINT_RUN_SPRINKLERS,
    ENDPOINT_STOP_SPRINKLERS,
    MAX_PROGRAMS,
    MAX_ZONES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class IrrigationCaddyData:
    """Parsed state from the Irrigation Caddy."""

    active_zones: list[bool] = field(default_factory=lambda: [False] * MAX_ZONES)
    active_program: int = 0  # 0 = none
    remaining_seconds: int = 0
    enabled: bool = True
    zone_names: list[str] = field(default_factory=lambda: [f"Zone {i+1}" for i in range(MAX_ZONES)])
    programs: list[dict] = field(default_factory=list)


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
        rand = int(time.time())
        sep = "&" if "?" in endpoint else "?"
        return f"{self._base_url}{endpoint}{sep}rand={rand}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get_json(self, endpoint: str) -> dict:
        session = await self._get_session()
        async with session.get(self._url(endpoint)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _post(self, endpoint: str, data: dict) -> None:
        data["rand"] = int(time.time())
        session = await self._get_session()
        async with session.post(
            f"{self._base_url}{endpoint}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            resp.raise_for_status()

    async def _async_update_data(self) -> IrrigationCaddyData:
        try:
            status_task = self._get_json(ENDPOINT_STATUS)
            names_task = self._get_json(ENDPOINT_ZONE_NAMES)
            programs_task = self._get_json(ENDPOINT_PROGRAM_DATA)

            status, zone_names_raw, programs_raw = await asyncio.gather(
                status_task, names_task, programs_task, return_exceptions=True
            )

            data = IrrigationCaddyData()

            if isinstance(status, Exception):
                raise UpdateFailed(f"Error fetching status: {status}") from status

            # Parse status — the controller returns various shapes depending on firmware
            if isinstance(status, dict):
                # Active zones: may be a list of booleans/ints or a single active zone index
                raw_zones = status.get("activeZones", status.get("activeZone", []))
                if isinstance(raw_zones, list):
                    data.active_zones = [bool(z) for z in (raw_zones + [False] * MAX_ZONES)[:MAX_ZONES]]
                elif isinstance(raw_zones, int) and raw_zones > 0:
                    data.active_zones = [i + 1 == raw_zones for i in range(MAX_ZONES)]

                data.active_program = int(status.get("activeProgram", status.get("pgmNum", 0)))
                data.remaining_seconds = int(status.get("remaining", status.get("timeRemaining", 0)))

                run_state = status.get("run", status.get("status", "on"))
                data.enabled = str(run_state).lower() not in ("off", "disabled", "0", "false")

            # Parse zone names
            if not isinstance(zone_names_raw, Exception) and isinstance(zone_names_raw, dict):
                names = zone_names_raw.get("zoneNames", zone_names_raw.get("zones", []))
                if isinstance(names, list):
                    for i, name in enumerate(names[:MAX_ZONES]):
                        if name:
                            data.zone_names[i] = name

            # Parse programs
            if not isinstance(programs_raw, Exception) and isinstance(programs_raw, dict):
                data.programs = programs_raw.get("programs", [])

            return data

        except UpdateFailed:
            raise
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Cannot connect to Irrigation Caddy at {self.host}:{self.port}: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    # --- Control methods ---

    async def async_run_program(self, program: int) -> None:
        """Run a program by number (1-indexed)."""
        await self._post(ENDPOINT_RUN_PROGRAM, {
            "doProgram": "1",
            "pgmNum": str(program),
            "runNow": "true",
        })
        await self.async_request_refresh()

    async def async_stop_all(self) -> None:
        """Stop all active zones and programs."""
        await self._post(ENDPOINT_STOP_SPRINKLERS, {"stop": "off"})
        await self.async_request_refresh()

    async def async_enable_all(self) -> None:
        """Re-enable all programs (undo global disable)."""
        await self._post(ENDPOINT_RUN_SPRINKLERS, {"run": "run"})
        await self.async_request_refresh()

    async def async_run_zone(self, zone: int, duration_minutes: int) -> None:
        """Run a single zone for a given duration in minutes (zone is 1-indexed)."""
        await self._post(ENDPOINT_RUN_ZONE, {
            "zone": str(zone),
            "duration": str(duration_minutes),
            "run": "run",
        })
        await self.async_request_refresh()

    async def async_stop_zone(self, zone: int) -> None:
        """Stop a specific zone (stops the active zone if it matches)."""
        await self.async_stop_all()

    async def async_close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
