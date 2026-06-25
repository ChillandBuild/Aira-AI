# Ai Reply Service

> 10 nodes · cohesion 0.36

## Key Concepts

- **str** (19 connections) — `backend/app/services/ai_reply.py`
- **get_groq_client()** (17 connections) — `backend/app/services/groq_client.py`
- **RuntimeError** (11 connections)
- **_groq_complete()** (6 connections) — `backend/app/services/ai_reply.py`
- **_groq_chat()** (6 connections) — `backend/app/services/ai_reply.py`
- **generate_reengagement_message()** (6 connections) — `backend/app/services/ai_reply.py`
- **_recent_thread()** (5 connections) — `backend/app/services/ai_reply.py`
- **int** (3 connections) — `backend/app/services/ai_reply.py`
- **str** (1 connections) — `backend/app/services/groq_client.py`
- **bool** (1 connections) — `backend/app/services/groq_client.py`

## Relationships

- [[Ai Reply Service]] (13 shared connections)
- [[AI Reply Pipeline (Groq)]] (4 shared connections)
- [[Ai Tune API]] (3 shared connections)
- [[Leads API]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Knowledge Base (pgvector RAG)]] (2 shared connections)
- [[Telecmi Client Service]] (2 shared connections)
- [[Config Dynamic]] (2 shared connections)
- [[Call Summarizer Service]] (2 shared connections)
- [[Settings Page]] (1 shared connections)
- [[Segments API]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`
- `backend/app/services/groq_client.py`

## Audit Trail

- EXTRACTED: 46 (61%)
- INFERRED: 29 (39%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*