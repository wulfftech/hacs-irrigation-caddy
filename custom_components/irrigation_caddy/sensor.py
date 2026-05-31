"""Sensor entities for Irrigation Caddy."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IrrigationCaddyCoordinator
from .switch import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IrrigationCaddyActiveZoneSensor(coordinator, entry),
        IrrigationCaddyActiveProgramSensor(coordinator, entry),
        IrrigationCaddyRemainingTimeSensor(coordinator, entry),
    ])


class IrrigationCaddyActiveZoneSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Reports the currently active zone name (or 'None')."""

    _attr_has_entity_name = True
    _attr_name = "Active Zone"
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_zone"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "Unknown"
        for i, active in enumerate(self.coordinator.data.active_zones):
            if active:
                return self.coordinator.data.zone_names[i]
        return "None"


class IrrigationCaddyActiveProgramSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Reports the currently running program number (0 = none)."""

    _attr_has_entity_name = True
    _attr_name = "Active Program"
    _attr_icon = "mdi:timer-play"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_program"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.active_program


class IrrigationCaddyRemainingTimeSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Reports remaining watering time in seconds."""

    _attr_has_entity_name = True
    _attr_name = "Remaining Time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_remaining_time"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.remaining_seconds
