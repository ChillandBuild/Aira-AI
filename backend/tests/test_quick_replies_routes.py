import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.routes.quick_replies import slugify_label, validate_block

_OK_BUTTONS = [{"id": "menu", "label": "Menu card"}]


def test_validate_accepts_a_good_block():
    validate_block("Menu options", "lead asks about food", "What would you like?", _OK_BUTTONS)


def test_validate_rejects_blank_name():
    with pytest.raises(HTTPException) as e:
        validate_block("  ", "lead asks about food", "Body", _OK_BUTTONS)
    assert e.value.status_code == 400


def test_validate_rejects_blank_use_when():
    with pytest.raises(HTTPException):
        validate_block("Menu", "", "Body", _OK_BUTTONS)


def test_validate_rejects_blank_body():
    with pytest.raises(HTTPException):
        validate_block("Menu", "asks food", "   ", _OK_BUTTONS)


def test_validate_rejects_zero_buttons():
    with pytest.raises(HTTPException, match="1 and 3"):
        validate_block("Menu", "asks food", "Body", [])


def test_validate_rejects_four_buttons():
    buttons = [{"id": f"b{i}", "label": f"B{i}"} for i in range(4)]
    with pytest.raises(HTTPException, match="1 and 3"):
        validate_block("Menu", "asks food", "Body", buttons)


def test_validate_rejects_long_button_label():
    with pytest.raises(HTTPException, match="20 characters"):
        validate_block("Menu", "asks food", "Body", [{"id": "a", "label": "A" * 21}])


def test_validate_rejects_blank_button_label():
    with pytest.raises(HTTPException, match="empty"):
        validate_block("Menu", "asks food", "Body", [{"id": "a", "label": "   "}])


def test_validate_rejects_body_over_1024():
    with pytest.raises(HTTPException, match="1024"):
        validate_block("Menu", "asks food", "x" * 1025, _OK_BUTTONS)


def test_slugify_label_makes_a_stable_id():
    assert slugify_label("Menu card") == "menu_card"
    assert slugify_label("Book a Table!") == "book_a_table"


def test_slugify_label_falls_back_when_nothing_survives():
    assert slugify_label("!!!") == "option"
