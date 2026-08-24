"""Irrigation Caddy integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DEFAULT_PORT, DOMAIN, MAX_PROGRAMS
from .coordinator import IrrigationCaddyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
]

SERVICE_SET_PROGRAM = "set_program"

# Setup happens exclusively via config entries; async_setup exists only to
# register domain services.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_PROGRAM = "program"
ATTR_ENABLED = "enabled"
ATTR_DAYS = "days"
ATTR_START_TIMES = "start_times"
ATTR_ZONE_DURATIONS = "zone_durations"

VALID_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

SET_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PROGRAM): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_PROGRAMS)),
        vol.Optional(ATTR_ENABLED): cv.boolean,
        vol.Optional(ATTR_DAYS): vol.All(
            cv.ensure_list, [vol.In(VALID_DAYS)]
        ),
        vol.Optional(ATTR_START_TIMES): vol.All(
            cv.ensure_list, [cv.time]
        ),
        vol.Optional(ATTR_ZONE_DURATIONS): vol.Schema(
            {vol.Coerce(int): vol.All(vol.Coerce(int), vol.Range(min=0, max=720))}
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    coordinator = IrrigationCaddyCoordinator(hass, host, port)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to reach Irrigation Caddy at {host}:{port}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _parse_start_time(value) -> tuple[int, int]:
    """Convert a service-call time value (datetime.time or string) to 24h hour/min."""
    if isinstance(value, str):
        parts = value.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return hour, minute
    return value.hour, value.minute


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Register domain-level services."""

    def _get_coordinator(call: ServiceCall) -> IrrigationCaddyCoordinator:
        coordinators = hass.data.get(DOMAIN, {})
        if not coordinators:
            raise HomeAssistantError("No Irrigation Caddy is configured")
        # Single-device integration: use the first configured coordinator.
        return next(iter(coordinators.values()))

    async def handle_set_program(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        program = call.data[ATTR_PROGRAM]

        kwargs: dict = {}
        if ATTR_ENABLED in call.data:
            kwargs["enabled"] = call.data[ATTR_ENABLED]
        if ATTR_DAYS in call.data:
            days = {d: False for d in VALID_DAYS}
            for d in call.data[ATTR_DAYS]:
                days[d] = True
            kwargs["days"] = days
        if ATTR_START_TIMES in call.data:
            start_times = []
            for value in call.data[ATTR_START_TIMES]:
                hour, minute = _parse_start_time(value)
                # Any explicitly listed time is armed, including 00:00.
                start_times.append({"hr": hour, "min": minute, "isOn": True})
            while len(start_times) < 5:
                start_times.append({"hr": 0, "min": 0, "isOn": False})
            kwargs["start_times"] = start_times[:5]
        if ATTR_ZONE_DURATIONS in call.data:
            durations = [
                {"hr": 0, "min": 0} for _ in range(coordinator.data.max_zones)
            ]
            for zone_str, minutes in call.data[ATTR_ZONE_DURATIONS].items():
                zone = int(zone_str)
                if not 1 <= zone <= coordinator.data.max_zones:
                    raise HomeAssistantError(
                        f"Zone {zone} is out of range (1-{coordinator.data.max_zones})"
                    )
                durations[zone - 1] = {
                    "hr": minutes // 60,
                    "min": minutes % 60,
                }
            kwargs["zone_durations"] = durations

        try:
            await coordinator.async_save_program_schedule(program, **kwargs)
        except Exception as err:
            raise HomeAssistantError(f"Failed to save program {program}: {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_SET_PROGRAM, handle_set_program, schema=SET_PROGRAM_SCHEMA
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
