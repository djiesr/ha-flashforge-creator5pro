"""Home Assistant tests. Need pytest-homeassistant-custom-component (requirements-test-ha.txt)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from flashforge.api.controls.info import MachineInfoParser
from flashforge.models import DetailResponse
import pytest

if sys.platform == "win32":
    # Windows only: asyncio builds its self-pipe from a local TCP socket pair,
    # which the harness's socket guard rejects. The printer is always mocked in
    # these tests, so lifting the guard does not let them reach the network.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None
    pytest_socket.socket_allow_hosts = lambda *args, **kwargs: None

FIXTURE =Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "detail_c5pro_printing.json"

FAKE_HOST = "192.0.2.10"
FAKE_SERIAL = "TESTSERIAL0000"
FAKE_CHECK_CODE = "TESTCODE"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def machine_info():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return MachineInfoParser.from_detail(DetailResponse(**raw).detail)
