# Subscription → Client Toggle Sync, and Notification Fold-In — Design

## Context

This follows directly from `2026-07-04-itemized-subscription-pricing-design.md`, which shipped the
itemized cart/approval flow (migrations 123–128). That design assumed approval already "seeds the
baseline" of the operator's per-client sidebar toggles (`enabled_features`) and the
`calling_provider` setting — but it does not. This was investigated end-to-end:

- `approve_request()` (`backend/app/services/subscription_requests.py:157-158`) writes
  `tenants.enabled_features = resolve_entitlements(...)["features"]`, but that array is built by
  walking `feature_catalog.depends_on`, and **no** catalog row's `depends_on` has ever listed the
  three bare keys the sidebar actually reads: `inbound_leads`, `outbound_leads`, `telecalling`
  (`frontend/.../client/[id]/sidebar.tsx:31,32,178`). So approving a subscription never turns those
  toggles on.
- A hardcoded bridge for exactly this (`features.extend(["whatsapp","inbound_leads",
  "outbound_leads","analytics"])` etc.) existed in the old plan-assignment `create_client` flow and
  was deleted in commit `e54ee4b` when the itemized model replaced it — never rebuilt.
- `calling_provider` lives entirely outside this array, in `app_settings.telecalling_config`
  (`backend/app/services/assignment.py:429-513`), defaulting to `"telecmi"` and only ever changed
  by an operator manually via the Configuration tab. Nothing connects it to the client's purchased
  `telecalling_sim` vs `telecalling_telecmi` cart item, even though the cart already treats those as
  a mutually-exclusive choice matching this exact setting.
- Symptom: a client ("Zha") approved for `inbound_messaging`, `outbound_messaging`,
  `telecalling_sim`, `bulk_lead_upload`, and 2× `numbers_pool` still shows every sidebar toggle off
  and Calling Provider stuck on TeleCMI.

Separately: `feature_catalog` has a standalone `notifications` item (₹499/mo,
`depends_on: push_notifications, callbacks, dnc, webhook_health, token_expiry_alerts`), rendered as
its own priced "Add-ons" cart section. Per direction, this should not be separately purchasable —
it should come free with inbound or outbound messaging.

## Goals

- Approving (or backfilling) a client's subscription automatically sets exactly the sidebar toggles
  and calling-provider config implied by their currently-active `tenant_subscription_items` — no
  manual step required.
- The toggle vocabulary offered in the client console is never wider than what's purchasable in the
  subscription catalog (aside from quantity add-ons like extra telecaller seats / extra numbers,
  which remain pure quantity, not toggles).
- Any toggle not derived from billing (e.g. `analytics`, if set some other way) survives an
  approval untouched — only the billing-derived keys are forced to mirror the subscription.
- An operator can still manually flip a billing-derived toggle for troubleshooting; it will be
  re-derived back to the billing-correct state on the next approval.
- Notifications become a bundled inclusion of inbound/outbound messaging — no separate line item,
  no separate cost, for new and existing clients alike.
- Existing already-approved tenants (e.g. Zha) get fixed via a one-time backfill, not just new
  approvals going forward.

## Non-goals

- No new UI for removing/downgrading a subscription item — none exists today. The sync mechanism is
  written generically (recomputed from current `tenant_subscription_items` state) so that whenever
  such a flow is added later, it gets correct toggle/provider sync for free by calling the same
  function this design introduces.
- No change to quantity-based add-ons (`telecaller_seats`, `numbers_pool`) — they stay
  quantity-only, no associated toggle.
- No change to the Approval Queue UI, cart UI structure, or pricing editor beyond removing the
  Notifications section/row.

## Design

### 1. Notification fold-in

- Migration: append `push_notifications`, `callbacks`, `dnc`, `webhook_health`,
  `token_expiry_alerts` to **both** `inbound_messaging.depends_on` and
  `outbound_messaging.depends_on` in `feature_catalog`.
