import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import expert_handoff as eh


def _db_with_config(stored_json: str | None):
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": stored_json} if stored_json is not None else None
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    return db


def test_get_expert_handoff_config_returns_defaults_when_unset():
    db = _db_with_config(None)
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config == eh._DEFAULT_CONFIG


def test_get_expert_handoff_config_merges_stored_over_defaults():
    db = _db_with_config('{"enabled": true, "amount_paise": 2900}')
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config["enabled"] is True
    assert config["amount_paise"] == 2900
    assert config["fields"] == []  # default preserved


def test_save_expert_handoff_config_upserts_json_value():
    db = MagicMock()
    eh.save_expert_handoff_config("t-1", {"enabled": True, "amount_paise": 2900}, db=db)
    db.table.assert_called_with("app_settings")
    upsert_call = db.table.return_value.upsert
    upsert_call.assert_called_once()
    payload = upsert_call.call_args[0][0]
    assert payload["key"] == "expert_handoff_config"
    assert payload["tenant_id"] == "t-1"
    assert '"enabled": true' in payload["value"] or '"enabled":true' in payload["value"]


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_true_on_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": True})):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is True


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_false_on_no_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": False})):
        result = await eh.detect_expert_handoff_intent(
            "What are your opening hours?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_fails_closed_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


_FIELDS = [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "birthplace", "label": "Birthplace", "type": "text"},
]


def test_missing_field_labels_returns_unfilled_only():
    collected = {"name": "Priya"}
    assert eh.missing_field_labels(_FIELDS, collected) == ["Date of birth", "Birthplace"]


def test_missing_field_labels_empty_when_all_filled():
    collected = {"name": "Priya", "date_of_birth": "5 March 1995", "birthplace": "Chennai"}
    assert eh.missing_field_labels(_FIELDS, collected) == []


@pytest.mark.asyncio
async def test_extract_fields_merges_new_values_over_existing():
    llm_response = {"name": "Priya", "date_of_birth": "5 March 1995"}
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value=llm_response)):
        result = await eh.extract_fields(
            "I'm Priya, born 5 March 1995",
            fields=_FIELDS,
            collected_data={"birthplace": "Chennai"},  # already had this from an earlier turn
            tenant_id="t-1",
        )
    assert result == {"birthplace": "Chennai", "name": "Priya", "date_of_birth": "5 March 1995"}


@pytest.mark.asyncio
async def test_extract_fields_ignores_unknown_keys_from_llm():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"name": "Priya", "favorite_color": "blue"})):
        result = await eh.extract_fields("I'm Priya", fields=_FIELDS, collected_data={}, tenant_id="t-1")
    assert result == {"name": "Priya"}
    assert "favorite_color" not in result


@pytest.mark.asyncio
async def test_extract_fields_returns_unchanged_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.extract_fields("random unrelated text", fields=_FIELDS, collected_data={"name": "Priya"}, tenant_id="t-1")
    assert result == {"name": "Priya"}
