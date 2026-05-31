"""Shared device info helpers — three sub-devices under one config entry."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def system_device_info(host: str, port: int, entry: ConfigEntry, fw: str = "") -> DeviceInfo:
    """Main controller device — system status, sensors, master switch."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Irrigation Caddy",
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        sw_version=fw or None,
        configuration_url=f"http://{host}:{port}",
    )


def zones_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Zones sub-device — one switch per zone for manual runs."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_zones")},
        name="Zones",
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        via_device=(DOMAIN, entry.entry_id),
    )


def programs_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Programs sub-device — run-now switches and per-program enable switches."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_programs")},
        name="Programs",
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        via_device=(DOMAIN, entry.entry_id),
    )
