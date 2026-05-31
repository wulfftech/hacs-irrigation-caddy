"""Binary sensor entities for Irrigation Caddy."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IrrigationCaddyCoordinator
from .device_info import system_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IrrigationCaddyWateringBinarySensor(coordinator, entry),
        IrrigationCaddyEnabledBinarySensor(coordinator, entry),
        IrrigationCaddyRainSensorActive(coordinator, entry),
        IrrigationCaddyRainSensorEnabled(coordinator, entry),
    ])


def _sys_device(coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry):
    fw = coordinator.data.firmware_version if coordinator.data else ""
    return system_device_info(coordinator.host, coordinator.port, entry, fw)


class IrrigationCaddyWateringBinarySensor(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when the controller is actively running a zone."""

    _attr_has_entity_name = True
    _attr_name = "Watering"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_watering"
        self._entry = entry

    @property
    def device_info(self):
        return _sys_device(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.running)


class IrrigationCaddyEnabledBinarySensor(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when the controller is globally enabled (allowRun / System ON)."""

    _attr_has_entity_name = True
    _attr_name = "System Enabled"
    _attr_icon = "mdi:toggle-switch"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._entry = entry

    @property
    def device_info(self):
        return _sys_device(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return True
        return self.coordinator.data.allow_run


class IrrigationCaddyRainSensorActive(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when the rain sensor is detecting moisture (isRaining AND sensor is enabled)."""

    _attr_has_entity_name = True
    _attr_name = "Rain Sensor Wet"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_icon = "mdi:weather-rainy"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_is_raining"
        self._entry = entry

    @property
    def device_info(self):
        return _sys_device(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.is_raining and self.coordinator.data.use_sensor1

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {
            "sensor_enabled": self.coordinator.data.use_sensor1,
            "raw_state": self.coordinator.data.is_raining,
        }


class IrrigationCaddyRainSensorEnabled(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when the rain sensor input is enabled in settings (useSensor1)."""

    _attr_has_entity_name = True
    _attr_name = "Rain Sensor Enabled"
    _attr_icon = "mdi:leak"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_use_sensor1"
        self._entry = entry

    @property
    def device_info(self):
        return _sys_device(self.coordinator, self._entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.use_sensor1
