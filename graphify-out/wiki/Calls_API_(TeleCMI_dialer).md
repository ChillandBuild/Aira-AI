# Calls API (TeleCMI dialer)

> 14 nodes · cohesion 0.19

## Key Concepts

- **_run_summarization()** (11 connections) — `backend/app/routes/calls.py`
- **str** (10 connections) — `backend/app/routes/calls.py`
- **_process_telecmi_recording()** (8 connections) — `backend/app/routes/calls.py`
- **generate_summary()** (8 connections) — `backend/app/routes/calls.py`
- **_should_evaluate()** (7 connections) — `backend/app/routes/calls.py`
- **bool** (3 connections) — `backend/app/routes/calls.py`
- **Download TeleCMI recording and run AI summarization.** (1 connections) — `backend/app/routes/calls.py`
- **Layer 3 gate: decide whether a call gets full AI evaluation.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`
- **Download TeleCMI recording and run AI summarization.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`
- **Download TeleCMI recording and run AI summarization.** (1 connections) — `backend/app/routes/calls.py`
- **On-demand AI summary (re)generation from a call's recording.** (1 connections) — `backend/app/routes/calls.py`
- **Download TeleCMI recording and run AI summarization.** (1 connections) — `backend/app/routes/calls.py`

## Relationships

- [[Calls API]] (11 shared connections)
- [[Operator Console & Audit]] (5 shared connections)
- [[Call Summarizer Service]] (2 shared connections)
- [[Telecaller Assignment Engine]] (1 shared connections)
- [[Knowledge Base (pgvector RAG)]] (1 shared connections)

## Source Files

- `backend/app/routes/calls.py`

## Audit Trail

- EXTRACTED: 46 (84%)
- INFERRED: 9 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*