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


def test_pending_fields_excludes_collected_and_skipped():
    pending = ik.pending_fields(_FIELDS, {"name": "Cheran"}, skipped=("tob",))
    assert [f["key"] for f in pending] == ["place"]


async def _run(session, extracted, sent):
    db = MagicMock()
    updates: dict = {}

    def _capture(session_id, patch_dict, _db):
        updates.update(patch_dict)

    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=session), \
         patch.object(ik, "_update_session", side_effect=_capture), \
         patch.object(ik, "extract_fields", new=AsyncMock(return_value=extracted)), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "compose_line", new=AsyncMock(side_effect=lambda purpose, **k: f"<{purpose}:{k.get('field_label')}>")), \
         patch.object(ik, "compose_wrapped", new=AsyncMock(return_value="<summary>")), \
         patch.object(ik, "_send_and_log", new=AsyncMock(side_effect=lambda p, t, *a, **k: sent.append(t))):
        await ik.route_intake(lead_id="l-1", tenant_id="t-1", phone="+91", body="theriyathu", db=db)
    return updates


@pytest.mark.asyncio
async def test_first_failed_answer_rephrases_instead_of_repeating():
    sent: list[str] = []
    session = {
        "id": "s-1", "status": "collecting",
        "collected_data": {"name": "Cheran"}, "ask_attempts": {}, "skipped_fields": [],
    }
    updates = await _run(session, {"name": "Cheran"}, sent)
    assert sent == ["<reask_field:Time of birth>"]
    assert updates["ask_attempts"] == {"tob": 1}
    assert updates["skipped_fields"] == []


@pytest.mark.asyncio
async def test_second_failed_answer_skips_the_field_and_moves_on():
    sent: list[str] = []
    session = {
        "id": "s-1", "status": "collecting",
        "collected_data": {"name": "Cheran"}, "ask_attempts": {"tob": 1}, "skipped_fields": [],
    }
    updates = await _run(session, {"name": "Cheran"}, sent)
    assert sent == ["<skip_field:Time of birth>"]
    assert updates["skipped_fields"] == ["tob"]


@pytest.mark.asyncio
async def test_a_useful_answer_asks_the_next_field_without_counting_an_attempt():
    sent: list[str] = []
    session = {
        "id": "s-1", "status": "collecting",
        "collected_data": {"name": "Cheran"}, "ask_attempts": {}, "skipped_fields": [],
    }
    updates = await _run(session, {"name": "Cheran", "tob": "10.45"}, sent)
    assert sent == ["<ask_field:Place of birth>"]
    assert updates["ask_attempts"] == {}


@pytest.mark.asyncio
async def test_skipping_the_last_outstanding_field_goes_to_the_summary():
    sent: list[str] = []
    session = {
        "id": "s-1", "status": "collecting",
        "collected_data": {"name": "Cheran", "place": "chidambaram"},
        "ask_attempts": {"tob": 1}, "skipped_fields": [],
    }
    updates = await _run(session, {"name": "Cheran", "place": "chidambaram"}, sent)
    assert sent == ["<summary>"]
    assert updates["skipped_fields"] == ["tob"]
    assert updates["status"] == "awaiting_confirmation"
