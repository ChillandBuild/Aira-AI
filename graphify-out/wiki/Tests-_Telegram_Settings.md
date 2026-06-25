# Tests: Telegram Settings

> 13 nodes · cohesion 0.22

## Key Concepts

- **test_telegram_settings.py** (12 connections) — `backend/tests/test_telegram_settings.py`
- **create_token_incident()** (7 connections) — `backend/app/services/incidents.py`
- **_mock_recent_incidents()** (5 connections) — `backend/tests/test_telegram_settings.py`
- **webhook_health()** (3 connections) — `backend/app/routes/app_settings.py`
- **test_create_token_incident_inserts_when_none_recent()** (3 connections) — `backend/tests/test_telegram_settings.py`
- **test_create_token_incident_deduped_when_same_channel_recent()** (3 connections) — `backend/tests/test_telegram_settings.py`
- **test_create_token_incident_not_deduped_across_channels()** (3 connections) — `backend/tests/test_telegram_settings.py`
- **incidents.py** (2 connections) — `backend/app/services/incidents.py`
- **test_webhook_health_includes_telegram()** (2 connections) — `backend/tests/test_telegram_settings.py`
- **str** (1 connections) — `backend/app/services/incidents.py`
- **Shared incident recording helpers.  Kept dependency-light (takes `db` as a param** (1 connections) — `backend/app/services/incidents.py`
- **Record a `token_invalid` incident, deduped per (tenant, channel) per 23h.      D** (1 connections) — `backend/app/services/incidents.py`
- **Wire the recent-token_invalid select chain used by create_token_incident.** (1 connections) — `backend/tests/test_telegram_settings.py`

## Relationships

- [[Ai Reply Service]] (4 shared connections)
- [[Tests: Telegram Settings]] (3 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[App Settings API]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/services/incidents.py`
- `backend/tests/test_telegram_settings.py`

## Audit Trail

- EXTRACTED: 34 (77%)
- INFERRED: 10 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*