"""Switch entities for Irrigation Caddy."""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_PROGRAMS, MAX_ZONES, OPTIMISTIC_TIMEOUT_SECONDS
from .coordinator import IrrigationCaddyCoordinator
from .device_info import programs_device_info, run_now_device_info, system_device_info
from .options import zone_duration


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCaddyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = [IrrigationCaddySystemSwitch(coordinator, entry)]

    zone_count = coordinator.data.max_zones if coordinator.data else MAX_ZONES
    for zone in range(1, zone_count + 1):
        entities.append(IrrigationCaddyZoneSwitch(coordinator, entry, zone))

    for program in range(1, MAX_PROGRAMS + 1):
        entities.append(IrrigationCaddyProgramEnableSwitch(coordinator, entry, program))

    async_add_entities(entities)


class IrrigationCaddyZoneSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Run one zone manually, and stop it again.

    ON means the controller reports this specific zone as the one watering, so
    the switch stays on for the whole run instead of flicking back once the
    command lands. OFF posts stop=active, which halts watering while leaving
    the system enabled — the System switch is what disables the controller.

    Turning a zone on cancels whatever else was watering: the firmware's Run
    Now (pgmNum=4) submission replaces the active run rather than queueing.
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_has_entity_name = True
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator: IrrigationCaddyCoordinator, entry: ConfigEntry, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone}_switch"
        self._attr_device_info = run_now_device_info(entry)
        # Commanded state, held only until the device confirms it or the grace
        # window lapses. The controller needs a few seconds to reflect a run in
        # status.json, and without this the switch would snap straight back.
        self._commanded: bool | None = None
        self._commanded_until: float = 0.0

    @property
    def name(self) -> str:
        if self.coordinator.data:
            return self.coordinator.data.zone_names[self._zone - 1]
        return f"Zone {self._zone}"

    @property
    def _device_says_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.running and data.zone_number == self._zone)

    @property
    def is_on(self) -> bool:
        if self._commanded is not None:
            return self._commanded
        return self._device_says_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "zone_number": self._zone,
            "run_duration_minutes": self._duration(),
        }
        if self._device_says_on and data:
            attrs["remaining_seconds"] = data.zone_sec_left
        return attrs

    def _duration(self) -> int:
        max_run = self.coordinator.data.max_zone_run_time if self.coordinator.data else None
        return zone_duration(self._entry, self._zone, max_run)

    def _hold(self, state: bool) -> None:
        self._commanded = state
        self._commanded_until = time.monotonic() + OPTIMISTIC_TIMEOUT_SECONDS
        self.async_write_ha_state()

    def _release(self) -> None:
        self._commanded = None
        self._commanded_until = 0.0

    def _handle_coordinator_update(self) -> None:
        if self._commanded is not None and (
            self._device_says_on == self._commanded
            or time.monotonic() >= self._commanded_until
        ):
            self._release()
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._hold(True)
        try:
            await self.coordinator.async_run_zone(self._zone, self._duration())
        except Exception:
            self._release()
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self._device_says_on:
            # Another zone (or nothing) is watering — stopping here would kill
            # someone else's run. Just drop any stale commanded state.
            self._release()
            self.async_write_ha_state()
            return
        self._hold(False)
        try:
            await self.coordinator.async_stop_zone()
        except Exception:
            self._release()
            raise


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


class IrrigationCaddyProgramEnableSwitch(CoordinatorEntity[IrrigationCaddyCoordinator], SwitchEntity):
    """Enable/disable a saved program (allowRun per program).

    When off, the program won't run on its scheduled days even if the system is on.
    The full schedule (days/times/durations) is visible on the matching
    sensor.program_{n}_state entity; edit it via the irrigation_caddy.set_program
    service.
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
        # Optimistic state so the switch responds instantly; corrected on next
        # coordinator refresh (which each command triggers immediately).
        self._optimistic_state: bool | None = None

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        if not self.coordinator.data or not self.coordinator.data.programs:
            return True
        progs = self.coordinator.data.programs
        if self._program <= len(progs):
            return bool(progs[self._program - 1].get("allowRun", True))
        return True

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once real device data arrives."""
        self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._optimistic_state = True
        self.async_write_ha_state()
        try:
            await self.coordinator.async_set_program_enabled(self._program, True)
        except Exception:
            self._optimistic_state = None
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._optimistic_state = False
        self.async_write_ha_state()
        try:
            await self.coordinator.async_set_program_enabled(self._program, False)
        except Exception:
            self._optimistic_state = None
            raise
