# Tests: Scoring Engine

> 14 nodes · cohesion 0.23

## Key Concepts

- **_apply_segment_lock()** (19 connections) — `backend/app/services/scoring_engine.py`
- **TestSegmentLock** (10 connections) — `backend/tests/test_scoring_engine.py`
- **.test_upgrade_c_to_b_is_immediate()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_upgrade_b_to_a_is_immediate()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_upgrade_d_to_a_is_immediate()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_first_small_drop_holds_segment()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_second_small_drop_allows_downgrade()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_first_small_drop_c_to_b()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_a_to_d_big_drop_is_immediate()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_big_drop_2_segments_immediate()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **.test_same_segment_resets_drop_count()** (2 connections) — `backend/tests/test_scoring_engine.py`
- **Returns (final_segment, new_drop_count).      Upgrade:            always immedia** (1 connections) — `backend/app/services/scoring_engine.py`
- **Returns (final_segment, new_drop_count).      Upgrade:            always immedia** (1 connections) — `backend/app/services/scoring_engine.py`
- **Returns (final_segment, new_drop_count).      Upgrade:            always immedia** (1 connections) — `backend/app/services/scoring_engine.py`

## Relationships

- [[Score Engine v2 & Segmentation]] (4 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Tests: Scoring Engine]] (2 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`
- `backend/tests/test_scoring_engine.py`

## Audit Trail

- EXTRACTED: 32 (64%)
- INFERRED: 18 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*