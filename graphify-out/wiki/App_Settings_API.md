# App Settings API

> 27 nodes · cohesion 0.11

## Key Concepts

- **app_settings.py** (20 connections) — `backend/app/routes/app_settings.py`
- **get_inbox_config()** (13 connections) — `backend/app/services/assignment.py`
- **str** (10 connections) — `backend/app/routes/app_settings.py`
- **setup_telegram_webhook()** (8 connections) — `backend/app/routes/app_settings.py`
- **activate_channel()** (8 connections) — `backend/app/routes/app_settings.py`
- **patch_telecalling_config()** (7 connections) — `backend/app/routes/app_settings.py`
- **patch_inbox_config()** (6 connections) — `backend/app/routes/app_settings.py`
- **WebhookHealth** (4 connections) — `frontend/app/dashboard/channels/page.tsx`
- **SettingsUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **ActivateChannelRequest** (3 connections) — `backend/app/routes/app_settings.py`
- **InboxConfigUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **TelecallingConfigUpdate** (3 connections) — `backend/app/routes/app_settings.py`
- **_get_setting_value()** (3 connections) — `backend/app/routes/app_settings.py`
- **list_settings()** (3 connections) — `backend/app/routes/app_settings.py`
- **webhook_health()** (2 connections) — `backend/app/routes/app_settings.py`
- **get_inbox_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **bool** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return last inbound event timestamp per channel + recent token_invalid incidents** (1 connections) — `backend/app/routes/app_settings.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (12 shared connections)
- [[Telecaller Assignment Engine]] (5 shared connections)
- [[Leads API]] (4 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[Settings Page]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Channels Page]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/services/assignment.py`
- `frontend/app/dashboard/channels/page.tsx`

## Audit Trail

- EXTRACTED: 92 (84%)
- INFERRED: 17 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*