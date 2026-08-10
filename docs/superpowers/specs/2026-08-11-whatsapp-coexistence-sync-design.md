# WhatsApp Coexistence Sync — Contact & History Backfill (Approach B) — Design

**Date:** 2026-08-11
**Status:** Approved, ready for implementation planning

Builds on [2026-08-08-whatsapp-coexistence-onboarding-design.md](2026-08-08-whatsapp-coexistence-onboarding-design.md)
(Approach A, shipped and confirmed working live with the pilot client). This
covers the two pieces Approach A explicitly deferred: importing the client's
existing phone contacts and their pre-connection chat history after a
coexistence signup completes.

## Problem

Approach A connects a client's WhatsApp Business app number to Aira going
forward, but a client who's been using that number for months arrives with
empty context: none of their existing phone contacts or past conversations
show up in Aira. Meta's Coexistence flow supports pulling both in via the
**SMB App Data API**, but nothing currently triggers or handles it — the
`history` and `smb_app_state_sync` webhook fields are subscribed (Meta
dashboard, confirmed) but Approach A left them unhandled by design (D5 in the
prior spec), deferring exactly this work.

Confirmed against Meta's official docs (`onboarding-business-app-users`):

- **Trigger**: two explicit `POST https://graph.facebook.com/<version>/<phone_number_id>/smb_app_data`
  calls, bodies `{"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync"}`
  and `{"messaging_product": "whatsapp", "sync_type": "history"}`, each bearer-authed
  with the tenant's access token. Nothing happens until we make these calls.
- **`smb_app_state_sync` payload**: one entry per contact —
  `{type: "contact", contact: {full_name, first_name, phone_number}, action: "add"|"remove", metadata: {timestamp}}`.
- **`history` payload**: chunked (`metadata: {phase, chunk_order, progress}`,
  `progress: 100` = last chunk), grouped into `threads` (one per customer
  phone number), each with a `messages` array. Per message: `from`, `to`
  (**present only when the business sent it** — this is our direction
  signal), `id`, `timestamp` (epoch seconds), `type`, type-specific body,
  `history_context.status`. Covers up to 180 days back. Media sent >14 days
  ago arrives as `type: "media_placeholder"`, not the actual media.

## Product decisions (confirmed with the client-facing owner)

1. **Unmatched contacts are never turned into leads.** A phone-book entry
   isn't consent, and `leads.opt_in_source` gates broadcast eligibility
   (Hard Invariant 7) — auto-creating leads here would either need a
   fabricated opt-in reason or pollute the lead list with people who never
   engaged. Contact sync only **enriches** leads that already exist by phone
   match.
2. **Backfilled history is informational only.** It populates the
   conversation view so agents have context, but never runs through
   `scoring_engine`, `maybe_assign_lead`, or `record_stage_event` — a
   6-month-old message shouldn't move a lead's segment or reassign it today.
   Consistent with decision 1: a thread for a phone number with no matching
   lead is skipped entirely, not used to create one.

## Scope

**In scope:**
- New `request_coexistence_sync(phone_number_id, access_token)` in
  `meta_cloud.py`, called (fire-and-forget, logged not raised) right after
  the existing "skip `register_phone_number`" branch in
  `whatsapp_embedded_signup` (`app_settings.py`), only when `is_coexistence`.
- New `elif field == "smb_app_state_sync":` branch in `webhook.py`, before
  the `smb_message_echoes` branch: match contact by phone to an existing
  lead; if matched, `action != "remove"`, and `leads.name` is currently
  blank, set it to `full_name`. No match → skip, nothing written.
- New `elif field == "history":` branch in `webhook.py`: for each thread,
  match `thread.id` (customer phone) to an existing lead; no match → skip
  the whole thread. For matched threads, only `type: "text"` messages are
  inserted into `messages`, with `created_at` set explicitly to the
  message's own historical `timestamp` (verified `messages.created_at` has
  no trigger forcing `now()` — a plain insert can backdate it) and
  `direction` derived from whether `to` is present (`outbound`) or absent
  (`inbound`). Dedup by `meta_message_id`, same pattern as the
  `smb_message_echoes` handler. Non-text types (including
  `media_placeholder`) are logged and skipped.

