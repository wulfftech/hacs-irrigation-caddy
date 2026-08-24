"""Sensor entities for Irrigation Caddy."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_PROGRAMS, MAX_ZONES
from .coordinator import IrrigationCaddyCoordinator
from .device_info import programs_device_info, system_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        IrrigationCaddyActiveZoneSensor(coordinator, entry),
        IrrigationCaddyActiveProgramSensor(coordinator, entry),
        IrrigationCaddyZoneTimeRemainingSensor(coordinator, entry),
        IrrigationCaddyProgramTimeRemainingSensor(coordinator, entry),
    ]
    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramStateSensor(coordinator, entry, program))
    async_add_entities(entities)


def _sys(coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry):
    fw = coordinator.data.firmware_version if coordinator.data else ""
    return system_device_info(coordinator.host, coordinator.port, entry, fw)


class IrrigationCaddyActiveZoneSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Reports the currently active zone name (or 'None')."""

    _attr_has_entity_name = True
    _attr_name = "Active Zone"
    _attr_icon = "mdi:sprinkler"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_active_zone"

    @property
    def device_info(self):
        return _sys(self.coordinator, self._entry)

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "Unknown"
        z = self.coordinator.data.zone_number
        if z == 0:
            return "None"
        return self.coordinator.data.zone_names[z - 1]

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {"zone_number": self.coordinator.data.zone_number}


class IrrigationCaddyActiveProgramSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Reports the currently running program number (0 = none)."""

    _attr_has_entity_name = True
    _attr_name = "Active Program"
    _attr_icon = "mdi:timer-play"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_active_program"

    @property
    def device_info(self):
        return _sys(self.coordinator, self._entry)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.prog_number


class IrrigationCaddyProgramStateSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """State of one saved program: running, enabled, or disabled.

    Attributes expose the full schedule so it's visible without leaving HA.
    Edit schedules via the irrigation_caddy.set_program service.

    "running" only reflects a SCHEDULED run of this program — the firmware
    reports manual Run Now as progNumber=4 regardless of which program was
    triggered (the Watering binary sensor and Active Program sensor cover that).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, program: int) -> None:
        super().__init__(coordinator)
        self._program = program
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_program_{program}_state"
        self._attr_name = f"Program {program} State"
        self._attr_device_info = programs_device_info(entry)

    def _current_program(self) -> dict | None:
        data = self.coordinator.data
        if not data or not data.programs or self._program > len(data.programs):
            return None
        return data.programs[self._program - 1]

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "unknown"
        if self.coordinator.data.prog_number == self._program:
            return "running"
        if not (prog := self._current_program()):
            return "unknown"
        return "enabled" if bool(prog.get("allowRun", False)) else "disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"program_number": self._program}
        prog = self._current_program()
        if prog is None:
            return attrs

        data = self.coordinator.data
        attrs["enabled"] = bool(prog.get("allowRun", False))
        attrs["days_to_run"] = [d for d, v in prog.get("daysToRun", {}).items() if v]
        # Slot 0 is always armed when its time is set — the coordinator already
        # normalises its bogus isOn=false readback, so this filter is accurate.
        attrs["start_times"] = [
            f"{st.get('hr', 0):02d}:{st.get('min', 0):02d}"
            for st in prog.get("startTimes", [])
            if st.get("isOn")
        ]
        durations = {}
        for i, dur in enumerate(prog.get("zoneDuration", [])[:MAX_ZONES]):
            minutes = int(dur.get("hr", 0)) * 60 + int(dur.get("min", 0))
            if minutes:
                zone_name = (
                    data.zone_names[i] if i < len(data.zone_names) else f"Zone {i+1}"
                )
                durations[zone_name] = minutes
        attrs["zone_durations_minutes"] = durations
        attrs["total_run_minutes"] = sum(durations.values())
        return attrs


class IrrigationCaddyZoneTimeRemainingSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Seconds remaining for the active zone."""

    _attr_has_entity_name = True
    _attr_name = "Zone Time Remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_sec_left"

    @property
    def device_info(self):
        return _sys(self.coordinator, self._entry)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.zone_sec_left


class IrrigationCaddyProgramTimeRemainingSensor(CoordinatorEntity[IrrigationCaddyCoordinator], SensorEntity):
    """Seconds remaining for the active program run."""

    _attr_has_entity_name = True
    _attr_name = "Program Time Remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand-complete"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_prog_sec_left"

    @property
    def device_info(self):
        return _sys(self.coordinator, self._entry)

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.prog_sec_left
