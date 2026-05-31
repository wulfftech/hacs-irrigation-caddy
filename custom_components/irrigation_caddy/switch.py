"""Switch entities for Irrigation Caddy — zones and programs."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
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
        entities.append(IrrigationCaddyProgramSwitch(coordinator, entry, program))

    async_add_entities(entities)


def _device_info(coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> DeviceInfo:
    fw = coordinator.data.firmware_version if coordinator.data else ""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        sw_version=fw or None,
        configuration_url=f"http://{coordinator.host}:{coordinator.port}",
    )


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
        self._attr_device_info = _device_info(coordinator, entry)

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
    """A switch that represents a single irrigation zone."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}"
        self._attr_device_info = _device_info(coordinator, entry)

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


class IrrigationCaddyProgramSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """A switch that represents an irrigation program."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, program: int) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}"
        self._attr_name = f"Program {program}"
        self._attr_icon = "mdi:timer-play-outline"
        self._attr_device_info = _device_info(coordinator, entry)

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
            programs = self.coordinator.data.programs
            if self._program <= len(programs):
                prog = programs[self._program - 1]
                attrs["allow_run"] = prog.get("allowRun", True)
                days = prog.get("daysToRun", {})
                attrs["days_to_run"] = [d for d, v in days.items() if v]
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_program(self._program)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_all()