**Out of scope:**
- Actual media download/import for history media messages.
- Any retry/resume mechanism if a sync request itself fails to reach Meta —
  logged only; a failed trigger call doesn't block or retry automatically
  (client's live messaging is unaffected either way, since this only affects
  backfilled data, not the live connection from Approach A).
- Deleting a lead's name or any other field on `action: "remove"` — removal
  from a phone contact list has no effect on Aira's data at all.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Trigger both sync requests unconditionally right after a coexistence signup, not gated by any UI toggle | Matches Meta's own guidance to request both within 24h of onboarding; there's no meaningful case where a coexistence client wouldn't want their own historical data restored. |
| D2 | Sync trigger failures are logged, not surfaced to the tenant admin as an error | The "connect" flow already succeeded (Approach A) — a failed backfill *request* shouldn't read as a failed connection. Matches `register_phone_number`'s existing "non-fatal by design" convention in `meta_cloud.py`. |
| D3 | Direction for history messages comes from presence/absence of `to`, not phone-number comparison against the tenant's own number | It's what Meta's payload already encodes directly — comparing phone numbers ourselves would just be re-deriving the same fact with an extra failure mode (formatting mismatches). |
| D4 | Only `type: "text"` handled in both history and (already, from Approach A) `smb_message_echoes` | Consistent scope boundary already accepted in Approach A. Media requires a separate authenticated download call per message — real added complexity deferred, not silently dropped: every skip is logged. |
| D5 | No new "backfilled" flag column on `messages` | Nothing downstream needs to distinguish backfilled from live messages once decision 2 above is enforced at write time (backfilled ones simply never reach scoring/assignment code) — a column with no reader is schema for its own sake. |

## Data flow

1. Coexistence signup completes (Approach A, unchanged) →
   `whatsapp_embedded_signup` now also calls `request_coexistence_sync`
   twice (contact sync, then history sync) using the same `access_token`
   already exchanged for this request.
2. Meta responds to each POST with a `request_id` (logged, not otherwise
   used — no polling; we just wait for the webhooks).
3. Over the following minutes to hours, Meta delivers `smb_app_state_sync`
   webhook events (one or more, one contact per `state_sync` entry) and
   chunked `history` webhook events (`progress` climbs to 100 across
   possibly several deliveries).
4. Each webhook delivery is handled statelessly — no need to track "have we
   seen all chunks yet," since every message/contact is matched and
   deduped independently on arrival.

## Error handling

- No tenant match for `phone_number_id` on either field → log and drop,
  matching the existing `messages`/`smb_message_echoes` pattern.
- Malformed/missing `phone_number` or `timestamp` on an individual
  contact/message entry → skip that entry, keep processing the rest of the
  payload (one bad entry in a chunk shouldn't drop the whole chunk).
- No signature-verification changes — both new branches sit inside the
  webhook route's existing `X-Hub-Signature-256` check.

## Testing

- Unit: `request_coexistence_sync` makes exactly two POSTs with the correct
  `sync_type` bodies and bearer header; a non-200/error response is logged,
  not raised.
- Unit: `smb_app_state_sync` handler — matched lead with blank name gets
  updated; matched lead with existing name is untouched; unmatched contact
  writes nothing; `action: "remove"` writes nothing regardless of match.
- Unit: `history` handler — matched thread's text messages land in
  `messages` with correct `direction` (derived from `to` presence) and
  backdated `created_at`; unmatched thread writes nothing; replay of the
  same chunk doesn't duplicate rows (dedup by `meta_message_id`);
  non-text/`media_placeholder` entries are skipped without erroring.
- Existing webhook signature and `messages`/`smb_message_echoes` tests must
  keep passing unchanged.
