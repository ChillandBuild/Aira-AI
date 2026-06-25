# Facebook / Webhook Verification

> 12 nodes · cohesion 0.23

## Key Concepts

- **facebook_webhook()** (16 connections) — `backend/app/routes/facebook.py`
- **facebook.py** (5 connections) — `backend/app/routes/facebook.py`
- **verify_facebook_webhook()** (5 connections) — `backend/app/routes/facebook.py`
- **test_facebook.py** (4 connections) — `backend/tests/test_facebook.py`
- **test_facebook_webhook_ignores_echo()** (4 connections) — `backend/tests/test_facebook.py`
- **str** (2 connections) — `backend/app/routes/facebook.py`
- **Request** (2 connections) — `backend/app/routes/facebook.py`
- **test_verify_facebook_webhook_success()** (2 connections) — `backend/tests/test_facebook.py`
- **test_facebook_webhook_new_lead()** (2 connections) — `backend/tests/test_facebook.py`
- **BackgroundTasks** (1 connections) — `backend/app/routes/facebook.py`
- **Echo messages (is_echo=True) should be silently skipped.** (1 connections) — `backend/tests/test_facebook.py`
- **Echo messages (is_echo=True) should be silently skipped.** (1 connections) — `backend/tests/test_facebook.py`

## Relationships

- [[Config Dynamic]] (2 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Meta Webhook Verify Service]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Conversation Compactor Service]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/routes/facebook.py`
- `backend/tests/test_facebook.py`

## Audit Trail

- EXTRACTED: 29 (64%)
- INFERRED: 16 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*