# Call Coach Service

> 7 nodes · cohesion 0.38

## Key Concepts

- **get_groq_client()** (19 connections) — `backend/app/services/groq_client.py`
- **coaching_tip()** (6 connections) — `backend/app/services/call_coach.py`
- **call_coach.py** (3 connections) — `backend/app/services/call_coach.py`
- **_summarize_logs()** (3 connections) — `backend/app/services/call_coach.py`
- **str** (2 connections) — `backend/app/services/call_coach.py`
- **str** (1 connections) — `backend/app/services/groq_client.py`
- **bool** (1 connections) — `backend/app/services/groq_client.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (2 shared connections)
- [[Ai Tune API]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Booking Flow]] (2 shared connections)
- [[Call Summarizer Service]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[Callers CRUD & Coaching]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[Caller Daily Digest]] (1 shared connections)
- [[Razorpay Payments]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Knowledge Base (pgvector RAG)]] (1 shared connections)

## Source Files

- `backend/app/services/call_coach.py`
- `backend/app/services/groq_client.py`

## Audit Trail

- EXTRACTED: 17 (49%)
- INFERRED: 18 (51%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*