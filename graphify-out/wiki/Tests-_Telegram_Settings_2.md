# Tests: Telegram Settings

> 11 nodes · cohesion 0.24

## Key Concepts

- **activate_channel()** (12 connections) — `backend/app/routes/app_settings.py`
- **_FakeClient** (10 connections) — `backend/tests/test_telegram_settings.py`
- **ActivateChannelRequest** (7 connections) — `backend/app/routes/app_settings.py`
- **test_activate_telegram_success_return_shape()** (4 connections) — `backend/tests/test_telegram_settings.py`
- **test_activate_telegram_requires_saved_token()** (3 connections) — `backend/tests/test_telegram_settings.py`
- **.__init__()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **.__aenter__()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **.__aexit__()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **.post()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **.get()** (1 connections) — `backend/tests/test_telegram_settings.py`
- **Validate Meta credentials and auto-subscribe webhook for whatsapp / instagram /** (1 connections) — `backend/app/routes/app_settings.py`

## Relationships

- [[App Settings API]] (5 shared connections)
- [[Ai Reply Service]] (3 shared connections)
- [[Operator Console & Audit]] (3 shared connections)
- [[Tests: Telegram Settings]] (3 shared connections)
- [[Leads API]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/tests/test_telegram_settings.py`

## Audit Trail

- EXTRACTED: 27 (64%)
- INFERRED: 15 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*