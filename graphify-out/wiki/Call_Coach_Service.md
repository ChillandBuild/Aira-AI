# Call Coach Service

> 5 nodes · cohesion 0.60

## Key Concepts

- **get_coaching()** (6 connections) — `backend/app/routes/callers.py`
- **coaching_tip()** (6 connections) — `backend/app/services/call_coach.py`
- **call_coach.py** (3 connections) — `backend/app/services/call_coach.py`
- **_summarize_logs()** (3 connections) — `backend/app/services/call_coach.py`
- **str** (2 connections) — `backend/app/services/call_coach.py`

## Relationships

- [[Operator Console & Audit]] (3 shared connections)
- [[Callers CRUD & Coaching]] (2 shared connections)
- [[Callers API]] (1 shared connections)
- [[Config]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`
- `backend/app/services/call_coach.py`

## Audit Trail

- EXTRACTED: 14 (70%)
- INFERRED: 6 (30%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*