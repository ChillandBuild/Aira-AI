# Telecaller Assignment Engine

> 27 nodes · cohesion 0.12

## Key Concepts

- **get_telecalling_config()** (31 connections) — `backend/app/services/assignment.py`
- **auto_assign_lead()** (20 connections) — `backend/app/services/assignment.py`
- **assignment.py** (19 connections) — `backend/app/services/assignment.py`
- **str** (17 connections) — `backend/app/services/assignment.py`
- **maybe_assign_lead()** (16 connections) — `backend/app/services/assignment.py`
- **process_callback_reassignments()** (8 connections) — `backend/app/services/assignment.py`
- **get_caller_id_for_user()** (6 connections) — `backend/app/services/assignment.py`
- **int** (6 connections) — `backend/app/services/assignment.py`
- **_in_shift_caller_ids()** (6 connections) — `backend/app/services/assignment.py`
- **_open_lead_count()** (5 connections) — `backend/app/services/assignment.py`
- **get_my_performance()** (3 connections) — `backend/app/routes/callers.py`
- **get_assignment_mode()** (2 connections) — `backend/app/routes/calls.py`
- **Return callers.id for this auth user, or None if not a caller.** (1 connections) — `backend/app/services/assignment.py`
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
- **Return callers.id for this auth user, or None if not a caller.** (1 connections) — `backend/app/services/assignment.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Assignment Service]] (24 shared connections)
- [[Operator Console & Audit]] (7 shared connections)
- [[Calls API]] (5 shared connections)
- [[Notify Service]] (5 shared connections)
- [[App Settings API]] (4 shared connections)
- [[Callers API]] (3 shared connections)
- [[App Entry & Schedulers]] (3 shared connections)
- [[AI Reply Pipeline (Groq)]] (3 shared connections)
- [[Callers CRUD & Coaching]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[Telegram Channel]] (2 shared connections)

## Source Files

- `backend/app/routes/callers.py`
- `backend/app/routes/calls.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 116 (75%)
- INFERRED: 38 (25%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*