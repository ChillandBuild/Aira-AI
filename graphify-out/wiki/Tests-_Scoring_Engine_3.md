# Tests: Scoring Engine

> 15 nodes · cohesion 0.23

## Key Concepts

- **TestCompositeScoreLogic** (15 connections) — `backend/tests/test_scoring_engine.py`
- **._composite()** (11 connections) — `backend/tests/test_scoring_engine.py`
- **.test_hot_lead_ok_message_stays_high()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_hot_lead_does_not_drop_on_ok()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_booking_keyword_pushes_above_threshold()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_decay_drifts_hot_lead()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_recency_boosts_score()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_engagement_lifts_warm_to_hot()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_score_clamped_at_10()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_score_clamped_at_1()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_rejection_overrides_everything()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_high_intent_stale_lead()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_engagement_decay_drifts_hot_lead()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **Verify composite arithmetic stays correct and clamped.** (1 connections) — `backend/tests/test_scoring_engine.py`
- **Verify composite arithmetic stays correct and clamped.** (1 connections) — `backend/tests/test_scoring_engine.py`

## Relationships

- [[Tests: Scoring Engine]] (2 shared connections)

## Source Files

- `backend/tests/test_scoring_engine.py`

## Audit Trail

- EXTRACTED: 49 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*