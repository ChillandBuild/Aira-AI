"""Handover line, escalation wording, fallback cap and refusal opt-out (2026-09-24)."""
import asyncio
from unittest.mock import MagicMock, patch

from app.services import ai_reply, knowledge_service, scoring_engine

TENANT = "tenant-1"
LINE = "Use the Support option in our app."


def _settings(values: dict):
    return lambda key, fallback=None, tenant_id=None: values.get(key, fallback)


def test_handover_rule_uses_client_line_and_forbids_callback_promise():
    with patch.object(ai_reply, "get_setting", _settings({"handover_line": LINE})):
        block = ai_reply._handover_rule_block(TENANT)
    assert LINE in block
    assert "Do not say anyone will contact them" in block


def test_handover_rule_default_when_client_line_missing():
    with patch.object(ai_reply, "get_setting", _settings({})):
        block = ai_reply._handover_rule_block(TENANT)
    assert "hand_to_human" in block and "they will reply here" in block
    assert "callback" in block  # forbidden, not promised


def test_base_prompt_routes_missing_link_to_handover_rule():
    with patch.object(ai_reply, "get_setting", _settings({"handover_line": LINE})), \
         patch.object(ai_reply, "get_master_prompt", lambda: "MASTER"):
        prompt = ai_reply._build_base_prompt("whatsapp", TENANT)
    assert "HANDOVER RULE (this business's own instruction)" in prompt
    assert "say a team member will send it" not in prompt


def test_escalation_block_with_client_line_never_promises_contact():
    block = ai_reply._escalation_prompt_block({}, handover_line=LINE)
    assert LINE in block
    assert "will follow up" not in block
    assert "will contact" not in block


def test_escalation_block_without_line_keeps_team_follow_up():
    bh = {"enabled": False}
    with patch("app.services.business_hours.is_within_business_hours", return_value=True), \
         patch("app.services.business_hours.describe_hours", return_value="9-5"), \
         patch("app.services.business_hours.next_open_description", return_value="tomorrow"):
        block = ai_reply._escalation_prompt_block(bh)
    assert "will follow up" in block


def test_fallback_is_capped():
    big = "x" * (knowledge_service._FALLBACK_MAX_CHARS + 5000)
    assert len(knowledge_service._cap_fallback(big)) == knowledge_service._FALLBACK_MAX_CHARS
    assert knowledge_service._cap_fallback("short") == "short"


def test_clear_refusal_opts_the_lead_out():
    db = MagicMock()
    lead_row = {"score": 6, "score_arc": 6, "score_intent_delta": 0, "score_engagement": 0,
                "segment": "B", "segment_drop_count": 0}
    leads_table = MagicMock()
    leads_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = lead_row
    leads_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = lead_row
    messages_table = MagicMock()
    messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    db.table.side_effect = lambda name: leads_table if name == "leads" else messages_table

    result = asyncio.run(scoring_engine.compute_score(
        message="not interested, stop messaging me", lead_id="lead-1", db=db, tenant_id=None,
    ))

    assert result["segment"] == "D"
    payload = leads_table.update.call_args[0][0]
    assert payload["opted_out"] is True
    assert payload["opted_out_at"]
