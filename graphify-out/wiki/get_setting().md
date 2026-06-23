# get_setting()

> God node · 31 connections · `backend/app/config_dynamic.py`

**Community:** [[Config Dynamic]]

## Connections by Relation

### calls
- [[get_supabase()]] `INFERRED`
- [[generate_reply()]] `INFERRED`
- [[_creds()]] `EXTRACTED`
- [[telecmi_cdr()]] `EXTRACTED`
- [[get_groq_client()]] `EXTRACTED`
- [[telegram_webhook()]] `EXTRACTED`
- [[get_knowledge_context()]] `INFERRED`
- [[verify_meta_signature()]] `EXTRACTED`
- [[upload_template_media()]] `EXTRACTED`
- [[CreateTemplate]] `EXTRACTED`
- [[send_facebook()]] `INFERRED`
- [[send_instagram()]] `INFERRED`
- [[send_telegram()]] `INFERRED`
- [[InitiateCall]] `EXTRACTED`
- [[create_template()]] `EXTRACTED`
- [[_score_arc()]] `INFERRED`
- [[_auto_generate_rubric()]] `INFERRED`
- [[setup_telegram_webhook()]] `INFERRED`
- [[initiate_call()]] `EXTRACTED`
- [[_verify_telecmi_webhook_secret()]] `EXTRACTED`

### contains
- [[config_dynamic.py]] `EXTRACTED`

### rationale_for
- [[Read from cache → app_settings table → fallback. No env-var fallback: every]] `EXTRACTED`
- [[Read from cache → app_settings table → env var → fallback.]] `EXTRACTED`
- [[Read from cache → app_settings table → env var → fallback.]] `EXTRACTED`

### references
- [[str]] `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*