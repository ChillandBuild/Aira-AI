# How the Consultation Bridge Works — Developer Guide

This explains, from zero, how the WhatsApp consultation system is built:
what happens when a customer pays, which project does what, why each design
decision was made, and how to run and test it. It assumes no prior knowledge
of the codebase. The exact request/response shapes live in
[ConsultationAPIEndpoints.md](ConsultationAPIEndpoints.md) — keep both files
updated together.

---

## 1. The big picture

A customer chats with **Aira** on WhatsApp, pays for a consultation, and gives
five things: name, gender, date of birth, time of birth, place of birth. An
astrologer — managed in the existing **adminweb → Our Astrologer** list —
answers from the astrologer portal, and the answer travels back to the
customer's WhatsApp. Four projects cooperate:

```
 Customer on WhatsApp
        │  pays + gives birth details
        ▼
 ┌─────────────┐   A: push consultation    ┌──────────────────────┐
 │    AIRA     │ ────────────────────────▶ │  astrobackmatrimony  │
 │  (FastAPI,  │        X-API-Key          │  (Django + DRF)      │
 │  this repo) │ ◀──────────────────────── │  customers, payments,│
 └─────────────┘   B: reply callback       │  questions, jathagam │
        │            HMAC signature        └──────────┬───────────┘
        │ sends reply to                              │ reads/writes
        ▼ customer's WhatsApp              ┌──────────┴───────────┐
                                           │ astrologerwelcomes   │ ← astrologer replies here
                                           │ (portal, React)      │   (Inbox → “Aira” tab)
                                           ├──────────────────────┤
                                           │ adminweb (React)     │ ← admins watch here
                                           │ Our Astrologer →     │   (“Aira Customers” page)
                                           │ Aira Customers       │
                                           └──────────────────────┘
```

Three directions of traffic:

- **A (Aira → Django)**: payment confirmed → create customer + paid question +
  horoscope in Django.
- **B (Django → Aira)**: astrologer replied → hand the reply back → Aira sends
  it to WhatsApp (text / image / voice).
- **C (Aira → Django)**: customer asks a follow-up → a new question in the
  same thread.

## 2. Step-by-step: the life of one consultation

1. **Payment confirms** in Aira (`confirm_intake_payment`). The status
   flip is an *atomic conditional UPDATE* (`WHERE status='awaiting_payment'`)
   so two concurrent payment webhooks can never both succeed.
2. **Normalization** (`backend/app/services/astro_normalize.py`). The customer
   typed things like `"12th March 1990"`, `"9:30 AM"`, `"பெண்"`. Pure functions
   convert them to `1990-03-12`, `09:30:00`, `F`. **If a value can't be parsed
   with confidence, we refuse and skip the push** rather than guess — because
   Django silently turns an unknown gender into `M` and an un-geocodable
   birthplace into Chennai coordinates, which would produce a *wrong horoscope
   that looks right*. Refusing loudly beats corrupting quietly.
3. **Push** (`astro_bridge.push_consultation`) → Django's bridge endpoint.
   Django (`astrologerwelcome/bridge.py`) finds-or-creates the customer by
   phone, creates a PAID credit, reuses the existing `user_submit_question`
   logic (so every side effect the app relies on still runs), computes the
   jathagam, and — when shift routing is off — assigns the question to the
   first active, non-deleted, **non-demo** astrologer. With shift routing on,
   no assignment is needed: whoever is on shift sees it.
4. **Aira records** `astro_question_id` / `astro_horoscope_id` /
   `astro_user_id` on the session (migration 179). If the push failed, the
   **reconcile job** retries every 5 minutes for up to 3 days — pushes are
   idempotent, so retrying is always safe.
5. **The astrologer replies** in the portal (Inbox → **Aira** tab; bridged
   customers wear a green 📲 AIRA chip everywhere). The reply view spawns a
   daemon thread → `notify_aira_reply` → signed callback to Aira.
6. **Aira delivers to WhatsApp**: claims the reply id (dedup), then sends text
   → image → voice via the exact phone number the customer messaged. Total
   failure = claim rolled back + staff alerted. The 24-hour WhatsApp window is
   checked before sending — failing loudly beats the astrologer seeing
   “delivered” while the customer got nothing.
7. **Follow-up**: the customer writes again → Direction C with
   `external_ref = "<session>::f1"` → new ₹0 question in the same thread.

## 3. The design decisions, and *why*

These are the parts that separate “it works on my machine” from production
software. Each one exists because of a specific failure it prevents.

