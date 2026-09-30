"""Aira Brain handovers: reason classification and the likely message."""
import pytest

from app.services.ai_reply import _TRIGGER_REASONS
from app.services.brain import handovers
from app.services.deal_turn import TEAM_CLAIM_REASON
from brain_helpers import BrainDB

T1, T2 = "tenant-1", "tenant-2"


@pytest.mark.parametrize("reason, kind", [
    ("User requested a human agent", "asked_for_human"),
    (TEAM_CLAIM_REASON, "knowledge_gap"),
    ("Aira told the customer it is checking with the team", "knowledge_gap"),
    (_TRIGGER_REASONS["B"], "knowledge_gap"),   # AI failed to generate a response
    (_TRIGGER_REASONS["A"], "knowledge_gap"),   # generic fallback reply
    (_TRIGGER_REASONS["F"], "knowledge_gap"),   # AI said the team will follow up
    ("Payment link could not be created for a package", "payment"),
    ("Payment link could not be created for a product order", "payment"),
    (_TRIGGER_REASONS["D"], "other"),           # repeated the same question
    ("something new", "other"),
    ("", "other"),
    (None, "other"),
])
def test_reason_classification(reason, kind):
    assert handovers.classify_reason(reason) == kind


def _msg(db, tenant, lead, content, created_at, direction="inbound"):
    db.add("messages", tenant_id=tenant, lead_id=lead, content=content, direction=direction, created_at=created_at)


class TestLikelyQuestion:
    def test_latest_inbound_at_or_before_opened_at(self):
        db = BrainDB()
        _msg(db, T1, "L", "old question", "2026-09-28T10:00:00")
        _msg(db, T1, "L", "the real question", "2026-09-29T10:00:00")
        _msg(db, T1, "L", "sent after the handover", "2026-09-29T10:05:00")
        _msg(db, T1, "L", "our reply", "2026-09-29T10:00:30", direction="outbound")
        assert handovers.likely_question(db, T1, "L", "2026-09-29T10:00:00") == "the real question"

    def test_no_inbound_message_gives_none(self):
        assert handovers.likely_question(BrainDB(), T1, "L", "2026-09-29T10:00:00") is None

    def test_other_tenants_message_is_never_used(self):
        db = BrainDB()
        _msg(db, T2, "L", "leaked", "2026-09-29T09:00:00")
        assert handovers.likely_question(db, T1, "L", "2026-09-29T10:00:00") is None

    def test_long_message_is_trimmed(self):
        db = BrainDB()
        _msg(db, T1, "L", "x" * 1000, "2026-09-29T09:00:00")
        assert len(handovers.likely_question(db, T1, "L", "2026-09-29T10:00:00")) == handovers.QUESTION_MAX_CHARS


class TestRecentHandovers:
    def test_rows_carry_kind_question_and_are_tenant_scoped(self):
        db = BrainDB()
        h = db.add("chat_handovers", tenant_id=T1, lead_id="L", reason="User requested a human agent", opened_at="2026-09-29T10:00:00")
        db.add("chat_handovers", tenant_id=T2, lead_id="Z", reason="User requested a human agent", opened_at="2026-09-29T10:00:00")
        db.add("chat_handovers", tenant_id=T1, lead_id="M", reason="x", opened_at="2026-09-01T10:00:00")  # before the window
        _msg(db, T1, "L", "can I talk to someone", "2026-09-29T09:59:58")
        result = handovers.recent_handovers(db, T1, "2026-09-24T00:00:00")
        assert result == [{
            "handover_id": h["id"], "lead_id": "L", "reason": "User requested a human agent",
            "kind": "asked_for_human", "likely_question": "can I talk to someone", "opened_at": "2026-09-29T10:00:00",
        }]
