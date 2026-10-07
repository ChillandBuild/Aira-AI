"""The plug-in's core must reproduce the shared vectors exactly (same ones the backend is tested against)."""
import json
from pathlib import Path

import pytest

from anril_private_send import core

VECTORS = Path(__file__).resolve().parents[2] / "spec" / "vectors"


def _load(name):
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


COMPONENTS = _load("components.json")["cases"]
NORMALIZE = _load("normalize.json")
PARSE = _load("parse.json")["cases"]


@pytest.mark.parametrize("case", COMPONENTS, ids=[c["name"] for c in COMPONENTS])
def test_build_components(case):
    assert core.build_components(case["template"], case["rule"], case["ctx"]) == case["expected_components"]


@pytest.mark.parametrize("raw,expected", NORMALIZE["events"])
def test_normalize_event(raw, expected):
    assert core.normalize_event(raw) == expected


@pytest.mark.parametrize("raw,expected", NORMALIZE["phones"])
def test_normalize_phone(raw, expected):
    assert core.normalize_phone(raw) == expected


@pytest.mark.parametrize("case", PARSE, ids=[c["name"] for c in PARSE])
def test_parse_payload(case):
    assert core.parse_payload(case["payload"]) == case["expected"]


def test_inputs_are_not_mutated():
    case = COMPONENTS[2]
    before = json.dumps(case, sort_keys=True)
    core.build_components(case["template"], case["rule"], case["ctx"])
    assert json.dumps(case, sort_keys=True) == before
