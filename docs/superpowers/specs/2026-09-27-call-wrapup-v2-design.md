# Call Wrap-up v2 — Design

**Date:** 2026-09-27
**Applies to:** SIM (`sim_basic`) and cloud (`telecmi`) calls — one wrap-up for both.
**Replaces:** the two separate outcome lists (SIM `ManualStatus`, cloud `TELECMI_OUTCOMES`), the star rating, tags and "Log the sale" in the wrap-up, and the "Call Outcome" card on the lead page.

## 1. Decisions made with the user

| # | Decision |
|---|---|
| D1 | Two-tap wrap-up, identical for SIM and cloud (the user's final option list, below). |
| D2 | Star rating and tags are removed from the wrap-up; "Converted" replaces "Log the sale" by creating the deal itself. |
| D3 | The "Call Outcome" card on the lead page (Overview tab) is replaced by a **Send details on WhatsApp** card. The wrap-up form itself has **no** WhatsApp button — only the notes box. |
| D4 | Send details: from the business WhatsApp number. Customer messaged within 24 h → free message pre-filled from the Services page, editable. Otherwise → pick an approved template, blanks pre-filled and editable. Nothing is ever sent automatically; the telecaller taps Send. Message lands in Conversations. |
| D5 | Retry suggestions: Not picked → +2 h; Busy → +30 min; Switched off / not reachable → tomorrow 10:00 (tenant local = IST). After 3 consecutive failed attempts on the lead → tomorrow 10:00. Telecaller can change the time; saving creates the reminder in Scheduled Calls. |
| D6 | Lead effects per option — the approved table in §4. |
| D7 | Next-step / follow-up / callback times are chosen by the telecaller with quick buttons: In 1 hour · This evening 6 PM · Tomorrow 10 AM · Pick a date & time. |
| D8 | Notes are required for "Interested, next step booked", "Interested, needs time" and "Converted". |
| D9 | "Language barrier" requires a preferred language from: Tamil, English, Hindi, Telugu, Malayalam, Kannada, Other. |
| D10 | Cloud calls: the AI (from the call scoring) checks Hot/Warm/Cold against the recording and may correct it; the admin sees the correction. SIM keeps the telecaller's choice. |

WhatsApp templates the user is submitting for approval: `call_details_share` (vars: 1 customer name, 2 business name, 3 details) and `call_details_next_step` (vars: 1 customer name, 2 details, 3 next step), English + Tamil, category Marketing.

## 2. Verified facts

- Only 2 call_logs rows have a real business outcome today (1 `interested`, 1 SIM `connected`); ~880 have none or `no_answer`. Migration of old values is trivial.
- TeleCMI CDRs report only `answered` / `missed` — busy vs switched-off can't be told apart, so a missed cloud call pre-fills **Not picked**, editable.
- Deals API (`routes/deals.py` `NewDealIn`) needs ≥1 line item (`catalog_item_id` or free `name`, `qty`, `unit_price_paise`), `source` ∈ call|walk_in|manual, `stage` ∈ won|awaiting_payment|quoted.
- Every telecalling tenant has WhatsApp enabled; 2 of 5 currently have approved templates.
- Today the outcome drives `leads.call_status`, `converted_at`, DNC/opt-out flags, follow-up job sync/cancel, stage events, analytics outcome breakdown, and scoring check 10.

## 3. The wrap-up form

**Tap 1 — Did the call connect?** `connected | not_picked | busy | switched_off`
- SIM: telecaller taps. Cloud: pre-filled from the CDR (answered → connected, otherwise not_picked), editable.
- For not_picked/busy/switched_off: show the suggested retry time (D5) with the quick-time buttons; Save creates the reminder.

**Tap 2 — What happened?** (only when Connected)

| value | Label | Required |
|---|---|---|
| `interested_booked` | 👍 Interested, next step booked | next-step date+time, notes |
| `interested_needs_time` | 🤔 Interested, needs time or more information | follow-up date, notes |
| `maybe_later` | 🙂 Maybe later | follow-up date (optional) |
| `call_later` | 📅 Call later (customer asked) | callback date+time |
| `converted` | 🎉 Converted | ≥1 product from catalog OR an amount, notes |
| `not_interested` | 👎 Not interested | reason ∈ price, already_bought, no_need, other |
| `disqualified` | 🚫 Disqualified | reason ∈ never_enquired, not_a_fit, not_decision_maker |
| `wrong_number` | ❓ Wrong number | — |
| `language_barrier` | 🗣️ Language barrier | preferred language (D9) |
| `do_not_call` | ⛔ Do not call | optional checkbox "Also stop WhatsApp/SMS" |

**Always on the form:** notes box. Nothing else (D2, D3).

The mandatory-wrap-up / pending-wrap-ups behaviour (blocking list, SIM lazy call-log creation, keepalive) is unchanged.

## 4. What each option does to the lead (D6)

| Option | `leads.call_status` | Reminder | Other |
|---|---|---|---|
| not_picked / busy / switched_off | `trying` → `unreachable` once no-connect count ≥ `max_call_attempts` (existing rule) | retry per D5 | — |
| interested_booked | `hot` | at next-step time | — |
| interested_needs_time | `warm` | at follow-up date | — |
| maybe_later | `cold` | at follow-up date if given | — |
| call_later | `callback` | at callback time | — |
| converted | `converted` | cancel others | `converted_at`; create a `won` deal, source `call` |
| not_interested | `not_interested` | cancel others | reason saved |
| disqualified | `disqualified` | cancel others | reason saved |
| wrong_number | `wrong_number` | cancel others | `do_not_call = true` |
| language_barrier | `language_barrier` | cancel others | `language_barrier` alert in Needs attention: "Reassign to a {language} speaker" |
| do_not_call | `dnc` | cancel all | `do_not_call = true`; if ticked also `opted_out = true` |

A lead's A/B/C/D segment is not changed by the wrap-up (AI lead scoring owns it). Stage events keep being recorded.

## 5. Send details on WhatsApp (lead page)

Replaces the "Call Outcome" card on the lead page Overview tab.
- Shows whether a free message is possible (customer's last inbound < 24 h) or a template is needed.
- Free message: textarea pre-filled from the Services page (business packages/prices), editable.
- Template: dropdown of the tenant's approved templates; variables pre-filled — customer name, business name, details (Services-page text), next step (from the lead's latest scheduled next step, formatted "Demo on Friday at 11 AM"); all editable; unknown variables are empty and must be filled.
- Send uses the existing WhatsApp send path so the message appears in Conversations. No automatic sending anywhere.
- Hidden when the tenant has no WhatsApp or the lead opted out.

## 6. Scoring and reports

- **Check 10 (CRM update)** and the early-exit CRM check use the new values; the status guide in the check-10 prompt maps directly (hot/warm/cold/disqualified/call_later/wrong_number/language_barrier/do_not_call). `crm_matches_expected`: wrong_number ↔ `wrong_number`; not_enquired ↔ `disqualified` (reason never_enquired) or `not_interested`; callback ↔ `call_later` with a time; language_barrier ↔ `language_barrier`; voicemail → no matching status (note only).
- **Cloud Hot/Warm/Cold check (D10):** the check-10 marking also returns the AI's reading of the customer (hot/warm/cold/none). If the telecaller chose hot/warm/cold and the AI's majority differs, `leads.call_status` is updated to the AI's value, the original is kept in the evaluation, and an admin-visible note is recorded on the call card ("AI changed Warm → Hot"). SIM unchanged.
- **Analytics / outcome charts / Recent calls / lead history / operator console** show the new labels. Connect rate = connected ÷ all wrap-ups.

## 7. Data

- `call_logs`: `manual_status` holds tap 1 (connected/not_picked/busy/switched_off) for both providers; `outcome` holds tap 2 (the 10 values). New columns: `outcome_reason text`, `preferred_language text`, `next_action_at timestamptz` (next-step/follow-up/callback/retry time; replaces `wrapup_callback_at`), `ai_call_status text` (D10).
- Check constraints on `outcome`, `manual_status`, `leads.call_status` updated to the new sets.
- Migration maps the 2 old rows: `interested` → `interested_needs_time`; SIM `connected` stays.

## 8. Out of scope

Telecaller language skills / auto-reassignment (only the admin alert), bulk WhatsApp, editing templates from Aira, SIM auto-fill of tap 1 from the Aira Sync app.

## 9. Testing

Backend unit tests per option (lead updates, reminders, deal creation, DNC/opt-out, alerts), retry suggestion rules incl. 3-failure rule, check-10 mapping, D10 correction; frontend typecheck + lint; screenshots of the wrap-up (SIM + cloud pre-fill), each tap-2 variant's required fields, and the lead-page WhatsApp card (free-message and template modes).
