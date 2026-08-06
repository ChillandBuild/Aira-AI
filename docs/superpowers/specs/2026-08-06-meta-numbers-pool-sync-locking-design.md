# Meta-Account-Driven Numbers Pool Sync + Quota Locking — Design

## Purpose

Today the numbers pool (`.agents/context/subsystem-notes.md` → "Telecaller seats &
numbers pool: hard enforcement restored") is enforced purely at *creation time*:
`POST /api/v1/numbers` hard-blocks once the tenant's row count reaches
`_numbers_pool_limit()`. There is no way to see numbers that exist on a client's
connected Meta WhatsApp Business Account (WABA) but aren't in our `phone_numbers`
table yet — "Sync from Meta" today only refreshes quality/tier for numbers already
added one-by-one with a `meta_phone_number_id`.

This build adds a **bulk discovery sync** that pulls every number already registered
on the client's Meta WABA into `phone_numbers`, regardless of how many the tenant's
subscription allows — and gates *usability*, not *visibility*, by quota. Numbers
beyond what's purchased are visible but locked/blurred in the UI and functionally
inert, rather than being silently dropped or blocked from ever being imported.

## Locking rule

Locking is **computed live on every read/route**, never stored as a column. This is
what makes it self-healing: a subscription upgrade or downgrade takes effect on the
next read/routing decision, with no migration or re-sync required.

For a tenant's non-archived `phone_numbers`, with `limit = numbers_pool.limit`
(existing `_numbers_pool_limit()`):

- If a `role="primary"` number exists → it is always unlocked. The remaining
  `limit - 1` slots are filled **oldest-first by `created_at`** among the
  non-primary numbers. Everything past that is `locked`.
- If **no** primary exists yet (e.g. a brand-new tenant's first sync pulls in
  several numbers at once) → **every number is locked**, regardless of `limit`.
  Oldest-first filling only ever awards slots *in addition to* a guaranteed
  primary slot — it never operates without a primary present. This is deliberate:
  on a fresh WABA connection with e.g. 3 numbers and a 1-number subscription, the
  client must explicitly choose which number becomes primary rather than the
  system picking one for them by arbitrary sync-batch order.

Setting a number as primary (`PATCH /{id}` with `role="primary"`) is **always
allowed**, on any number, locked or not — it is the mechanism by which a client
either makes their first choice (no-primary case) or swaps which number occupies
the primary slot (existing-primary case, demoting the old primary back into the
ordinary oldest-first pool).

## Backend: bulk sync endpoint

New `POST /api/v1/numbers/sync-from-meta` (tenant-scoped, `require_numbers_manage`,
alongside the existing per-number `POST /{number_id}/sync-meta`, not replacing it):

1. Read the tenant's `meta_waba_id` and `meta_access_token` via
   `get_setting(..., tenant_id=tenant_id)` (`app/config_dynamic.py`, same pattern
   `meta_cloud.py` already uses). If either is missing, 400 with a message pointing
   at Settings ("Connect Meta WhatsApp first").
2. New `meta_cloud.list_waba_phone_numbers(waba_id, access_token, tenant_id)`:
   paginated `GET {waba_id}/phone_numbers` on the Graph API
   (`fields=id,display_phone_number,verified_name,quality_rating,messaging_limit_tier`),
   following the same pagination pattern as `list_all_templates`.
3. Define one normalization helper — strip everything except digits and a leading
   `+` (e.g. `"+91 98765-43210"` → `"+919876543210"`) — used both for matching and
   for what gets stored, so it's consistent with how manually-added numbers already
   look (`+919876543210`, per the existing "Add Number" placeholder).
4. For each Meta number returned:
   - Match to an existing `phone_numbers` row by `meta_phone_number_id`.
   - If no match, fall back to matching on the normalized `number` (covers numbers
     added manually before an ID was recorded) and backfill
     `meta_phone_number_id` onto that row.
   - If still no match, insert a new row: `provider="meta_cloud"`,
     `role="standby"`, `status="warming"`, `warm_up_day=0`,
     `paused_outbound=False`, `display_name=verified_name or display_phone_number`,
     `number` = normalized `display_phone_number`,
     `quality_rating`/`messaging_tier` taken directly from Meta's response
     (mapped through the existing `_QUALITY_MAP`/`_TIER_MAP`).
   - **Never auto-assign `role="primary"`** on insert — new numbers always start
     `standby`, consistent with the no-primary-until-chosen locking rule above.
5. Every matched/inserted row then gets the same quality/warm-up refresh
   `sync_number_from_meta` already does today (quality snapshot, incident on
   degradation, warm-up day advancement), **except**: if the row is currently
   `locked` (computed per the rule above, evaluated before applying this row's
   update), skip the `status: "warming" → "active"` transition even if warm-up day
   would otherwise qualify. It can still accrue `warm_up_day` harmlessly.
6. Returns the same shape as `GET /` (full number list including `locked` per row,
   plus `numbers_pool`), so the frontend can refresh from the response directly
   instead of an extra round-trip.

Extract the lock computation into a shared helper (e.g.
`services/numbers_pool.py::get_unlocked_number_ids(db, tenant_id) -> set[str]`) —
it's needed in three places (below), and duplicating the primary/oldest-first logic
across them is the kind of drift that breaks quietly.

## Enforcement — three layers

1. **`GET /api/v1/numbers/`** — every row in `data` gets a computed `locked: bool`
   using the shared helper.
2. **`PATCH /{number_id}`** — rejects (400, "upgrade your numbers pool to activate
   this number") any update that would set `status="active"` or
   `paused_outbound=false` on a number that is *currently* locked (computed before
   applying the update). `role="primary"` is exempt from this check per the locking
   rule above — it's always allowed and is itself what changes lock state.
3. **`outbound_router.get_best_number()`** — today this selects the best candidate
   among **all** `status=active, quality!=red, warm_up_day>=14, paused_outbound=false`
   numbers for the tenant, without regard to `role`. It gets an added filter against
   the same shared `get_unlocked_number_ids()` helper. This is the layer that makes
   a downgrade take effect **immediately** — the moment quota shrinks, a
   newly-over-quota number stops being selectable for outbound sends on the very
   next send, without waiting for a manual re-sync or any write to that row.

**Explicitly unchanged:**
- `failover.py`'s `handle_quality_red()` may still auto-promote a locked standby
  number to primary during a red-quality outage. Once promoted it legitimately
  wins the guaranteed primary slot (per the locking rule) — this is a resilience
  path, not a quota bypass, and losing it would mean a client could be left with
  zero working numbers during an outage.
- Inbound messages to a locked number are received and logged completely normally.
  Locking only ever excludes a number from being *chosen to send from*
  (`get_best_number`) — it never drops or gates inbound customer messages, which
  Meta routes to us regardless of our internal quota bookkeeping.
- Manual single-number `POST /api/v1/numbers` keeps its existing hard 400-at-quota
  block, unchanged. Only the new bulk Meta sync is allowed to bring in numbers
  beyond quota (landing them locked, not rejected).

## Frontend (`frontend/app/dashboard/numbers/page.tsx`)

- `PhoneNumber` type gains `locked: boolean` (from the API response).
- The existing "Sync from Meta" bulk button (`handleSyncAllMeta`) is rewired to
  call the new `POST /api/v1/numbers/sync-from-meta` once, instead of
  `Promise.all`-ing the per-number `sync-meta` endpoint across every already-known
  number. The per-number "Sync Meta" button/action on each card is unchanged
  (still useful for refreshing a single number's quality on demand).
- Locked cards render with a blur/opacity treatment and a lock icon overlay.
  **"Set Primary" stays enabled** on locked cards — it's the unlock action.
  Pause/Resume is disabled on locked cards (grayed out, tooltip explaining it's
  locked). Rename, Delete, and the individual "Sync Meta" action stay enabled on
  locked cards same as unlocked ones.
- The numbers pool usage badge (`{used}/{limit} used`) and the "Add Number" disable
  state are unchanged — both already reflect quota correctly today.

## Non-goals

- No new DB column or migration — `locked` is computed at read/route time from
  existing `phone_numbers` columns (`role`, `created_at`, `status`) plus the
  existing `numbers_pool` limit calculation.
- No change to how `numbers_pool.limit` itself is calculated
  (`_numbers_pool_limit()` in `numbers.py` — baseline free number from
  inbound/outbound messaging entitlement + purchased `numbers_pool` add-ons).
- No inbound-side gating, as noted above.
