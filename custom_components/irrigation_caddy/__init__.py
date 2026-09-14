"""Irrigation Caddy integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import CONF_ENABLED_ZONES, DEFAULT_PORT, DOMAIN, MAX_PROGRAMS, MAX_ZONES
from .coordinator import IrrigationCaddyCoordinator
from .options import derive_enabled_zones, enabled_zones

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

    max_zones = coordinator.data.max_zones if coordinator.data else MAX_ZONES

    # First run (including the first load after upgrading): pick the zones that
    # look wired up so the Run Now device isn't padded out with the controller's
    # unused outputs. Seeded into options rather than derived on every load, so
    # the selection stays put once the user has seen it.
    if CONF_ENABLED_ZONES not in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                CONF_ENABLED_ZONES: derive_enabled_zones(coordinator.data),
            },
        )

    coordinator.enabled_zones = enabled_zones(entry, max_zones)
    _purge_hidden_zone_entities(hass, entry, coordinator.enabled_zones)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _purge_hidden_zone_entities(
    hass: HomeAssistant, entry: ConfigEntry, zones: list[int]
) -> None:
    """Forget registry entries for zones that are no longer shown.

    Entities are only created for selected zones, so without this a zone that
    gets switched off would linger as an unavailable "restored" entity rather
    than disappearing. Turning the zone back on recreates it — the unique ids
    are stable.
    """
    stale = {
        unique_id
        for zone in range(1, MAX_ZONES + 1)
        if zone not in zones
        for unique_id in (
            f"{entry.entry_id}_zone_{zone}_switch",
            f"{entry.entry_id}_zone_{zone}_duration",
        )
    }
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id in stale:
            registry.async_remove(registered.entity_id)


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

    def _get_coordinator() -> IrrigationCaddyCoordinator:
        coordinators = hass.data.get(DOMAIN, {})
        if not coordinators:
            raise HomeAssistantError("No Irrigation Caddy is configured")
        # Single-device integration: use the first configured coordinator.
        return next(iter(coordinators.values()))

    async def handle_set_program(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        if coordinator.data is None:
            raise HomeAssistantError(
                "Irrigation Caddy has no data yet — the controller is unreachable"
            )
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
            max_zones = coordinator.data.max_zones
            max_run = coordinator.data.max_zone_run_time
            durations = [{"hr": 0, "min": 0} for _ in range(max_zones)]
            for zone_str, minutes in call.data[ATTR_ZONE_DURATIONS].items():
                zone = int(zone_str)
                if not 1 <= zone <= max_zones:
                    raise HomeAssistantError(
                        f"Zone {zone} is out of range (1-{max_zones})"
                    )
                # The controller enforces maxZRunTime itself; reject rather than
                # silently truncate, so the saved schedule matches what was asked.
                if minutes > max_run:
                    raise HomeAssistantError(
                        f"Zone {zone}: {minutes} minutes exceeds the controller's "
                        f"maximum zone run time of {max_run} minutes"
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
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_PROGRAM)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """React to an options change, reloading only when it changes the entities.

    Durations are read straight from entry.options by the entities that use
    them, so a state push is enough — reloading would flash every entity
    unavailable each time a slider is nudged. Which zones exist is decided when
    the platforms are set up, so that one does need a reload.
    """
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    max_zones = coordinator.data.max_zones if coordinator.data else MAX_ZONES

    if set(enabled_zones(entry, max_zones)) != set(coordinator.enabled_zones):
        await hass.config_entries.async_reload(entry.entry_id)
        return

    coordinator.async_update_listeners()
