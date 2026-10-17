"""Value extraction from a parsed /detail payload."""
from __future__ import annotations

import copy
from datetime import timezone

from flashforge.api.controls.info import MachineInfoParser
from flashforge.models import DetailResponse, MachineState
import pytest

import values as v


def parse(raw: dict):
    return MachineInfoParser.from_detail(DetailResponse(**raw).detail)


@pytest.fixture
def info(detail_printing):
    return parse(detail_printing)


def test_state_and_progress(info):
    assert v.machine_state(info) == "printing"
    assert v.progress(info) == 42
    assert v.current_file(info) == "bracket.3mf"
    assert v.elapsed_seconds(info) == 3600
    assert v.remaining_seconds(info) == 4980
    assert v.is_printing(info) and not v.is_paused(info)


def test_temperatures_come_from_status(info):
    assert v.bed_temp(info) == 60.0
    assert v.bed_temp(info, target=True) == 60.0
    assert v.nozzle_temp(info) == pytest.approx(219.6)
    assert [v.tool_temp(info, i) for i in range(4)] == [219.6, 25.1, 24.9, 25.0]
    assert v.tool_temp(info, 0, target=True) == 220.0
    assert v.has_chamber(info)
    assert v.chamber_temp(info) == pytest.approx(35.2)


def test_missing_tool_is_none_not_zero(detail_printing):
    data = copy.deepcopy(detail_printing)
    data["detail"]["nozzleTemps"] = [200.0]
    data["detail"]["nozzleTargetTemps"] = [200.0]
    data["detail"]["nozzleCnt"] = 1
    info = parse(data)
    assert v.tool_temp(info, 3) is None


def test_chamber_sentinel_means_no_chamber(detail_printing):
    data = copy.deepcopy(detail_printing)
    data["detail"]["chamberTemp"] = -108
    info = parse(data)
    assert not v.has_chamber(info)
    assert v.chamber_temp(info) is None


def test_material_slots(info):
    assert v.active_slot(info) == 2
    assert v.slot_material(info, 1) == "PLA"
    assert v.slot_material(info, 2) == "PETG"
    assert v.slot_material(info, 3) == "empty"
    assert v.slot_material(info, 4) == "unknown"  # firmware reports "?"
    assert v.slot_attributes(info, 2) == {"has_filament": True, "color": "#FF0000", "active": True}
    assert v.slot_attributes(info, 1)["active"] is False
    assert v.slot_material(info, 5) is None


def test_no_station(detail_printing):
    data = copy.deepcopy(detail_printing)
    del data["detail"]["matlStationInfo"]
    info = parse(data)
    assert v.active_slot(info) is None
    assert v.slot_material(info, 1) is None
    assert v.slot_attributes(info, 1) == {}


def test_completion_time_only_while_printing(detail_printing):
    info = parse(detail_printing)
    ts = v.completion_time(info, timezone.utc)
    assert ts is not None and ts.tzinfo is not None and ts.second == 0

    data = copy.deepcopy(detail_printing)
    data["detail"]["status"] = "pause"
    paused = parse(data)
    assert paused.machine_state in (MachineState.PAUSED, MachineState.PAUSING)
    assert v.completion_time(paused, timezone.utc) is None
    assert v.is_paused(paused)


def test_problem_from_error_code_while_paused(detail_printing):
    """A Creator 5 Pro clog pauses the job and sets errorCode, without ERROR state."""
    data = copy.deepcopy(detail_printing)
    data["detail"]["status"] = "pause"
    data["detail"]["errorCode"] = "E0163"
    assert v.has_problem(parse(data))
    assert not v.has_problem(parse(detail_printing))


def test_door(info, detail_printing):
    assert v.door_open(info) is False
    data = copy.deepcopy(detail_printing)
    data["detail"]["doorStatus"] = "open"
    assert v.door_open(parse(data)) is True


def test_disk_space(info):
    assert v.free_disk_space_gb(info) == 10.42


def test_state_options_cover_all_states():
    assert set(v.MACHINE_STATE_OPTIONS) == {s.value for s in MachineState}


@pytest.mark.parametrize(
    ("status", "expected"),
    [("printing", True), ("pause", True), ("heating", True), ("ready", False), ("completed", False), ("cancel", False)],
)
def test_can_cancel(detail_printing, status, expected):
    data = copy.deepcopy(detail_printing)
    data["detail"]["status"] = status
    assert v.can_cancel(parse(data)) is expected


def test_can_cancel_without_data():
    assert v.can_cancel(None) is False


@pytest.mark.parametrize(
    ("status", "pause", "resume"),
    [("printing", True, False), ("pause", False, True), ("pausing", False, False),
     ("heating", False, False), ("ready", False, False)],
)
def test_can_pause_resume(detail_printing, status, pause, resume):
    data = copy.deepcopy(detail_printing)
    data["detail"]["status"] = status
    info = parse(data)
    assert v.can_pause(info) is pause
    assert v.can_resume(info) is resume


@pytest.mark.parametrize(("raw", "expected"), [("open", True), ("close", False)])
def test_light_on(detail_printing, raw, expected):
    data = copy.deepcopy(detail_printing)
    data["detail"]["lightStatus"] = raw
    assert v.light_on(parse(data)) is expected
