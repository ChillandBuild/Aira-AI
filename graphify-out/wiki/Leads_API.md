# Leads API

> 49 nodes · cohesion 0.07

## Key Concepts

- **leads.py** (35 connections) — `backend/app/routes/leads.py`
- **str** (23 connections) — `backend/app/routes/leads.py`
- **UUID** (23 connections) — `backend/app/routes/leads.py`
- **send_human_message()** (11 connections) — `backend/app/routes/leads.py`
- **manual_compact()** (11 connections) — `backend/app/routes/leads.py`
- **clear_chat()** (10 connections) — `backend/app/routes/leads.py`
- **release_lead()** (10 connections) — `backend/app/routes/leads.py`
- **update_lead()** (9 connections) — `backend/app/routes/leads.py`
- **mark_converted()** (8 connections) — `backend/app/routes/leads.py`
- **toggle_archive()** (8 connections) — `backend/app/routes/leads.py`
- **toggle_block()** (8 connections) — `backend/app/routes/leads.py`
- **score_history()** (8 connections) — `backend/app/routes/leads.py`
- **toggle_ai()** (7 connections) — `backend/app/routes/leads.py`
- **pre_call_brief()** (6 connections) — `backend/app/routes/leads.py`
- **list_leads()** (5 connections) — `backend/app/routes/leads.py`
- **get_lead()** (5 connections) — `backend/app/routes/leads.py`
- **toggle_pin()** (5 connections) — `backend/app/routes/leads.py`
- **delete_lead()** (5 connections) — `backend/app/routes/leads.py`
- **get_lead_messages()** (4 connections) — `backend/app/routes/leads.py`
- **get_lead_call_logs()** (4 connections) — `backend/app/routes/leads.py`
- **get_last_send_error()** (4 connections) — `backend/app/services/ai_reply.py`
- **export_leads()** (3 connections) — `backend/app/routes/leads.py`
- **export_assigned_leads()** (3 connections) — `backend/app/routes/leads.py`
- **Toggle a conversation's archived state (inbox tidy — does not stop AI).** (1 connections) — `backend/app/routes/leads.py`
- **Toggle a contact's blocked state — hides from active inbox and stops AI auto-rep** (1 connections) — `backend/app/routes/leads.py`
- *... and 24 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (33 shared connections)
- [[Leads API]] (28 shared connections)
- [[Ai Reply Service]] (6 shared connections)
- [[Notify Service]] (5 shared connections)
- [[Growth Service]] (5 shared connections)
- [[Segments API]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Telecaller Assignment Engine]] (1 shared connections)
- [[Conversation Compactor Service]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 182 (76%)
- INFERRED: 59 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*