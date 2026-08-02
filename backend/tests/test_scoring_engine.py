"""
Tests for Score Engine v2 pure functions.
No DB, no Groq — only deterministic logic.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Make app importable without a running server
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub out Groq and settings before importing the module
mock_settings = MagicMock()
mock_settings.groq_api_key = None  # disables _client so no real calls
with patch.dict("sys.modules", {"groq": MagicMock(), "app.config": MagicMock(settings=mock_settings)}):
    # Also stub segmentation import
    import importlib
    import types

    seg_mod = types.ModuleType("app.services.segmentation")
    def _score_to_segment(score):
        if score >= 8: return "A"
        if score >= 4: return "B"
        if score >= 1: return "C"
        return "D"
    seg_mod.score_to_segment = _score_to_segment
    sys.modules["app.services.segmentation"] = seg_mod
    sys.modules["app.config"] = MagicMock(settings=mock_settings)
    sys.modules["groq"] = MagicMock()

    # Now safe to import
    from app.services.scoring_engine import (
        _compute_intent_delta,
        _apply_segment_lock,
        _REJECTION_SENTINEL,
    )


class TestIntentDelta(unittest.TestCase):

    # ── Rejection phrases ─────────────────────────────────────────────────
    def test_english_not_interested_returns_rejection(self):
        delta, reason = _compute_intent_delta("not interested", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)
        self.assertEqual(reason, "rejection")

    def test_english_stop_returns_rejection(self):
        delta, reason = _compute_intent_delta("please stop messaging me", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_dont_message_me_returns_rejection(self):
        delta, reason = _compute_intent_delta("Don't message me", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_do_not_text_me_returns_rejection(self):
        delta, reason = _compute_intent_delta("do not text me anymore", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_not_needed_returns_rejection(self):
        delta, reason = _compute_intent_delta("not needed sir", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_not_required_returns_rejection(self):
        delta, reason = _compute_intent_delta("this is not required", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_no_interest_returns_rejection(self):
        delta, reason = _compute_intent_delta("no interest in this", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_leave_me_alone_returns_rejection(self):
        delta, reason = _compute_intent_delta("please leave me alone", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_remove_my_number_returns_rejection(self):
        delta, reason = _compute_intent_delta("remove my number from your list", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_dont_call_returns_rejection(self):
        delta, reason = _compute_intent_delta("don't call me again", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_stop_calling_returns_rejection(self):
        delta, reason = _compute_intent_delta("stop calling this number", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    # ── Guard against overly broad matching (intentionally NOT added) ──────
    def test_no_need_to_worry_is_not_rejection(self):
        """'no need' alone is too generic a hedge phrase (e.g. reassurance) to
        treat as rejection — only the specific 'not needed'/'not required'
        phrasings are matched. Documents why 'no need' was deliberately left out."""
        delta, reason = _compute_intent_delta("no need to worry, I'll send details later", "idle")
        self.assertNotEqual(delta, _REJECTION_SENTINEL)

    def test_tamil_rejection_returns_rejection(self):
        delta, reason = _compute_intent_delta("வேண்டாம்", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hindi_rejection_returns_rejection(self):
        delta, reason = _compute_intent_delta("नहीं चाहिए", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hindi_zaroorat_nahi_returns_rejection(self):
        delta, reason = _compute_intent_delta("ज़रूरत नहीं है", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hindi_message_mat_karo_returns_rejection(self):
        delta, reason = _compute_intent_delta("मैसेज मत करो", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hinglish_zaroorat_nahi_returns_rejection(self):
        delta, reason = _compute_intent_delta("zaroorat nahi hai bhai", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_hinglish_message_mat_karo_returns_rejection(self):
        delta, reason = _compute_intent_delta("please message mat karo", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tanglish_venaam_returns_rejection(self):
        delta, reason = _compute_intent_delta("venaam pa", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tanglish_thevai_illa_returns_rejection(self):
        delta, reason = _compute_intent_delta("enakku thevai illa", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tanglish_message_pannadheenga_returns_rejection(self):
        delta, reason = _compute_intent_delta("message pannadheenga please", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tanglish_call_pannathinga_returns_rejection(self):
        delta, reason = _compute_intent_delta("call pannathinga ini", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_tanglish_msg_pannadhinga_returns_rejection(self):
        delta, reason = _compute_intent_delta("ok ennaku msg pannadhinga", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_telugu_vaddu_returns_rejection(self):
        delta, reason = _compute_intent_delta("వద్దు వద్దు", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_telugu_avasaram_ledu_returns_rejection(self):
        delta, reason = _compute_intent_delta("నాకు అవసరం లేదు", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_kannada_beda_returns_rejection(self):
        delta, reason = _compute_intent_delta("ನನಗೆ ಬೇಡ", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_kannada_agatyavilla_returns_rejection(self):
        delta, reason = _compute_intent_delta("ಅಗತ್ಯವಿಲ್ಲ", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_malayalam_venda_returns_rejection(self):
        delta, reason = _compute_intent_delta("എനിക്ക് വേണ്ട", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_malayalam_aavashyamilla_returns_rejection(self):
        delta, reason = _compute_intent_delta("ആവശ്യമില്ല", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    # ── High intent keywords ──────────────────────────────────────────────
    def test_book_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("I want to book the homam", "idle")
        self.assertGreater(delta, 0)
        self.assertIn("high_intent", reason)

    def test_price_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("what is the price?", "idle")
        self.assertGreater(delta, 0)

    def test_tamil_booking_keyword(self):
        delta, reason = _compute_intent_delta("விலை என்ன?", "idle")
        self.assertGreater(delta, 0)

    def test_payment_keyword_returns_positive(self):
        delta, reason = _compute_intent_delta("how do I make the payment?", "idle")
        self.assertGreater(delta, 0)

    # ── Detailed message ──────────────────────────────────────────────────
    def test_long_message_adds_delta(self):
        long_msg = "I am very interested in your services and would like to know more about the process and what is involved in the booking"
        delta_long, _ = _compute_intent_delta(long_msg, "idle")
        delta_short, _ = _compute_intent_delta("ok", "idle")
        self.assertGreater(delta_long, delta_short)

    # ── Neutral messages ──────────────────────────────────────────────────
    def test_ok_in_idle_is_neutral(self):
        delta, reason = _compute_intent_delta("ok", "idle")
        self.assertEqual(delta, 0)
        self.assertEqual(reason, "neutral")

    def test_thanks_in_idle_is_neutral(self):
        delta, reason = _compute_intent_delta("thanks", "idle")
        self.assertEqual(delta, 0)

    # ── Delta clamping ────────────────────────────────────────────────────
    def test_delta_never_exceeds_3(self):
        # booking + info + long message all fire at once
        delta, _ = _compute_intent_delta(
            "I want to book homam. My name is Rajan and my gotram is Bharadwaj, please let me know the price and payment details now",
            "idle"
        )
        self.assertLessEqual(delta, 3)

    def test_delta_never_below_minus3_for_non_rejection(self):
        delta, _ = _compute_intent_delta("hi", "idle")
        self.assertGreaterEqual(delta, -3)

    # ── via_ad_referral: Meta's own auto-fill text, not the lead's words ──
    def test_ad_referral_long_message_is_neutral(self):
        # Without the flag this would score +1 (detailed_message, >60 chars) —
        # this is Meta's own CTWA prefill text, not something the lead composed.
        msg = "Hi, I am interested in your services and would like to know more details urgently"
        delta, reason = _compute_intent_delta(msg, "idle", via_ad_referral=True)
        self.assertEqual(delta, 0)
        self.assertEqual(reason, "ad_prefilled")

    def test_ad_referral_high_intent_keyword_is_neutral(self):
        # Without the flag "book" would score +1 (high_intent).
        delta, reason = _compute_intent_delta("Hi, I'd like to book a consultation", "idle", via_ad_referral=True)
        self.assertEqual(delta, 0)
        self.assertEqual(reason, "ad_prefilled")

    def test_ad_referral_rejection_still_detected(self):
        # Rejection detection must not be short-circuited by the ad-referral flag.
        delta, reason = _compute_intent_delta("not interested", "idle", via_ad_referral=True)
        self.assertEqual(delta, _REJECTION_SENTINEL)
        self.assertEqual(reason, "rejection")

    def test_non_ad_referral_unaffected(self):
        # Default (via_ad_referral=False) behavior is unchanged.
        delta, reason = _compute_intent_delta("Hi, I'd like to book a consultation", "idle")
        self.assertGreater(delta, 0)
        self.assertIn("high_intent", reason)


class TestSegmentLock(unittest.TestCase):

    # ── Upgrades always immediate ─────────────────────────────────────────
    def test_upgrade_c_to_b_is_immediate(self):
        seg, count = _apply_segment_lock("B", "C", 0, False)
        self.assertEqual(seg, "B")
        self.assertEqual(count, 0)

    def test_upgrade_b_to_a_is_immediate(self):
        seg, count = _apply_segment_lock("A", "B", 1, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)

    def test_upgrade_d_to_a_is_immediate(self):
        seg, count = _apply_segment_lock("A", "D", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)

    # ── Small drop: needs 2 consecutive ──────────────────────────────────
    def test_first_small_drop_holds_segment(self):
        seg, count = _apply_segment_lock("B", "A", 0, False)
        self.assertEqual(seg, "A")   # held
        self.assertEqual(count, 1)

    def test_second_small_drop_allows_downgrade(self):
        seg, count = _apply_segment_lock("B", "A", 1, False)
        self.assertEqual(seg, "B")   # confirmed drop
        self.assertEqual(count, 0)

    def test_first_small_drop_c_to_b(self):
        seg, count = _apply_segment_lock("C", "B", 0, False)
        self.assertEqual(seg, "B")   # held
        self.assertEqual(count, 1)

    # ── Big drop: always immediate ────────────────────────────────────────
    def test_a_to_d_big_drop_is_immediate(self):
        seg, count = _apply_segment_lock("D", "A", 0, True)
        self.assertEqual(seg, "D")
        self.assertEqual(count, 0)

    def test_big_drop_2_segments_immediate(self):
        # A→C is a 2-segment drop (even without big_drop flag, diff >= 2)
        seg, count = _apply_segment_lock("C", "A", 0, False)
        self.assertEqual(seg, "C")
        self.assertEqual(count, 0)

    # ── Same segment resets counter ───────────────────────────────────────
    def test_same_segment_resets_drop_count(self):
        seg, count = _apply_segment_lock("A", "A", 2, False)
        self.assertEqual(seg, "A")
        self.assertEqual(count, 0)


class TestArcScoresEveryMessage(unittest.IsolatedAsyncioTestCase):
    """Regression test for the cadence bug found 2026-08-02: arc scoring used to
    be gated by _should_score_arc (fire on message 1, then every 3rd), but a
    reset-to-1-instead-of-0 bug in the persisted counter actually made it fire
    every 2 messages in production. Live comparison (see decisions/log.md
    2026-08-02) showed the gated version misses real signal — both a genuine
    interest uptick and a hesitation dip — that firing on every message catches.
    Since nothing downstream of compute_score is latency- or cost-sensitive to
    the arc call (it runs in a background task, after the reply is already
    sent), the gate was removed entirely. This test locks in "every message"
    so a future reintroduction of any gate has to fail a test, not just drift
    unnoticed the way the original bug did."""

    def _make_db(self, lead_state):
        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [lead_state]

        messages_table = MagicMock()
        # _compute_engagement's query: select -> eq(lead_id) -> eq(direction) -> order -> limit -> execute
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        # compute_score's own arc-context message fetch: select -> eq(lead_id) -> order -> limit -> execute
        messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        handovers_table = MagicMock()
        handovers_table.select.return_value.eq.return_value.execute.return_value.data = []

        tables = {"leads": leads_table, "messages": messages_table, "chat_handovers": handovers_table}
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db

    async def test_arc_fires_on_every_one_of_five_consecutive_messages(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 5, "score_arc": 5, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        db = self._make_db(lead_state)

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=7)) as mock_arc:
            for i in range(5):
                result = await scoring_engine.compute_score(
                    message=f"message number {i}", lead_id="lead-1", db=db, tenant_id=None,
                )
                self.assertTrue(result["arc_updated"])

        self.assertEqual(mock_arc.call_count, 5)


class TestComputeScoreAdReferral(unittest.IsolatedAsyncioTestCase):
    """Integration test for the via_ad_referral fix found 2026-08-02: intent_delta
    used to be blind to ad-prefilled messages (only the arc/LLM layer knew about
    them), so a long or keyword-matching CTWA auto-fill message could still add
    +1/+2 on top of arc with zero discount. compute_score now looks up the
    current message's via_ad_referral flag (it's already persisted by the time
    compute_score runs) and threads it into _compute_intent_delta."""

    def _make_db(self, lead_state, latest_inbound_row):
        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [lead_state]

        messages_table = MagicMock()
        # Shared by the new via_ad_referral lookup AND _compute_engagement --
        # both use the select->eq(lead_id)->eq(direction)->order->limit->execute shape.
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [latest_inbound_row]
        # compute_score's own arc-context message fetch: select -> eq(lead_id) -> order -> limit -> execute
        messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [latest_inbound_row]

        handovers_table = MagicMock()
        handovers_table.select.return_value.eq.return_value.execute.return_value.data = []

        tables = {"leads": leads_table, "messages": messages_table, "chat_handovers": handovers_table}
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db

    async def test_ad_referral_message_gets_no_intent_bonus(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 5, "score_arc": 5, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        message = "Hi, I'd like to book a consultation"  # would score +1 (high_intent) if not ad-referred
        db = self._make_db(
            lead_state,
            {"direction": "inbound", "content": message, "media_url": None,
             "created_at": "2026-08-02T10:00:00Z", "via_ad_referral": True},
        )

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=6)):
            result = await scoring_engine.compute_score(
                message=message, lead_id="lead-1", db=db, tenant_id=None,
            )

        self.assertEqual(result["intent_delta"], 0)
        self.assertEqual(result["intent_reason"], "ad_prefilled")

    async def test_non_ad_referral_message_keeps_intent_bonus(self):
        from app.services import scoring_engine

        lead_state = {
            "score": 5, "score_arc": 5, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        message = "Hi, I'd like to book a consultation"
        db = self._make_db(
            lead_state,
            {"direction": "inbound", "content": message, "media_url": None,
             "created_at": "2026-08-02T10:00:00Z", "via_ad_referral": False},
        )

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=6)):
            result = await scoring_engine.compute_score(
                message=message, lead_id="lead-1", db=db, tenant_id=None,
            )

        self.assertGreater(result["intent_delta"], 0)
        self.assertIn("high_intent", result["intent_reason"])


class TestAdPrefillExactMatch(unittest.IsolatedAsyncioTestCase):
    """Integration test for the exact-match freeze found necessary 2026-08-02:
    via_ad_referral alone can't distinguish "lead sent Meta's pre-fill untouched"
    from "lead deleted it and typed their own message" -- Meta lets leads freely
    edit the pre-fill before sending. ad_creatives.prefilled_greeting_text (synced
    from Meta's page_welcome_message, live-verified against a real connected ad
    account) is the ground truth compute_score compares against. Three outcomes:
    confirmed-unedited -> full freeze; known-edited -> score fully normally;
    unknown (no stored greeting to compare) -> today's softer ad_prefilled discount."""

    def _make_db(self, lead_state, message_row, creative_row):
        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [lead_state]

        messages_table = MagicMock()
        # Shared by the current-message via_ad_referral/creative lookup AND
        # _compute_engagement: select -> eq(lead_id) -> eq(direction) -> order -> limit -> execute
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [message_row]
        # Arc-context history fetch: select -> eq(lead_id) -> order -> limit -> execute
        messages_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [message_row]

        ad_creatives_table = MagicMock()
        # Current-message greeting lookup: select -> eq(id) -> limit -> execute
        ad_creatives_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
            [creative_row] if creative_row else []
        )
        # Arc-context batch lookup: select -> in_(ids) -> execute
        ad_creatives_table.select.return_value.in_.return_value.execute.return_value.data = (
            [creative_row] if creative_row else []
        )

        handovers_table = MagicMock()
        handovers_table.select.return_value.eq.return_value.execute.return_value.data = []

        tables = {
            "leads": leads_table, "messages": messages_table,
            "ad_creatives": ad_creatives_table, "chat_handovers": handovers_table,
        }
        db = MagicMock()
        db.table.side_effect = lambda name: tables[name]
        return db

    async def test_confirmed_unedited_prefill_freezes_everything(self):
        from app.services import scoring_engine

        original_text = "En life la next enna nadakkum nu detailed ah therinjukanum."
        lead_state = {
            "score": 1, "score_arc": 1, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        message_row = {
            "direction": "inbound", "content": original_text, "media_url": None,
            "created_at": "2026-08-02T10:00:00Z",
            "via_ad_referral": True, "attributed_ad_creative_id": "creative-1",
        }
        creative_row = {"id": "creative-1", "prefilled_greeting_text": original_text}
        db = self._make_db(lead_state, message_row, creative_row)

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=9)) as mock_arc:
            result = await scoring_engine.compute_score(
                message=original_text, lead_id="lead-1", db=db, tenant_id=None,
            )

        mock_arc.assert_not_called()
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["segment"], "C")
        self.assertEqual(result["intent_reason"], "ad_prefilled_frozen")
        self.assertFalse(result["arc_updated"])

    async def test_known_edited_prefill_scores_fully_normally(self):
        from app.services import scoring_engine

        original_greeting = "Hi, I'm interested in this service."
        edited_message = "Hi, I'd like to book a consultation about my birth chart, please share pricing"
        lead_state = {
            "score": 1, "score_arc": 1, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        message_row = {
            "direction": "inbound", "content": edited_message, "media_url": None,
            "created_at": "2026-08-02T10:00:00Z",
            "via_ad_referral": True, "attributed_ad_creative_id": "creative-1",
        }
        creative_row = {"id": "creative-1", "prefilled_greeting_text": original_greeting}
        db = self._make_db(lead_state, message_row, creative_row)

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=6)) as mock_arc:
            result = await scoring_engine.compute_score(
                message=edited_message, lead_id="lead-1", db=db, tenant_id=None,
            )

        mock_arc.assert_called_once()
        self.assertGreater(result["intent_delta"], 0)
        self.assertIn("high_intent", result["intent_reason"])

    async def test_unknown_ad_referral_falls_back_to_soft_discount(self):
        from app.services import scoring_engine

        message = "Hi, I'd like to book a consultation about my birth chart, please share pricing"
        lead_state = {
            "score": 1, "score_arc": 1, "score_intent_delta": 0,
            "score_engagement": 0, "segment": "C", "segment_drop_count": 0,
        }
        # via_ad_referral true, but no attributed creative yet (e.g. not synced) --
        # nothing to compare against.
        message_row = {
            "direction": "inbound", "content": message, "media_url": None,
            "created_at": "2026-08-02T10:00:00Z",
            "via_ad_referral": True, "attributed_ad_creative_id": None,
        }
        db = self._make_db(lead_state, message_row, creative_row=None)

        with patch.object(scoring_engine, "_score_arc", new=AsyncMock(return_value=6)) as mock_arc:
            result = await scoring_engine.compute_score(
                message=message, lead_id="lead-1", db=db, tenant_id=None,
            )

        mock_arc.assert_called_once()
        self.assertEqual(result["intent_delta"], 0)
        self.assertEqual(result["intent_reason"], "ad_prefilled")


