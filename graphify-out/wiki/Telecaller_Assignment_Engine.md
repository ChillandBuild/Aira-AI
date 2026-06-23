# Telecaller Assignment Engine

> 24 nodes · cohesion 0.12

## Key Concepts

- **get_telecalling_config()** (31 connections) — `backend/app/services/assignment.py`
- **auto_assign_lead()** (20 connections) — `backend/app/services/assignment.py`
- **assignment.py** (19 connections) — `backend/app/services/assignment.py`
- **maybe_assign_lead()** (16 connections) — `backend/app/services/assignment.py`
- **process_callback_reassignments()** (8 connections) — `backend/app/services/assignment.py`
- **int** (6 connections) — `backend/app/services/assignment.py`
- **_in_shift_caller_ids()** (6 connections) — `backend/app/services/assignment.py`
- **_open_lead_count()** (5 connections) — `backend/app/services/assignment.py`
- **get_my_performance()** (3 connections) — `backend/app/routes/callers.py`
- **get_telecalling_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **get_assignment_mode()** (2 connections) — `backend/app/routes/calls.py`
- **Active workload for a caller = assigned leads that are still open.      Excludes** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with the fewest OPEN leads (least-loaded     ro** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return the set of active caller ids currently within their shift hours.** (1 connections) — `backend/app/services/assignment.py`
- **Reassign overdue callbacks from away callers to available ones.      Returns the** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with fewest assigned non-disqualified leads.** (1 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Assignment Service]] (20 shared connections)
- [[Operator Console & Audit]] (7 shared connections)
- [[Notify Service]] (6 shared connections)
- [[App Settings API]] (5 shared connections)
- [[Calls API (TeleCMI dialer)]] (4 shared connections)
- [[Ai Reply Service]] (4 shared connections)
- [[App Entry & Schedulers]] (3 shared connections)
- [[Callers CRUD & Coaching]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[WhatsApp Inbound Webhook]] (2 shared connections)
- [[Telecalling Upload API]] (2 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/routes/callers.py`
- `backend/app/routes/calls.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 94 (72%)
- INFERRED: 37 (28%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*