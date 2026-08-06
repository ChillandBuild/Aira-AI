# Paid Expert Handoff — Design

**Date:** 2026-08-07
**Status:** Approved, ready for implementation planning

A generic, tenant-configurable flow: when a lead's message signals they need a
real human expert (not the AI), offer a paid consultation, collect whatever
details that tenant's expert needs — in free-flowing conversation, not a rigid
script — take payment in WhatsApp, and hand the lead off.

## Problem

Astrotamil's current flow (client's Android app) tells a lead who asks a
personal astrology question to download an app and pay there to talk to an
astrologer. That's friction that loses leads who won't install an app just to
pay ₹29. The fix: collect details and take payment **inside the WhatsApp
chat**, no app required.

This must not be Astrotamil-specific — the trigger question, the fields
collected, and the fee vary per client (astrologer needs DOB/birthplace; a
gym's trainer needs age/goal; a clinic's doctor needs symptoms).

### Why not reuse `feature/client-requirements`'s booking flow

A generic 5-step booking state machine already exists on that branch
(`booking_flow.py`, `bookings` table, `lead_conversation_state.state`). It
was rejected as a foundation for one specific, load-bearing reason: it is a
**rigid step machine** — `collecting_name → collecting_rasi → …` — and it
breaks under normal conversation. If a lead answers an off-topic question
mid-flow, `_is_booking_question` lets the AI answer it but then re-prompts
the *same* pending step; if the lead volunteers two fields in one message
("I'm Priya, born 5 March 1995"), only the current step's field is captured
and the rest is lost. This was reported as a recurring real problem, not a
hypothetical.

This design replaces the collection mechanism with LLM slot-filling and
treats the booking branch as reference only, not a base to build on.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | LLM slot-filling, not a state machine | Every inbound message (while a session is active) is run through an LLM extractor that pulls whatever configured fields it can find, in any order, embedded in normal conversation. No "current step" means no way to fall off it. |
| D2 | Explicit opt-in before collecting anything | AI detects intent → **offers** the paid consultation → only starts collecting on a yes. Auto-starting on inferred intent risks feeling presumptuous and collects data from leads who never agreed to pay. |
| D3 | Fields, fee, and offer message are per-tenant JSON config | Different clients need different fields (astrologer: DOB/birthplace; trainer: goal). Config lives in `app_settings` (existing per-tenant key/value store), no schema change per client. |
| D4 | Tenant admin UI to edit that config | Ships now, not deferred — onboarding a new client (or the client themselves) edits fields/fee/message from the dashboard, no code touched, no deploy needed. |
| D5 | One summary confirmation, not per-field | Show all collected fields back once before payment ("Name: Priya, DOB: 5 Mar 1995 — correct?"). Per-field confirmation is naggy in a casual chat. |
| D6 | Single fixed fee per tenant for v1 | Multiple price tiers is a real feature with its own UX (which tier, how offered) — add when a client asks for it. |
| D7 | New dedicated table, not `bookings`/`lead_conversation_state` | Those are coupled to the temple-specific booking flow (`booking_id` FK, fixed devotee/rasi/gotram columns). A clean `expert_handoff_sessions` table avoids inheriting that coupling and the bugs above. |
| D8 | Reuse `leads.ai_enabled` to mute the AI post-payment | Already exists, already checked in `generate_reply` (`ai_reply.py:1164`) before any auto-reply fires. No new mute mechanism needed — flip it `False` on payment confirmation. This is a **different** behavior from existing chat escalation (which deliberately keeps the AI live, see `2026-07-19-escalation-whatsapp-alerts-design.md` D6) — here, silence is the explicit product decision because a paying customer's consultation shouldn't have the AI talking over it. |
| D9 | Reuse `payment_razorpay.py` as-is | Its `create_payment_link()` is already generic (booking_id/ref/amount/customer/description as params) — no astrology-specific assumptions. Reused, not rewritten. |
| D10 | Astrologer delivery + reply relay is **out of scope** for this design | Requires knowing how Astrotamil's dashboard receives data and sends replies back — an external fact, not something this codebase can determine. Tracked separately; see Out of scope. |

## Data model

New table, migration `168_expert_handoff_sessions.sql`:

```sql
CREATE TABLE IF NOT EXISTS expert_handoff_sessions (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid        NOT NULL,
  lead_id        uuid        NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  status         text        NOT NULL DEFAULT 'offer_pending'
                   CHECK (status IN (
                     'offer_pending', 'collecting', 'awaiting_confirmation',
                     'awaiting_payment', 'paid', 'resolved', 'cancelled'
                   )),
  collected_data jsonb       NOT NULL DEFAULT '{}',
  trigger_reason text,
  amount_paise   integer,
  payment_link   text,
  razorpay_payment_id text,
  paid_at        timestamptz,
  resolved_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS expert_handoff_lead_idx   ON expert_handoff_sessions (lead_id, tenant_id);
CREATE INDEX IF NOT EXISTS expert_handoff_status_idx ON expert_handoff_sessions (status, tenant_id);
```

One active (non-`resolved`/`cancelled`) session per lead at a time — enforced
in application code (check-before-insert), same pattern as
`_create_draft_booking`'s existing-booking check.

**Tenant config** — `app_settings` row per tenant, key `expert_handoff_config`,
JSON-encoded value (text column, matches how every other multi-value config in
this table is stored):

```json
{
  "enabled": true,
  "trigger_description": "Lead asks a personal astrology question (marriage, career, health, timing) that needs a real astrologer's reading, not a generic answer.",
  "offer_message": "That's something our astrologer can help with directly — ₹29 for a consultation, right here on WhatsApp. Want to go ahead?",
  "fields": [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "birthplace", "label": "Birthplace", "type": "text"}
  ],
  "amount_paise": 2900
}
```

