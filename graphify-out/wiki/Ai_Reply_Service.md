# Ai Reply Service

> 11 nodes · cohesion 0.20

## Key Concepts

- **send_telegram()** (15 connections) — `backend/app/services/ai_reply.py`
- **_FakeResp** (6 connections) — `backend/tests/test_telegram_settings.py`
- **test_send_telegram_records_incident_on_401()** (4 connections) — `backend/tests/test_telegram_settings.py`
- **test_send_telegram_no_incident_on_403_blocked_by_user()** (4 connections) — `backend/tests/test_telegram_settings.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **.__init__()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **.json()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`
- **Send a Telegram message via Bot API. Returns message ID (as string) or None on f** (1 connections) — `backend/app/services/ai_reply.py`

## Relationships

- [[Tests: Telegram Settings]] (7 shared connections)
- [[Ai Reply Service]] (2 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Segments API]] (1 shared connections)
- [[Leads API]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/services/ai_reply.py`
- `backend/tests/test_telegram_settings.py`

## Audit Trail

- EXTRACTED: 26 (72%)
- INFERRED: 10 (28%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*