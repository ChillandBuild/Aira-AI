# Admin-Customizable Subscription Plans — Design

Date: 2026-07-02
Status: Approved, pending implementation plan

## Problem

The operator console's monetization layer (migrations 123–126) hardcodes six
subscription plans (3 messaging tiers + 3 telecalling tiers) plus a separately
hardcoded `ai_tier` enum. A tenant can simultaneously hold a messaging plan, a
telecalling plan, and an AI tier — three independent knobs — plus operators can
further toggle individual `feature_catalog` rows on/off per tenant outside of
any plan, bumping MRR ad hoc via a quote-confirm dialog.

This is rigid: adding or changing a plan requires a migration. The system
admin wants full control to create, edit, and price plans from the console
itself, with each plan defining exactly which features and quota amounts a
tenant on that plan gets. Billing and usage for a tenant should be driven
entirely by whichever single plan is assigned.

Separately, the Fleet page (fleet health/MRR table) and "View as tenant"
impersonation feature are being removed, freeing up a sidebar slot.

## Goals

- System admin creates/edits/deletes subscription plans from the operator
  console — no plan is hardcoded or seeded as "the" default set going forward.
- A plan bundles: name, monthly price, a feature checklist (from the existing
  `feature_catalog`), and quota numbers for every metered usage type
  (messages, AI replies, call minutes, team seats, storage, AI call summaries,
  AI call scoring).
- Each tenant is assigned exactly one plan (or none). That plan alone
  determines `enabled_features`, quotas, and `mrr`.
- The plan-builder page lives in the sidebar slot currently occupied by
  Fleet, renamed "Subscription."
- The per-tenant Feature Store becomes a plan picker (view assigned plan,
  switch plans) — no more a-la-carte feature toggling with ad hoc pricing.
- Tenant creation shows a plan-selection step only if at least one active
  plan exists, and selection is optional (tenant can be created with no
  plan, same as pre-monetization tenants today).
- Fleet page and View-as-tenant impersonation are deleted entirely.
- No entitlement regressions for tenants currently on the 6 hardcoded plans.

## Non-goals

- Quota enforcement stays track-only (no hard-blocking of sends/calls at
  quota limit) — unchanged from the existing explicit decision.
- The Alerts bell (`GET /operator/alerts`) is not being removed; it shares a
  query-building helper with the old Fleet page and keeps working, internally
  renamed away from "fleet" framing.
- No changes to how AI replies are actually generated/routed — `ai_tier` was
  already billing-only (grep confirms it's not read anywhere in the AI
  generation path), so folding it into plan quotas has no runtime-behavior
  impact.

## Data model

### `plans` (altered)

Drop `pillar`, `tier`, `ai_tier`. Resulting shape:

```
id            uuid primary key
name          text not null
monthly_price numeric not null default 0   -- admin-typed, not auto-summed
feature_keys  jsonb not null default '[]'   -- array of feature_catalog.feature_key
quotas        jsonb not null default '{}'   -- {message_sent, ai_reply, call_minute,
                                             --  team_seat_active, storage_gb,
                                             --  ai_call_summary, ai_call_scoring} -> int
active        boolean not null default true -- soft-delete flag
created_at    timestamptz default now()
```

Quota semantics unchanged from today's `UsageMeterRow` convention: a metric
missing or `<= 0` displays/behaves as unlimited for that plan.

### `tenant_subscriptions` (altered)

Drop `messaging_plan_id`, `telecalling_plan_id`, `ai_tier`, `custom_overrides`.
Add:

```
plan_id  uuid references plans(id) on delete set null   -- nullable, optional
```

`mrr` is retained but becomes a point-in-time snapshot of `plan.monthly_price`
taken when the plan is assigned — it does not silently change if the plan is
edited later (an admin who changes a plan's price must explicitly re-apply it
per tenant, or a future "propagate price change" action can be added later —
out of scope here).

### `resolve_entitlements()` (backend/app/services/entitlements.py)

Simplifies from "merge messaging plan + telecalling plan + custom_overrides"
to a single lookup:

```python
sub = tenant_subscriptions row (plan_id, mrr)
if sub.plan_id:
    plan = plans row (feature_keys, quotas)
    features = plan.feature_keys
    quotas = plan.quotas
else:
    features = [], quotas = {}
```

## Migration strategy (no entitlement loss)

One migration, run against live Supabase:

1. Add `plan_id` to `tenant_subscriptions` (nullable).
2. Backfill: for every tenant currently referencing a `messaging_plan_id`
   and/or `telecalling_plan_id`, synthesize one new `plans` row that unions
   the feature_keys/quotas of whichever of those plans they hold (folding in
   the `ai_reply` quota implied by their old `ai_tier`, using the existing
   `ai_tier.*` feature_catalog `included_qty` values as the source), priced
   at their current `mrr`. Point `tenant_subscriptions.plan_id` at the
   synthesized row.
