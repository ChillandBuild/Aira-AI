# Nested Packages + Settings Navigation Restructure

Status: approved by user, ready for implementation plan.
Date: 2026-08-23

## 1. Problem

`IntakeConfigPanel.tsx` renders a flat list of packages (`{key, name, amount_paise,
description}`) that a lead picks from right after accepting an offer. The client needs
packages that contain sub-options ("package inside package"), potentially nested to
unlimited depth, plus optional addons on top of a chosen package, plus the ability to
temporarily hide a package without deleting it.

Separately, the whole Settings screen is one page (`frontend/app/dashboard/settings/page.tsx`)
with 5 tabs behind a `?tab=` query param, stacking 10 unrelated config panels — the
"automations" tab alone stacks 5. Adding a package tree editor into that mix makes it
worse. Settings also isn't reachable from the main sidebar today (buried in `MoreMenu`/
`ProfileMenu`).

## 2. Data model

`app_settings.value` (JSON blob, `key='intake_config'`) — `packages` array entries become
recursive nodes:

```json
{
  "key": "basic",
  "name": "Basic",
  "amount_paise": 10000,
  "description": "...",
  "active": true,
  "options": [
    { "key": "basic_q", "name": "One Question", "amount_paise": 10000, "description": "...", "active": true },
    { "key": "basic_detail", "name": "Detailed Consultation", "amount_paise": 30000, "description": "...", "active": true,
      "addons": [
        { "key": "pdf_summary", "name": "Written PDF summary", "amount_paise": 20000, "description": "...", "active": true }
      ]
    }
  ]
}
```

- Leaf = no `options` key. Existing flat packages are already valid leaves —
  `normalize_packages()` (`backend/app/services/intake.py:280-295`) needs no data migration,
  only logic changes (section 4).
- `addons` is optional, leaf-only.
- `active: bool` (default `true`) on any node at any depth. Inactive node (and its whole
  subtree) is filtered out of both the bot's package list and `match_package()` candidates.
- **Non-leaf `amount_paise` is display-only and unused for charging** — a parent's true price
  depends on which leaf gets picked. `package_list_block()` (section 4) shows a price only for
  leaf entries in the list it's given; non-leaf entries show name + description, no price.
  Validation (`backend/app/routes/app_settings.py:1643-1650`) requires `amount_paise >= 1` only
  on leaves — non-leaf nodes default `amount_paise` to `0` and skip that check.

## 3. Session snapshot (`intake_sessions` table)

New migration, additive columns:

| column | type | purpose |
|---|---|---|
| `package_path` | `jsonb` | breadcrumb `[{key,name}, ...]` root→leaf. Reporting + future astrologer-bridge tier visibility (not built here, see section 8). |
| `selected_addons` | `jsonb` | chosen addon list `[{key,name,amount_paise}, ...]`. |
| `total_amount_paise` | `int` | `package_amount_paise` + sum(addons) — what Razorpay/receipt actually charge. |
| `package_draft_path` | `jsonb` | scratch: keys navigated so far, mid-conversation, before a leaf is reached. Cleared on finalize. |
| `addon_draft_selection` | `jsonb` | scratch: addon keys tentatively picked before confirmation. Cleared on finalize. |

Existing `package_key`, `package_name`, `package_amount_paise` (migration
`176_intake_rename_and_packages.sql:9-13`) keep their current meaning: the final leaf,
snapshotted at choice time so editing packages later never rewrites what a past lead was
actually charged. Unchanged consumers (Razorpay link, receipts, astrologer bridge amount)
keep working without modification.

## 4. Bot flow (`route_intake()`, `backend/app/services/intake.py`)

- **Auto-descend, now recursive at every depth** (today only applies at root): while the
  current level has exactly 1 active option, auto-pick it and descend, appending to
  `package_draft_path`. 0 active options at a level: log error, fail safe (don't crash —
  fall back to legacy single-fee flow or flag for support).
- **`awaiting_package_choice`**: `match_package()` scoped to the *current level's* active
  siblings only, not the whole tree (today it's implicitly root-only since there's only one
  level). On match: append to `package_draft_path`; if the matched node has `options`,
  recurse (auto-descend check, then re-ask if >1 active child); if leaf, finalize
  `package_key`/`package_name`/`package_amount_paise`.
- Leaf has active addons → new status `awaiting_addon_choice`. Send addon menu (LLM
  classifier variant of `match_package`, purpose tag `intake_addon_match`, multi-select
  aware — accepts 0+ picks, "skip"/"none" allowed). On confirm: sum into
  `total_amount_paise`, clear `addon_draft_selection`, proceed to field collection
  (unchanged next step).
- Leaf has no addons → finalize immediately as today, `total_amount_paise =
  package_amount_paise`.

### Example conversation

