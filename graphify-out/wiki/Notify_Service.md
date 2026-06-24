# Notify Service

> 16 nodes · cohesion 0.22

## Key Concepts

- **record_assignment_event()** (13 connections) — `backend/app/services/assignment.py`
- **notify_user()** (11 connections) — `backend/app/services/notify.py`
- **notify_assigned_caller_of_reply()** (9 connections) — `backend/app/services/notify.py`
- **clear_pool_notifications_for_lead()** (9 connections) — `backend/app/services/notify.py`
- **assign_lead()** (8 connections) — `backend/app/routes/leads.py`
- **notify_pool()** (8 connections) — `backend/app/services/notify.py`
- **bulk_assign()** (7 connections) — `backend/app/routes/leads.py`
- **notify.py** (6 connections) — `backend/app/services/notify.py`
- **str** (6 connections) — `backend/app/services/notify.py`
- **_active_caller_user_ids()** (3 connections) — `backend/app/services/notify.py`
- **_owner_user_id()** (3 connections) — `backend/app/services/notify.py`
- **Write the proof event powering the Assignment Log. Never raises.** (1 connections) — `backend/app/services/assignment.py`
- **Insert a single notification for one user. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- **Notify the caller who owns this lead that the lead replied. Best-effort.** (1 connections) — `backend/app/services/notify.py`
- **Fan out one notification per active caller + owner. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- **Mark handover/pool notifications for a lead as read for all users when claimed/r** (1 connections) — `backend/app/services/notify.py`

## Relationships

- [[Operator Console & Audit]] (9 shared connections)
- [[Assignment Service]] (6 shared connections)
- [[Leads API]] (5 shared connections)
- [[Pydantic Schemas]] (2 shared connections)
- [[Calls API]] (2 shared connections)
- [[Telecalling Upload API]] (2 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Ai Reply Service]] (2 shared connections)
- [[Chat Handovers (escalation pool)]] (2 shared connections)
- [[Facebook / Webhook Verification]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Templates API]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/services/assignment.py`
- `backend/app/services/notify.py`

## Audit Trail

- EXTRACTED: 50 (57%)
- INFERRED: 38 (43%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*