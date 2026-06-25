# Instagram Channel

> 9 nodes · cohesion 0.31

## Key Concepts

- **instagram_webhook()** (15 connections) — `backend/app/routes/instagram.py`
- **instagram.py** (5 connections) — `backend/app/routes/instagram.py`
- **verify_instagram_webhook()** (5 connections) — `backend/app/routes/instagram.py`
- **test_instagram.py** (3 connections) — `backend/tests/test_instagram.py`
- **str** (2 connections) — `backend/app/routes/instagram.py`
- **Request** (2 connections) — `backend/app/routes/instagram.py`
- **test_verify_instagram_webhook_success()** (2 connections) — `backend/tests/test_instagram.py`
- **test_instagram_webhook_new_lead()** (2 connections) — `backend/tests/test_instagram.py`
- **BackgroundTasks** (1 connections) — `backend/app/routes/instagram.py`

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

- `backend/app/routes/instagram.py`
- `backend/tests/test_instagram.py`

## Audit Trail

- EXTRACTED: 23 (62%)
- INFERRED: 14 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*