```
Bot: 1. Basic  2. Premium (₹500)
Lead: Basic
Bot: 1. One Question (₹100)  2. Detailed Consultation (₹300)
Lead: Detailed
Bot: Want a written PDF summary too? +₹200 — yes/no?
Lead: yes
→ package_key=basic_detail, package_amount_paise=30000,
  package_path=[{Basic},{Detailed Consultation}],
  selected_addons=[{PDF summary,20000}], total_amount_paise=50000
→ proceeds to field collection, same as today
```

## 5. Tap UI — buttons and list messages (revives, adapts `2026-08-24-intake-package-buttons-design.md`)

That spec was implemented, merged, then reverted the same day (2026-08-24) because reply
buttons were judged to belong in the general, standalone Quick Reply Blocks system instead of
welded to intake specifically. Revisited and reversed after tracing the actual runtime
wiring: `route_intake` and the AI tool-call path (`generate_reply`) are mutually exclusive per
turn (`webhook.py:338-348` — a message `route_intake` consumes never reaches `generate_reply`),
so a package menu can never be sent via the AI's tool-call decision no matter how the button
data is stored. The deterministic mechanism is revived, adapted to fire at any depth in the
now-recursive tree, and extended to a second WhatsApp UI type this session identified as
already built but never wired up.

**Two WhatsApp-native tap UIs already exist in this codebase, both currently uncalled by
anything:**

| Type | Function | Real WhatsApp limits (verified against Meta's Cloud API docs, 2026-08-24) |
|---|---|---|
| Reply buttons | `send_interactive_buttons` (`meta_cloud.py:612`) | 2-3 buttons, title ≤ 20 chars (`BUTTON_COUNT_MAX`/`BUTTON_TITLE_MAX`, `meta_cloud.py:83-84`) |
| List message | `send_list_message` (`meta_cloud.py:678`) | ≤ 10 rows total, row title ≤ 24 chars, row description ≤ 72 chars, section title ≤ 24 chars, open-button label ≤ 20 chars |

Both already receive correctly: `webhook.py:548` normalizes a tapped button *or* a tapped list
row into plain text (`button_reply`/`list_reply`, same `.title` field) before it ever reaches
`route_intake` — so `match_package`/`match_addons` need no changes at all. A tap looks
identical to a typed exact-match reply.

**Three-tier eligibility, decided in pure Python — no LLM, same rule as prices never being
LLM-authored:**

1. 1 active option at a level → auto-select, no message (existing `_resolve_choice` behavior,
   unchanged).
2. 2-3 active options, every one's short label ≤ 20 chars → reply buttons.
3. 4-10 active options, every one's short label ≤ 24 chars → list message.
4. Anything else (11+ options, or a label too long even for the list tier) → today's plain-text
   `package_list_block`/`addon_list_block` path, unchanged.

**Data model addition** — one new optional field per package/addon node, reused for both
tiers (list rows tolerate more characters than buttons, so a label valid for buttons is always
valid for a list row too):

```json
{ "key": "basic_detail", "name": "Detailed Consultation", "button_label": "Detailed", "amount_paise": 30000, ... }
```

Resolution order for a node's short label: `button_label` if set, else `name` if it fits the
tier's limit, else that node makes the whole level ineligible for that tier (drops to the next
one down).

**`send_list_message` gets the same fail-loud treatment `send_interactive_buttons` already
has** (`meta_cloud.py:624-631`, the fix kept from the reverted spec) — today it silently
truncates `button_text`/`header_text`/`footer_text` and validates nothing about `sections`.
Zero callers exist yet, so tightening this to raise on an over-limit row/section title, an
over-limit row description, or more than 10 total rows is a safe, behavior-invisible change
until this plan adds the first caller.

Prices and button/row titles are never composed by the LLM — the composer (`compose_wrapped`)
still only writes the surrounding intro/outro sentence, exactly as it does for the text-list
path today; the classifier (`match_package`/`match_addons`) is unchanged because a tap already
arrives as normalized text.

## 6. Frontend — package editor (new page, see section 8 for routing)

Recursive `PackageEditor` component: expand/collapse per node, "Add sub-package" (→
`options[]`), "Add addon" (→ `addons[]`, leaf rows only), active-toggle checkbox, indent per
depth. Key uniqueness enforced tree-wide on save (dedupe suffix on collision) — today's
`commitPackageName` (`IntakeConfigPanel.tsx:128-130`) only slugifies within a flat list.

## 7. Testing

- Unit: `normalize_packages()` backward-compat (flat array = all leaves, no `options` key).
- Unit: auto-descend at multiple depths; 0-active-option edge case doesn't crash.
- Unit: `match_package()` scoped to current level only, not whole tree.
- Unit: tap-UI eligibility function — 1/2/3/4/10/11-option boundaries, and a label too long for
  buttons but fine for a list row (verifies tier fallback, not just a pass/fail split).
- Unit: `send_list_message` raises (not truncates) on an over-limit row title, row description,
  section title, or more than 10 total rows.
- Integration: multi-turn conversation sim — drill 2 levels → addon pick → verify all
  snapshot columns land correctly.
- Regression: existing single-level-package tenants unaffected (no `options` present).

## 8. Settings navigation restructure

