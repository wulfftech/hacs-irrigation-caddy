"""Helpers for reading and writing the config entry's manual-run options.

Manual (Run Now) zone durations live in HA rather than on the controller. The
device does store per-zone Run Now durations, but its only way to write them is
the program.htm form with runNow=1 — which starts watering immediately — so
there is no way to persist a duration there without also running the zone.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import CONF_ZONE_DURATION, CONF_ZONE_DURATIONS, DEFAULT_ZONE_DURATION


def default_duration(entry: ConfigEntry) -> int:
    """The fallback run duration used by any zone without its own setting."""
    return int(entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION))


def zone_duration(entry: ConfigEntry, zone: int, max_run: int | None = None) -> int:
    """Run duration in minutes for one zone, clamped to the firmware cap."""
    per_zone = entry.options.get(CONF_ZONE_DURATIONS) or {}
    minutes = int(per_zone.get(str(zone), default_duration(entry)))
    if max_run is not None:
        minutes = min(minutes, max_run)
    return max(minutes, 1)


def with_zone_duration(entry: ConfigEntry, zone: int, minutes: int) -> dict:
    """New options mapping with one zone's duration overridden."""
    per_zone = dict(entry.options.get(CONF_ZONE_DURATIONS) or {})
    per_zone[str(zone)] = int(minutes)
    return {**entry.options, CONF_ZONE_DURATIONS: per_zone}
