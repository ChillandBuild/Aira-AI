# AI Reply Pipeline (Groq)

> 29 nodes · cohesion 0.13

## Key Concepts

- **generate_reply()** (37 connections) — `backend/app/services/ai_reply.py`
- **ai_reply.py** (23 connections) — `backend/app/services/ai_reply.py`
- **str** (19 connections) — `backend/app/services/ai_reply.py`
- **send_instagram()** (9 connections) — `backend/app/services/ai_reply.py`
- **_groq_complete()** (6 connections) — `backend/app/services/ai_reply.py`
- **_groq_chat()** (6 connections) — `backend/app/services/ai_reply.py`
- **generate_reengagement_message()** (6 connections) — `backend/app/services/ai_reply.py`
- **fetchConversations()** (6 connections) — `frontend/app/dashboard/conversations/page.tsx`
- **_resolve_campaign()** (5 connections) — `backend/app/services/ai_reply.py`
- **_fetch_conversation_summary()** (5 connections) — `backend/app/services/ai_reply.py`
- **_recent_thread()** (5 connections) — `backend/app/services/ai_reply.py`
- **_get_prompt()** (4 connections) — `backend/app/services/ai_reply.py`
- **invalidate_prompt_cache()** (4 connections) — `backend/app/services/ai_reply.py`
- **get_last_send_error()** (4 connections) — `backend/app/services/ai_reply.py`
- **int** (3 connections) — `backend/app/services/ai_reply.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (2 connections) — `backend/app/services/ai_reply.py`
- **Resolve the campaign this lead most recently belongs to, from lead_tag_interest** (1 connections) — `backend/app/services/ai_reply.py`
- **Send an Instagram DM via Facebook Graph API (Messenger Platform for Instagram).** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **# NOTE: This is the generic fallback. Every tenant should configure their own pr** (1 connections) — `backend/app/services/ai_reply.py`
- **Resolve the campaign this lead most recently belongs to, from lead_tag_interest** (1 connections) — `backend/app/services/ai_reply.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (1 connections) — `backend/app/services/ai_reply.py`
- **Send an Instagram DM via Facebook Graph API (Messenger Platform for Instagram).** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **# NOTE: This is the generic fallback. Every tenant should configure their own pr** (1 connections) — `backend/app/services/ai_reply.py`
- *... and 4 more nodes in this community*

## Relationships

- [[Ai Reply Service]] (9 shared connections)
- [[Booking Flow]] (6 shared connections)
- [[Calls API (TeleCMI dialer)]] (5 shared connections)
- [[Leads API]] (4 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Razorpay Payments]] (3 shared connections)
- [[Growth Service]] (3 shared connections)
- [[Call Coach Service]] (2 shared connections)
- [[Ai Tune API]] (2 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[App Settings API]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`
- `frontend/app/dashboard/conversations/page.tsx`

## Audit Trail

- EXTRACTED: 126 (80%)
- INFERRED: 31 (20%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*