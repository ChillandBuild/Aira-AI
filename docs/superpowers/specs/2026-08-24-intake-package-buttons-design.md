# Intake Package Picker — WhatsApp Reply Buttons

Status: approved by user, ready for implementation plan.
Date: 2026-08-24

## 1. Problem

When a lead accepts the intake offer, `route_intake` moves the session to
`awaiting_package_choice` and sends a plain-text price list built by
`package_list_block()` ([intake.py:305](../../../backend/app/services/intake.py#L305)):

```
Here are our consultation options:

• One Question — ₹100
• Detailed Consultation — ₹300

Which one would you like?
```

The lead must then **type** their choice. That typed reply goes to
`match_package()` ([intake.py:339](../../../backend/app/services/intake.py#L339)), which
exact-matches on name or key and otherwise falls through to an LLM call to interpret
"the detailed one", "2", "detiled", or Tanglish phrasing. On no-match it re-asks, and the
lead sees the same list again.

Three costs: leads drop off at a typing step, every non-exact reply burns an LLM call, and
a mis-parsed reply risks charging the wrong amount (guarded today by `match_package`
failing closed, which converts the risk into a re-ask loop).

WhatsApp reply buttons remove the typing step. This spec covers **only** the package
picker. The general client-authored button library is separate work (section 8).

## 2. Why this is cheap

Three of the four pieces already exist and are verified:

| Piece | Where | State |
|---|---|---|
| Sending buttons | `send_interactive_buttons()` [meta_cloud.py:606](../../../backend/app/services/meta_cloud.py#L606) | Written, **zero callers** |
| Receiving a tap | [webhook.py:546-548](../../../backend/app/routes/webhook.py#L546-L548) | Live — maps `button_reply.title` into `body` as if typed |
| Exact-match short-circuit | [intake.py:346-349](../../../backend/app/services/intake.py#L346) | Live — skips the LLM when the reply equals a package name |
| Rendering buttons at the picker | — | **This spec** |

Because the webhook already normalises a tap into text, `route_intake`'s
`awaiting_package_choice` branch needs no change to its *receiving* logic. A tap arrives as
`body = "One Question"`, hits the exact-match short-circuit, and returns the package
without an LLM call.

The channel question is also already settled: `_send_and_log`
([intake.py:421](../../../backend/app/services/intake.py#L421)) hardcodes
`"channel": "whatsapp"`, so the intake flow is WhatsApp-only today. No multi-channel
fallback is needed.

## 3. Data model

`app_settings.value` (JSON blob, `key='intake_config'`) — each package node gains one
optional field:

```json
{
  "key": "basic_detail",
  "name": "Detailed Consultation",
  "button_label": "Detailed",
  "amount_paise": 30000,
  "description": "..."
}
```

`button_label` is optional. It exists because WhatsApp truncates button titles to 20
characters at [meta_cloud.py:625](../../../backend/app/services/meta_cloud.py#L625) with no
error — "Detailed Consultation" is 21 characters and would reach the lead as "Detailed
Consultatio".

Resolution order for a button's title:
1. `button_label` if set
2. `name` if ≤ 20 characters
3. otherwise the package is **not** eligible for buttons (see section 4)

No migration. This rides in the existing JSON config.

**Interaction with the nested-packages spec:** [2026-08-23-nested-packages-and-settings-nav-design.md](2026-08-23-nested-packages-and-settings-nav-design.md)
is restructuring these same nodes to be recursive. `button_label` should be added to the
node shape there rather than bolted on separately; whichever spec is implemented second
inherits the other's field.

## 4. Eligibility rule

At the moment of asking, buttons are used only when **all** of these hold:

- 2 ≤ package count ≤ 3 (WhatsApp allows at most 3 reply buttons)
- every package resolves to a title ≤ 20 characters per section 3
- the composed body text is ≤ 1024 characters (WhatsApp interactive body limit)

Otherwise the existing plain-text path runs unchanged. A single package already bypasses
the picker entirely ([intake.py:547-548](../../../backend/app/services/intake.py#L547)).

Four or more packages fall back to text in this version. WhatsApp's scrollable list format
holds 10 rows and `send_list_message()` already exists
([meta_cloud.py:659](../../../backend/app/services/meta_cloud.py#L659)), but list rows carry
their own 24-character title limit and a separate section structure — enough extra surface
that it belongs in a follow-up once buttons are proven in production.

## 5. What the lead receives

The body text is **unchanged** — the same `compose_wrapped("packages", block=package_list_block(packages))`
output that ships today. Prices stay in the body, rendered in Python, for exactly the
reason the existing code comments give:

> *"Rendered in Python, never by the LLM: these are prices the customer will be held to,
> and a hallucinated figure is a real liability."*

Buttons carry names only. Prices are never put on a button, where the 20-character limit
would truncate them.

```
Here are our consultation options:

• One Question — ₹100
• Detailed Consultation — ₹300

Which one would you like?
[ One Question ]  [ Detailed ]
```

## 6. Changes

### 6.1 `backend/app/services/meta_cloud.py`

`send_interactive_buttons` currently truncates titles silently at
[:625](../../../backend/app/services/meta_cloud.py#L625). Change it to **raise** on a title
over 20 characters rather than truncate. Silent truncation is the failure mode this whole
design works around; it should not be reachable. Callers are responsible for supplying
valid titles, and section 4's eligibility check guarantees that for this path.

This is safe: the function has zero existing callers.

### 6.2 `backend/app/services/intake.py`

**`_send_buttons_and_log(phone, text, buttons, tenant_id, lead_id, db)`** — new, mirroring
`_send_and_log` ([:421](../../../backend/app/services/intake.py#L421)) including its
"logging must never raise" guarantee, which exists because a raise there makes
`route_intake`'s caller treat the turn as unconsumed and send a second reply on top of one
the customer already received.

Logged `messages.content` is the body text, then a blank line, then the offered labels
joined as `[One Question] [Detailed]`, so that conversation history read back by the AI and
shown in the operator inbox reflects what the lead actually saw. `reply_source` stays
`"expert_handoff"`.

On any send failure it falls back to `_send_and_log` with the same body text. A button
failure must never cost the turn.

**`package_buttons(packages) -> list[dict] | None`** — new. Applies section 4's eligibility
rule; returns `[{"id": key, "title": label}, ...]` or `None`.

**`awaiting_package_choice` send site** ([:566-577](../../../backend/app/services/intake.py#L566)) —
compose the body exactly as today, then route through `_send_buttons_and_log` when
`package_buttons()` returns buttons, else `_send_and_log`.

**Re-ask site** ([:585-593](../../../backend/app/services/intake.py#L585)) — same treatment.
A lead who failed to match once is precisely the lead who benefits most from tapping.

**`match_package`** ([:339](../../../backend/app/services/intake.py#L339)) — extend the
exact-match short-circuit at [:346-349](../../../backend/app/services/intake.py#L346) to also
compare against `button_label`. Without this, a tenant who sets `button_label: "Detailed"`
gets a tapped reply of "Detailed" that no longer equals `name`, silently falling through to
the LLM and losing the determinism this feature exists to provide.

### 6.3 Frontend — `IntakeConfigPanel.tsx`

Per-package optional **Button label** input, with a live character counter that hard-blocks
at 20. Shown with a hint when `name` exceeds 20 characters, since that is when it becomes
required for buttons to appear at all.

Surface the eligibility rule honestly: when a tenant has 4+ packages, or a package has no
valid title, show a short inline note that the picker will send as a text list. Silent
non-appearance is the worst outcome for a client trying to understand why buttons did not
show up.

## 7. Testing

Unit tests under `backend/tests/`:

- `package_buttons` returns `None` for 1, 4, and 5 packages; returns buttons for 2 and 3
- `package_buttons` returns `None` when any title exceeds 20 characters and no
  `button_label` is set
- `button_label` takes precedence over `name`
- `match_package` exact-matches `button_label` without invoking the LLM
- `send_interactive_buttons` raises on a 21-character title
- `_send_buttons_and_log` falls back to text send when the button send raises
- `_send_buttons_and_log` does not raise when the `messages` insert fails

Manual verification on a live number before merge: accept an offer with 2 packages,
confirm buttons render, tap one, confirm the session advances to `collecting` and that no
`intake_package_match` LLM call was logged for that turn.

## 8. Out of scope

- **The general client-authored button library** (a `quick_reply_blocks` table plus an AI
  tool that selects a saved block by a "use when" description). Designed and agreed in
  conversation on 2026-08-24; deferred until the package picker proves buttons in
  production. It is separate work with its own table, route, and UI.
- **List format for 4+ packages** — section 4.
- **Buttons on any other intake step** (field collection, summary confirmation, payment).
  Confirmation in particular looks like an easy yes/no button pair, but `_is_affirmative`
  handles free text across languages today and changing it is not needed here.
- **Chaining buttons to reveal more buttons.** Nested packages ask one level at a time
  through the existing session state machine; that is a sequence of questions, not a flow
  engine. Any design where a button's tap is configured to open another button set is the
  Bot Flow Builder removed on 2026-06-01 ([decisions/log.md:16](../../../.agents/decisions/log.md#L16))
  and is explicitly rejected.

## 9. Known risk — build order

`button_label` is a new optional field on the same `intake_config` JSON blob that the
nested-packages spec restructures into recursive nodes. Built independently, one overwrites
the other's node shape.

**Ordering decided by the user on 2026-08-24: this spec ships first, nested packages
second.**

Consequence to carry into the nested-packages implementation: its recursive node shape must
preserve `button_label` on every node it defines, and `package_buttons()` must then be
revisited so it reads whichever level of the tree is currently being asked. Neither is
work for this spec, but the nested-packages plan cannot be written as if `button_label`
does not exist.
