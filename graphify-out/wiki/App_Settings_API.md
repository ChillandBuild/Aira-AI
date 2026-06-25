# App Settings API

> 17 nodes · cohesion 0.17

## Key Concepts

- **app_settings.py** (20 connections) — `backend/app/routes/app_settings.py`
- **str** (10 connections) — `backend/app/routes/app_settings.py`
- **setup_telegram_webhook()** (9 connections) — `backend/app/routes/app_settings.py`
- **patch_telecalling_config()** (7 connections) — `backend/app/routes/app_settings.py`
- **patch_inbox_config()** (6 connections) — `backend/app/routes/app_settings.py`
- **WebhookHealth** (4 connections) — `frontend/app/dashboard/channels/page.tsx`
- **SettingsUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **InboxConfigUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **TelecallingConfigUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **_get_setting_value()** (3 connections) — `backend/app/routes/app_settings.py`
- **list_settings()** (3 connections) — `backend/app/routes/app_settings.py`
- **get_telecalling_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **bool** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return (success, secret_token, error_detail).** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return last inbound event timestamp per channel + recent token_invalid incidents** (1 connections) — `backend/app/routes/app_settings.py`

## Relationships

- [[Operator Console & Audit]] (7 shared connections)
- [[Tests: Telegram Settings]] (6 shared connections)
- [[Assignment Service]] (6 shared connections)
- [[Telecaller Assignment Engine]] (4 shared connections)
- [[Leads API]] (3 shared connections)
- [[Settings Page]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Channels Page]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `frontend/app/dashboard/channels/page.tsx`

## Audit Trail

- EXTRACTED: 69 (88%)
- INFERRED: 9 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*