Current state (verified):
- Main sidebar (`frontend/components/sidebar.tsx:46`) is flat — no "Settings" entry. Only
  existing nested-group pattern is Telecalling (`sidebar.tsx:417-477`,
  `toggleGroup`/`expandedGroups` state at `:72-78`) which expands in place within the same
  sidebar (not a full swap).
- Settings reached only via `MoreMenu.tsx:52` / `ProfileMenu.tsx:80` → `/dashboard/settings`.
- `frontend/app/dashboard/settings/page.tsx` (`SettingsPage()`, line 210) is one route, 5
  tabs via `?tab=`, rendered in both a mobile pill switcher (`:455-517`) and desktop nav in
  `AppHeader.tsx:332-360`.

New structure — reuse the Telecalling expand-in-place pattern for a new "Settings" sidebar
entry (not a Vercel-style full sidebar replace, to keep main nav reachable while configuring
settings):

```
/dashboard/settings/general              (admin identity + ChangePasswordCard)
/dashboard/settings/connect-channels     (already exists as its own folder — reuse, just link it)
/dashboard/settings/telecalling          (TeleCMI credentials + webhook guide)
/dashboard/settings/auto-reply           (AI Auto-Reply toggle)
/dashboard/settings/follow-ups           (Silence-Nudge config)
/dashboard/settings/inbox                (InboxConfigPanel)
/dashboard/settings/telecalling-behavior (TelecallingConfigPanel — confirmed distinct from
                                           the telecalling credentials page above, 2026-08-24)
/dashboard/settings/intake-config        (IntakeConfigPanel: fields, offer message, trigger)
  /dashboard/settings/intake-config/packages   (new recursive package tree editor, section 5)
/dashboard/settings/business-hours       (BusinessHoursPanel)
/dashboard/settings/notifications        (NotificationConfigPanel)
```

- 6 of the 10 panels are already self-contained components (`ConnectChannelsPanel`,
  `InboxConfigPanel`, `TelecallingConfigPanel`, `IntakeConfigPanel`, `BusinessHoursPanel`,
  `NotificationConfigPanel`) — their new route page renders them unchanged, no logic
  rewritten.
- The other 4 (admin identity card, TeleCMI credentials, AI Auto-Reply toggle, Silence-Nudge
  config) are raw JSX currently living inline in `page.tsx:540-841`, sharing one page-level
  state blob (`drafts`, `saveStates`, `handleSave`, `settingFor`, a single `GET/PATCH
  /api/v1/settings/` fetch). Splitting them into routes requires lifting that shared state out
  first:
  - New `frontend/app/dashboard/settings/SettingsFormContext.tsx` — `SettingsFormProvider`
    (the exact state/effects from `page.tsx:225-337` and `handleSave` from `:404-437`, moved
    verbatim) + `useSettingsForm()` hook exposing `{ loading, error, canViewSettings,
    canManageSettings, settings, drafts, setDrafts, saveStates, settingFor, handleSave, email,
    fullName, initials, memberSince, tenantId, hasNotifications, hasTelecmiConfig }`. Provider
    renders the `roleLoading` spinner / `!canViewSettings` fallback (`page.tsx:439-453`)
    itself, so every route under it gets that guard for free.
  - New `frontend/app/dashboard/settings/layout.tsx` wraps all child routes in
    `SettingsFormProvider` — one fetch, shared by every settings page, same network behavior
    as today.
  - Each of the 4 raw-JSX sections becomes its own page consuming `useSettingsForm()`; each
    page-specific constant (`SECTIONS`/`AI_AUTO_REPLY_TOGGLE`/`SILENCE_NUDGE_KEYS`/
    `parseSilenceDelays`/`OutlinedField`/`SecretField`) moves from `page.tsx` into the one page
    that uses it — no shared-component file needed for single-consumer pieces (YAGNI).
- `frontend/app/dashboard/settings/page.tsx` shrinks to a redirect to
  `/dashboard/settings/general`. `MoreMenu`/`ProfileMenu` links need no change (still point at
  `/dashboard/settings`).
- The mobile pill-switcher (`page.tsx:461-524`) and desktop tab-nav (`AppHeader.tsx:332-360`)
  are deleted — dead once the sidebar Settings group replaces them.
- Old `?tab=` bookmarks/links break silently — acceptable, this is operator-only tooling (no
  external client ever reaches these settings).

### Example

Sidebar gets a new "Settings" row. Click it → expands in place (same mechanic as
Telecalling today) → shows the list above → click "Intake Config" → click into "Packages"
→ lands on the tree editor from section 5. Main sidebar (Conversations, Leads, etc.) stays
visible throughout.

## 9. Known risk, explicitly out of scope

The astrologer bridge currently receives only the rupee amount, not which package tier was
purchased (`.agents/context/subsystem-notes.md:416`). Nesting deepens this gap — sub-option
choice becomes invisible to the astrologer too. `package_path` (section 3) is captured so
this is fixable later without another migration, but closing the gap itself is not part of
this work.
