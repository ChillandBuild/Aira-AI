# Ai Reply Service

> 10 nodes · cohesion 0.20

## Key Concepts

- **_is_similar()** (8 connections) — `backend/app/services/ai_reply.py`
- **_trigger_chat_escalation()** (8 connections) — `backend/app/services/ai_reply.py`
- **_is_generic_fallback()** (4 connections) — `backend/app/services/ai_reply.py`
- **bool** (3 connections) — `backend/app/services/ai_reply.py`
- **float** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Create a pending chat handover into the shared escalation pool.      The handove** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`
- **Create a pending chat handover into the shared escalation pool.      The handove** (1 connections) — `backend/app/services/ai_reply.py`
- **True if two messages share ≥threshold fraction of words (rough duplicate check).** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[AI Reply Pipeline (Groq)]] (9 shared connections)
- [[Assignment Service]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 27 (93%)
- INFERRED: 2 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*