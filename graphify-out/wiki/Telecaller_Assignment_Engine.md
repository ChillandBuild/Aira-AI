# Telecaller Assignment Engine

> 43 nodes · cohesion 0.07

## Key Concepts

- **assignment.py** (17 connections) — `backend/app/services/assignment.py`
- **str** (16 connections) — `backend/app/services/assignment.py`
- **is_round_robin_enabled()** (14 connections) — `backend/app/services/assignment.py`
- **record_assignment_event()** (13 connections) — `backend/app/services/assignment.py`
- **reassign_backlog()** (11 connections) — `backend/app/services/assignment.py`
- **save_telecalling_config()** (11 connections) — `backend/app/services/assignment.py`
- **save_inbox_config()** (8 connections) — `backend/app/services/assignment.py`
- **should_escalate_hot_lead()** (8 connections) — `backend/app/services/assignment.py`
- **should_assign_to_telecalling()** (8 connections) — `backend/app/services/assignment.py`
- **is_caller_on_call()** (8 connections) — `backend/app/services/assignment.py`
- **set_round_robin_enabled()** (7 connections) — `backend/app/services/assignment.py`
- **bool** (6 connections) — `backend/app/services/assignment.py`
- **get_caller_id_for_user()** (6 connections) — `backend/app/services/assignment.py`
- **Flip the single auto-assign switch (telecalling_config.enabled).** (2 connections) — `backend/app/services/assignment.py`
- **Whether auto-assign to telecallers is on.      Single source of truth: telecalli** (1 connections) — `backend/app/services/assignment.py`
- **Return callers.id for this auth user, or None if not a caller.** (1 connections) — `backend/app/services/assignment.py`
- **Write the proof event powering the Assignment Log. Never raises.** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Persist inbox_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Segment-driven hot lead escalation. Used by score ≥ 7 events     in both AI and** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this event should auto-assign to a telecaller.** (1 connections) — `backend/app/services/assignment.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Check for any unassigned Hot leads or flagged leads and assign them     to this** (1 connections) — `backend/app/services/assignment.py`
- **Persist inbox_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- *... and 18 more nodes in this community*

## Relationships

- [[Assignment Service]] (20 shared connections)
- [[Calls API (TeleCMI dialer)]] (7 shared connections)
- [[Callers CRUD & Coaching]] (5 shared connections)
- [[App Settings API]] (4 shared connections)
- [[Notify Service]] (3 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Tenant]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[Telecalling Upload API]] (1 shared connections)

## Source Files

- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 140 (85%)
- INFERRED: 24 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*