3. The original 6 hardcoded plan rows are kept (not deleted) and become part
   of the initial admin-editable plan list — `pillar`/`tier`/`ai_tier`
   columns are dropped from them, `feature_keys`/`quotas` populated from
   their old `included` jsonb shape. Admin can edit, merge, or retire them
   from the new Subscription page.
4. Drop `messaging_plan_id`, `telecalling_plan_id`, `ai_tier`,
   `custom_overrides` from `tenant_subscriptions`.

Tenants with no subscription row at all (pre-monetization) are untouched —
they continue to show "no plan" until an admin assigns one, same as today.

## Backend changes (`backend/app/routes/operator.py`, `services/entitlements.py`)

- New CRUD: `GET /operator/plans`, `POST /operator/plans`,
  `PATCH /operator/plans/{id}`, `DELETE /operator/plans/{id}` (soft-delete →
  sets `active=false`; never a hard delete, since tenants already assigned to
  the plan keep referencing the row regardless of `active`). All admin-only
  (`Depends(get_system_admin)`).
- `POST /clients` (tenant creation): payload's `messaging_plan_id` /
  `telecalling_plan_id` / `ai_tier` fields replaced by one optional
  `plan_id`. `mrr` and seeded `enabled_features`/usage counters derive from
  that single plan via `resolve_entitlements`.
- Subscription update route (`PATCH .../subscription` or equivalent) takes
  `plan_id`, recalculates `mrr` from the plan's current `monthly_price`, and
  re-resolves `enabled_features`.
- `POST /clients/{tenant_id}/features/toggle` is removed — no more a-la-carte
  per-feature billing path.
- `GET /operator/fleet` and impersonation routes (`/operator/impersonation/*`)
  are removed.
- `_build_fleet_rows` is kept as a private helper (renamed, e.g.
  `_build_tenant_health_rows`) used only by `GET /operator/alerts`.

## Frontend changes

- **Delete**: `frontend/app/operator/(console)/fleet/` (whole directory),
  Fleet sidebar entry, Fleet command-palette entry,
  `client/[id]/components/view-as-tenant-button.tsx`, `lib/impersonation.ts`,
  `components/impersonation-banner.tsx`, and their usages.
- **New**: `frontend/app/operator/(console)/subscription/page.tsx` (or
  similarly named) occupying the sidebar slot vacated by Fleet, titled
  "Subscription." Lists existing plans (name, price, feature count, quota
  summary, count of tenants assigned) and opens a builder panel/modal to
  create or edit a plan: name + price fields, a feature checklist grouped by
  `feature_catalog.category` (reusing the existing category icons/labels from
  `feature-store.tsx`), and numeric quota inputs for the 7 canonical usage
  metrics. Delete action soft-deletes.
- **Rewrite** `client/[id]/views/feature-store.tsx`: drop the per-feature
  toggle grid and quote-confirm modal. Show the tenant's assigned plan (name,
  price, included features list, quota bars via the existing
  `UsageMeterRow`-style component) plus a "Change plan" dropdown sourced from
  `GET /operator/plans`. Empty state when the tenant has no plan, and a
  distinct empty state ("No plans exist yet — create one in Subscription")
  when the catalog of plans itself is empty.
- **Rewrite** the relevant step(s) of `components/onboarding-wizard.tsx`:
  collapse the messaging-plan / telecalling-plan / AI-tier pickers into one
  "Subscription Plan" step with a dropdown of active plans + "Skip for now."
  The step is only rendered if `GET /operator/plans` returns at least one
  active plan.
- `billing.tsx` needs no structural change beyond the crash fix already
  applied (`(subscription.mrr || 0)`); it continues to read
  `subscription.mrr`/plan-derived data, now from the simplified shape.

## Testing

- Backend: delete `test_fleet_health.py` and `test_operator_impersonation.py`
  (or repurpose the fleet-health test into an alerts test if it covers logic
  still in use). Add tests for plan CRUD and the simplified
  `resolve_entitlements`.
- Frontend: no existing test coverage for these views to update beyond what's
  already noted in subsystem-notes (shared `lib/` vitest suite); not blocking.

## Open follow-ups (explicitly out of scope for this change)

- Propagating a plan's price/quota edit to tenants already assigned to it
  (currently a no-op until an admin explicitly reassigns).
- Hard quota enforcement.
- Alerts-bell performance (`_build_tenant_health_rows` still runs an N+1
  query loop per tenant) — pre-existing, already tracked in the backlog.
