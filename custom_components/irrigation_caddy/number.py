"""Number entity for per-zone run duration override."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION, DOMAIN, MAX_ZONES
from .coordinator import IrrigationCaddyCoordinator
from .switch import _device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationCaddyZoneDurationNumber(coordinator, entry)])


class IrrigationCaddyZoneDurationNumber(CoordinatorEntity[IrrigationCaddyCoordinator], NumberEntity):
    """Sets how long (minutes) a zone runs when turned on manually."""

    _attr_has_entity_name = True
    _attr_name = "Zone Run Duration"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_duration"
        self._attr_device_info = _device_info(coordinator, entry)
        self._value = entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION)

    @property
    def native_value(self) -> float:
        return self._entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION)

    async def async_set_native_value(self, value: float) -> None:
        new_options = {**self._entry.options, CONF_ZONE_DURATION: int(value)}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
