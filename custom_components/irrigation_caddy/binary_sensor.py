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
from .switch import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IrrigationCaddyWateringBinarySensor(coordinator, entry),
        IrrigationCaddyEnabledBinarySensor(coordinator, entry),
    ])


class IrrigationCaddyWateringBinarySensor(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when any zone is actively watering."""

    _attr_has_entity_name = True
    _attr_name = "Watering"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_watering"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return any(self.coordinator.data.active_zones)


class IrrigationCaddyEnabledBinarySensor(CoordinatorEntity[IrrigationCaddyCoordinator], BinarySensorEntity):
    """True when the controller has programs enabled (not globally disabled)."""

    _attr_has_entity_name = True
    _attr_name = "Enabled"
    _attr_icon = "mdi:toggle-switch"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return True
        return self.coordinator.data.enabled
