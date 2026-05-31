"""Number entity for per-zone run duration."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION, DOMAIN
from .coordinator import IrrigationCaddyCoordinator
from .device_info import zones_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationCaddyZoneDurationNumber(coordinator, entry)])


class IrrigationCaddyZoneDurationNumber(CoordinatorEntity[IrrigationCaddyCoordinator], NumberEntity):
    """Sets how long (minutes) a zone runs when its switch is turned on manually."""

    _attr_has_entity_name = True
    _attr_name = "Zone Run Duration"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_duration"
        self._attr_device_info = zones_device_info(entry)

    @property
    def native_max_value(self) -> float:
        """Cap at the firmware's maxZRunTime."""
        if self.coordinator.data:
            return float(self.coordinator.data.max_zone_run_time)
        return 40.0

    @property
    def native_value(self) -> float:
        return float(self._entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION))

    async def async_set_native_value(self, value: float) -> None:
        new_options = {**self._entry.options, CONF_ZONE_DURATION: int(value)}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
