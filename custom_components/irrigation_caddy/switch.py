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

    entities: list[SwitchEntity] = []

    for zone in range(1, MAX_ZONES + 1):
        entities.append(IrrigationCaddyZoneSwitch(coordinator, entry, zone))

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramSwitch(coordinator, entry, program))

    async_add_entities(entities)


def _device_info(coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        configuration_url=f"http://{coordinator.host}:{coordinator.port}",
    )


class IrrigationCaddyZoneSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """A switch that represents a single irrigation zone."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IrrigationCaddyCoordinator,
        entry: ConfigEntry,
        zone: int,
    ) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def name(self) -> str:
        if self.coordinator.data:
            return self.coordinator.data.zone_names[self._zone - 1]
        return f"Zone {self._zone}"

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.active_zones[self._zone - 1]

    @property
    def icon(self) -> str:
        return "mdi:sprinkler" if self.is_on else "mdi:sprinkler-variant"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"zone_number": self._zone}
        if self.coordinator.data and self.is_on:
            attrs["remaining_seconds"] = self.coordinator.data.remaining_seconds
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        duration = self._entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION)
        await self.coordinator.async_run_zone(self._zone, duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_zone(self._zone)


class IrrigationCaddyProgramSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """A switch that represents an irrigation program."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IrrigationCaddyCoordinator,
        entry: ConfigEntry,
        program: int,
    ) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}"
        self._attr_name = f"Program {program}"
        self._attr_icon = "mdi:timer-play-outline"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.active_program == self._program

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_program(self._program)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_all()
