# AI Reply Pipeline (Groq)

> 22 nodes · cohesion 0.15

## Key Concepts

- **ai_reply.py** (24 connections) — `backend/app/services/ai_reply.py`
- **str** (19 connections) — `backend/app/services/ai_reply.py`
- **get_groq_client()** (17 connections) — `backend/app/services/groq_client.py`
- **RuntimeError** (11 connections)
- **_groq_complete()** (6 connections) — `backend/app/services/ai_reply.py`
- **_groq_chat()** (6 connections) — `backend/app/services/ai_reply.py`
- **_fetch_conversation_summary()** (6 connections) — `backend/app/services/ai_reply.py`
- **generate_reengagement_message()** (6 connections) — `backend/app/services/ai_reply.py`
- **fetchConversations()** (6 connections) — `frontend/app/dashboard/conversations/page.tsx`
- **_recent_thread()** (5 connections) — `backend/app/services/ai_reply.py`
- **_get_prompt()** (4 connections) — `backend/app/services/ai_reply.py`
- **int** (3 connections) — `backend/app/services/ai_reply.py`
- **groq_client.py** (3 connections) — `backend/app/services/groq_client.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (2 connections) — `backend/app/services/ai_reply.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (1 connections) — `backend/app/services/ai_reply.py`
- **# NOTE: This is the generic fallback. Every tenant should configure their own pr** (1 connections) — `backend/app/services/ai_reply.py`
- **str** (1 connections) — `backend/app/services/groq_client.py`
- **bool** (1 connections) — `backend/app/services/groq_client.py`
- **# NOTE: This is the generic fallback. Every tenant should configure their own pr** (1 connections) — `backend/app/services/ai_reply.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (1 connections) — `backend/app/services/ai_reply.py`
- **# NOTE: This is the generic fallback. Every tenant should configure their own pr** (1 connections) — `backend/app/services/ai_reply.py`
- **Fetch the compacted conversation_summary from lead_conversation_state.     Retur** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[Ai Reply Service]] (25 shared connections)
- [[Ai Tune API]] (4 shared connections)
- [[Leads API]] (3 shared connections)
- [[Config]] (2 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Telecmi Client Service]] (2 shared connections)
- [[Templates API]] (2 shared connections)
- [[Call Summarizer Service]] (2 shared connections)
- [[Broadcast Executor & Outbound Router]] (1 shared connections)
- [[Embeddings Service]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`
- `backend/app/services/groq_client.py`
- `frontend/app/dashboard/conversations/page.tsx`

## Audit Trail

- EXTRACTED: 96 (76%)
- INFERRED: 30 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*