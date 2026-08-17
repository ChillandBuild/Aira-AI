# Consultation Bridge — API Endpoints

Every endpoint created for the WhatsApp consultation bridge between **Aira**
(FastAPI, this repo) and **astrobackmatrimony** (Django). This is the wire
contract: field names, methods, auth, and exact request/response shapes. If you
change any of these, change them on **both** sides and update this file.

| Base | Local dev | Notes |
|---|---|---|
| Aira backend | `http://127.0.0.1:8001` | `cd backend && uvicorn app.main:app --port 8001` |
| Django backend | `http://127.0.0.1:8000` | astrobackmatrimony `manage.py runserver` |

**Configuration** (never hardcode; all three live in Aira's `app_settings`
table, per tenant):

| Key | Meaning |
|---|---|
| `astro_bridge_url` | Base URL of the Django backend (e.g. `http://127.0.0.1:8000`) |
| `astro_bridge_api_key` | Value of a `PermanentAPIKey` row in Django — sent as `X-API-Key` |
| `astro_bridge_secret` | Shared HMAC secret for the reply callback (Django reads it from the `AIRA_BRIDGE_SECRET` env var) |

---

## Direction A — Aira ➜ Django (customer paid)

### 1. `POST /api/astrologer-welcome/bridge/consultation/`

Called by Aira (service `backend/app/services/astro_bridge.py →
push_consultation`) the moment a WhatsApp customer's payment is confirmed.
Creates, in one call: the customer (`AstroUser`), a PAID payment credit
(`WelcomePayment`), the question (`UserQuestion`, `source='aira_whatsapp'`) and
the computed horoscope (`UserHoroscope`).

**Auth**: header `X-API-Key: <PermanentAPIKey.key>`

**Request** (all values already normalized by Aira — Django does not clean input):

```json
{
  "external_ref":       "b5d2fafe-b209-4fb7-8e70-1c54780bd3d2",
  "phone":              "+919990010001",
  "customer_name":      "Meena Raman",
  "person_name":        "Meena Raman",
  "person_gender":      "F",
  "person_birth_date":  "1990-03-12",
  "person_birth_time":  "09:30:00",
  "person_birth_place": "Coimbatore, Tamil Nadu",
  "question_text":      "Will my career improve this year?",
  "amount":             199.0,
  "tenant_id":          "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
}
```

Field rules (Django rejects or silently corrupts anything else — that is why
Aira normalizes first, see `astro_normalize.py`):

| Field | Rule |
|---|---|
| `external_ref` | Aira session UUID. **This is the idempotency key** — required |
| `phone` | `+91XXXXXXXXXX` |
| `person_gender` | Exactly `"M"` or `"F"` (anything else silently becomes `M` in Django) |
| `person_birth_date` | Strictly `YYYY-MM-DD` |
| `person_birth_time` | Strictly `HH:MM:SS` 24-hour |
| `person_birth_place` | Must geocode (Nominatim); Django would otherwise silently fall back to Chennai coordinates |
| `question_text` | Non-empty |

**Response `200/201`**:

```json
{
  "success": true,
  "question_id": 4190,
  "horoscope_id": "HOR-D95S67CC",
  "astro_user_id": 19178,
  "already_existed": false
}
```

**Idempotency**: `WelcomePayment.razorpay_order_id = "aira_{external_ref}"` is
UNIQUE. Re-sending the same `external_ref` returns the existing `question_id`
with `already_existed: true`. Nothing is ever created twice.

**Errors**: `{"success": false, "error": "..."}` with 400 (bad field) /
401 (bad key) / 500. Aira records nothing on failure — the reconcile job
(below) retries later.

---

### 2. `POST /api/astrologer-welcome/bridge/followup/`

A follow-up message from the same customer, riding the session they already
paid for. Creates a **new** `UserQuestion` (₹0 credit) in the same thread.

**Auth**: same `X-API-Key`.

**Request**:

```json
{
  "external_ref": "b5d2fafe-b209-4fb7-8e70-1c54780bd3d2::f1",
  "phone": "+919990010001",
  "customer_name": "Meena Raman",
  "question_text": "What remedy should I do?"
}
```

⚠️ `external_ref` **must** carry the per-follow-up suffix `::f<n>` (`::f1`,
`::f2`, …). A bare session UUID collides with the consultation's idempotency
key and the follow-up would be silently swallowed (this was a confirmed
high-severity bug during review). Aira's reply path strips the suffix when
resolving the session (`session_ref_to_id`).

**Response**: same shape as the consultation endpoint.

---

## Direction B — Django ➜ Aira (astrologer replied)

### 3. `POST /api/v1/expert-handoff/astro-reply`

Called by Django (`astrologerwelcome/bridge.py → notify_aira_reply`, spawned
on a daemon thread from the astrologer-reply view) whenever an astrologer
answers a bridged question. Aira verifies, dedupes, and delivers the reply to
the customer's WhatsApp.

**Auth**: HMAC-SHA256 over the **raw request body** using
`app_settings.astro_bridge_secret`, sent as:

```
X-Astro-Signature: sha256=<hexdigest>
```

Compared with `hmac.compare_digest`. Signature failure → **401** (this is a
partner endpoint, not a provider webhook — bad signatures are rejected loudly).

**Request**:

```json
{
  "external_ref": "b5d2fafe-b209-4fb7-8e70-1c54780bd3d2",
  "question_id": 4190,
  "reply_id": 789,
  "reply_text": "Jupiter's transit favours you this year.",
  "reply_image_url": "https://…/replies/4190/image.jpg",
  "reply_voice_url": null,
  "astrologer_name": "Revathi",
  "replied_at": "2026-08-17T18:00:00Z"
}
```

`reply_text` may be an empty string; `reply_image_url` / `reply_voice_url` are
absolute public URLs or `null`.

