"""Switch entities for Irrigation Caddy."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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

    entities: list[SwitchEntity] = [IrrigationCaddySystemSwitch(coordinator, entry)]

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramEnableSwitch(coordinator, entry, program))

    async_add_entities(entities)


class IrrigationCaddySystemSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Master system switch — mirrors the ON/OFF button in the web UI (allowRun)."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True
    _attr_name = "System"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_system"

    @property
    def device_info(self):
        fw = self.coordinator.data.firmware_version if self.coordinator.data else ""
        return system_device_info(self.coordinator.host, self.coordinator.port, self._entry, fw)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return True
        return self.coordinator.data.allow_run

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable_system()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_all()


class IrrigationCaddyProgramEnableSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Enable/disable a saved program (allowRun per program).

    When off, the program won't run on its scheduled days even if the system is on.
    The full schedule (days/times/durations) is visible on the matching
    sensor.program_{n}_state entity; edit it via the irrigation_caddy.set_program
    service.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, program: int) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}_enable"
        self._attr_name = f"Program {program} Enabled"
        self._attr_icon = "mdi:calendar-check-outline"
        self._attr_device_info = programs_device_info(entry)
        # Optimistic state so the switch responds instantly; corrected on next
        # coordinator refresh (which each command triggers immediately).
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        if not self.coordinator.data or not self.coordinator.data.programs:
            return True
        progs = self.coordinator.data.programs
        if self._program <= len(progs):
            return bool(progs[self._program - 1].get("allowRun", True))
        return True

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once real device data arrives."""
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._optimistic_state = True
        self.async_write_ha_state()
        try:
            await self.coordinator.async_set_program_enabled(self._program, True)
        except Exception:
            self._optimistic_state = None
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._optimistic_state = False
        self.async_write_ha_state()
        try:
            await self.coordinator.async_set_program_enabled(self._program, False)
        except Exception:
            self._optimistic_state = None
            raise
