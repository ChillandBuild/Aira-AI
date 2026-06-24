# Assignment Service

> 17 nodes · cohesion 0.12

## Key Concepts

- **get_telecalling_config()** (31 connections) — `backend/app/services/assignment.py`
- **reassign_backlog()** (12 connections) — `backend/app/services/assignment.py`
- **_process_callback_reassignments()** (11 connections) — `backend/app/main.py`
- **process_callback_reassignments()** (8 connections) — `backend/app/services/assignment.py`
- **get_my_performance()** (3 connections) — `backend/app/routes/callers.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Reassign overdue callbacks from away callers to available ones.      Returns the** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Telecaller Assignment Engine]] (11 shared connections)
- [[Operator Console & Audit]] (5 shared connections)
- [[Callers API]] (4 shared connections)
- [[App Settings API]] (4 shared connections)
- [[Calls API]] (4 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Notify Service]] (3 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Telecalling Upload API]] (2 shared connections)
- [[Leads API]] (1 shared connections)
- [[Contact Recycler Service]] (1 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/routes/callers.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 50 (65%)
- INFERRED: 27 (35%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*