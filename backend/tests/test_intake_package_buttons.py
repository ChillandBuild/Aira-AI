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


from unittest.mock import AsyncMock, patch

import pytest

from app.services.intake import match_package


@pytest.mark.asyncio
async def test_match_package_matches_button_label_without_llm():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("Detailed", pkgs, "tenant-1")
    assert result["key"] == "det"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_match_package_button_label_is_case_insensitive():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("  detailed  ", pkgs, "tenant-1")
    assert result["key"] == "det"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_match_package_still_matches_name_without_llm():
    pkgs = [_pkg("basic", "One Question"), _pkg("det", "Detailed Consultation", "Detailed")]
    with patch("app.services.intake.gemini_chat_completion_json", new=AsyncMock()) as llm:
        result = await match_package("One Question", pkgs, "tenant-1")
    assert result["key"] == "basic"
    llm.assert_not_called()


from unittest.mock import MagicMock

from app.services.intake import _send_buttons_and_log

_BUTTONS = [{"id": "basic", "title": "One Question"}, {"id": "det", "title": "Detailed"}]


def _fake_db():
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value = MagicMock()
    return db


@pytest.mark.asyncio
async def test_send_buttons_logs_body_and_labels():
    db = _fake_db()
    send = AsyncMock(return_value={"messages": [{"id": "wamid.9"}]})
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)

    send.assert_awaited_once()
    logged = db.table.return_value.insert.call_args[0][0]
    assert logged["content"] == "Pick one\n\n[One Question] [Detailed]"
    assert logged["meta_message_id"] == "wamid.9"
    assert logged["channel"] == "whatsapp"
    assert logged["reply_source"] == "expert_handoff"


@pytest.mark.asyncio
async def test_send_buttons_falls_back_to_text_when_send_fails():
    db = _fake_db()
    send = AsyncMock(side_effect=RuntimeError("meta down"))
    fallback = AsyncMock()
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        with patch("app.services.intake._send_and_log", new=fallback):
            await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)

    fallback.assert_awaited_once_with("+919000000000", "Pick one", "t1", "l1", db)


@pytest.mark.asyncio
async def test_send_buttons_falls_back_when_body_too_long():
    db = _fake_db()
    long_body = "x" * 1025
    send = AsyncMock()
    fallback = AsyncMock()
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        with patch("app.services.intake._send_and_log", new=fallback):
            await _send_buttons_and_log("+919000000000", long_body, _BUTTONS, "t1", "l1", db)

    send.assert_not_awaited()
    fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_buttons_never_raises_when_logging_fails():
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("constraint")
    send = AsyncMock(return_value={"messages": [{"id": "wamid.9"}]})
    with patch("app.services.meta_cloud.send_interactive_buttons", new=send):
        await _send_buttons_and_log("+919000000000", "Pick one", _BUTTONS, "t1", "l1", db)
    # No assertion needed: the test fails if this raises.