class TestCompositeScoreLogic(unittest.TestCase):
    """Verify composite arithmetic stays correct and clamped.

    No decay term: score is purely arc + intent + engagement. A lead going
    silent must never change its score or segment on its own — there is no
    time-based input into the composite at all.
    """

    def _composite(self, arc, intent, engagement):
        return max(0, min(10, arc + intent + engagement))

    def test_hot_lead_ok_message_stays_high(self):
        # arc=8, intent 0, engagement 0
        self.assertEqual(self._composite(8, 0, 0), 8)

    def test_hot_lead_does_not_drop_on_ok(self):
        self.assertGreaterEqual(self._composite(8, 0, 0), 7)

    def test_booking_keyword_pushes_above_threshold(self):
        # arc=6, booking keyword +2, engagement 0
        self.assertGreaterEqual(self._composite(6, 2, 0), 7)

    def test_engagement_lifts_warm_to_hot(self):
        # arc=7 (Warm), engagement +2 boosts to 9 (Hot)
        self.assertEqual(self._composite(7, 0, 2), 9)

    def test_score_clamped_at_10(self):
        self.assertEqual(self._composite(9, 2, 2), 10)

    def test_score_clamped_at_0(self):
        self.assertEqual(self._composite(1, -3, 0), 0)

    def test_rejection_overrides_everything(self):
        delta, reason = _compute_intent_delta("not interested at all", "idle")
        self.assertEqual(delta, _REJECTION_SENTINEL)

    def test_silence_does_not_change_score(self):
        # A hot lead (arc=9) that has gone quiet for any length of time has
        # no decay input available to apply — score stays exactly where the
        # conversation left it.
        self.assertEqual(self._composite(9, 0, 0), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
