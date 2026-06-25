# WhatsApp Inbound Webhook

> 18 nodes · cohesion 0.24

## Key Concepts

- **whatsapp_webhook()** (24 connections) — `backend/app/routes/webhook.py`
- **webhook.py** (13 connections) — `backend/app/routes/webhook.py`
- **str** (9 connections) — `backend/app/routes/webhook.py`
- **_resolve_tenant_from_payload()** (7 connections) — `backend/app/routes/webhook.py`
- **_process_inbound_message_background()** (7 connections) — `backend/app/routes/webhook.py`
- **_handle_opt_out()** (6 connections) — `backend/app/routes/webhook.py`
- **_is_opt_out()** (4 connections) — `backend/app/routes/webhook.py`
- **bool** (4 connections) — `backend/app/routes/webhook.py`
- **_get_tenant_id_for_meta_number()** (4 connections) — `backend/app/routes/webhook.py`
- **_has_prior_inbound_in_broadcast()** (4 connections) — `backend/app/routes/webhook.py`
- **_record_per_broadcast_opt_out()** (3 connections) — `backend/app/routes/webhook.py`
- **verify_webhook()** (3 connections) — `backend/app/routes/webhook.py`
- **_get_tenant_id_for_twilio_number()** (3 connections) — `backend/app/routes/webhook.py`
- **Request** (2 connections) — `backend/app/routes/webhook.py`
- **BackgroundTasks** (1 connections) — `backend/app/routes/webhook.py`
- **Extract first phone_number_id from payload and look up its tenant.** (1 connections) — `backend/app/routes/webhook.py`
- **Extract first phone_number_id from payload and look up its tenant.** (1 connections) — `backend/app/routes/webhook.py`
- **Extract first phone_number_id from payload and look up its tenant.** (1 connections) — `backend/app/routes/webhook.py`

## Relationships

- [[Tests: Delivery Error Classification]] (3 shared connections)
- [[Conversation Compactor Service]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Meta Webhook Verify Service]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/routes/webhook.py`

## Audit Trail

- EXTRACTED: 77 (79%)
- INFERRED: 20 (21%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*