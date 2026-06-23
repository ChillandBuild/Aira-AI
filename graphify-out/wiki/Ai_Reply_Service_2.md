# Ai Reply Service

> 16 nodes · cohesion 0.12

## Key Concepts

- **send_whatsapp()** (17 connections) — `backend/app/services/ai_reply.py`
- **send_telegram()** (10 connections) — `backend/app/services/ai_reply.py`
- **send_facebook()** (10 connections) — `backend/app/services/ai_reply.py`
- **broadcast_custom_message()** (7 connections) — `backend/app/routes/leads.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Facebook Messenger message via Graph API. Returns message id or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Facebook Messenger message via Graph API. Returns message id or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Facebook Messenger message via Graph API. Returns message id or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a WhatsApp message via Meta Cloud API. Returns message ID or None on failur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Facebook Messenger message via Graph API. Returns message id or None on f** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[Leads API]] (6 shared connections)
- [[AI Reply Pipeline (Groq)]] (6 shared connections)
- [[Ai Reply Service]] (4 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Config Dynamic]] (2 shared connections)
- [[Growth Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[CSV Upload & Bulk Send]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Notify Service]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 35 (62%)
- INFERRED: 21 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*