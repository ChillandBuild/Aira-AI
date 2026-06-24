# Callers API

> 10 nodes · cohesion 0.20

## Key Concepts

- **get_digest()** (9 connections) — `backend/app/routes/callers.py`
- **trigger_digest()** (8 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (2 connections) — `backend/app/routes/callers.py`
- **int** (1 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (1 connections) — `backend/app/routes/callers.py`
- **Manually trigger today's digest for a caller (owner only, for testing).** (1 connections) — `backend/app/routes/callers.py`
- **Manually trigger today's digest for a caller (owner only, for testing).** (1 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (1 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (1 connections) — `backend/app/routes/callers.py`
- **Manually trigger today's digest for a caller (owner only, for testing).** (1 connections) — `backend/app/routes/callers.py`

## Relationships

- [[Callers CRUD & Coaching]] (4 shared connections)
- [[Callers API]] (2 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Caller Daily Digest]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`

## Audit Trail

- EXTRACTED: 24 (92%)
- INFERRED: 2 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*