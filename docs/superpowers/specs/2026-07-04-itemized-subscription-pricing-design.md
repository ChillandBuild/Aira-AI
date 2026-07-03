# Itemized Subscription Pricing & Approval Flow — Design

## Context

The current monetization layer (migrations 123–127, shipped 2026-07-01/02) has the system admin
assign one whole admin-authored `plan` to a tenant from an operator-console "Feature Store"
picker. `tenant_subscriptions` currently has **zero rows** — no tenant has ever been assigned a
plan. Metering is track-only everywhere (`entitlements.py::meter()` never blocks). No client ever
sees a subscription, plan, or usage page — that surface exists only on the operator side today.

This design replaces the "admin assigns one bundled plan" model with an **itemized, client-driven
cart** model: the client picks individual priced items (channels, telecalling type, seats,
numbers, notifications), submits the cart, and is gated out of the rest of the product until an
admin manually confirms payment and approves. The admin's role shifts from "assign a plan" to
"price the catalog, optionally bundle packages, and approve/reject requests."

## Goals

- Client onboarding: a new tenant sees **only** a Subscriptions cart page until approved.
- Admin (developer console) sets price, per-unit overage price, and default included quantity for
  every individually purchasable item (inbound messaging, outbound/WhatsApp, telecalling
  SIM/Tele-CMI, bulk lead upload, numbers pool, telecaller seats, notifications).
- Admin can also author discounted **Packages** (bundles of catalog items) as a one-click cart
  shortcut, without losing the ability to price items individually.
- Quantity-based items (numbers, telecaller seats) and consumption quotas (messages, AI replies,
  call minutes) become **hard-blocked** at the purchased/included quantity — not track-only.
- After approval, the client manages their subscription and views usage from a Settings tab, and
  can submit incremental top-up requests without losing access to the rest of the product.
- Existing tenants (pre-dating this feature) are never gated — the cart only applies to tenants
  onboarded after this ships.

## Non-goals (explicitly deferred)

- Razorpay-driven auto-confirmation of payment. Approval is a manual admin action for now; the
  schema leaves a clean seam (a payment-confirmed flag on the request) for a webhook to flip
  later without a schema change.
- Email/SMS notifications on approval/rejection — in-app notification only.
- Proration or mid-cycle billing math — an approved change takes effect immediately at the new
  total; no partial-month credit/debit.
- Invoice / PDF generation.
- Migrating existing `tenant_subscriptions`/plan data — there is none to migrate (table is empty).

## Data model

### Reused, unchanged
- `tenant_usage_counters(tenant_id, period, metric, used, included, hard_cap)` — already the right
  shape for both track-only and hard-cap enforcement. No schema change.

### Reused, extended
- `feature_catalog` — becomes the literal backing store for the admin's new Pricing Catalog tab.
  Existing columns (`monthly_price`, `unit_price`, `included_qty`, `usage_metric`, `category`,
  `is_metered`) are used as-is. Additions:
  - New `usage_metric` enum value `phone_number` (doesn't exist today — numbers pool isn't
    metered at all currently).
  - New catalog rows for anything not already seeded: numbers pool (`usage_metric =
    phone_number`), telecaller seats (`usage_metric = team_seat_active` — this enum value already
    exists in `tenant_usage_counters` but has never had a catalog row or an enforcement check
    behind it), bulk lead upload, notifications, telecalling–SIM, telecalling–Tele-CMI.
- `plans` — repurposed as **Packages**. Add `discount_percent numeric`. A package's price is
  **computed**, not hand-entered: sum of component item prices × (1 − discount / 100), so it can
  never drift from the catalog. `feature_keys jsonb` becomes a list of `{feature_key, quantity}`
  objects (was a flat key list) so a package can bundle e.g. "2 numbers included." Soft-delete
  (`active=false`) behavior unchanged.
- `tenant_subscriptions` — `status` becomes the single gating field the frontend shell reads:
  `none` → `pending_approval` → `active`. `plan_id` stays as a nullable "started from this
  package" display reference only — never authoritative for entitlements. `mrr` is recomputed at
  each approval from the sum of active `tenant_subscription_items`.

### New tables
- `tenant_subscription_items(id, tenant_id, feature_key, quantity, unit_price_snapshot,
  package_id nullable, created_at, updated_at)` — the tenant's **current effective entitlements**.
  This is the only table enforcement code reads. Quantity is the purchased cap (e.g. 3 telecaller
  seats). One row per feature_key per tenant; approving a top-up increments `quantity` on the
  existing row rather than inserting a duplicate.
- `subscription_requests(id, tenant_id, status: submitted|approved|rejected, requested_items
  jsonb, package_id nullable, total_amount, is_initial bool, payment_confirmed bool, submitted_at,
  reviewed_at, reviewed_by, rejection_reason)` — append-only approval log. Every cart submission
  (first-time) or later top-up ask (from Settings) creates one row. This is what the admin's
  Approval Queue lists, and gives a full per-tenant audit trail independent of current state.

### Rollout backfill
A one-time migration inserts a `tenant_subscriptions` row with `status='active'` (no items
attached) for every tenant that exists as of cutover, so the gate never fires retroactively.
New tenants start with no row at all, which the frontend shell treats as `status='none'`.

