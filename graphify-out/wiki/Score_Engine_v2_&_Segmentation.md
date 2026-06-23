# Score Engine v2 & Segmentation

> 21 nodes · cohesion 0.16

## Key Concepts

- **compute_score()** (19 connections) — `backend/app/services/scoring_engine.py`
- **scoring_engine.py** (16 connections) — `backend/app/services/scoring_engine.py`
- **str** (11 connections) — `backend/app/services/scoring_engine.py`
- **int** (10 connections) — `backend/app/services/scoring_engine.py`
- **_score_arc()** (9 connections) — `backend/app/services/scoring_engine.py`
- **_parse_dt()** (6 connections) — `backend/app/services/scoring_engine.py`
- **_compute_engagement()** (5 connections) — `backend/app/services/scoring_engine.py`
- **_rollup_tag_interest()** (5 connections) — `backend/app/services/scoring_engine.py`
- **datetime** (4 connections) — `backend/app/services/scoring_engine.py`
- **_update_recipient_sentiment()** (4 connections) — `backend/app/services/scoring_engine.py`
- **AIRA Score Engine v2  Composite score = clamp(arc + intent_delta + engagement +** (1 connections) — `backend/app/services/scoring_engine.py`
- **Rule-based engagement score from message history. 0..+2.** (1 connections) — `backend/app/services/scoring_engine.py`
- **LLM scores the conversation thread for overall purchase intent.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **LLM scores the conversation thread for overall purchase intent.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **LLM scores the conversation thread for overall purchase intent.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Write reply_sentiment to the broadcast_recipients row for this lead.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Update lead_tag_interest with the most-recent broadcast's score.** (1 connections) — `backend/app/services/scoring_engine.py`

## Relationships

- [[Tests: Scoring Engine]] (20 shared connections)
- [[App Entry & Schedulers]] (10 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`

## Audit Trail

- EXTRACTED: 95 (95%)
- INFERRED: 5 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*