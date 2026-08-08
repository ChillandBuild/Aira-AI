# WhatsApp Coexistence Onboarding (Approach A — Minimal) — Design

**Date:** 2026-08-08
**Status:** Approved, ready for implementation planning

Let a client keep using the WhatsApp Business app on their phone while Aira
also sends/receives on the same number via Cloud API ("Coexistence"), instead
of the current flow which fully migrates the number away from the app.

## Problem

Today's Embedded Signup (`ConnectChannelsPanel.tsx`, `routes/app_settings.py`)
only supports the standard flow: create/select a WABA, then
`register_phone_number` claims the number for the Cloud API exclusively. A
client who wants to keep using the WhatsApp Business app on the phone has no
path to do that.

Meta's actual coexistence mechanism (confirmed against the live Meta App
Dashboard for this app, `AIRA`, config `Aira - Bloom Matrix` /
`1063294086656120`):

- The popup only offers "connect your existing WhatsApp Business app" when
  `FB.login()` is called with `extras: { featureType:
  'whatsapp_business_app_onboarding', sessionInfoVersion: '3' }`. Verified via
  the Embedded Signup Builder tool's "Feature Type" dropdown, which lists
  exactly `None` / `WhatsApp Business App Onboarding`.
- On completion, the popup's `postMessage` event fires with
  `event: "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"` instead of `"FINISH"`.
  `ConnectChannelsPanel.tsx`'s `handleMessage` listener only matches `"FINISH"`
  today — the coexistence event is silently dropped, so nothing happens.
- The number is already registered on the phone app, so calling
  `register_phone_number` (`app_settings.py:673`) again for this path is
  wrong.
- Webhook fields `history`, `smb_app_state_sync`, `smb_message_echoes` carry
  coexistence-specific data. `history` (past-message backfill) and
  `smb_app_state_sync` (contact backfill) are already subscribed in the Meta
  dashboard but have no handler in `webhook.py` — verified the field dispatch
  is a plain `if/elif` with no `else`, so unrecognized fields are silently
  ignored (no crash, no data loss risk to existing flows). `smb_message_echoes`
  is the field that matters most for correctness: it's how Meta reports a
  message a human sent **from the phone app**. Without handling it, Aira never
  learns a human already replied, so the AI can post a conflicting reply on
  top, and the conversation view has holes.

## Scope

**In scope (Approach A):**
- Pass `featureType`/`sessionInfoVersion` on the coexistence login trigger.
- Handle the `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` event.
- Skip `register_phone_number` for the coexistence path.
- Handle `smb_message_echoes` — record the phone-app-sent message into the
  same place outbound messages already land, and make sure it reads as "a
  human already responded" to whatever logic decides if the AI should reply.

**Out of scope (deferred, Approach B):**
- Backfilling `history` (past messages) and `smb_app_state_sync` (existing
  contacts) on connect. These payloads are already subscribed and will keep
  arriving; they're simply not processed yet, so nothing is lost by deferring
  — a later change can start handling them retroactively is not possible
  (Meta doesn't replay), but the SMB App Data API sync call itself can be
  triggered later once Approach B is designed. Explicitly accepted: the first
  coexistence client's pre-connection chat history and existing app contacts
  will not import into Aira.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Add a second, explicit "Connect existing WhatsApp Business app" entry point in the UI, separate from the current "Connect with Facebook" button | The two flows produce different Meta popup experiences (create-new vs. connect-existing) and need different `extras`. Reusing one button with a hidden mode is harder to reason about than two clearly labeled actions. |
| D2 | Distinguish the two finish events in the shared `message` listener by `data.event`, not by which button was clicked | The Meta popup is the source of truth for which flow actually completed — a user could in principle back out and switch flows inside the popup. |
| D3 | Add `is_coexistence: bool` to `EmbeddedSignupRequest` and thread it through to the backend route | The route needs to know explicitly whether to skip `register_phone_number`, and inferring it from other fields would be fragile. |
| D4 | `smb_message_echoes` messages are stored via the same code path as existing outbound messages, tagged with a distinct sender/source (e.g. `source: "whatsapp_business_app"`) rather than `source: "ai"` or `source: "operator"` | Keeps the conversation timeline complete and lets AI-reply gating logic treat it exactly like any other "human already replied" signal, without inventing a parallel storage path. |
| D5 | No changes to `history` / `smb_app_state_sync` handling in this pass | Both already fail safe (silently ignored, no crash). Handling them means designing how backfilled historical data interacts with lead scoring and segment assignment without misfiring on old messages — real design work, deliberately deferred rather than rushed for one client's onboarding deadline. |

## Data flow (coexistence path)

1. Tenant admin clicks "Connect existing WhatsApp Business app" →
   `FB.login()` with `config_id: META_CONFIG_ID`, `extras: { featureType:
   'whatsapp_business_app_onboarding', sessionInfoVersion: '3' }`.
2. Client scans the QR code in their WhatsApp Business app, confirms.
3. Popup posts `{ type: "WA_EMBEDDED_SIGNUP", event:
   "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING", data: { waba_id,
   phone_number_id, business_id } }`.
4. Frontend calls `POST /api/v1/settings/whatsapp/embedded-signup` with
   `is_coexistence: true` added to the existing payload shape.
5. Backend: exchange code → access token (unchanged). Skip
   `register_phone_number` when `is_coexistence`. Subscribe app to the WABA
   (unchanged — still required so webhooks flow). Fetch phone number info,
   save credentials, mark `whatsapp_status: live` (unchanged).
6. Going forward: customer messages still arrive via the existing `messages`
   field handler (unchanged). Messages the human sends from the phone app
   arrive via `smb_message_echoes` and get a new handler branch in
   `webhook.py`.

## Error handling

- If `is_coexistence` is true and `register_phone_number` is skipped, no new
  failure mode is introduced (the call simply doesn't happen).
- `smb_message_echoes` payloads missing an expected field (no matching
  tenant/phone_number_id) log and drop, mirroring the existing pattern in the
  `messages` branch (`webhook.py:387`).
- No change to signature verification — coexistence payloads go through the
  same `X-Hub-Signature-256` check already in place.

## Testing

- Manual: complete a real coexistence signup with the pilot client's number
  (already meets the 7-day/app-version/QR prerequisites) and confirm
  credentials save without a `register_phone_number` call in the logs.
- Manual: send a message from the phone app during a live conversation and
  confirm it appears in the dashboard conversation view and the AI does not
  post a duplicate/conflicting reply.
- Existing webhook signature and `messages`-field tests must keep passing
  unchanged.
