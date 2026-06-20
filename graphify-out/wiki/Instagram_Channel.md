# Instagram Channel

> 24 nodes · cohesion 0.11

## Key Concepts

- **instagram_webhook()** (16 connections) — `backend/app/routes/instagram.py`
- **verify_meta_signature()** (13 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **config_dynamic.py** (12 connections) — `backend/app/config_dynamic.py`
- **resolve_tenant_for_page()** (7 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **instagram.py** (5 connections) — `backend/app/routes/instagram.py`
- **verify_instagram_webhook()** (5 connections) — `backend/app/routes/instagram.py`
- **meta_webhook_verify.py** (5 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **telegram.py** (3 connections) — `backend/app/routes/telegram.py`
- **groq_client.py** (3 connections) — `backend/app/services/groq_client.py`
- **test_instagram.py** (3 connections) — `backend/tests/test_instagram.py`
- **str** (2 connections) — `backend/app/routes/instagram.py`
- **Request** (2 connections) — `backend/app/routes/instagram.py`
- **str** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **test_verify_instagram_webhook_success()** (2 connections) — `backend/tests/test_instagram.py`
- **test_instagram_webhook_new_lead()** (2 connections) — `backend/tests/test_instagram.py`
- **str** (2 connections) — `backend/app/services/meta_webhook_verify.py`
- **BackgroundTasks** (1 connections) — `backend/app/routes/instagram.py`
- **bytes** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **bool** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **Shared helpers for Meta webhook verification (FB Messenger + Instagram).** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **Verify Meta's X-Hub-Signature-256 header against raw request body.      Returns** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **Look up the tenant that owns this page_id for the given channel.      channel: "** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- **bytes** (1 connections) — `backend/app/services/meta_webhook_verify.py`
- **bool** (1 connections) — `backend/app/services/meta_webhook_verify.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (6 shared connections)
- [[Facebook / Webhook Verification]] (3 shared connections)
- [[Config]] (3 shared connections)
- [[Tenant]] (3 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[Booking Flow]] (3 shared connections)
- [[Templates API]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Channels Page]] (1 shared connections)
- [[Ai Tune API]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Razorpay Payments]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/services/meta_webhook_verify.py`
- `backend/app/config_dynamic.py`
- `backend/app/routes/instagram.py`
- `backend/app/routes/telegram.py`
- `backend/app/services/groq_client.py`
- `backend/app/services/meta_webhook_verify.py`
- `backend/tests/test_instagram.py`

## Audit Trail

- EXTRACTED: 70 (76%)
- INFERRED: 22 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*