- Deactivate (or delete, pending the check below) the standalone `notifications` row.
- Before removing the row: query `tenant_subscription_items` and `subscription_requests` for any
  reference to `feature_key = 'notifications'`. If none exist (expected — Zha's own approved cart
  already excludes it), delete the row outright; otherwise soft-deactivate and handle the
  referencing rows explicitly (re-derive to inbound/outbound, drop the row's price contribution).
- Frontend: remove the Notifications section and its icon/price rendering from `CartBuilder.tsx`.

### 2. Toggle sync (data fix + merge, not full overwrite)

- Migration: add `inbound_leads` to `inbound_messaging.depends_on`; add `outbound_leads` to
  `outbound_messaging.depends_on`; add `telecalling` to both `telecalling_sim.depends_on` and
  `telecalling_telecmi.depends_on`. (The four `telecalling.*` sub-keys and `telecalling.upload` are
  already correctly wired via existing `depends_on` entries — untouched.)
- Code change in `approve_request()`: replace the current full-array overwrite
  (`update({"enabled_features": ent["features"]})`) with a **merge**:
  `new = (old_enabled_features - BILLING_DERIVED_KEYS) | ent["features"]`, where
  `BILLING_DERIVED_KEYS` is the fixed, known union of every key ever produced by any
  `feature_catalog.depends_on` entry (computed once from the catalog, not hand-maintained). This
  makes the billing-derived subset always exactly mirror the subscription (auto ON when purchased,
  auto OFF when not), while any toggle outside that universe (e.g. `analytics`) is left alone.
- Extract this into a small reusable function, e.g.
  `sync_client_toggles(db, tenant_id) -> None` in `backend/app/services/subscription_requests.py`
  (or `entitlements.py`), callable both from `approve_request()` and from the backfill script in
  §4, so there is exactly one implementation of the merge logic.

### 3. Calling-provider bridge

- Inside `sync_client_toggles()`: read the tenant's active `tenant_subscription_items`. If
  `telecalling_sim` is active and `telecalling_telecmi` is not, call `save_telecalling_config(...,
  calling_provider="sim_basic")`. If `telecalling_telecmi` is active and `telecalling_sim` is not,
  set `"telecmi"`. If neither is active, leave `calling_provider` untouched (dormant — the
  `telecalling` toggle is off, so the setting has no visible effect). If both are somehow active at
  once (the cart enforces mutual exclusivity, so this is a defensive-only case), default to
  `"telecmi"` and leave a log line — not expected to occur in practice.

### 4. Backfill for existing tenants

- New one-off script `backend/scripts/backfill_client_toggles.py`: iterates every tenant that has
  at least one row in `tenant_subscription_items`, calls `sync_client_toggles(db, tenant_id)` for
  each.
- Dry-run mode first: print a diff (old vs. new `enabled_features`, old vs. new `calling_provider`)
  per tenant without writing, for manual review on staging.
- Then run for real against staging, spot-check Zha's sidebar and Configuration tab render
  correctly (Inbound Leads / Outbound Leads / Telecalling on, Calling Provider = SIM Basic), then
  run against production.

## Testing

- Backend unit test for `sync_client_toggles()`: given a tenant with `inbound_messaging` +
  `telecalling_sim` active and a pre-existing unrelated `analytics` key in `enabled_features`,
  asserts result contains `inbound_leads`, `telecalling`, `telecalling.dialer/.scheduled/.notes`,
  still contains `analytics`, does not contain `outbound_leads`, and that
  `telecalling_config.calling_provider == "sim_basic"`.
- Unit test asserting `BILLING_DERIVED_KEYS` removal correctly turns a toggle back off when its
  backing item is absent (simulates the "auto OFF" case for a tenant with no telecalling item).
- Manual pass: submit and approve a fresh test subscription request end-to-end in the operator
  console, confirm sidebar toggles and Configuration tab reflect it immediately with no manual
  step.
- Backfill script dry-run reviewed manually on staging before the real run (per §4).

## Rollout

1. Migrations for §1 (notification fold-in) and §2 (depends_on additions).
2. Code changes: merge-based `sync_client_toggles()`, calling-provider bridge, wired into
   `approve_request()`.
3. Frontend: remove Notifications cart section.
4. Backfill script, dry-run on staging, review, then run on staging, then production.
