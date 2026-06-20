# get_setting()

> God node · 38 connections · `backend/app/config_dynamic.py`

**Community:** [[Calls API (TeleCMI dialer)]]

## Connections by Relation

### calls
- [[get_supabase()]] `INFERRED`
- [[generate_reply()]] `INFERRED`
- [[_creds()]] `EXTRACTED`
- [[get_groq_client()]] `EXTRACTED`
- [[get_or_create_state()]] `INFERRED`
- [[telecmi_cdr()]] `EXTRACTED`
- [[telegram_webhook()]] `EXTRACTED`
- [[get_knowledge_context()]] `INFERRED`
- [[upload_template_media()]] `EXTRACTED`
- [[verify_meta_signature()]] `EXTRACTED`
- [[CreateTemplate]] `EXTRACTED`
- [[InitiateCall]] `EXTRACTED`
- [[create_template()]] `EXTRACTED`
- [[send_facebook()]] `INFERRED`
- [[send_instagram()]] `INFERRED`
- [[send_telegram()]] `INFERRED`
- [[_auto_generate_rubric()]] `INFERRED`
- [[razorpay_webhook()]] `INFERRED`
- [[initiate_call()]] `EXTRACTED`
- [[_verify_telecmi_webhook_secret()]] `EXTRACTED`

### contains
- [[config_dynamic.py]] `EXTRACTED`

### rationale_for
- [[Read from cache → app_settings table → env var → fallback.]] `EXTRACTED`
- [[Read from cache → app_settings table → env var → fallback.]] `EXTRACTED`

### references
- [[str]] `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*