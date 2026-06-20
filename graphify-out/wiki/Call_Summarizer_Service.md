# Call Summarizer Service

> 13 nodes · cohesion 0.23

## Key Concepts

- **analyze_call()** (8 connections) — `backend/app/services/call_summarizer.py`
- **call_summarizer.py** (7 connections) — `backend/app/services/call_summarizer.py`
- **str** (5 connections) — `backend/app/services/call_summarizer.py`
- **transcribe_recording()** (4 connections) — `backend/app/services/call_summarizer.py`
- **_quality_label()** (4 connections) — `backend/app/services/call_summarizer.py`
- **_finalize_evaluation()** (4 connections) — `backend/app/services/call_summarizer.py`
- **summarize_call()** (2 connections) — `backend/app/services/call_summarizer.py`
- **evaluate_call()** (2 connections) — `backend/app/services/call_summarizer.py`
- **float** (1 connections) — `backend/app/services/call_summarizer.py`
- **Derive overall_score/quality_label from the 7 graded criteria and tag the schema** (1 connections) — `backend/app/services/call_summarizer.py`
- **Single LLM pass returning (summary_dict, evaluation_dict).      evaluation_dict** (1 connections) — `backend/app/services/call_summarizer.py`
- **Single LLM pass returning (summary_dict, evaluation_dict).      Replaces calling** (1 connections) — `backend/app/services/call_summarizer.py`
- **Single LLM pass returning (summary_dict, evaluation_dict).      Replaces calling** (1 connections) — `backend/app/services/call_summarizer.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (2 shared connections)
- [[Call Coach Service]] (2 shared connections)
- [[Config]] (1 shared connections)

## Source Files

- `backend/app/services/call_summarizer.py`

## Audit Trail

- EXTRACTED: 37 (90%)
- INFERRED: 4 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*