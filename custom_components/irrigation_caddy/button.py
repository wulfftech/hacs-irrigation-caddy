"""Button entities for Irrigation Caddy — momentary run/stop commands."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ZONE_DURATION,
    DEFAULT_ZONE_DURATION,
    DOMAIN,
    MAX_PROGRAMS,
    MAX_ZONES,
)
from .coordinator import IrrigationCaddyCoordinator
from .device_info import programs_device_info, system_device_info, zones_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = [IrrigationCaddyStopButton(coordinator, entry)]

    for zone in range(1, MAX_ZONES + 1):
        entities.append(IrrigationCaddyZoneRunButton(coordinator, entry, zone))

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramRunButton(coordinator, entry, program))

    async_add_entities(entities)


class IrrigationCaddyStopButton(CoordinatorEntity[IrrigationCaddyCoordinator], ButtonEntity):
    """Stop the currently watering zone without disabling the system.

    Posts stop=active (verified): halts watering but leaves allowRun=true.
    The System switch is what turns the whole controller on/off.
    """

    _attr_has_entity_name = True
    _attr_name = "Stop Watering"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_stop_watering"
        fw = coordinator.data.firmware_version if coordinator.data else ""
        self._attr_device_info = system_device_info(coordinator.host, coordinator.port, entry, fw)

    def press(self) -> None:
        """Fire-and-forget press; the async work happens in async_press."""
        raise NotImplementedError

    async def async_press(self) -> None:
        await self.coordinator.async_stop_zone()


class IrrigationCaddyZoneRunButton(CoordinatorEntity[IrrigationCaddyCoordinator], ButtonEntity):
    """Run a single zone now for the configured Zone Run Duration."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}_run"
        self._attr_device_info = zones_device_info(entry)

    @property
    def name(self) -> str:
        if self.coordinator.data:
            name = self.coordinator.data.zone_names[self._zone - 1]
            if name and name != f"Zone {self._zone}":
                return f"Run {name} Now"
        return f"Run Zone {self._zone} Now"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        duration = self._configured_duration()
        return {"run_duration_minutes": duration}

    def _configured_duration(self) -> int:
        duration = int(self._entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION))
        if self.coordinator.data:
            duration = min(duration, self.coordinator.data.max_zone_run_time)
        return duration

    async def async_press(self) -> None:
        await self.coordinator.async_run_zone(self._zone, self._configured_duration())


class IrrigationCaddyProgramRunButton(CoordinatorEntity[IrrigationCaddyCoordinator], ButtonEntity):
    """Run a saved program now (momentary — programs are not a toggleable state).

    The device reports this run as progNumber=4 (Run Now); per-program state
    sensors report "running" only for scheduled runs of that program.
    """

    _attr_has_entity_name = True
    _attr_name = None  # set in __init__
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, program: int) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}_run"
        self._attr_name = f"Run Program {program} Now"
        self._attr_device_info = programs_device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_run_program(self._program)
