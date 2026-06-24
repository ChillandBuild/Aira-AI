# App Settings API

> 35 nodes · cohesion 0.09

## Key Concepts

- **app_settings.py** (20 connections) — `backend/app/routes/app_settings.py`
- **TelecallingConfigPanel.tsx** (15 connections) — `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx`
- **get_inbox_config()** (13 connections) — `backend/app/services/assignment.py`
- **str** (10 connections) — `backend/app/routes/app_settings.py`
- **setup_telegram_webhook()** (8 connections) — `backend/app/routes/app_settings.py`
- **update_settings()** (8 connections) — `backend/app/routes/app_settings.py`
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
- **get_telecalling_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **bool** (1 connections) — `backend/app/routes/app_settings.py`
- **Register Telegram webhook + return (success, secret_token, error_detail).** (1 connections) — `backend/app/routes/app_settings.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **TelecallingConfig** (1 connections) — `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx`
- **DEFAULT** (1 connections) — `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx`
- **SEGMENT_LABELS** (1 connections) — `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx`
- *... and 10 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (9 shared connections)
- [[Assignment Service]] (5 shared connections)
- [[Pydantic Schemas]] (5 shared connections)
- [[Telecaller Assignment Engine]] (3 shared connections)
- [[Authrolecontext (frontend)]] (3 shared connections)
- [[Channels Page]] (2 shared connections)
- [[Operator API]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Templates API]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Settings Page]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/services/assignment.py`
- `frontend/app/dashboard/channels/page.tsx`
- `frontend/app/dashboard/settings/TelecallingConfigPanel.tsx`

## Audit Trail

- EXTRACTED: 117 (84%)
- INFERRED: 22 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*