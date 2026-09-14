"""Button entities for Irrigation Caddy — momentary run/stop commands."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_PROGRAMS
from .coordinator import IrrigationCaddyCoordinator
from .device_info import programs_device_info, system_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = [IrrigationCaddyStopButton(coordinator, entry)]

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramRunButton(coordinator, entry, program))

    entities.append(IrrigationCaddyRunNowRepeatButton(coordinator, entry))

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

    async def async_press(self) -> None:
        await self.coordinator.async_stop_zone()


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


class IrrigationCaddyRunNowRepeatButton(CoordinatorEntity[IrrigationCaddyCoordinator], ButtonEntity):
    """Re-run the stored Run Now configuration ("repeat last manual watering").

    The firmware persists the per-zone durations of the last manual run; this
    replays them unchanged. Fails with a clear error if nothing is stored yet.
    """

    _attr_has_entity_name = True
    _attr_name = "Repeat Run Now"
    _attr_icon = "mdi:replay"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_run_now_repeat"
        self._attr_device_info = programs_device_info(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_run_now_repeat()
