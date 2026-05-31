"""Config flow for Irrigation Caddy integration."""
from __future__ import annotations

import asyncio
import socket
import time
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ZONE_DURATION,
    DEFAULT_PORT,
    DEFAULT_ZONE_DURATION,
    DOMAIN,
    ENDPOINT_STATUS,
    MAX_ZONES,
    UDP_DISCOVERY_MESSAGE,
    UDP_DISCOVERY_PORT,
)

_LOGGER = logging.getLogger(__name__)


async def _async_discover_devices(timeout: float = 2.0) -> list[str]:
    """Broadcast UDP discovery and collect responding hosts."""
    loop = asyncio.get_event_loop()
    discovered: list[str] = []

    def _discover() -> list[str]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)
            sock.sendto(UDP_DISCOVERY_MESSAGE.encode(), ("<broadcast>", UDP_DISCOVERY_PORT))
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    discovered.append(addr[0])
                except socket.timeout:
                    break
        finally:
            sock.close()
        return discovered

    return await loop.run_in_executor(None, _discover)


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


class IrrigationCaddyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_hosts: list[str] = []

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

        # Pre-populate host from discovery if we came via that step
        suggested_host = self._discovered_hosts[0] if self._discovered_hosts else ""

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=suggested_host): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_zeroconf(self, discovery_info: Any) -> FlowResult:
        """Handle zeroconf discovery (future-proofing)."""
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IrrigationCaddyOptionsFlow:
        return IrrigationCaddyOptionsFlow(config_entry)


class IrrigationCaddyOptionsFlow(OptionsFlow):
    """Handle options (zone duration, etc.)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options

        schema = vol.Schema({
            vol.Optional(
                CONF_ZONE_DURATION,
                default=current.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION),
            ): vol.All(int, vol.Range(min=1, max=120)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
