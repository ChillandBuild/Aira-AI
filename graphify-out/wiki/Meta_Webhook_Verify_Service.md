# Meta Webhook Verify Service

> 17 nodes · cohesion 0.21

## Key Concepts

- **verify_meta_signature()** (14 connections) — `backend/app/services/meta_webhook_verify.py`
- **resolve_tenant_for_page()** (6 connections) — `backend/app/services/meta_webhook_verify.py`
- **test_meta_webhook_verify.py** (6 connections) — `backend/tests/test_meta_webhook_verify.py`
- **_sig()** (6 connections) — `backend/tests/test_meta_webhook_verify.py`
- **meta_webhook_verify.py** (5 connections) — `backend/app/services/meta_webhook_verify.py`
- **_settings()** (5 connections) — `backend/tests/test_meta_webhook_verify.py`
- **test_default_uses_meta_app_secret()** (4 connections) — `backend/tests/test_meta_webhook_verify.py`
- **test_instagram_secret_verified_against_instagram_app_secret()** (4 connections) — `backend/tests/test_meta_webhook_verify.py`
- **test_instagram_falls_back_to_meta_app_secret_when_unset()** (4 connections) — `backend/tests/test_meta_webhook_verify.py`
- **test_no_secret_configured_fails_closed()** (4 connections) — `backend/tests/test_meta_webhook_verify.py`
- **str** (2 connections) — `backend/app/services/meta_webhook_verify.py`
- **bytes** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **bool** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **Shared helpers for Meta webhook verification (FB Messenger + Instagram).** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **Verify Meta's X-Hub-Signature-256 header against raw request body.      Returns** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **Look up the tenant that owns this page_id for the given channel.      channel: "** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **str** (1 connections) — `backend/tests/test_meta_webhook_verify.py`

## Relationships

- [[Templates API]] (3 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[WhatsApp Inbound Webhook]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)

## Source Files

- `backend/app/services/meta_webhook_verify.py`
- `backend/tests/test_meta_webhook_verify.py`

## Audit Trail

- EXTRACTED: 51 (77%)
- INFERRED: 15 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*