| # | Decision | The failure it prevents |
|---|---|---|
| 1 | **Idempotency key** on every create (`razorpay_order_id = aira_<ref>`, UNIQUE) | Network retries / crashed processes creating the same paid question twice — the customer would be answered twice, or worse, charged twice in the books |
| 2 | **HMAC-SHA256 over the raw body** for the reply callback, `hmac.compare_digest` | Anyone who discovers the URL forging “astrologer replies” into customers' WhatsApp. Signing the *raw* bytes (before JSON parsing) means re-serialization differences can't break or bypass verification |
| 3 | **Refuse, don't guess** in normalization (gender/date/place) | Silently defaulted gender → a wrong-but-plausible horoscope. Wrong data that *looks* right is the worst kind of bug |
| 4 | **Monotonic reply claim** (`astro_last_reply_id IS NULL OR < id`) + rollback + staff alert | Two callback retries double-sending on WhatsApp; or a total send failure being swallowed so a *paid* reply is lost with nobody knowing |
| 5 | **Reconcile job** (every 5 min, idempotent re-push) | Django being down for a minute at the exact moment a customer pays — without this the consultation would simply never arrive |
| 6 | **Follow-up suffix `::f<n>`** | Bare session id collides with decision #1's key, so follow-ups would silently vanish (found in adversarial review) |
| 7 | **Bulkwise suppression** (`source='aira_whatsapp'` → no Django-side WhatsApp template) | The customer getting messages from two different numbers about one conversation |
| 8 | **Demo-astrologer gate** (no auto-assignment; replies never forwarded) | A training-sandbox reply reaching a real paying customer |
| 9 | **Tenant-scoped settings** (`get_setting(key, tenant_id=…)` — always pass it) | Config silently resolving to the bootstrap tenant, sending one tenant's traffic with another tenant's credentials |
| 10 | **Uniform 401** for unknown-ref *and* bad-signature on the callback | An attacker probing which session ids exist |

## 4. Where the code lives

**Aira (this repo)**
- `backend/app/services/astro_normalize.py` — pure normalization functions (no I/O)
- `backend/app/services/astro_bridge.py` — Direction A + C clients, signature verify
- `backend/app/services/intake.py` — payment confirm, reply nudge, reconcile job, `session_ref_to_id`, `_compose_reply_nudge`
- `backend/app/routes/intake.py` — push hook after payment; public `/astro-reply` route
- `backend/app/main.py` — `astro-push-reconcile` scheduler job
- `backend/supabase/migrations/179_astro_bridge_session_links.sql`, `181_astro_reply_nudge.sql` (180 added a follow-up counter and 181 dropped it again — see below)
- Tests: `backend/tests/test_astro_normalize.py`, `test_astro_bridge.py`, `test_astro_reply_hardening.py`, `test_intake_stats.py`, plus updates in `test_expert_handoff*.py`

**astrobackmatrimony (Django)**
- `astrologerwelcome/bridge.py` — all bridge logic (deliberately *not* in the 21k-line `views.py`)
- `astrologerwelcome/admin_aira.py` — the Aira Customers admin endpoint
- `astrologerwelcome/views.py` — three surgical hooks only: Bulkwise suppression, reply→Aira thread, `type=aira` inbox filter + dashboard `aira` block
- Migration `0109_userquestion_source`
- Tests: `tests_bridge.py`, `tests_bridge_views.py`, `tests_admin_aira.py`, `tests_inbox_aira.py`

**astrologerwelcomes (portal)** — Inbox third tab “Aira”, AIRA chip, Dashboard Aira card.
**adminweb** — sidebar child “Aira Customers” + page (`src/pages/astrologer-welcomes/AiraCustomers.jsx`).

## 5. Running it locally

| Port | What | Command |
|---|---|---|
| 8001 | Aira backend | `cd backend && uvicorn app.main:app --port 8001` |
| 8000 | Django | `AIRA_BRIDGE_URL=http://127.0.0.1:8001 AIRA_BRIDGE_SECRET=<astro_bridge_secret> python manage.py runserver 127.0.0.1:8000` |
| 3000 | Aira frontend | `cd frontend && npm run dev` |
| 3002 | astrologer portal | `PORT=3002 npm start` |
| 3003 | adminweb | `PORT=3003 npm start` |

Django needs the two `AIRA_BRIDGE_*` env vars or replies never reach Aira.
Aira needs the three `astro_bridge_*` settings rows (see the endpoints file).
The same two env vars must be set on the **deployed** Django for production.

## 6. Testing

