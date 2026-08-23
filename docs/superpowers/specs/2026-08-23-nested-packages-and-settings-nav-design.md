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

## 5. Frontend — package editor (new page, see section 7 for routing)

Recursive `PackageEditor` component: expand/collapse per node, "Add sub-package" (→
`options[]`), "Add addon" (→ `addons[]`, leaf rows only), active-toggle checkbox, indent per
depth. Key uniqueness enforced tree-wide on save (dedupe suffix on collision) — today's
`commitPackageName` (`IntakeConfigPanel.tsx:128-130`) only slugifies within a flat list.

## 6. Testing

- Unit: `normalize_packages()` backward-compat (flat array = all leaves, no `options` key).
- Unit: auto-descend at multiple depths; 0-active-option edge case doesn't crash.
- Unit: `match_package()` scoped to current level only, not whole tree.
- Integration: multi-turn conversation sim — drill 2 levels → addon pick → verify all
  snapshot columns land correctly.
- Regression: existing single-level-package tenants unaffected (no `options` present).

## 7. Settings navigation restructure

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

- Each new route's page component renders the existing panel component unchanged — no panel
  logic rewritten, just relocated out of the tabbed monolith.
- `/dashboard/settings` becomes a redirect to `/dashboard/settings/general`. `MoreMenu`/
  `ProfileMenu` links need no change (still point at `/dashboard/settings`).
- Old `?tab=` bookmarks/links break silently — acceptable, this is operator-only tooling (no
  external client ever reaches these settings).

### Example

Sidebar gets a new "Settings" row. Click it → expands in place (same mechanic as
Telecalling today) → shows the list above → click "Intake Config" → click into "Packages"
→ lands on the tree editor from section 5. Main sidebar (Conversations, Leads, etc.) stays
visible throughout.

## 8. Known risk, explicitly out of scope

The astrologer bridge currently receives only the rupee amount, not which package tier was
purchased (`.agents/context/subsystem-notes.md:416`). Nesting deepens this gap — sub-option
choice becomes invisible to the astrologer too. `package_path` (section 3) is captured so
this is fixable later without another migration, but closing the gap itself is not part of
this work.
