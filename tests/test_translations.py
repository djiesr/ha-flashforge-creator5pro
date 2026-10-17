"""Every translation has the same keys and placeholders as strings.json."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "flashforge_creator5pro"
STRINGS = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
LANGS = sorted(p.stem for p in (COMPONENT / "translations").glob("*.json"))


def flatten(node, prefix=""):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}{key}."))
        return out
    return {prefix[:-1]: node}


def test_expected_languages():
    assert {"en", "fr", "es", "zh-Hans", "pt", "pt-BR"} <= set(LANGS)


@pytest.mark.parametrize("lang", LANGS)
def test_same_keys_and_placeholders(lang):
    reference = flatten(STRINGS)
    translated = flatten(
        json.loads((COMPONENT / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
    )
    assert translated.keys() == reference.keys()
    for key, text in reference.items():
        assert set(re.findall(r"{\w+}", translated[key])) == set(re.findall(r"{\w+}", text)), key
        assert translated[key].strip(), key


def test_english_matches_strings():
    en = json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8"))
    assert en == STRINGS
