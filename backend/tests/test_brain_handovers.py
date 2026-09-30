"""Aira Brain handovers: reason classification and the likely message."""
from datetime import datetime, timezone

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


class TestCustomerMessagesNeedConversationsView:
    """lead_id and the customer's message are conversation data: knowledge.view alone must not see them."""

    @staticmethod
    def _seeded():
        db = BrainDB()
        db.add("chat_handovers", tenant_id=T1, lead_id="L", reason="User requested a human agent", opened_at="2026-09-29T10:00:00")
        _msg(db, T1, "L", "my card number is 4111", "2026-09-29T09:59:58")
        return db

    def test_recent_handovers_can_leave_the_message_and_lead_out(self):
        rows = handovers.recent_handovers(self._seeded(), T1, "2026-09-24T00:00:00", include_conversation=False)
        assert len(rows) == 1
        assert rows[0]["likely_question"] is None and rows[0]["lead_id"] is None
        assert rows[0]["kind"] == "asked_for_human" and rows[0]["opened_at"] == "2026-09-29T10:00:00"
        assert rows[0]["reason"] == "User requested a human agent"

    def test_recent_handovers_reads_no_messages_when_they_are_hidden(self):
        db = self._seeded()
        tables: list[str] = []
        original = db.table
        db.table = lambda name: tables.append(name) or original(name)
        handovers.recent_handovers(db, T1, "2026-09-24T00:00:00", include_conversation=False)
        assert "messages" not in tables

    @pytest.mark.parametrize("role, perms, visible", [
        ("caller", ["knowledge.view"], False),
        ("caller", ["knowledge.view", "conversations.view"], True),
        ("caller", ["knowledge.view", "conversations.manage"], True),
        ("caller", ["knowledge.view", "conversations.reply"], True),
        ("owner", [], True),
    ])
    def test_build_brain_hides_them_without_conversations_view(self, role, perms, visible, monkeypatch):
        from app.services import brain
        monkeypatch.setattr(brain.status, "build_status", lambda *a, **k: {})
        monkeypatch.setattr(brain.inputs, "build_inputs", lambda *a, **k: [])
        monkeypatch.setattr(brain.waiting, "waiting_summary", lambda *a, **k: {})
        monkeypatch.setattr(brain.headline, "window_start", lambda now: datetime(2026, 9, 24, tzinfo=timezone.utc))
        monkeypatch.setattr(brain.headline, "build_headline", lambda *a, **k: {})
        row = brain.build_brain(T1, role=role, permissions=perms, db=self._seeded())["handovers"][0]
        assert (row["likely_question"] is not None) is visible
        assert (row["lead_id"] is not None) is visible
        assert row["kind"] == "asked_for_human"

    def test_the_operator_still_sees_them(self):
        from app.services import operator_brain
        from app.services.brain.access import has_permission
        assert has_permission(None, operator_brain.OPERATOR_VIEW_PERMISSIONS, "conversations.view")
