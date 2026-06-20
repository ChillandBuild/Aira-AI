# App Settings API

> 27 nodes · cohesion 0.12

## Key Concepts

- **app_settings.py** (20 connections) — `backend/app/routes/app_settings.py`
- **get_inbox_config()** (12 connections) — `backend/app/services/assignment.py`
- **str** (10 connections) — `backend/app/routes/app_settings.py`
- **update_settings()** (8 connections) — `backend/app/routes/app_settings.py`
- **activate_channel()** (8 connections) — `backend/app/routes/app_settings.py`
- **setup_telegram_webhook()** (7 connections) — `backend/app/routes/app_settings.py`
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
- **get_telecalling_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **bool** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Register Telegram webhook + return generated secret (None if base_url missing).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return last inbound event timestamp per channel + recent token_invalid incidents** (1 connections) — `backend/app/routes/app_settings.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (6 shared connections)
- [[Operator Console & Audit]] (6 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Leads API]] (4 shared connections)
- [[Telecaller Assignment Engine]] (4 shared connections)
- [[Telecallingconfigpanel (frontend)]] (2 shared connections)
- [[Channels Page]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[Tenant]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/services/assignment.py`
- `frontend/app/dashboard/channels/page.tsx`

## Audit Trail

- EXTRACTED: 93 (81%)
- INFERRED: 22 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*