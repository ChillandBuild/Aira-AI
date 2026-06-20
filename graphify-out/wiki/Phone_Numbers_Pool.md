# Phone Numbers Pool

> 11 nodes · cohesion 0.40

## Key Concepts

- **numbers.py** (9 connections) — `backend/app/routes/numbers.py`
- **UpdatePhoneNumber** (7 connections) — `backend/app/routes/numbers.py`
- **str** (7 connections) — `backend/app/routes/numbers.py`
- **update_phone_number()** (6 connections) — `backend/app/routes/numbers.py`
- **sync_number_from_meta()** (6 connections) — `backend/app/routes/numbers.py`
- **delete_phone_number()** (6 connections) — `backend/app/routes/numbers.py`
- **CreatePhoneNumber** (5 connections) — `backend/app/routes/numbers.py`
- **UUID** (5 connections) — `backend/app/routes/numbers.py`
- **create_phone_number()** (4 connections) — `backend/app/routes/numbers.py`
- **list_phone_numbers()** (3 connections) — `backend/app/routes/numbers.py`
- **Hard delete a phone number. FK on incidents.phone_number_id is ON     DELETE SET** (1 connections) — `backend/app/routes/numbers.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (7 shared connections)
- [[Operator Console & Audit]] (4 shared connections)
- [[Leads API]] (2 shared connections)
- [[Tenant]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)

## Source Files

- `backend/app/routes/numbers.py`

## Audit Trail

- EXTRACTED: 47 (80%)
- INFERRED: 12 (20%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*