# Tests: Delivery Error Classification

> 7 nodes · cohesion 0.43

## Key Concepts

- **_is_transient_delivery_error()** (7 connections) — `backend/app/routes/webhook.py`
- **test_delivery_error_classification.py** (5 connections) — `backend/tests/test_delivery_error_classification.py`
- **test_known_transient_codes_are_transient()** (2 connections) — `backend/tests/test_delivery_error_classification.py`
- **test_transient_code_as_string_is_transient()** (2 connections) — `backend/tests/test_delivery_error_classification.py`
- **test_permanent_codes_are_not_transient()** (2 connections) — `backend/tests/test_delivery_error_classification.py`
- **test_none_and_garbage_are_not_transient()** (2 connections) — `backend/tests/test_delivery_error_classification.py`
- **Tests for transient WhatsApp delivery error classification. No DB, no network.** (1 connections) — `backend/tests/test_delivery_error_classification.py`

## Relationships

- [[WhatsApp Inbound Webhook]] (3 shared connections)

## Source Files

- `backend/app/routes/webhook.py`
- `backend/tests/test_delivery_error_classification.py`

## Audit Trail

- EXTRACTED: 13 (62%)
- INFERRED: 8 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*