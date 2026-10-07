"""Drift guard: the shared Private Send vectors (sdk/spec/vectors/*.json) must match the backend.

The Python and Node plug-ins pass the same vectors, so if the backend's build_components,
normalize_event, parse_payload or phone normalizer changes behaviour this fails until the vectors
(sdk/spec/generate_vectors.py) and the plug-ins are updated together.
"""
import json
from pathlib import Path

import pytest

from app.routes.upload import _normalize_phone
from app.services.auto_messages import build_components, normalize_event, parse_payload

VECTORS = Path(__file__).resolve().parents[2] / "sdk" / "spec" / "vectors"


def _load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


COMPONENT_CASES = _load("components.json")["cases"]
NORMALIZE = _load("normalize.json")
PARSE_CASES = _load("parse.json")["cases"]


def test_vectors_are_not_empty():
    assert len(COMPONENT_CASES) >= 30
    assert len(NORMALIZE["events"]) >= 20
    assert len(NORMALIZE["phones"]) >= 20
    assert len(PARSE_CASES) >= 5


@pytest.mark.parametrize("case", COMPONENT_CASES, ids=[c["name"] for c in COMPONENT_CASES])
def test_build_components_matches_vector(case):
    assert build_components(case["template"], case["rule"], case["ctx"]) == case["expected_components"]


@pytest.mark.parametrize("raw,expected", NORMALIZE["events"])
def test_normalize_event_matches_vector(raw, expected):
    assert normalize_event(raw) == expected


@pytest.mark.parametrize("raw,expected", NORMALIZE["phones"])
def test_normalize_phone_matches_vector(raw, expected):
    assert _normalize_phone(raw) == expected


@pytest.mark.parametrize("case", PARSE_CASES, ids=[c["name"] for c in PARSE_CASES])
def test_parse_payload_matches_vector(case):
    assert parse_payload(case["payload"]) == case["expected"]
