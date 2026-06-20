# Assignment Service

> 14 nodes · cohesion 0.14

## Key Concepts

- **get_telecalling_config()** (27 connections) — `backend/app/services/assignment.py`
- **_process_callback_reassignments()** (9 connections) — `backend/app/main.py`
- **should_escalate_to_inbox()** (8 connections) — `backend/app/services/assignment.py`
- **get_my_performance()** (3 connections) — `backend/app/routes/callers.py`
- **get_assignment_mode()** (2 connections) — `backend/app/routes/calls.py`
- **Return telecalling_config from app_settings, merged with defaults.** (2 connections) — `backend/app/services/assignment.py`
- **Return True if this trigger should create an inbox handover.     Trigger C alway** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **APScheduler job: escalate overdue callbacks from inactive/busy callers (no auto-** (1 connections) — `backend/app/main.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this trigger should create an inbox handover.     Trigger C alway** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this trigger should create an inbox handover.     Trigger C alway** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Telecaller Assignment Engine]] (10 shared connections)
- [[Calls API (TeleCMI dialer)]] (8 shared connections)
- [[App Settings API]] (4 shared connections)
- [[Callers CRUD & Coaching]] (2 shared connections)
- [[Telecalling Upload API]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Assignment Service]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Contact Recycler Service]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/routes/callers.py`
- `backend/app/routes/calls.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 36 (61%)
- INFERRED: 23 (39%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*