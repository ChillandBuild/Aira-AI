# Conversation Compactor Service

> 13 nodes · cohesion 0.18

## Key Concepts

- **compact_conversation()** (11 connections) — `backend/app/services/conversation_compactor.py`
- **get_or_create_state()** (9 connections) — `backend/app/services/conversation_state.py`
- **_format_messages()** (5 connections) — `backend/app/services/conversation_compactor.py`
- **conversation_compactor.py** (3 connections) — `backend/app/services/conversation_compactor.py`
- **str** (2 connections) — `backend/app/services/conversation_compactor.py`
- **conversation_state.py** (2 connections) — `backend/app/services/conversation_state.py`
- **Format messages for LLM context.** (1 connections) — `backend/app/services/conversation_compactor.py`
- **Compact conversation messages into a summary.          Args:         lead_id: Le** (1 connections) — `backend/app/services/conversation_compactor.py`
- **str** (1 connections) — `backend/app/services/conversation_state.py`
- **Conversation state tracking for lead inactivity, compaction, and message countin** (1 connections) — `backend/app/services/conversation_state.py`
- **Fetch the conversation state for a lead, or return a fresh idle state.      Also** (1 connections) — `backend/app/services/conversation_state.py`
- **Format messages for LLM context.** (1 connections) — `backend/app/services/conversation_compactor.py`
- **Compact conversation messages into a summary.          Args:         lead_id: Le** (1 connections) — `backend/app/services/conversation_compactor.py`

## Relationships

- [[WhatsApp Inbound Webhook]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Facebook / Webhook Verification]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Telegram Channel]] (1 shared connections)

## Source Files

- `backend/app/services/conversation_compactor.py`
- `backend/app/services/conversation_state.py`

## Audit Trail

- EXTRACTED: 27 (69%)
- INFERRED: 12 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*