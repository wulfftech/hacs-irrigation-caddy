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
    CONF_ENABLED_ZONES,
    CONF_ZONE_DURATION,
    CONF_ZONE_DURATIONS,
    DEFAULT_PORT,
    DEFAULT_ZONE_DURATION,
    DOMAIN,
    ENDPOINT_STATUS,
    MAX_PROGRAMS,
    MAX_ZONES,
    RUN_NOW_MIN_DURATION,
)
from .options import default_duration, enabled_zones, run_now_max, zone_duration

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


def _minutes_selector(
    minimum: int, maximum: int, mode: selector.NumberSelectorMode
) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=mode,
            unit_of_measurement="min",
        )
    )


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
                    # enabled_zones is deliberately left out: setup seeds it
                    # from the controller's own programs and zone names, which
                    # are not known until the first poll.
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
    """Zone selection and Run Now durations, plus a schedule editor per program.

    Schedules are written straight to the controller rather than kept as
    options: the device's program form is all-or-nothing, so one form submit
    maps cleanly onto one POST. The options themselves carry only what the
    device cannot hold — which zones to show, and the manual run durations —
    which is why the program branches finish by re-saving the options unchanged.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    # --- Entry point ---

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "zones",
                "run_now",
                *(f"program_{n}" for n in range(1, MAX_PROGRAMS + 1)),
            ],
        )

    def _finish(self) -> FlowResult:
        """Close the flow without disturbing the stored options."""
        return self.async_create_entry(title="", data=dict(self._config_entry.options))

    def _coordinator(self):
        return self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)

    def _device_data(self):
        coordinator = self._coordinator()
        return coordinator.data if coordinator else None

    def _zone_label(self, zone: int) -> str:
        data = self._device_data()
        if data and zone <= len(data.zone_names):
            return f"{zone}: {data.zone_names[zone - 1]}"
        return f"Zone {zone}"

    # --- Zone selection ---

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Choose which of the controller's outputs exist as entities.

        The firmware always reports nine zones whether or not anything is wired
        to them, so this is what keeps unused outputs out of Home Assistant.
        Changing the selection reloads the entry — see _async_update_listener.
        """
        data = self._device_data()
        max_zones = data.max_zones if data else MAX_ZONES
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = sorted(int(z) for z in user_input.get(CONF_ENABLED_ZONES, []))
            if not chosen:
                errors["base"] = "no_zones_selected"
            else:
                return self.async_create_entry(
                    title="",
                    data={**self._config_entry.options, CONF_ENABLED_ZONES: chosen},
                )

        current = [str(z) for z in enabled_zones(self._config_entry, max_zones)]
        schema = vol.Schema({
            vol.Required(CONF_ENABLED_ZONES, default=current): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=str(zone), label=self._zone_label(zone)
                        )
                        for zone in range(1, max_zones + 1)
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        })
        return self.async_show_form(step_id="zones", data_schema=schema, errors=errors)

    # --- Run Now durations ---

    async def async_step_run_now(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """How long each selected zone waters when its Run Now switch goes on."""
        data = self._device_data()
        max_zones = data.max_zones if data else MAX_ZONES
        max_run = run_now_max(data.max_zone_run_time if data else None)
        zones = enabled_zones(self._config_entry, max_zones)

        if user_input is not None:
            per_zone = dict(self._config_entry.options.get(CONF_ZONE_DURATIONS) or {})
            for zone in zones:
                per_zone[str(zone)] = int(user_input[f"zone_{zone}"])
            return self.async_create_entry(
                title="",
                data={
                    **self._config_entry.options,
                    CONF_ZONE_DURATION: int(user_input[CONF_ZONE_DURATION]),
                    CONF_ZONE_DURATIONS: per_zone,
                },
            )

        slider = _minutes_selector(
            RUN_NOW_MIN_DURATION, max_run, selector.NumberSelectorMode.SLIDER
        )
        fields: dict = {
            vol.Required(
                CONF_ZONE_DURATION,
                default=default_duration(self._config_entry, max_run),
            ): slider,
        }
        for zone in zones:
            fields[
                vol.Required(
                    f"zone_{zone}",
                    default=zone_duration(self._config_entry, zone, max_run),
                )
            ] = slider

        return self.async_show_form(
            step_id="run_now",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "max_run": str(max_run),
                "zones": ", ".join(self._zone_label(z) for z in zones),
            },
        )

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
        current = data.programs[program - 1]
        zones = enabled_zones(self._config_entry, data.max_zones)
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await coordinator.async_save_program_schedule(
                    program,
                    enabled=bool(user_input["enabled"]),
                    days={d: d in user_input.get("days", []) for d in DAY_KEYS},
                    start_times=_collect_start_times(user_input),
                    zone_durations=_collect_zone_durations(
                        user_input, data.max_zones, zones, current
                    ),
                )
            except Exception:  # noqa: BLE001 — reported in the form, logged by HA
                errors["base"] = "save_failed"
            else:
                return self._finish()

        return self.async_show_form(
            step_id=f"program_{program}",
            data_schema=self._program_schema(
                current, user_input, zones, data.max_zone_run_time
            ),
            errors=errors,
            description_placeholders={
                "program": str(program),
                "max_run": str(data.max_zone_run_time),
                "zones": ", ".join(self._zone_label(z) for z in zones),
            },
        )

    def _program_schema(
        self,
        current: dict,
        user_input: dict[str, Any] | None,
        zones: list[int],
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

        # Schedule durations start at 0 (= skip this zone) and stay a box rather
        # than a slider: a program can legitimately water a zone for far longer
        # than a manual Run Now.
        box = _minutes_selector(0, max_run, selector.NumberSelectorMode.BOX)
        device_durations = current.get("zoneDuration", [])
        for zone in zones:
            dur = device_durations[zone - 1] if zone <= len(device_durations) else {}
            minutes = int(dur.get("hr", 0)) * 60 + int(dur.get("min", 0))
            fields[
                vol.Required(f"zone_{zone}", default=prefill(f"zone_{zone}", minutes))
            ] = box

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


def _collect_zone_durations(
    user_input: dict[str, Any],
    zone_count: int,
    shown: list[int],
    current: dict,
) -> list[dict]:
    """Durations for every zone the controller has, in zone order.

    Zones hidden from Home Assistant are not on the form, so their durations
    are echoed back from the device unchanged — deselecting a zone must never
    silently rewrite a schedule that still uses it.
    """
    device_durations = current.get("zoneDuration", [])
    durations: list[dict] = []
    for zone in range(1, zone_count + 1):
        if zone in shown:
            minutes = int(user_input.get(f"zone_{zone}", 0))
        else:
            dur = device_durations[zone - 1] if zone <= len(device_durations) else {}
            minutes = int(dur.get("hr", 0)) * 60 + int(dur.get("min", 0))
        durations.append({"hr": minutes // 60, "min": minutes % 60})
    return durations
