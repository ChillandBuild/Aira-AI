# App Entry & Schedulers

> 19 nodes · cohesion 0.12

## Key Concepts

- **_apply_engagement_decay()** (16 connections) — `backend/app/main.py`
- **apply_engagement_decay_all()** (11 connections) — `backend/app/services/scoring_engine.py`
- **score_to_segment()** (8 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **parse_thresholds()** (7 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **segmentation.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **APScheduler 6h job: decay scores for leads silent >24h.** (1 connections) — `backend/app/main.py`
- **Scheduler job: recompute engagement delta and score for all leads     that have** (1 connections) — `backend/app/services/scoring_engine.py`
- **int** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **SegmentType** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **str** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **Map a 1-10 score to a segment label per CLAUDE.md invariants.      thresholds: o** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **Parse JSON threshold string from app_settings. Returns None on any error.** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- **Scheduler job: recompute engagement delta and score for all leads     that have** (1 connections) — `backend/app/services/scoring_engine.py`
- **APScheduler 6h job: decay scores for leads silent >24h.** (1 connections) — `backend/app/main.py`
- **APScheduler 6h job: decay scores for leads silent >24h.** (1 connections) — `backend/app/main.py`
- **APScheduler 6h job: decay scores for leads silent >24h.** (1 connections) — `backend/app/main.py`
- **Scheduler job: recompute engagement delta and score for all leads     that have** (1 connections) — `backend/app/services/scoring_engine.py`
- **int** (1 connections) — `backend/app/services/segmentation.py`
- **str** (1 connections) — `backend/app/services/segmentation.py`

## Relationships

- [[Score Engine v2 & Segmentation]] (10 shared connections)
- [[Tests: Scoring Engine]] (4 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/services/segmentation.py`
- `backend/app/main.py`
- `backend/app/services/scoring_engine.py`
- `backend/app/services/segmentation.py`

## Audit Trail

- EXTRACTED: 45 (78%)
- INFERRED: 13 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*