# Notify Service

> 30 nodes · cohesion 0.10

## Key Concepts

- **record_assignment_event()** (13 connections) — `backend/app/services/assignment.py`
- **takeover_lead()** (12 connections) — `backend/app/routes/leads.py`
- **notify_user()** (11 connections) — `backend/app/services/notify.py`
- **notify_assigned_caller_of_reply()** (9 connections) — `backend/app/services/notify.py`
- **clear_pool_notifications_for_lead()** (9 connections) — `backend/app/services/notify.py`
- **assign_lead()** (8 connections) — `backend/app/routes/leads.py`
- **notify_pool()** (8 connections) — `backend/app/services/notify.py`
- **bulk_assign()** (7 connections) — `backend/app/routes/leads.py`
- **chat_handovers.py** (6 connections) — `backend/app/routes/chat_handovers.py`
- **assign_handover()** (6 connections) — `backend/app/routes/chat_handovers.py`
- **notify.py** (6 connections) — `backend/app/services/notify.py`
- **str** (6 connections) — `backend/app/services/notify.py`
- **resolve_handover()** (5 connections) — `backend/app/routes/chat_handovers.py`
- **handover_count()** (3 connections) — `backend/app/routes/chat_handovers.py`
- **AssignBody** (3 connections) — `backend/app/routes/chat_handovers.py`
- **_active_caller_user_ids()** (3 connections) — `backend/app/services/notify.py`
- **_owner_user_id()** (3 connections) — `backend/app/services/notify.py`
- **list_handovers()** (2 connections) — `backend/app/routes/chat_handovers.py`
- **str** (2 connections) — `backend/app/routes/chat_handovers.py`
- **Sidebar badge polls this every 60s. Swallow transient Supabase     HTTP/2 discon** (1 connections) — `backend/app/routes/chat_handovers.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Write the proof event powering the Assignment Log. Never raises.** (1 connections) — `backend/app/services/assignment.py`
- **Insert a single notification for one user. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- **Notify the caller who owns this lead that the lead replied. Best-effort.** (1 connections) — `backend/app/services/notify.py`
- **Fan out one notification per active caller + owner. Best-effort: never raises.** (1 connections) — `backend/app/services/notify.py`
- *... and 5 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (17 shared connections)
- [[Leads API]] (8 shared connections)
- [[Telecaller Assignment Engine]] (5 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[Calls API]] (2 shared connections)
- [[Telecalling Upload API]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Callers API]] (1 shared connections)
- [[Segments API]] (1 shared connections)
- [[Facebook / Webhook Verification]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Telegram Channel]] (1 shared connections)

## Source Files

- `backend/app/routes/chat_handovers.py`
- `backend/app/routes/leads.py`
- `backend/app/services/assignment.py`
- `backend/app/services/notify.py`

## Audit Trail

- EXTRACTED: 82 (62%)
- INFERRED: 51 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*