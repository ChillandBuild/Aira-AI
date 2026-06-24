# Telecaller Assignment Engine

> 38 nodes · cohesion 0.07

## Key Concepts

- **assignment.py** (19 connections) — `backend/app/services/assignment.py`
- **str** (17 connections) — `backend/app/services/assignment.py`
- **is_round_robin_enabled()** (14 connections) — `backend/app/services/assignment.py`
- **save_telecalling_config()** (12 connections) — `backend/app/services/assignment.py`
- **should_escalate_to_inbox()** (9 connections) — `backend/app/services/assignment.py`
- **should_escalate_hot_lead()** (9 connections) — `backend/app/services/assignment.py`
- **should_assign_to_telecalling()** (9 connections) — `backend/app/services/assignment.py`
- **set_round_robin_enabled()** (7 connections) — `backend/app/services/assignment.py`
- **bool** (6 connections) — `backend/app/services/assignment.py`
- **get_caller_id_for_user()** (6 connections) — `backend/app/services/assignment.py`
- **_in_shift_caller_ids()** (6 connections) — `backend/app/services/assignment.py`
- **Flip the single auto-assign switch (telecalling_config.enabled).** (2 connections) — `backend/app/services/assignment.py`
- **Return telecalling_config from app_settings, merged with defaults.** (2 connections) — `backend/app/services/assignment.py`
- **Whether auto-assign to telecallers is on.      Single source of truth: telecalli** (1 connections) — `backend/app/services/assignment.py`
- **Return callers.id for this auth user, or None if not a caller.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this trigger should create an inbox handover.     Trigger C alway** (1 connections) — `backend/app/services/assignment.py`
- **Segment-driven hot lead escalation. Used by score ≥ 7 events     in both AI and** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this event should auto-assign to a telecaller.** (1 connections) — `backend/app/services/assignment.py`
- **Return the set of active caller ids currently within their shift hours.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this trigger should create an inbox handover.     Trigger C alway** (1 connections) — `backend/app/services/assignment.py`
- **Segment-driven hot lead escalation. Used by score ≥ 7 events     in both AI and** (1 connections) — `backend/app/services/assignment.py`
- **Return True if this event should auto-assign to a telecaller.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- *... and 13 more nodes in this community*

## Relationships

- [[Assignment Service]] (21 shared connections)
- [[Operator Console & Audit]] (5 shared connections)
- [[Callers API]] (4 shared connections)
- [[App Settings API]] (3 shared connections)
- [[Leads API]] (3 shared connections)
- [[Ai Reply Service]] (3 shared connections)
- [[Notify Service]] (2 shared connections)

## Source Files

- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 130 (91%)
- INFERRED: 13 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*