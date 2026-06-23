# Tests: Scoring Engine

> 23 nodes · cohesion 0.15

## Key Concepts

- **_compute_intent_delta()** (26 connections) — `backend/app/services/scoring_engine.py`
- **TestIntentDelta** (19 connections) — `backend/tests/test_scoring_engine.py`
- **.test_english_not_interested_returns_rejection()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_english_stop_returns_rejection()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_tamil_rejection_returns_rejection()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_hindi_rejection_returns_rejection()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_book_keyword_returns_positive()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_price_keyword_returns_positive()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_tamil_booking_keyword()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_payment_keyword_returns_positive()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_long_message_adds_delta()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_ok_in_idle_is_neutral()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_thanks_in_idle_is_neutral()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_delta_never_exceeds_3()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_delta_never_below_minus3_for_non_rejection()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_collecting_name_state_returns_plus2()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_collecting_rasi_state_returns_plus2()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_awaiting_payment_state_returns_plus2()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_collecting_name_state_returns_plus3()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_awaiting_payment_state_returns_plus3()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **Returns (delta, reason).     delta is -2..+2 or _REJECTION_SENTINEL for immediat** (1 connections) — `backend/app/services/scoring_engine.py`
- **Returns (delta, reason).     delta is -2..+2 or _REJECTION_SENTINEL for immediat** (1 connections) — `backend/app/services/scoring_engine.py`
- **Returns (delta, reason).     delta is -3..+3 or _REJECTION_SENTINEL for immediat** (1 connections) — `backend/app/services/scoring_engine.py`

## Relationships

- [[Score Engine v2 & Segmentation]] (4 shared connections)
- [[Tests: Scoring Engine]] (2 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`
- `backend/tests/test_scoring_engine.py`

## Audit Trail

- EXTRACTED: 47 (56%)
- INFERRED: 37 (44%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*