**Responses**:

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"ok": true}` | Accepted (delivery attempted) |
| 200 | `{"ok": true, "duplicate": true}` | `reply_id` already processed — Django must not retry |
| 200 | `{"ok": true, "delivered": [], "failed": […], "delivery_failed": true}` | Accepted but every WhatsApp send failed — claim rolled back, staff alerted |
| 401 | `{"error": …}` | Unknown `external_ref` or bad signature (deliberately identical, no information leak) |

**Delivery order** (per reply, each via the phone number the lead actually
messaged): text → image (download → upload to Meta → send) → voice. Every sent
message is logged to `messages` with `reply_source="expert_handoff"`.

**Dedup / crash-safety**: `expert_handoff_sessions.astro_last_reply_id` is
claimed **monotonically** (`IS NULL OR < reply_id`) before sending. If *all*
sends fail, the claim is rolled back to its prior value and `notify_pool`
alerts staff — a paid reply is never silently lost.

---

## Admin panel (adminweb ➜ Django)

### 4. `GET /api/astrologer-welcome/admin/aira-customers/`

Backs the adminweb page **Our Astrologer → Aira Customers**. Lists every
bridged question with customer, birth details, jathagam, payment, assignment
and replies. Implementation: `astrologerwelcome/admin_aira.py`.

**Auth**: owner token — `Authorization: Token <owner_token>` (same
`@_admin_auth` chain as every other admin endpoint).

**Query params**: `status=pending|replied` · `date_from=YYYY-MM-DD` ·
`date_to=YYYY-MM-DD` · `page` · `page_size` (default 20, max 200).

**Response**:

```json
{
  "success": true,
  "shift_routing": true,
  "results": [{
    "question_id": 4190,
    "aira_session": "b5d2fafe-…",
    "is_followup": false,
    "customer_name": "Meena Raman",
    "phone": "+919990010001",
    "question_text": "…",
    "amount": 199,
    "status": "pending",
    "created_at": "2026-08-17T…Z",
    "astrologer": "Revathi",
    "birth_details": {
      "person_name": "Meena Raman", "gender": "F",
      "date_of_birth": "1990-03-12", "time_of_birth": "09:30:00",
      "place_of_birth": "Coimbatore"
    },
    "horoscope": {"id": "HOR-D95S67CC", "rasi": "கன்னி", "nakshatra": "உத்திரம்", "lagna": "மேஷம்"},
    "replies": [{"id": 789, "astrologer": "Revathi", "text": "…",
                 "image_url": null, "voice_url": null, "replied_at": "…"}]
  }],
  "stats": {"total": 1, "pending": 1, "replied": 0, "revenue": 199},
  "pagination": {"current_page": 1, "total_pages": 1, "total_items": 1, "page_size": 20}
}
```

Notes: `astrologer` is the replier if replied, else the assigned astrologer,
else `null` — and when `shift_routing` is `true`, `null` means "whoever is on
shift", which the UI labels **On-shift astrologer**. Stats are global for the
bridged set (filters don't change the cards). Follow-ups show `amount: 0`
(already paid in the first session) and fall back to the customer's own
jathagam for birth details.

---

## Astrologer portal (astrologerwelcomes ➜ Django)

### 5. `GET /api/astrologer-welcome/astrologer/inbox/?type=aira`

The portal Inbox's third tab. `type` now accepts `paid | free | aira`;
`aira` returns only WhatsApp-bridged customers. In **every** tab, each row
carries a new boolean `is_aira` (rendered as the green "📲 AIRA" chip).

**Auth**: astrologer token — `Authorization: Token <astrologer_token>`.

### 6. `GET /api/astrologer-welcome/astrologer/dashboard/`

The dashboard payload gained a top-level `aira` block (payload version 7):

```json
"aira": {
  "total_customers": 1,
  "total_questions": 1,
  "pending": 1,
  "replied_by_me": 0,
  "received_today": 1
}
```

Same visibility scope as every other dashboard figure (shift window or
assignment). The portal renders it as its own "📲 Aira — WhatsApp Customers"
card with a View button deep-linking to `/inbox?tab=aira`.

---

## Aira dashboard (frontend ➜ Aira)

### 7. `GET /api/v1/expert-handoff/stats`

Backs the **Consultations → Dashboard** tab in Aira's own dashboard. Mirrors
the adminweb "Aira Customers" stats so both teams read the same numbers.

**Auth**: Aira dashboard session (`conversations.view` permission), tenant-scoped.

**Response**:

```json
{
  "totals": {
    "messages": 3,          // paid consultations (status paid|resolved)
    "answered": 2,          // astrologer's reply came back over the bridge
    "pending": 1,           // paid but not yet answered
    "awaiting_payment": 1,  // leads still on the payment step
    "revenue_inr": 399
  },
  "daily": [{"date": "2026-08-04", "count": 0}, …]   // last 14 days, oldest first
}
```

"Answered" is `astro_last_reply_id IS NOT NULL` — i.e. the reply was received
*and* claimed for delivery, the same definition the reply-dedup logic uses.

## Background job (Aira, not an HTTP endpoint)

**`astro-push-reconcile`** — APScheduler job, every 5 minutes
(`backend/app/main.py`). Re-drives Direction A for any *paid* session from the
last 3 days whose `astro_question_id` is still NULL (Django was down, network
blip, crash between payment and push). Push is idempotent, so re-driving is
always safe. This is the reason a paid consultation can never be permanently
lost between the two systems.

## Session columns (Aira, migration 176)

`expert_handoff_sessions` gained: `astro_question_id`, `astro_horoscope_id`,
`astro_user_id` (stamped after a successful push) and `astro_last_reply_id`
(the reply-dedup claim).
