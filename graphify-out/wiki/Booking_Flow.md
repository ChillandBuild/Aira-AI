# Booking Flow

> 89 nodes · cohesion 0.05

## Key Concepts

- **whatsapp_webhook()** (26 connections) — `backend/app/routes/webhook.py`
- **send_whatsapp()** (24 connections) — `backend/app/services/ai_reply.py`
- **route_booking_intent()** (21 connections) — `backend/app/services/booking_flow.py`
- **booking_flow.py** (20 connections) — `backend/app/services/booking_flow.py`
- **str** (19 connections) — `backend/app/services/booking_flow.py`
- **get_or_create_state()** (18 connections) — `backend/app/services/booking_flow.py`
- **advance_state()** (14 connections) — `backend/app/services/booking_flow.py`
- **webhook.py** (13 connections) — `backend/app/routes/webhook.py`
- **test_booking_flow.py** (11 connections) — `backend/tests/test_booking_flow.py`
- **start_booking_flow()** (10 connections) — `backend/app/services/booking_flow.py`
- **compact_conversation()** (10 connections) — `backend/app/services/conversation_compactor.py`
- **str** (9 connections) — `backend/app/routes/webhook.py`
- **_send_payment_link()** (9 connections) — `backend/app/services/booking_flow.py`
- **_make_db()** (9 connections) — `backend/tests/test_booking_flow.py`
- **_process_inbound_message_background()** (8 connections) — `backend/app/routes/webhook.py`
- **send_whatsapp_text()** (8 connections) — `backend/app/services/booking_flow.py`
- **send_migration_notice()** (8 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/failover.py`
- **_is_transient_delivery_error()** (7 connections) — `backend/app/routes/webhook.py`
- **_resolve_tenant_from_payload()** (7 connections) — `backend/app/routes/webhook.py`
- **_create_draft_booking()** (7 connections) — `backend/app/services/booking_flow.py`
- **confirm_booking()** (7 connections) — `backend/app/services/booking_flow.py`
- **handle_quality_red()** (7 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/failover.py`
- **update_number_quality()** (7 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/failover.py`
- **_handle_opt_out()** (6 connections) — `backend/app/routes/webhook.py`
- **detect_booking_intent()** (6 connections) — `backend/app/services/booking_flow.py`
- *... and 64 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (17 shared connections)
- [[AI Reply Pipeline (Groq)]] (6 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Leads API]] (4 shared connections)
- [[Tenant]] (3 shared connections)
- [[Meta Cloud API Client]] (3 shared connections)
- [[Growth Service]] (3 shared connections)
- [[Instagram Channel]] (3 shared connections)
- [[Config]] (2 shared connections)
- [[Notify Service]] (2 shared connections)
- [[Call Coach Service]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/services/failover.py`
- `backend/app/routes/webhook.py`
- `backend/app/services/ai_reply.py`
- `backend/app/services/booking_flow.py`
- `backend/app/services/conversation_compactor.py`
- `backend/app/services/failover.py`
- `backend/tests/test_booking_flow.py`
- `backend/tests/test_delivery_error_classification.py`

## Audit Trail

- EXTRACTED: 356 (78%)
- INFERRED: 102 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*