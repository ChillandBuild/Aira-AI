# Score Engine v2 & Segmentation

> 17 nodes · cohesion 0.19

## Key Concepts

- **compute_score()** (16 connections) — `backend/app/services/scoring_engine.py`
- **scoring_engine.py** (14 connections) — `backend/app/services/scoring_engine.py`
- **str** (10 connections) — `backend/app/services/scoring_engine.py`
- **int** (8 connections) — `backend/app/services/scoring_engine.py`
- **_score_arc()** (8 connections) — `backend/app/services/scoring_engine.py`
- **_parse_dt()** (6 connections) — `backend/app/services/scoring_engine.py`
- **_rollup_tag_interest()** (5 connections) — `backend/app/services/scoring_engine.py`
- **_update_recipient_sentiment()** (4 connections) — `backend/app/services/scoring_engine.py`
- **datetime** (3 connections) — `backend/app/services/scoring_engine.py`
- **AIRA Score Engine v2  Composite score = clamp(arc + intent_delta + engagement_de** (1 connections) — `backend/app/services/scoring_engine.py`
- **LLM scores the conversation thread for overall purchase intent.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **LLM scores the conversation thread for overall purchase intent.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Main entry point. Computes composite score, persists to DB, returns breakdown.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Write reply_sentiment to the broadcast_recipients row for this lead.** (1 connections) — `backend/app/services/scoring_engine.py`
- **Update lead_tag_interest with the most-recent broadcast's score.** (1 connections) — `backend/app/services/scoring_engine.py`

## Relationships

- [[Tests: Scoring Engine]] (16 shared connections)
- [[App Entry & Schedulers]] (10 shared connections)
- [[Config]] (1 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/services/scoring_engine.py`

## Audit Trail

- EXTRACTED: 77 (94%)
- INFERRED: 5 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*