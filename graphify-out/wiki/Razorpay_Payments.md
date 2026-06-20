# Razorpay Payments

> 14 nodes · cohesion 0.25

## Key Concepts

- **RuntimeError** (14 connections)
- **create_payment_link()** (12 connections) — `backend/app/services/payment_razorpay.py`
- **verify_webhook_signature()** (9 connections) — `backend/app/services/payment_razorpay.py`
- **payment_razorpay.py** (6 connections) — `backend/app/services/payment_razorpay.py`
- **_get_key_id()** (5 connections) — `backend/app/services/payment_razorpay.py`
- **str** (5 connections) — `backend/app/services/payment_razorpay.py`
- **_get_key_secret()** (5 connections) — `backend/app/services/payment_razorpay.py`
- **_get_webhook_secret()** (5 connections) — `backend/app/services/payment_razorpay.py`
- **int** (1 connections) — `backend/app/services/payment_razorpay.py`
- **Any** (1 connections) — `backend/app/services/payment_razorpay.py`
- **bytes** (1 connections) — `backend/app/services/payment_razorpay.py`
- **bool** (1 connections) — `backend/app/services/payment_razorpay.py`
- **Create a Razorpay Payment Link and return the short URL.      Returns dict with** (1 connections) — `backend/app/services/payment_razorpay.py`
- **Verify Razorpay webhook payload using HMAC-SHA256.** (1 connections) — `backend/app/services/payment_razorpay.py`

## Relationships

- [[AI Reply Pipeline (Groq)]] (3 shared connections)
- [[Calls API (TeleCMI dialer)]] (3 shared connections)
- [[Growth Service]] (1 shared connections)
- [[Broadcast Executor & Outbound Router]] (1 shared connections)
- [[Knowledge Base (pgvector RAG)]] (1 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)
- [[Tests: Notify Service]] (1 shared connections)
- [[Tests: Reengagement Service]] (1 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Booking Flow]] (1 shared connections)
- [[Tenant]] (1 shared connections)

## Source Files

- `backend/app/services/payment_razorpay.py`

## Audit Trail

- EXTRACTED: 43 (64%)
- INFERRED: 24 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*