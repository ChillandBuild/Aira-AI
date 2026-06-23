# Ai Reply Service

> 18 nodes · cohesion 0.12

## Key Concepts

- **generate_reply()** (36 connections) — `backend/app/services/ai_reply.py`
- **_is_similar()** (9 connections) — `backend/app/services/ai_reply.py`
- **_trigger_chat_escalation()** (9 connections) — `backend/app/services/ai_reply.py`
- **_is_generic_fallback()** (4 connections) — `backend/app/services/ai_reply.py`
- **bool** (3 connections) — `backend/app/services/ai_reply.py`
- **float** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Create a pending chat handover into the shared escalation pool.      The handove** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Create a pending chat handover into the shared escalation pool.      The handove** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Create a pending chat handover into the shared escalation pool.      The handove** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Core pipeline:     1. Inject knowledge base context     2. Call Groq for reply** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[AI Reply Pipeline (Groq)]] (13 shared connections)
- [[Ai Reply Service]] (5 shared connections)
- [[Telecaller Assignment Engine]] (4 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[WhatsApp Inbound Webhook]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Notify Service]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[App Settings API]] (1 shared connections)
- [[Knowledge Base (pgvector RAG)]] (1 shared connections)
- [[Score Engine v2 & Segmentation]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 57 (77%)
- INFERRED: 17 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*