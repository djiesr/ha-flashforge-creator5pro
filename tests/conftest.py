"""Tests run without Home Assistant: only the HA-free modules are imported."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "flashforge_creator5pro"))

FIXTURES = Path(__file__).parent / "fixtures"

# Obviously fake values. Real ones come only from FF_SERIAL / FF_CHECK_CODE.
FAKE_SERIAL = "TESTSERIAL0000"
FAKE_CHECK_CODE = "TESTCODE"


@pytest.fixture
def detail_printing() -> dict:
    return json.loads((FIXTURES / "detail_c5pro_printing.json").read_text(encoding="utf-8"))
