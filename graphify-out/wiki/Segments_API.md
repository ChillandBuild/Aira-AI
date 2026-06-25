# Segments API

> 14 nodes · cohesion 0.21

## Key Concepts

- **send_whatsapp()** (20 connections) — `backend/app/services/ai_reply.py`
- **broadcast_custom_message()** (7 connections) — `backend/app/routes/leads.py`
- **segments.py** (6 connections) — `backend/app/routes/segments.py`
- **upsert_template()** (6 connections) — `backend/app/routes/segments.py`
- **broadcast_to_segment()** (5 connections) — `backend/app/routes/segments.py`
- **_ensure_templates()** (4 connections) — `backend/app/routes/segments.py`
- **str** (4 connections) — `backend/app/routes/segments.py`
- **list_templates()** (4 connections) — `backend/app/routes/segments.py`
- **TemplateUpdate** (3 connections) — `backend/app/routes/segments.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[Operator Console & Audit]] (7 shared connections)
- [[Leads API]] (5 shared connections)
- [[Ai Reply Service]] (5 shared connections)
- [[Tests: Outbound Number Routing]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Growth Service]] (1 shared connections)
- [[CSV Upload & Bulk Send]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Notify Service]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/routes/segments.py`
- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 41 (64%)
- INFERRED: 23 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*