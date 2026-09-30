"""Handover line, escalation wording, fallback cap and refusal opt-out (2026-09-24)."""
import asyncio
from unittest.mock import MagicMock, patch

from app.services import ai_reply, business_profile, knowledge_service, scoring_engine

TENANT = "tenant-1"
LINE = "Use the Support option in our app."


HANDOVER_HEADING = "WHAT AIRA SAYS WHEN IT BRINGS IN YOUR TEAM"


def _settings(values: dict):
    return lambda key, fallback=None, tenant_id=None: values.get(key, fallback)


def _with_settings(values: dict):
    """The handover reader lives in business_profile; the rest of the prompt reads ai_reply."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(ai_reply, "get_setting", _settings(values)))
    stack.enter_context(patch.object(business_profile, "get_setting", _settings(values)))
    return stack


def test_handover_rule_uses_client_line_and_forbids_callback_promise():
    with _with_settings({"handover_line": LINE}):
        block = ai_reply._handover_rule_block(TENANT)
    assert LINE in block
    assert "Do not say anyone will contact them" in block


def test_handover_rule_quotes_the_eighth_description_section():
    description = f"ABOUT US\nWe sell sarees.\n\n{HANDOVER_HEADING}\n{LINE}"
    with _with_settings({"business_description": description}):
        assert ai_reply._handover_line(TENANT) == LINE
        assert LINE in ai_reply._handover_rule_block(TENANT)


def test_handover_line_ignores_the_legacy_setting_once_the_description_has_the_heading():
    description = f"ABOUT US\nWe sell sarees.\n\n{HANDOVER_HEADING}\nSection wording."
    with _with_settings({"business_description": description, "handover_line": "Legacy wording."}):
        assert ai_reply._handover_line(TENANT) == "Section wording."


def test_cleared_eighth_section_uses_the_default_wording_not_the_legacy_line():
    description = f"ABOUT US\nWe sell sarees.\n\n{HANDOVER_HEADING}\n"
    with _with_settings({"business_description": description, "handover_line": "Legacy wording."}):
        assert ai_reply._handover_line(TENANT) == ""
        block = ai_reply._handover_rule_block(TENANT)
    assert "Legacy wording." not in block
    assert "hand_to_human" in block and "they will reply here" in block


def test_handover_rule_default_when_client_line_missing():
    with _with_settings({}):
        block = ai_reply._handover_rule_block(TENANT)
    assert "hand_to_human" in block and "they will reply here" in block
    assert "callback" in block  # forbidden, not promised


def test_base_prompt_routes_missing_link_to_handover_rule():
    with _with_settings({"handover_line": LINE}), \
         patch.object(ai_reply, "get_master_prompt", lambda: "MASTER"):
        prompt = ai_reply._build_base_prompt("whatsapp", TENANT)
    assert "HANDOVER RULE (this business's own instruction)" in prompt
    assert "say a team member will send it" not in prompt


def test_escalation_block_with_client_line_never_promises_contact():
    block = ai_reply._escalation_prompt_block(handover_line=LINE)
    assert LINE in block
    assert "will follow up" not in block
    assert "will contact" not in block


def test_escalation_block_without_line_says_the_team_replies_here():
    block = ai_reply._escalation_prompt_block()
    assert "will reply here" in block and "Never promise a specific time" in block


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