No new columns on `leads`. Mute uses the existing `ai_enabled` boolean.

## Backend flow

New service module `backend/app/services/expert_handoff.py`, mirroring the
shape of `booking_flow.py`'s webhook entry point but not its internals:

```
route_expert_handoff(lead_id, tenant_id, phone, body, db) -> bool
```

Called from the webhook handler in the same slot `route_booking_intent`
occupies today — before AI fallback, after inbound message is persisted.
Returns `True` if the message was consumed by this flow (caller skips normal
AI reply generation for that turn).

1. **No active session, feature enabled for tenant:**
   Run detection — one LLM call: "does this message match
   `trigger_description`?" (boolean). No match → return `False`, normal AI
   reply proceeds untouched.
   Match → send `offer_message`, create an `expert_handoff_sessions` row at
   `status='offer_pending'` (empty `collected_data`). Keeping this on the same
   table as everything else — rather than a second marker mechanism — is what
   D7 actually calls for; a stale `offer_pending` row a lead never answers is
   harmless and self-explanatory, unlike a hidden marker in an unrelated
   table. Return `True`.

2. **`offer_pending` session, lead replies:**
   Affirmative → move to `status='collecting'`, run extraction (step 3)
   immediately on this same message since it may already contain field data
   ("yes, I'm Priya").
   Negative/unclear → move to `status='cancelled'`, return `False` (let AI
   handle normally).

3. **Active `collecting` session:**
   One LLM call: given `collected_data` so far + configured `fields` +
   this message, return updated `collected_data` and list of still-missing
   fields (uses existing `gemini_chat_completion_json` — `app/services/
   gemini_client.py:281` — no new JSON-extraction plumbing needed).
   - All fields filled → move to `awaiting_confirmation`, send the summary
     message, return `True`.
   - Fields still missing → save partial `collected_data`, ask only for what's
     missing, return `True`.
   - Message is clearly unrelated to any field and extraction finds nothing
     → let the AI answer it *in addition to* the still-pending prompt (same
     spirit as the old `_is_booking_question` off-ramp, but non-blocking:
     collection state doesn't move, nothing is lost either way).

4. **`awaiting_confirmation`:**
   Yes → move to `awaiting_payment`, call `create_payment_link()` (existing,
   unmodified) with `amount_paise` from tenant config, send link. No → allow
   correction of a specific field (re-run extraction), stay in
   `awaiting_confirmation`.

5. **Razorpay webhook fires** (existing `razorpay_webhook` route, generic
   already — takes `payment_link_id`/`payment_id`, not booking-specific):
   mark session `paid`, `paid_at = now()`, set `leads.ai_enabled = False`,
   send WhatsApp receipt.

6. **Resolution (v1, manual):** no astrologer-dashboard signal exists yet
   (D10), so nothing automatically resumes the AI. Tenant admin flips
   `ai_enabled` back on manually from the existing lead view once the
   consultation is done — same control that already exists for any other
   manual mute today. Session `status` moves to `resolved` on the same
   action, closing out `expert_handoff_sessions`.

## Frontend

New panel `frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx`,
added to `settings/page.tsx` alongside the existing panels
(`InboxConfigPanel`, `TelecallingConfigPanel`, etc.) — same tab, same layout
convention, no new page.

- Toggle: enabled/disabled for this tenant
- Text area: trigger description (what counts as "needs an expert" — fed
  directly into the LLM detection prompt)
- Text area: offer message
- Repeatable field list: label + type (`text` | `date` | `choice`, with
  options for `choice`), add/remove/reorder
- Number input: fee (rupees, converted to paise on save)

Backed by a small settings API (GET/PUT `expert_handoff_config` via the
existing `/api/v1/settings` app_settings read/write path — no new endpoint
pattern, just a new key).

## Error handling

- Payment link creation fails → same fallback as the existing booking flow:
  "We've received your details, our team will send the payment link shortly"
  + log, session stays `awaiting_payment`.
- LLM extraction call fails/times out → treat as "no fields extracted this
  turn," re-ask the still-missing fields rather than blocking the
  conversation. Never silently drop the session.
- Detection LLM call fails → fail closed (`False`, normal AI reply proceeds).
  A missed offer is recoverable (lead can ask again); a wrongly-triggered
  payment flow on an LLM hiccup is not.

## Testing

- Unit: extraction merges partial `collected_data` correctly across turns,
  including two-fields-in-one-message and zero-fields-in-a-message cases.
- Unit: detection gates correctly on `enabled=false` and on tenants with no
  config at all (feature off by default, not opt-out).
- Integration: full flow end-to-end against a test tenant config — offer →
  collect (out of order) → confirm → payment webhook → `ai_enabled=False`
  verified on the lead row.
- Manual: live-tested against real Groq/Gemini calls for extraction accuracy
  before shipping the Astrotamil config live (per this repo's rule — LLM
  behavior needs live verification, not just unit tests with mocked
  responses).

## Out of scope

- **Astrologer/expert delivery adapter** (sending the paid session to
  Astrotamil's dashboard) and **reply relay** (astrologer's reply reaching
  the lead's WhatsApp) — blocked on Astrotamil's integration surface being
  unknown. Next concrete step outside this build: find out whether their
  dashboard exposes a webhook receiver, a REST API, or nothing, then design
  a per-tenant adapter interface (`push_session(session) -> None` /
  inbound webhook receiver) around whichever shape it turns out to be.
- Multiple fee tiers per tenant (D6).
- Non-technical self-serve onboarding beyond the settings panel itself (i.e.
  this ships the config UI, not a client-facing signup wizard).
- Automatic AI un-mute on consultation completion — manual for v1 (step 6)
  since there's no automated signal from the (not-yet-built) astrologer side
  to trigger it.