```bash
# Aira — full suite (1124 tests)
cd backend && pytest

# Django — bridge + admin + inbox suites
python manage.py test astrologerwelcome.tests_bridge astrologerwelcome.tests_bridge_views \
    astrologerwelcome.tests_admin_aira --settings=sqlite_test_settings
# tests_inbox_aira uses Postgres-only SQL (DISTINCT ON) — run it against Postgres:
DATABASE_URL=postgresql://…local python manage.py test astrologerwelcome.tests_inbox_aira
```

Never point a local Django at the production database while testing. Check the
resolved DB host before running anything destructive.

## 7. How industry-standard development differs from “just make it work”

This section is the honest answer to “what does a senior do differently?”.
Every item below was actually applied in this build — none of it is theory.

1. **Write the contract first.** Both sides were built against one written
   wire contract (now `ConsultationAPIEndpoints.md`). Without it, two devs
   invent two shapes and integration becomes guesswork.
2. **Assume every request happens twice.** Payments retry, threads crash,
   users double-tap. Idempotency keys and conditional UPDATEs make “twice”
   harmless. If your endpoint breaks when called twice, it's broken.
3. **Never trust input — including your own LLM's.** Parse strictly, refuse
   what you can't parse, and never let a framework's silent default (gender→M,
   place→Chennai) stand in for real data.
4. **Secrets live in settings/env, never in code or docs.** The API key and
   HMAC secret exist only in the database and environment. (Counter-example
   already in the codebase: hardcoded admin passwords — a known issue to fix.)
5. **Fail loudly where money or trust is involved.** A paid reply that can't
   be delivered rolls back its claim and pages staff. Silent failure is the
   most expensive kind.
6. **Schema changes are migrations, never hand-edits** — numbered, ordered,
   replayable. (While building this we found none of the three projects could
   rebuild its own schema from scratch; those repairs are part of this work.)
7. **Tests are the definition of done.** ~50 new tests across both backends,
   including regression tests written *from the review findings* — every bug
   found got a test that fails without its fix.
8. **Adversarial review before ship.** The build was reviewed by deliberately
   trying to break it: 14 confirmed defects (3 high) were found and fixed —
   including the follow-up idempotency collision that no happy-path test
   would ever catch.
9. **Docs are part of the deliverable.** This file and the endpoints file
   exist so the next person doesn't have to reverse-engineer 21,000-line
   files.
10. **Branches, not direct pushes to main.** Work lands on a named feature
    branch (`consultation-ansar-section`) so it can be reviewed and reverted
    as a unit.

## 8. Current limits & what's next

- **Real WhatsApp delivery** needs the client's Meta credentials *and* Meta
  lifting error 131031 on the WABA. Until then the delivery step fails cleanly
  (claim rollback, staff alert) — by design.
- **Deployed Django** must receive this code + the two `AIRA_BRIDGE_*` env
  vars before replies made on the live portal reach Aira.
- **Reply types** are text / image / voice — the portal has no video reply
  today; adding one is a Django model + portal + bridge change.
- Pre-existing security items reported separately to the maintainers
  (payment-webhook signature skip, hardcoded admin credentials, missing
  reply-ownership check, `DEBUG` hardcoded).


## The reply does not reach WhatsApp (changed 2026-08-18)

The astrologer's answer is deliberately **not** delivered to the customer's
WhatsApp. When the reply callback arrives, Aira sends one short message — "your
answer is ready, open the app and sign in with this number" — and the customer
reads the answer inside the AstroTamil app.

Consequences worth knowing before changing anything here:

- **`reply_image_url` and `reply_voice_url` are ignored.** The media relay
  (Meta upload + send) was deleted; nothing in Aira touches astrologer media.
- **`reply_text` is archived, not sent.** It lands on
  `intake_sessions.astro_last_reply_text` so support can answer "I can't find it
  in the app", and deliberately **not** in `messages`, which records what the
  customer actually received.
- **The app link is appended in code**, read from the `app_download_link`
  setting. Never let the model write it: a hallucinated download URL sent to a
  paying customer is the failure commit `24494b3d` already fixed once.
- **Follow-ups are gone from WhatsApp entirely** — no `push_followup`, no
  counter, no forwarding branch in `route_intake`. The conversation continues in
  the app.
- **No 24-hour window check and no staff alert on it**, by explicit decision:
  the astrologer answers same-day in practice, and anything after that is the
  app's problem. If that assumption ever breaks, the fix is a WhatsApp template
  for the nudge (its text is fixed, so it qualifies) rather than reinstating the
  check.
