# Notify Service

> 18 nodes · cohesion 0.17

## Key Concepts

- **takeover_lead()** (11 connections) — `backend/app/routes/leads.py`
- **notify_user()** (11 connections) — `backend/app/services/notify.py`
- **notify_assigned_caller_of_reply()** (9 connections) — `backend/app/services/notify.py`
- **clear_pool_notifications_for_lead()** (9 connections) — `backend/app/services/notify.py`
- **notify_pool()** (8 connections) — `backend/app/services/notify.py`
- **bulk_assign()** (7 connections) — `backend/app/routes/leads.py`
- **notify.py** (6 connections) — `backend/app/services/notify.py`
- **str** (6 connections) — `backend/app/services/notify.py`
- **_active_caller_user_ids()** (3 connections) — `backend/app/services/notify.py`
- **_owner_user_id()** (3 connections) — `backend/app/services/notify.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Insert a single notification for one user. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- **Notify the caller who owns this lead that the lead replied. Best-effort.** (1 connections) — `backend/app/services/notify.py`
- **Fan out one notification per active caller + owner. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- **Mark handover/pool notifications for a lead as read for all users when claimed/r** (1 connections) — `backend/app/services/notify.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Allow a telecaller to claim/take over an overdue callback lead from another call** (1 connections) — `backend/app/routes/leads.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (7 shared connections)
- [[Leads API]] (6 shared connections)
- [[Telecaller Assignment Engine]] (3 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Booking Flow]] (2 shared connections)
- [[Chat Handovers (escalation pool)]] (2 shared connections)
- [[Telecalling Upload API]] (1 shared connections)
- [[Facebook / Webhook Verification]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/services/notify.py`

## Audit Trail

- EXTRACTED: 50 (62%)
- INFERRED: 31 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*