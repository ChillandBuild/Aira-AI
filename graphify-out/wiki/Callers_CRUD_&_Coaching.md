# Callers CRUD & Coaching

> 50 nodes · cohesion 0.07

## Key Concepts

- **callers.py** (28 connections) — `backend/app/routes/callers.py`
- **str** (15 connections) — `backend/app/routes/callers.py`
- **UUID** (11 connections) — `backend/app/routes/callers.py`
- **toggle_round_robin()** (8 connections) — `backend/app/routes/callers.py`
- **update_my_status()** (8 connections) — `backend/app/routes/callers.py`
- **get_digest()** (8 connections) — `backend/app/routes/callers.py`
- **UpdateCaller** (7 connections) — `backend/app/routes/callers.py`
- **get_status_summary()** (7 connections) — `backend/app/routes/callers.py`
- **get_caller_timeline()** (7 connections) — `backend/app/routes/callers.py`
- **update_caller_target()** (7 connections) — `backend/app/routes/callers.py`
- **trigger_digest()** (7 connections) — `backend/app/routes/callers.py`
- **get_round_robin()** (6 connections) — `backend/app/routes/callers.py`
- **update_caller()** (6 connections) — `backend/app/routes/callers.py`
- **get_winners()** (6 connections) — `backend/app/routes/callers.py`
- **get_coaching()** (6 connections) — `backend/app/routes/callers.py`
- **CreateCaller** (5 connections) — `backend/app/routes/callers.py`
- **get_my_status()** (5 connections) — `backend/app/routes/callers.py`
- **create_caller()** (4 connections) — `backend/app/routes/callers.py`
- **delete_caller()** (4 connections) — `backend/app/routes/callers.py`
- **list_caller_logs()** (4 connections) — `backend/app/routes/callers.py`
- **RoundRobinToggle** (3 connections) — `backend/app/routes/callers.py`
- **StatusToggle** (3 connections) — `backend/app/routes/callers.py`
- **list_callers()** (3 connections) — `backend/app/routes/callers.py`
- **TargetUpdate** (3 connections) — `backend/app/routes/callers.py`
- **get_my_calls_today()** (2 connections) — `backend/app/routes/callers.py`
- *... and 25 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (18 shared connections)
- [[Operator Console & Audit]] (6 shared connections)
- [[Leads API]] (5 shared connections)
- [[Telecaller Assignment Engine]] (5 shared connections)
- [[Assignment Service]] (2 shared connections)
- [[Tenant]] (1 shared connections)
- [[Caller Daily Digest]] (1 shared connections)
- [[Call Coach Service]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`

## Audit Trail

- EXTRACTED: 170 (85%)
- INFERRED: 30 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*