"""Aira Brain headline: per-chat aggregation over the last 7 days in Asia/Kolkata.

AI vs human replies (verified in ai_reply.py / routes/leads.py, see services/brain/headline.py):
  Aira answer      is_ai_generated true,  reply_source ai|knowledge
  human reply      is_ai_generated false, reply_source null
  LLM-error canned is_ai_generated false, reply_source ai   (ai_reply.py:2005-2007)
  follow-up        is_ai_generated true,  reply_source null  (routes/follow_ups.py:105-112)"""
from datetime import datetime

from app.services.ai_reply import _TRIGGER_REASONS
from app.services.brain import headline
from app.services.deal_turn import TEAM_CLAIM_REASON
from brain_helpers import BrainDB

T1, T2 = "tenant-1", "tenant-2"
NOW = datetime(2026, 9, 30, 15, 0, tzinfo=headline.IST)


def _in(lead):
    return {"lead_id": lead, "direction": "inbound", "is_ai_generated": False, "reply_source": None}


def _aira(lead, source="ai"):
    return {"lead_id": lead, "direction": "outbound", "is_ai_generated": True, "reply_source": source}


def _human(lead):
    return {"lead_id": lead, "direction": "outbound", "is_ai_generated": False, "reply_source": None}


class TestAggregate:
    def test_matches_the_blueprint_example_shape(self):
        messages = [_in("a"), _aira("a"), _in("b"), _aira("b", "knowledge"), _in("c"), _in("d"), _aira("d")]
        handovers = [{"lead_id": "d", "reason": _TRIGGER_REASONS["C"]}]
        result = headline.aggregate(messages, handovers)
        assert result == {
            "chats": 4, "handled_by_aira": 2, "handed_over": 1, "unanswered": 1,
            "window_days": 7, "asked_for_human": 1, "knowledge_gaps": 0,
        }

    def test_human_reply_does_not_count_as_aira(self):
        result = headline.aggregate([_in("a"), _human("a")], [])
        assert result["handled_by_aira"] == 0 and result["unanswered"] == 1

    def test_llm_error_canned_reply_is_not_an_aira_answer(self):
        canned = {"lead_id": "a", "direction": "outbound", "is_ai_generated": False, "reply_source": "ai"}
        assert headline.aggregate([_in("a"), canned], [])["handled_by_aira"] == 0

    def test_follow_up_is_not_an_aira_answer(self):
        followup = {"lead_id": "a", "direction": "outbound", "is_ai_generated": True, "reply_source": None}
        assert headline.aggregate([_in("a"), followup], [])["handled_by_aira"] == 0

    def test_a_chat_with_a_handover_is_handed_over_even_if_aira_replied(self):
        result = headline.aggregate([_in("a"), _aira("a")], [{"lead_id": "a", "reason": TEAM_CLAIM_REASON}])
        assert (result["handed_over"], result["handled_by_aira"], result["knowledge_gaps"]) == (1, 0, 1)

    def test_outbound_only_leads_are_not_chats(self):
        assert headline.aggregate([_aira("a")], [])["chats"] == 0

    def test_handover_for_a_lead_with_no_inbound_in_window_is_ignored(self):
        assert headline.aggregate([_in("a")], [{"lead_id": "old", "reason": TEAM_CLAIM_REASON}])["handed_over"] == 0

    def test_a_chat_with_two_handovers_counts_once_under_its_top_reason(self):
        handovers = [
            {"lead_id": "a", "reason": "Payment link could not be created for a package"},
            {"lead_id": "a", "reason": _TRIGGER_REASONS["C"]},
        ]
        result = headline.aggregate([_in("a")], handovers)
        assert (result["handed_over"], result["asked_for_human"]) == (1, 1)

    def test_buckets_always_add_up_to_chats(self):
        messages = [_in("a"), _in("b"), _in("c"), _aira("a")]
        r = headline.aggregate(messages, [{"lead_id": "b", "reason": "x"}])
        assert r["handled_by_aira"] + r["handed_over"] + r["unanswered"] == r["chats"]


class TestWindow:
    def test_window_starts_at_ist_midnight_six_days_back(self):
        assert headline.window_start(NOW).isoformat() == "2026-09-24T00:00:00+05:30"

    def test_a_late_utc_evening_is_already_tomorrow_in_ist(self):
        late_utc = datetime.fromisoformat("2026-09-30T20:00:00+00:00")  # 01:30 IST on 1 Oct
        assert headline.window_start(late_utc).isoformat() == "2026-09-25T00:00:00+05:30"


