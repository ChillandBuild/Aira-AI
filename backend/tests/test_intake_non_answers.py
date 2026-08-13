import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import intake as ik


_FIELDS = [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "tob", "label": "Time of birth", "type": "text"},
    {"key": "place", "label": "Place of birth", "type": "text"},
]

_CONFIG = {
    "enabled": True, "trigger_description": "x", "offer_message": "y",
    "fields": _FIELDS, "packages": [], "service_noun": "consultation", "amount_paise": 2900,
}


@pytest.mark.parametrize("message", ["Hii", "hi", "hello", "Hey", "vanakkam", "வணக்கம்"])
def test_greetings_are_not_attempts(message):
    assert ik.classify_non_answer(message) == "greeting"


@pytest.mark.parametrize("message", ["vendaam", "Vendaam da", "cancel", "stop", "apparam pannikren", "வேண்டாம்"])
def test_withdrawals_are_cancels(message):
    assert ik.classify_non_answer(message) == "cancel"


@pytest.mark.parametrize("message", [
    "eppo astrologer contact pannuvanga?", "evlo aagum", "how long will it take?",
    "astrologer tamil la pesuvangala?",
])
def test_questions_are_questions(message):
    assert ik.classify_non_answer(message) == "question"


@pytest.mark.parametrize("message", ["theriyathu", "தெரியாது", "enaku theriyala", "no idea", "gibberish xyz"])
def test_genuine_non_answers_still_count_as_attempts(message):
    assert ik.classify_non_answer(message) == "attempt"


async def _run(session, extracted, body, sent):
    db = MagicMock()
    updates: dict = {}

    def _capture(session_id, patch_dict, _db):
        updates.update(patch_dict)

    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=session), \
         patch.object(ik, "_update_session", side_effect=_capture), \
         patch.object(ik, "extract_fields", new=AsyncMock(return_value=extracted)), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "collector_identity", return_value=""), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "compose_line", new=AsyncMock(side_effect=lambda purpose, **k: f"<{purpose}>")), \
         patch.object(ik, "compose_wrapped", new=AsyncMock(return_value="<summary>")), \
         patch.object(ik, "_send_and_log", new=AsyncMock(side_effect=lambda p, t, *a, **k: sent.append(t))):
        consumed = await ik.route_intake(lead_id="l-1", tenant_id="t-1", phone="+91", body=body, db=db)
    return consumed, updates


def _collecting_session():
    return {
        "id": "s-1", "status": "collecting",
        "collected_data": {"name": "Prem"}, "ask_attempts": {}, "skipped_fields": [],
    }


@pytest.mark.asyncio
async def test_a_greeting_does_not_burn_an_attempt():
    """Live evidence 2026-08-13: a fresh 'Hii' was recorded as the 2nd failed attempt
    at place of birth, which skipped the field and jumped to the summary."""
    sent: list[str] = []
    consumed, updates = await _run(_collecting_session(), {"name": "Prem"}, "Hii", sent)
    assert consumed is True
    assert sent == ["<greeting_reask>"]
    assert updates["ask_attempts"] == {}


@pytest.mark.asyncio
async def test_a_question_does_not_burn_an_attempt():
    sent: list[str] = []
    consumed, updates = await _run(
        _collecting_session(), {"name": "Prem"}, "eppo astrologer contact pannuvanga?", sent
    )
    assert consumed is True
    assert sent == ["<reask_field>"]
    assert updates["ask_attempts"] == {}


@pytest.mark.asyncio
async def test_a_withdrawal_cancels_and_hands_the_turn_to_the_ai():
    sent: list[str] = []
    consumed, updates = await _run(_collecting_session(), {"name": "Prem"}, "vendaam", sent)
    assert consumed is False
    assert sent == []
    assert updates["status"] == "cancelled"


@pytest.mark.asyncio
async def test_a_genuine_dont_know_still_burns_an_attempt():
    sent: list[str] = []
    consumed, updates = await _run(_collecting_session(), {"name": "Prem"}, "theriyathu", sent)
    assert consumed is True
    assert sent == ["<reask_field>"]
    assert updates["ask_attempts"] == {"tob": 1}
