# Tests: Scoring Engine

> 12 nodes · cohesion 0.29

## Key Concepts

- **_should_score_arc()** (14 connections) — `backend/app/services/scoring_engine.py`
- **TestShouldScoreArc** (10 connections) — `backend/tests/test_scoring_engine.py`
- **bool** (2 connections) — `backend/app/services/scoring_engine.py`
- **.test_first_message_always_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_third_message_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_sixth_message_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_second_message_does_not_score()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_fourth_message_does_not_score()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_high_intent_on_second_message_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_neutral_on_non_multiple_does_not_score()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_booking_intent_on_second_message_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_active_booking_flow_on_any_message_scores()** (2 connections) — `backend/tests/test_scoring_engine.py`

## Relationships

- [[Score Engine v2 & Segmentation]] (4 shared connections)
- [[Tests: Scoring Engine]] (2 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`
- `backend/tests/test_scoring_engine.py`

## Audit Trail

- EXTRACTED: 26 (59%)
- INFERRED: 18 (41%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*