class TestBuildHeadline:
    def test_reads_only_this_tenant_and_only_inside_the_window(self):
        db = BrainDB()
        inside, before = "2026-09-25T10:00:00+05:30", "2026-09-20T10:00:00+05:30"
        db.add("messages", tenant_id=T1, lead_id="a", direction="inbound", is_ai_generated=False, created_at=inside)
        db.add("messages", tenant_id=T1, lead_id="a", direction="outbound", is_ai_generated=True, reply_source="ai", created_at=inside)
        db.add("messages", tenant_id=T1, lead_id="old", direction="inbound", is_ai_generated=False, created_at=before)
        db.add("messages", tenant_id=T2, lead_id="x", direction="inbound", is_ai_generated=False, created_at=inside)
        db.add("chat_handovers", tenant_id=T2, lead_id="x", reason=_TRIGGER_REASONS["C"], opened_at=inside)
        result = headline.build_headline(db, T1, now=NOW)
        assert (result["chats"], result["handled_by_aira"], result["handed_over"]) == (1, 1, 0)

    def test_pages_past_the_1000_row_postgrest_cap(self):
        db = BrainDB()
        stamp = "2026-09-26T10:00:00+05:30"
        for i in range(1005):
            db.add("messages", tenant_id=T1, lead_id=f"lead-{i}", direction="inbound", is_ai_generated=False, created_at=stamp)
        assert headline.build_headline(db, T1, now=NOW)["chats"] == 1005


class _OrderRecordingDB(BrainDB):
    """Remembers every .order() call made on the messages table, in call order."""
    def __init__(self):
        super().__init__()
        self.message_orders: list[tuple] = []

    def table(self, name):
        query = super().table(name)
        if name != "messages":
            return query
        original = query.order

        def order(column, desc=False):
            self.message_orders.append((column, desc))
            return original(column, desc)

        query.order = order
        return query


class TestPagingIsStable:
    def test_the_paged_messages_query_ends_with_a_unique_id_tiebreaker(self):
        db = _OrderRecordingDB()
        db.add("messages", tenant_id=T1, lead_id="a", direction="inbound", is_ai_generated=False,
               created_at="2026-09-26T10:00:00+05:30")
        headline.build_headline(db, T1, now=NOW)
        assert db.message_orders == [("created_at", False), ("id", False)]


class TestHeadlineCache:
    @staticmethod
    def _db_with_chats(count):
        db = BrainDB()
        for i in range(count):
            db.add("messages", tenant_id=T1, lead_id=f"lead-{i}", direction="inbound", is_ai_generated=False,
                   created_at="2026-09-26T10:00:00+05:30")
        return db

    def test_a_second_call_inside_the_ttl_reuses_the_result(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(headline.time, "monotonic", lambda: clock[0])
        first = headline.build_headline(self._db_with_chats(1), T1, now=NOW)
        clock[0] += headline.CACHE_TTL_SECONDS - 1
        second = headline.build_headline(self._db_with_chats(3), T1, now=NOW)
        assert first["chats"] == second["chats"] == 1

    def test_the_result_is_recomputed_after_the_ttl(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(headline.time, "monotonic", lambda: clock[0])
        headline.build_headline(self._db_with_chats(1), T1, now=NOW)
        clock[0] += headline.CACHE_TTL_SECONDS + 1
        assert headline.build_headline(self._db_with_chats(3), T1, now=NOW)["chats"] == 3

    def test_the_cache_is_per_tenant(self):
        headline.build_headline(self._db_with_chats(1), T1, now=NOW)
        assert headline.build_headline(BrainDB(), T2, now=NOW)["chats"] == 0

    def test_clear_cache_forgets_everything(self):
        headline.build_headline(self._db_with_chats(1), T1, now=NOW)
        headline.clear_cache()
        assert headline.build_headline(self._db_with_chats(3), T1, now=NOW)["chats"] == 3

    def test_a_caller_cannot_change_the_cached_result(self):
        first = headline.build_headline(self._db_with_chats(1), T1, now=NOW)
        first["chats"] = 999
        assert headline.build_headline(self._db_with_chats(1), T1, now=NOW)["chats"] == 1
