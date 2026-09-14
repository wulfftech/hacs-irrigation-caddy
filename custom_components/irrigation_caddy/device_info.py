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


def run_now_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Run Now sub-device — per-zone manual run switches and their durations.

    Named to match the device's own web UI, where manual watering lives on a
    "Run Now" page rather than a zone list. The identifier keeps its original
    "_zones" suffix so the existing device registry entry (and the entity
    history attached to it) survives the rename.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_zones")},
        name="Run Now",
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        via_device=(DOMAIN, entry.entry_id),
    )


def programs_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Programs sub-device — per-program run buttons, enable switches and state."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_programs")},
        name="Programs",
        manufacturer="KGControls",
        model="Irrigation Caddy S1",
        via_device=(DOMAIN, entry.entry_id),
    )