## Admin (developer) console changes

**Removed:**
- `frontend/app/operator/(console)/client/[id]/views/feature-store.tsx` (the per-tenant
  plan-picker) and the plan-assignment PATCH route in its current "pick one plan" form. Admins no
  longer assign plans to tenants directly — they only price the catalog and approve requests.

**Repurposed:** `frontend/app/operator/(console)/subscription/page.tsx` becomes two tabs:
- **Pricing Catalog** — edit every `feature_catalog` row's price, unit price, and included
  quantity, grouped by category.
- **Packages** — build named bundles from catalog items + quantities, set a discount %, see the
  computed bundle price live. Same soft-delete semantics as today's plan CRUD.

**New:** an **Approval Queue** page listing pending `subscription_requests` across all tenants
(also filterable to one tenant from their client-detail page), showing requested items,
quantities, computed total, and a manual "payment confirmed" checkbox that gates the Approve
button. Reject requires a reason, shown back to the client.

**Unchanged:** the existing per-client operator sidebar module toggles (`enabled_features`,
telecalling sub-toggles, `calling_provider` radio) — an operational layer, not billing. Approval
seeds their baseline the same way plan-assignment used to.

## Client-facing changes

### Onboarding gate + Subscriptions cart
On login, the dashboard shell checks `tenant_subscriptions.status`. `none` or `pending_approval`
renders the entire app as a single full-page Subscriptions view — no sidebar, and direct
navigation to any other `/dashboard/*` route redirects back here.

Cart contents, each backed by a `feature_catalog` row:
- **Packages** shown as one-click starting points; picking one pre-fills the itemized selections
  below, which remain editable.
- **Inbound Messaging** — one toggle, one price; sub-toggles for Instagram/Facebook/Telegram
  included at no extra cost.
- **Outbound Messaging** — WhatsApp, one toggle, one price, shows the included messages/month.
- **Telecalling** — mutually-exclusive choice of SIM-based or Tele-CMI (matches the existing
  single `calling_provider` setting), each separately priced; Bulk Lead Upload as an optional
  add-on; a telecaller-seat quantity stepper (default 1, extra seats priced via `unit_price`).
- **Numbers Pool** — quantity stepper (default 1 included, extra via `unit_price`).
- **Notifications** — one toggle, one price.

A running summary shows line items, quantities, package discount if applied, and total. Submitting
creates a `subscription_requests` row (`is_initial=true`) and flips `tenant_subscriptions.status`
to `pending_approval`; the page becomes a read-only "awaiting approval" state. Rejection reopens
the cart with the reason shown; approval lifts the gate.

### Settings ▸ Subscription tab (post-approval)
A new tab combining:
- **Current plan summary** — active items, quantities, prices, total MRR, originating package if
  any.
- **Usage meters** — one row per metered item (messages, AI replies, call minutes, seats used,
  numbers used), reusing the existing color-coded `UsageMeterRow` pattern from the operator's
  per-tenant billing view, now surfaced client-side for the first time.
- **Request more** — the same cart-builder component in "add-on" mode (only shows increases/new
  items, not a full re-pick). Submitting creates a new `subscription_requests` row
  (`is_initial=false`); the rest of the dashboard stays fully usable while it's pending — only the
  specific action that triggered the request (e.g. adding a 4th telecaller) stays locked until
  approved.

## Enforcement (hard caps)

All checks reuse `entitlements.py::check_quota()`, which exists today but is called nowhere — this
wires it into real action points instead of leaving it dead code:

- **Telecaller invite** (`team.py::invite_member`) — block (403) once active-caller count reaches
  the tenant's purchased seat quantity. Client-side, "+ Add Telecaller" greys out with a tooltip
  pointing at Settings ▸ Subscription.
- **Numbers pool add** (`numbers.py::create_phone_number`) — same pattern against the new
  `phone_number` metric.
- **Outbound sends** (`broadcast_executor.py`, template sends) — check `message_sent` used vs.
  included before sending; a blocked send surfaces a clear "monthly message quota reached" error.
- **AI replies** (`ai_reply.py`) — same quota check before generating a reply. Must fail safe: a
  webhook handler still returns 200 to Meta/Telegram even when the AI reply is skipped for being
  over quota — the inbound message just doesn't get an auto-reply.
- **Call minutes** — minutes are only known after a call ends (TeleCMI CDR webhook), so the block
  has to sit at **call initiation**, not at the CDR-metering step — a new pre-call quota check on
  whatever endpoint starts a click-to-call.
- **Notifications** — not a quantity quota; gated purely on whether the tenant purchased the
  Notifications item at all. If not, that settings section is hidden/disabled.

Every blocked action gets the same client-side treatment: disabled control + tooltip pointing at
Settings ▸ Subscription, where a top-up request can be submitted.

## Rollout

- Existing tenants: backfilled to `status='active'` with no items, never gated (see backfill note
  above).
- New tenants: start with no `tenant_subscriptions` row, gated from first login until approved.
- Deferred: Razorpay auto-confirmation, email/SMS notifications, proration, invoice/PDF
  generation.
