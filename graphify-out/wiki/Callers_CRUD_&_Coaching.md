# Callers CRUD & Coaching

> 11 nodes · cohesion 0.27

## Key Concepts

- **str** (15 connections) — `backend/app/routes/callers.py`
- **UUID** (11 connections) — `backend/app/routes/callers.py`
- **get_caller_timeline()** (8 connections) — `backend/app/routes/callers.py`
- **UpdateCaller** (7 connections) — `backend/app/routes/callers.py`
- **update_caller()** (6 connections) — `backend/app/routes/callers.py`
- **delete_caller()** (4 connections) — `backend/app/routes/callers.py`
- **list_caller_logs()** (4 connections) — `backend/app/routes/callers.py`
- **list_callers()** (3 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's exact timeline for a specific day.** (1 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's exact timeline for a specific day.** (1 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's exact timeline for a specific day.** (1 connections) — `backend/app/routes/callers.py`

## Relationships

- [[Callers API]] (19 shared connections)
- [[Operator Console & Audit]] (9 shared connections)
- [[Call Coach Service]] (2 shared connections)
- [[Pydantic Schemas]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`

## Audit Trail

- EXTRACTED: 52 (85%)
- INFERRED: 9 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*