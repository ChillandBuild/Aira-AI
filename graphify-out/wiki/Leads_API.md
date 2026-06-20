# Leads API

> 72 nodes · cohesion 0.08

## Key Concepts

- **BaseModel** (63 connections)
- **leads.py** (35 connections) — `backend/app/routes/leads.py`
- **str** (23 connections) — `backend/app/routes/leads.py`
- **UUID** (23 connections) — `backend/app/routes/leads.py`
- **schemas.py** (19 connections) — `backend/app/models/schemas.py`
- **Lead** (16 connections) — `backend/app/models/schemas.py`
- **PaginatedResponse** (16 connections) — `backend/app/models/schemas.py`
- **LeadUpdate** (15 connections) — `backend/app/models/schemas.py`
- **Message** (15 connections) — `backend/app/models/schemas.py`
- **LeadWithMessages** (15 connections) — `backend/app/models/schemas.py`
- **compose_new_message()** (13 connections) — `backend/app/routes/leads.py`
- **send_human_message()** (11 connections) — `backend/app/routes/leads.py`
- **manual_compact()** (10 connections) — `backend/app/routes/leads.py`
- **update_lead()** (9 connections) — `backend/app/routes/leads.py`
- **clear_chat()** (9 connections) — `backend/app/routes/leads.py`
- **release_lead()** (9 connections) — `backend/app/routes/leads.py`
- **PreCallBriefResponse** (8 connections) — `backend/app/routes/leads.py`
- **ConvertPayload** (8 connections) — `backend/app/routes/leads.py`
- **AiToggle** (8 connections) — `backend/app/routes/leads.py`
- **HumanMessage** (8 connections) — `backend/app/routes/leads.py`
- **AssignPayload** (8 connections) — `backend/app/routes/leads.py`
- **BulkAssignPayload** (8 connections) — `backend/app/routes/leads.py`
- **CustomBroadcastRequest** (8 connections) — `backend/app/routes/leads.py`
- **assign_lead()** (8 connections) — `backend/app/routes/leads.py`
- **mark_converted()** (8 connections) — `backend/app/routes/leads.py`
- *... and 47 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (23 shared connections)
- [[Operator Console & Audit]] (20 shared connections)
- [[Notify Service]] (6 shared connections)
- [[Growth Service]] (6 shared connections)
- [[Callers CRUD & Coaching]] (5 shared connections)
- [[App Settings API]] (4 shared connections)
- [[Templates API]] (4 shared connections)
- [[AI Reply Pipeline (Groq)]] (4 shared connections)
- [[Booking Flow]] (4 shared connections)
- [[Call Scripts API]] (3 shared connections)
- [[Team API]] (3 shared connections)
- [[CSV Upload & Bulk Send]] (3 shared connections)

## Source Files

- `backend/app/models/schemas.py`
- `backend/app/routes/leads.py`

## Audit Trail

- EXTRACTED: 322 (63%)
- INFERRED: 192 (37%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*