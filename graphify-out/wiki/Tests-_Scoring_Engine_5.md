# Tests: Scoring Engine

> 13 nodes · cohesion 0.35

## Key Concepts

- **_compute_decay()** (15 connections) — `backend/app/services/scoring_engine.py`
- **TestDecay** (11 connections) — `backend/tests/test_scoring_engine.py`
- **._hours_ago()** (10 connections) — `backend/tests/test_scoring_engine.py`
- **.test_within_1_hour_is_plus3()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_6_hours_ago_is_plus1()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_18_hours_ago_is_zero()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_2_days_silent_is_minus1()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_5_days_silent_is_minus2()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_10_days_silent_is_minus3()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_45_days_silent_is_minus4()** (3 connections) — `backend/tests/test_scoring_engine.py`
- **.test_none_last_inbound_is_zero()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_naive_datetime_handled()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **Bidirectional time-decay: +3 (very recent) to -4 (stale).** (1 connections) — `backend/app/services/scoring_engine.py`

## Relationships

- [[Score Engine v2 & Segmentation]] (4 shared connections)
- [[Tests: Scoring Engine]] (3 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`
- `backend/tests/test_scoring_engine.py`

## Audit Trail

- EXTRACTED: 44 (71%)
- INFERRED: 18 (29%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*