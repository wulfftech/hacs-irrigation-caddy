"""Helpers for reading and writing the config entry's Run Now options.

Manual (Run Now) zone durations live in HA rather than on the controller. The
device does store per-zone Run Now durations, but its only way to write them is
the program.htm form with runNow=1 — which starts watering immediately — so
there is no way to persist a duration there without also running the zone.

Which zones are shown lives here too: the controller always reports nine zones
whether or not they are wired up, so the config entry carries the subset worth
creating entities for.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_ENABLED_ZONES,
    CONF_ZONE_DURATION,
    CONF_ZONE_DURATIONS,
    DEFAULT_ZONE_DURATION,
    MAX_ZONES,
    RUN_NOW_MAX_DURATION,
    RUN_NOW_MIN_DURATION,
)

if TYPE_CHECKING:
    from .coordinator import IrrigationCaddyData


def run_now_max(max_zone_run_time: int | None = None) -> int:
    """Upper bound for a Run Now duration, in minutes.

    The slider tops out at RUN_NOW_MAX_DURATION, but never above the value the
    firmware itself enforces — a longer run would just be truncated by the
    device.
    """
    if max_zone_run_time is None:
        return RUN_NOW_MAX_DURATION
    return max(RUN_NOW_MIN_DURATION, min(RUN_NOW_MAX_DURATION, int(max_zone_run_time)))


def default_duration(entry: ConfigEntry, max_run: int | None = None) -> int:
    """The fallback run duration used by any zone without its own setting."""
    minutes = int(entry.options.get(CONF_ZONE_DURATION, DEFAULT_ZONE_DURATION))
    return _clamp(minutes, max_run)


def zone_duration(entry: ConfigEntry, zone: int, max_run: int | None = None) -> int:
    """Run duration in minutes for one zone, clamped to the firmware cap."""
    per_zone = entry.options.get(CONF_ZONE_DURATIONS) or {}
    minutes = int(per_zone.get(str(zone), default_duration(entry)))
    return _clamp(minutes, max_run)


def _clamp(minutes: int, max_run: int | None) -> int:
    if max_run is not None:
        minutes = min(minutes, int(max_run))
    return max(minutes, RUN_NOW_MIN_DURATION)


def with_zone_duration(entry: ConfigEntry, zone: int, minutes: int) -> dict:
    """New options mapping with one zone's duration overridden."""
    per_zone = dict(entry.options.get(CONF_ZONE_DURATIONS) or {})
    per_zone[str(zone)] = int(minutes)
    return {**entry.options, CONF_ZONE_DURATIONS: per_zone}


def enabled_zones(entry: ConfigEntry, max_zones: int = MAX_ZONES) -> list[int]:
    """Zone numbers that should appear in Home Assistant, lowest first.

    A missing or empty selection means "all of them" — on a fresh entry the
    setup code seeds this from derive_enabled_zones(), so the fallback only
    matters if the stored value is somehow unusable.
    """
    raw = entry.options.get(CONF_ENABLED_ZONES)
    if not raw:
        return list(range(1, max_zones + 1))
    zones = sorted({int(z) for z in raw if 1 <= int(z) <= max_zones})
    return zones or list(range(1, max_zones + 1))


def derive_enabled_zones(data: IrrigationCaddyData | None) -> list[int]:
    """Guess which zones are actually wired up, for the initial selection.

    A zone counts as in use if some program waters it, or if it has been given
    a real name on the controller — an unused output keeps the firmware's
    placeholder "Zone 5". Falls back to every zone when nothing looks
    configured, so a brand-new controller still shows a full set to work with.
    """
    if data is None:
        return list(range(1, MAX_ZONES + 1))

    max_zones = data.max_zones
    zones: set[int] = set()

    for program in data.programs:
        if not isinstance(program, dict):
            continue
        for index, duration in enumerate(program.get("zoneDuration", [])[:max_zones]):
            if not isinstance(duration, dict):
                continue
            if int(duration.get("hr", 0)) or int(duration.get("min", 0)):
                zones.add(index + 1)

    for index, name in enumerate(data.zone_names[:max_zones]):
        if _is_named(name, index + 1):
            zones.add(index + 1)

    return sorted(zones) or list(range(1, max_zones + 1))


def _is_named(name: Any, zone: int) -> bool:
    """True when a zone name is something other than the firmware placeholder."""
    if not isinstance(name, str):
        return False
    return name.strip().casefold() not in ("", f"zone {zone}", f"zone{zone}")
