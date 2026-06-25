# Callers CRUD & Coaching

> 33 nodes · cohesion 0.11

## Key Concepts

- **callers.py** (28 connections) — `backend/app/routes/callers.py`
- **str** (15 connections) — `backend/app/routes/callers.py`
- **UUID** (11 connections) — `backend/app/routes/callers.py`
- **get_digest()** (9 connections) — `backend/app/routes/callers.py`
- **get_status_summary()** (8 connections) — `backend/app/routes/callers.py`
- **get_caller_timeline()** (8 connections) — `backend/app/routes/callers.py`
- **trigger_digest()** (8 connections) — `backend/app/routes/callers.py`
- **UpdateCaller** (7 connections) — `backend/app/routes/callers.py`
- **update_caller_target()** (7 connections) — `backend/app/routes/callers.py`
- **update_caller()** (6 connections) — `backend/app/routes/callers.py`
- **get_coaching()** (6 connections) — `backend/app/routes/callers.py`
- **CreateCaller** (5 connections) — `backend/app/routes/callers.py`
- **create_caller()** (4 connections) — `backend/app/routes/callers.py`
- **delete_caller()** (4 connections) — `backend/app/routes/callers.py`
- **list_caller_logs()** (4 connections) — `backend/app/routes/callers.py`
- **list_callers()** (3 connections) — `backend/app/routes/callers.py`
- **TargetUpdate** (3 connections) — `backend/app/routes/callers.py`
- **get_my_calls_today()** (2 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (2 connections) — `backend/app/routes/callers.py`
- **int** (1 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's status breakdown for today.** (1 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's exact timeline for a specific day.** (1 connections) — `backend/app/routes/callers.py`
- **Return the last N days of coaching digests for a caller.** (1 connections) — `backend/app/routes/callers.py`
- **Manually trigger today's digest for a caller (owner only, for testing).** (1 connections) — `backend/app/routes/callers.py`
- **Admin views a caller's status breakdown for today.** (1 connections) — `backend/app/routes/callers.py`
- *... and 8 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (20 shared connections)
- [[Callers API]] (11 shared connections)
- [[Leads API]] (3 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Assignment Service]] (1 shared connections)
- [[Caller Daily Digest]] (1 shared connections)
- [[Call Coach Service]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`

## Audit Trail

- EXTRACTED: 132 (86%)
- INFERRED: 22 (14%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*