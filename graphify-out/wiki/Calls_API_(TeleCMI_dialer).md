# Calls API (TeleCMI dialer)

> 15 nodes · cohesion 0.20

## Key Concepts

- **calls.py** (24 connections) — `backend/app/routes/calls.py`
- **_run_summarization()** (11 connections) — `backend/app/routes/calls.py`
- **set_outcome()** (11 connections) — `backend/app/routes/calls.py`
- **str** (10 connections) — `backend/app/routes/calls.py`
- **generate_summary()** (8 connections) — `backend/app/routes/calls.py`
- **_should_evaluate()** (7 connections) — `backend/app/routes/calls.py`
- **OutcomeUpdate** (3 connections) — `backend/app/routes/calls.py`
- **recent_by_leads()** (3 connections) — `backend/app/routes/calls.py`
- **int** (2 connections) — `backend/app/routes/calls.py`
- **stats_today()** (2 connections) — `backend/app/routes/calls.py`
- **get_pending_wrapups()** (2 connections) — `backend/app/routes/calls.py`
- **Layer 3 gate: decide whether a call gets full AI evaluation.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`

## Relationships

- [[Calls API]] (14 shared connections)
- [[Operator Console & Audit]] (13 shared connections)
- [[Telecaller Assignment Engine]] (4 shared connections)
- [[Call Summarizer Service]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[Knowledge Base (pgvector RAG)]] (1 shared connections)

## Source Files

- `backend/app/routes/calls.py`

## Audit Trail

- EXTRACTED: 68 (78%)
- INFERRED: 19 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*