# Assignment Service

> 8 nodes · cohesion 0.25

## Key Concepts

- **_process_callback_reassignments()** (11 connections) — `backend/app/main.py`
- **is_caller_on_call()** (9 connections) — `backend/app/services/assignment.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Telecaller Assignment Engine]] (4 shared connections)
- [[Notify Service]] (3 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Contact Recycler Service]] (1 shared connections)
- [[Assignment Service]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 18 (69%)
- INFERRED: 8 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*