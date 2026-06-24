# Chat Handovers (escalation pool)

> 8 nodes · cohesion 0.32

## Key Concepts

- **chat_handovers.py** (6 connections) — `backend/app/routes/chat_handovers.py`
- **assign_handover()** (6 connections) — `backend/app/routes/chat_handovers.py`
- **resolve_handover()** (5 connections) — `backend/app/routes/chat_handovers.py`
- **handover_count()** (3 connections) — `backend/app/routes/chat_handovers.py`
- **AssignBody** (3 connections) — `backend/app/routes/chat_handovers.py`
- **list_handovers()** (2 connections) — `backend/app/routes/chat_handovers.py`
- **str** (2 connections) — `backend/app/routes/chat_handovers.py`
- **Sidebar badge polls this every 60s. Swallow transient Supabase     HTTP/2 discon** (1 connections) — `backend/app/routes/chat_handovers.py`

## Relationships

- [[Operator Console & Audit]] (6 shared connections)
- [[Notify Service]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Pydantic Schemas]] (1 shared connections)

## Source Files

- `backend/app/routes/chat_handovers.py`

## Audit Trail

- EXTRACTED: 20 (71%)
- INFERRED: 8 (29%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*