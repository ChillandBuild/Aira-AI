# Chat Handovers (escalation pool)

> 10 nodes · cohesion 0.31

## Key Concepts

- **chat_handovers.py** (8 connections) — `backend/app/routes/chat_handovers.py`
- **assign_handover()** (6 connections) — `backend/app/routes/chat_handovers.py`
- **assignHandover()** (6 connections) — `frontend/app/dashboard/inbox/page.tsx`
- **resolve_handover()** (5 connections) — `backend/app/routes/chat_handovers.py`
- **resolveHandover()** (5 connections) — `frontend/app/dashboard/inbox/page.tsx`
- **AssignBody** (4 connections) — `backend/app/routes/chat_handovers.py`
- **str** (4 connections) — `backend/app/routes/chat_handovers.py`
- **handover_count()** (3 connections) — `backend/app/routes/chat_handovers.py`
- **list_handovers()** (2 connections) — `backend/app/routes/chat_handovers.py`
- **Sidebar badge polls this every 60s. Swallow transient Supabase     HTTP/2 discon** (1 connections) — `backend/app/routes/chat_handovers.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (4 shared connections)
- [[Operator Console & Audit]] (4 shared connections)
- [[Connectchannelspanel (frontend)]] (4 shared connections)
- [[Notify Service]] (2 shared connections)
- [[Tenant]] (1 shared connections)
- [[Leads API]] (1 shared connections)

## Source Files

- `backend/app/routes/chat_handovers.py`
- `frontend/app/dashboard/inbox/page.tsx`

## Audit Trail

- EXTRACTED: 34 (77%)
- INFERRED: 10 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*