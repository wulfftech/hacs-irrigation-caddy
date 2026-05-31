"""Switch entities for Irrigation Caddy."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = [IrrigationCaddySystemSwitch(coordinator, entry)]

    for zone in range(1, MAX_ZONES + 1):
        entities.append(IrrigationCaddyZoneSwitch(coordinator, entry, zone))

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramRunSwitch(coordinator, entry, program))
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


class IrrigationCaddyZoneSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Manual run switch for a single irrigation zone."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}"
        self._attr_device_info = zones_device_info(entry)

    @property
    def name(self) -> str:
        if self.coordinator.data:
            name = self.coordinator.data.zone_names[self._zone - 1]
            if name and name != f"Zone {self._zone}":
                return name
        return f"Zone {self._zone}"

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.zone_number == self._zone

    @property
    def icon(self) -> str:
        return "mdi:sprinkler" if self.is_on else "mdi:sprinkler-variant"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"zone_number": self._zone}
        if self.coordinator.data and self.is_on:
            attrs["remaining_seconds"] = self.coordinator.data.zone_sec_left
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        duration = self._entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION)
        if self.coordinator.data:
            duration = min(duration, self.coordinator.data.max_zone_run_time)
        await self.coordinator.async_run_zone(self._zone, duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_zone()


class IrrigationCaddyProgramRunSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Run-now switch for a saved program — on = run immediately, off = stop all."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, program: int) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}_run"
        self._attr_name = f"Program {program} Run"
        self._attr_icon = "mdi:play-circle-outline"
        self._attr_device_info = programs_device_info(entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.prog_number == self._program

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"program_number": self._program}
        if self.coordinator.data and self.is_on:
            attrs["remaining_seconds"] = self.coordinator.data.prog_sec_left
        if self.coordinator.data and self.coordinator.data.programs:
            progs = self.coordinator.data.programs
            if self._program <= len(progs):
                prog = progs[self._program - 1]
                days = prog.get("daysToRun", {})
                attrs["days_to_run"] = [d for d, v in days.items() if v]
                total_min = sum(
                    z.get("hr", 0) * 60 + z.get("min", 0)
                    for z in prog.get("zoneDuration", [])[:MAX_ZONES]
                )
                attrs["total_run_minutes"] = total_min
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_program(self._program)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_all()


class IrrigationCaddyProgramEnableSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Enable/disable a saved program (allowRun per program).

    When off, the program won't run on its scheduled days even if the system is on.
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

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data or not self.coordinator.data.programs:
            return True
        progs = self.coordinator.data.programs
        if self._program <= len(progs):
            return bool(progs[self._program - 1].get("allowRun", True))
        return True

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_program_enabled(self._program, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_program_enabled(self._program, False)
