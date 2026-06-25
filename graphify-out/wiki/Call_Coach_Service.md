# Call Coach Service

> 9 nodes · cohesion 0.28

## Key Concepts

- **config.py** (22 connections) — `backend/app/config.py`
- **coaching_tip()** (6 connections) — `backend/app/services/call_coach.py`
- **Settings** (3 connections) — `backend/app/config.py`
- **call_coach.py** (3 connections) — `backend/app/services/call_coach.py`
- **_summarize_logs()** (3 connections) — `backend/app/services/call_coach.py`
- **supabase.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/db/supabase.py`
- **str** (2 connections) — `backend/app/services/call_coach.py`
- **BaseSettings** (1 connections)
- **._warn_missing_secrets()** (1 connections) — `backend/app/config.py`

## Relationships

- [[App Entry & Schedulers]] (2 shared connections)
- [[Ai Reply Service]] (2 shared connections)
- [[Knowledge Base (pgvector RAG)]] (2 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Auth]] (1 shared connections)
- [[Ai Tune API]] (1 shared connections)
- [[App Settings API]] (1 shared connections)
- [[Calls API]] (1 shared connections)
- [[Facebook / Webhook Verification]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[WhatsApp Inbound Webhook]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/db/supabase.py`
- `backend/app/config.py`
- `backend/app/services/call_coach.py`

## Audit Trail

- EXTRACTED: 40 (93%)
- INFERRED: 3 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*