# Callers API

> 12 nodes · cohesion 0.17

## Key Concepts

- **reassign_backlog()** (12 connections) — `backend/app/services/assignment.py`
- **update_my_status()** (9 connections) — `backend/app/routes/callers.py`
- **StatusToggle** (3 connections) — `backend/app/routes/callers.py`
- **Caller toggles their own status.** (1 connections) — `backend/app/routes/callers.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Caller toggles their own status.** (1 connections) — `backend/app/routes/callers.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Caller toggles their own status.** (1 connections) — `backend/app/routes/callers.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Caller toggles their own idle/active status.** (1 connections) — `backend/app/routes/callers.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Operator Console & Audit]] (3 shared connections)
- [[Telecaller Assignment Engine]] (3 shared connections)
- [[Callers CRUD & Coaching]] (2 shared connections)
- [[Leads API]] (1 shared connections)
- [[Assignment Service]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/routes/callers.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 28 (85%)
- INFERRED: 5 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*