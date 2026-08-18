"""Turning Paid Intake off must actually silence it.

route_intake bails on `enabled` (intake.py), but the two system-prompt blocks in
build_reply_system_prompt read only the lead's session rows. Before this guard, a
tenant who switched the feature off left every lead holding a `paid` or in-flight
session being told "the expert will be in touch" / "reply so the payment can
continue" forever -- pointing at a flow that no longer runs.
"""
from unittest.mock import patch

import pytest

from app.services import ai_reply
from app.services import intake


CONFIG_ON = {"enabled": True, "service_noun": "consultation"}
CONFIG_OFF = {"enabled": False, "service_noun": "consultation"}


def _build(config, *, paid=None, in_progress=None):
    with patch.object(ai_reply, "_build_base_prompt", return_value="BASE"), \
         patch.object(ai_reply, "_fetch_conversation_summary", return_value=""), \
         patch.object(ai_reply, "_resolve_reply_language_mode", return_value="english"), \
         patch.object(ai_reply, "_language_rule_block", return_value=""), \
         patch("app.config_dynamic.get_setting", return_value=""), \
         patch.object(intake, "get_intake_config", return_value=config), \
         patch.object(intake, "get_paid_unresolved_session", return_value=paid), \
         patch.object(intake, "get_in_progress_session", return_value=in_progress):
        prompt, _mode = ai_reply.build_reply_system_prompt(
            db=object(),
            lead_id="lead-1",
            tenant_id="t-1",
            lead_data={"phone": "+910000000000"},
            message="when will I get my answer?",
        )
    return prompt


def test_paid_block_is_included_while_intake_is_enabled():
    prompt = _build(CONFIG_ON, paid={"id": "sess-1"})
    assert "PAID CONSULTATION CONTEXT" in prompt


def test_in_progress_block_is_included_while_intake_is_enabled():
    prompt = _build(CONFIG_ON, in_progress={"id": "sess-1", "status": "collecting"})
    assert "CONSULTATION IN PROGRESS" in prompt


@pytest.mark.parametrize("sessions", [
    {"paid": {"id": "sess-1"}},
    {"in_progress": {"id": "sess-1", "status": "awaiting_payment"}},
])
def test_disabling_intake_drops_both_blocks(sessions):
    """The lead's stale session row no longer speaks for a feature that is off."""
    prompt = _build(CONFIG_OFF, **sessions)
    assert "IN PROGRESS" not in prompt
    assert "PAID" not in prompt
