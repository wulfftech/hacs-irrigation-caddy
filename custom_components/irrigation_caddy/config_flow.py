"""Config and options flows for the Irrigation Caddy integration."""
from __future__ import annotations

import time
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ZONE_DURATION,
    DEFAULT_PORT,
    DEFAULT_ZONE_DURATION,
    DOMAIN,
    ENDPOINT_STATUS,
    MAX_PROGRAMS,
)

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LABELS = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}
START_SLOTS = 5


async def _async_test_connection(host: str, port: int) -> bool:
    """Try to reach the controller's status endpoint."""
    url = f"http://{host}:{port}{ENDPOINT_STATUS}?rand={int(time.time())}"
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                return resp.status == 200
    except Exception:
        return False


def _parse_time(value: str) -> tuple[int, int]:
    """Parse a time selector value (HH:MM or HH:MM:SS) into 24h hour/minute."""
    parts = value.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def _format_time(slot: dict) -> str:
    """Render one startTimes entry as the HH:MM:SS a time selector expects."""
    return f"{int(slot.get('hr', 0)):02d}:{int(slot.get('min', 0)):02d}:00"


class IrrigationCaddyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if await _async_test_connection(host, port):
                return self.async_create_entry(
                    title=f"Irrigation Caddy ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                    options={CONF_ZONE_DURATION: DEFAULT_ZONE_DURATION},
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=""): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IrrigationCaddyOptionsFlow:
        return IrrigationCaddyOptionsFlow(config_entry)


class IrrigationCaddyOptionsFlow(OptionsFlow):
    """Manual-run defaults, plus a full schedule editor for each program.

    Schedules are written straight to the controller rather than kept as
    options: the device's program form is all-or-nothing, so one form submit
    maps cleanly onto one POST. The options themselves only carry the
    manual-run duration, which is why the program branches finish by re-saving
    the existing options unchanged.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    # --- Entry point ---

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "manual_run",
                *(f"program_{n}" for n in range(1, MAX_PROGRAMS + 1)),
            ],
        )

    def _finish(self) -> FlowResult:
        """Close the flow without disturbing the stored options."""
        return self.async_create_entry(title="", data=dict(self._config_entry.options))

    # --- Manual run defaults ---

    async def async_step_manual_run(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        current = self._config_entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION)
        schema = vol.Schema({
            vol.Required(CONF_ZONE_DURATION, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=120)
            ),
        })
        return self.async_show_form(step_id="manual_run", data_schema=schema)

    # --- Program editors ---
    #
    # One thin step per program because the flow manager dispatches on the step
    # id; they all share _async_program_step.

    async def async_step_program_1(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_program_step(1, user_input)

    async def async_step_program_2(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_program_step(2, user_input)

    async def async_step_program_3(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_program_step(3, user_input)

    def _coordinator(self):
        return self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)

    async def _async_program_step(
        self, program: int, user_input: dict[str, Any] | None
    ) -> FlowResult:
        coordinator = self._coordinator()
        if (
            coordinator is None
            or not coordinator.data
            or len(coordinator.data.programs) < program
        ):
            return self.async_abort(reason="no_device_data")

        data = coordinator.data
        zone_count = data.max_zones
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await coordinator.async_save_program_schedule(
                    program,
                    enabled=bool(user_input["enabled"]),
                    days={d: d in user_input.get("days", []) for d in DAY_KEYS},
                    start_times=_collect_start_times(user_input),
                    zone_durations=_collect_zone_durations(user_input, zone_count),
                )
            except Exception:  # noqa: BLE001 — reported in the form, logged by HA
                errors["base"] = "save_failed"
            else:
                return self._finish()

        return self.async_show_form(
            step_id=f"program_{program}",
            data_schema=self._program_schema(
                data.programs[program - 1], user_input, zone_count, data.max_zone_run_time
            ),
            errors=errors,
            description_placeholders={
                "program": str(program),
                "max_run": str(data.max_zone_run_time),
                "zones": ", ".join(
                    f"{i + 1}: {name}" for i, name in enumerate(data.zone_names[:zone_count])
                ),
            },
        )

    def _program_schema(
        self,
        current: dict,
        user_input: dict[str, Any] | None,
        zone_count: int,
        max_run: int,
    ) -> vol.Schema:
        """Build the edit form, pre-filled from the device (or a failed submit)."""
        submitted = user_input or {}

        def prefill(key: str, device_value):
            return submitted.get(key, device_value)

        days_on = [d for d in DAY_KEYS if current.get("daysToRun", {}).get(d)]
        fields: dict = {
            vol.Required(
                "enabled", default=prefill("enabled", bool(current.get("allowRun")))
            ): selector.BooleanSelector(),
            vol.Required("days", default=prefill("days", days_on)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=d, label=DAY_LABELS[d])
                        for d in DAY_KEYS
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }

        device_times = current.get("startTimes", [])
        for i in range(1, START_SLOTS + 1):
            slot = device_times[i - 1] if i <= len(device_times) else {}
            device_value = _format_time(slot) if slot.get("isOn") else None
            value = prefill(f"start_time_{i}", device_value)
            # Optional with a suggested value rather than a default: clearing
            # the box has to leave the key out of user_input, or an armed slot
            # could never be turned back off.
            fields[
                vol.Optional(
                    f"start_time_{i}",
                    description={"suggested_value": value} if value else None,
                )
            ] = selector.TimeSelector()

        device_durations = current.get("zoneDuration", [])
        for zone in range(1, zone_count + 1):
            dur = device_durations[zone - 1] if zone <= len(device_durations) else {}
            minutes = int(dur.get("hr", 0)) * 60 + int(dur.get("min", 0))
            fields[
                vol.Required(f"zone_{zone}", default=prefill(f"zone_{zone}", minutes))
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=max_run,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            )

        return vol.Schema(fields)


def _collect_start_times(user_input: dict[str, Any]) -> list[dict]:
    """Build the 5 positional start slots; a blank field clears its slot."""
    slots: list[dict] = []
    for i in range(1, START_SLOTS + 1):
        value = user_input.get(f"start_time_{i}")
        if value:
            hour, minute = _parse_time(value)
            slots.append({"hr": hour, "min": minute, "isOn": True})
        else:
            slots.append({"hr": 0, "min": 0, "isOn": False})
    return slots


def _collect_zone_durations(user_input: dict[str, Any], zone_count: int) -> list[dict]:
    durations: list[dict] = []
    for zone in range(1, zone_count + 1):
        minutes = int(user_input.get(f"zone_{zone}", 0))
        durations.append({"hr": minutes // 60, "min": minutes % 60})
    return durations
