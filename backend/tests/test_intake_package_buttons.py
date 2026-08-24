import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.intake import package_button_title, package_buttons


def _pkg(key, name, button_label=None):
    p = {"key": key, "name": name, "amount_paise": 10000, "description": ""}
    if button_label is not None:
        p["button_label"] = button_label
    return p


def test_title_uses_name_when_short_enough():
    assert package_button_title(_pkg("basic", "One Question")) == "One Question"


def test_title_prefers_button_label_over_name():
    assert package_button_title(_pkg("det", "Detailed Consultation", "Detailed")) == "Detailed"


def test_title_none_when_name_too_long_and_no_label():
    assert package_button_title(_pkg("det", "Detailed Consultation")) is None


def test_title_none_when_button_label_itself_too_long():
    assert package_button_title(_pkg("det", "Short", "A" * 21)) is None


def test_title_none_when_name_blank():
    assert package_button_title(_pkg("det", "   ")) is None


def test_buttons_none_for_single_package():
    assert package_buttons([_pkg("a", "One Question")]) is None


def test_buttons_none_for_four_packages():
    pkgs = [_pkg(f"k{i}", f"Name {i}") for i in range(4)]
    assert package_buttons(pkgs) is None


def test_buttons_none_when_empty():
    assert package_buttons([]) is None


def test_buttons_for_two_packages():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    assert package_buttons(pkgs) == [
        {"id": "basic", "title": "One Question"},
        {"id": "det", "title": "Detailed"},
    ]


def test_buttons_for_three_packages():
    pkgs = [_pkg("a", "Basic"), _pkg("b", "Standard"), _pkg("c", "Premium")]
    assert package_buttons(pkgs) == [
        {"id": "a", "title": "Basic"},
        {"id": "b", "title": "Standard"},
        {"id": "c", "title": "Premium"},
    ]


def test_buttons_none_when_any_package_ineligible():
    pkgs = [_pkg("a", "Basic"), _pkg("b", "Detailed Consultation")]
    assert package_buttons(pkgs) is None
