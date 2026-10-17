"""Value extraction from the parsed status. No Home Assistant import.

Every temperature here comes from the ``/detail`` status. ``get_temperatures()``
is never used: in flashforge-python-api 1.6.0 it goes straight to TCP port 8899,
which the Creator 5 Pro does not open, and returns ``None``.

Functions return ``None`` for "not reported", never a made-up 0, so Home
Assistant shows "unknown" instead of a false reading.
"""
from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from flashforge.models import FFMachineInfo, MachineState

TOOL_COUNT = 4
SLOT_COUNT = 4

MACHINE_STATE_OPTIONS = [state.value for state in MachineState]


def _round(value: Any, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def machine_state(data: FFMachineInfo) -> str:
    return data.machine_state.value if data.machine_state else MachineState.UNKNOWN.value


def bed_temp(data: FFMachineInfo, *, target: bool = False) -> float | None:
    if data.print_bed is None:
        return None
    return _round(data.print_bed.set if target else data.print_bed.current)


def nozzle_temp(data: FFMachineInfo, *, target: bool = False) -> float | None:
    """The active nozzle, as the firmware reports it in the top-level fields."""
    if data.extruder is None:
        return None
    return _round(data.extruder.set if target else data.extruder.current)


def tool_temp(data: FFMachineInfo, index: int, *, target: bool = False) -> float | None:
    """Per-toolhead temperature, ``index`` 0..3 (T1..T4 in the UI)."""
    tools = data.tool_temps or []
    if index >= len(tools):
        return None
    tool = tools[index]
    return _round(tool.set if target else tool.current)


def has_chamber(data: FFMachineInfo) -> bool:
    """Set by the library only when a real reading was reported (not the -108 sentinel)."""
    return bool(data.has_chamber_sensor) and data.chamber is not None


def chamber_temp(data: FFMachineInfo, *, target: bool = False) -> float | None:
    if not has_chamber(data):
        return None
    return _round(data.chamber.set if target else data.chamber.current)


def progress(data: FFMachineInfo) -> int | None:
    return data.print_progress_int


def current_file(data: FFMachineInfo) -> str | None:
    return data.print_file_name or None


def elapsed_seconds(data: FFMachineInfo) -> int | None:
    return int(data.print_duration) if data.print_duration is not None else None


def remaining_seconds(data: FFMachineInfo) -> int | None:
    value = getattr(data, "estimated_time", None)
    return int(value) if value is not None else None


def completion_time(data: FFMachineInfo, default_tz: tzinfo) -> datetime | None:
    """Absolute end time, only while PRINTING.

    The firmware freezes ``estimatedTime`` when the job is not advancing, so an
    end time computed while paused or heating would drift forward every poll.
    """
    if data.machine_state is not MachineState.PRINTING:
        return None
    ts = data.completion_time
    if ts is None:
        return None
    ts = ts.replace(second=0, microsecond=0)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=default_tz)
    return ts


def free_disk_space_gb(data: FFMachineInfo) -> float | None:
    raw = data.free_disk_space
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _station(data: FFMachineInfo):
    if not data.has_matl_station:
        return None
    return data.matl_station_info


def active_slot(data: FFMachineInfo) -> int | None:
    """Active Material Station slot 1..4, 0 when none, None without a station."""
    if not data.has_matl_station:
        return None
    station = data.matl_station_info
    return (station.current_slot or 0) if station else 0


def slot(data: FFMachineInfo, slot_id: int):
    """The slot whose ``slotId`` is ``slot_id`` (1..4), or None."""
    station = _station(data)
    if station is None:
        return None
    for info in station.slot_infos:
        if info.slot_id == slot_id:
            return info
    return None


def slot_material(data: FFMachineInfo, slot_id: int) -> str | None:
    """Material name, ``"empty"`` when the slot has no filament, None if not reported."""
    info = slot(data, slot_id)
    if info is None:
        return None
    if not info.has_filament:
        return "empty"
    name = (info.material_name or "").strip()
    return name if name and name != "?" else "unknown"


def slot_attributes(data: FFMachineInfo, slot_id: int) -> dict[str, Any]:
    info = slot(data, slot_id)
    if info is None:
        return {}
    return {
        "has_filament": info.has_filament,
        "color": info.material_color or None,
        "active": active_slot(data) == slot_id,
    }


def is_printing(data: FFMachineInfo) -> bool:
    return data.machine_state is MachineState.PRINTING


def is_paused(data: FFMachineInfo) -> bool:
    return data.machine_state in (MachineState.PAUSED, MachineState.PAUSING)


def has_problem(data: FFMachineInfo) -> bool:
    """ERROR state, or an error code. A Creator 5 Pro clog pauses with a code set."""
    return data.machine_state is MachineState.ERROR or bool(data.error_code)


def door_open(data: FFMachineInfo) -> bool | None:
    if not data.has_door_sensor:
        return None
    return bool(data.door_open)


# States in which a job exists and cancelling it means something. HEATING and
# CALIBRATING cover the warm-up and levelling before the first layer.
CANCELLABLE_STATES = frozenset(
    {
        MachineState.PRINTING,
        MachineState.PAUSING,
        MachineState.PAUSED,
        MachineState.HEATING,
        MachineState.CALIBRATING,
    }
)


def can_cancel(data: FFMachineInfo | None) -> bool:
    return data is not None and data.machine_state in CANCELLABLE_STATES


def can_pause(data: FFMachineInfo | None) -> bool:
    return data is not None and data.machine_state is MachineState.PRINTING


def can_resume(data: FFMachineInfo | None) -> bool:
    return data is not None and data.machine_state is MachineState.PAUSED


def light_on(data: FFMachineInfo) -> bool:
    """``lightStatus`` from /detail, ``"open"`` when lit."""
    return bool(data.lights_on)
