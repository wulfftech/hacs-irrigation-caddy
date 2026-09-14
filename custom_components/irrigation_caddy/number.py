"""Number entities for manual (Run Now) zone run durations."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ZONE_DURATION, DOMAIN, RUN_NOW_MIN_DURATION
from .coordinator import IrrigationCaddyCoordinator
from .device_info import run_now_device_info
from .options import default_duration, run_now_max, with_zone_duration, zone_duration


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = [IrrigationCaddyDefaultDurationNumber(coordinator, entry)]

    # Matches the switch platform: a duration box only exists for a zone that
    # is switched on in the options flow.
    for zone in coordinator.enabled_zones:
        entities.append(IrrigationCaddyZoneDurationNumber(coordinator, entry, zone))

    async_add_entities(entities)


class _DurationNumber(CoordinatorEntity[IrrigationCaddyCoordinator], NumberEntity):
    """Shared plumbing for the minute-valued duration sliders."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = RUN_NOW_MIN_DURATION
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def _max_run(self) -> int:
        """Slider ceiling: 30 minutes, or the firmware's maxZRunTime if lower."""
        data = self.coordinator.data
        return run_now_max(data.max_zone_run_time if data else None)

    @property
    def native_max_value(self) -> float:
        return float(self._max_run)


class IrrigationCaddyDefaultDurationNumber(_DurationNumber):
    """Fallback run duration for zones that have no duration of their own."""

    _attr_name = "Default Run Duration"
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        # Unchanged from when this was the only duration entity, so existing
        # dashboards and automations keep working after the per-zone split.
        self._attr_unique_id = f"{entry.entry_id}_zone_duration"
        self._attr_device_info = run_now_device_info(entry)

    @property
    def native_value(self) -> float:
        return float(default_duration(self._entry, self._max_run))

    async def async_set_native_value(self, value: float) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_ZONE_DURATION: int(value)},
        )


class IrrigationCaddyZoneDurationNumber(_DurationNumber):
    """How long one zone runs when its switch is turned on.

    Held in Home Assistant, not on the controller: the device's only way to
    write a Run Now duration is the form that also starts watering.
    """

    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, zone: int) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._zone = zone
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}_duration"
        self._attr_device_info = run_now_device_info(entry)

    @property
    def name(self) -> str:
        if self.coordinator.data:
            return f"{self.coordinator.data.zone_names[self._zone - 1]} Duration"
        return f"Zone {self._zone} Duration"

    @property
    def native_value(self) -> float:
        return float(zone_duration(self._entry, self._zone, self._max_run))

    async def async_set_native_value(self, value: float) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=with_zone_duration(self._entry, self._zone, int(value)),
        )
