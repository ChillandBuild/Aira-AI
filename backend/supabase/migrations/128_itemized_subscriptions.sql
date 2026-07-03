-- Migration 128: Itemized subscription pricing + client-driven approval flow
--
-- Replaces "admin assigns one plan" with "client builds a cart of priced
-- catalog items, submits it, admin approves." See design doc:
-- docs/superpowers/specs/2026-07-04-itemized-subscription-pricing-design.md

-- 1. tenant_subscription_items: current effective entitlements (what
--    enforcement code reads). One row per feature_key per tenant.
create table if not exists tenant_subscription_items (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    feature_key text not null references feature_catalog(feature_key),
    quantity int not null default 1,
    unit_price_snapshot numeric not null default 0,
    package_id uuid references plans(id) on delete set null,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (tenant_id, feature_key)
);

-- 2. subscription_requests: append-only approval log. One row per cart
--    submission (initial onboarding) or top-up ask (later, from Settings).
create table if not exists subscription_requests (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    status text not null check (status in ('submitted', 'approved', 'rejected')) default 'submitted',
    requested_items jsonb not null default '[]',
    package_id uuid references plans(id) on delete set null,
    total_amount numeric not null default 0,
    is_initial boolean not null default true,
    payment_confirmed boolean not null default false,
    submitted_at timestamptz default now(),
    reviewed_at timestamptz,
    reviewed_by uuid,
    rejection_reason text
);

-- 3. plans: add package discount. Bundle price is computed client/server
--    side from component items × (1 - discount/100), never hand-typed.
alter table plans add column if not exists discount_percent numeric not null default 0;

-- 4. tenant_usage_counters: numbers pool needs its own metric — it isn't
--    modeled as a metric at all today.
alter table tenant_usage_counters drop constraint if exists tenant_usage_counters_metric_check;
alter table tenant_usage_counters add constraint tenant_usage_counters_metric_check
    check (metric in ('message_sent', 'ai_reply', 'call_minute', 'team_seat_active', 'storage_gb', 'ai_call_summary', 'ai_call_scoring', 'phone_number'));

-- 5. tenant_subscriptions: add the gating status the frontend shell reads.
alter table tenant_subscriptions drop constraint if exists tenant_subscriptions_status_check;
alter table tenant_subscriptions add constraint tenant_subscriptions_status_check
    check (status in ('trial', 'active', 'past_due', 'suspended', 'cancelled', 'pending_approval'));

-- 6. New sellable feature_catalog rows (the client-facing cart SKUs).
--    `depends_on` (existing, previously-unused column) lists the internal
--    granular feature_keys this SKU turns on when purchased.
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, usage_metric, unit_price, included_qty, depends_on, is_metered, sort_order)
values
('telecalling.upload', 'Bulk Lead Upload (internal)', 'telecalling', 'telecalling', 0, null, null, null, '{}', false, 29)
on conflict (feature_key) do nothing;

insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, usage_metric, unit_price, included_qty, depends_on, is_metered, sort_order)
values
('inbound_messaging', 'Inbound Messaging', 'channels', 'messaging', 1500, null, null, null, '{instagram,facebook,telegram}', false, 100),
('outbound_messaging', 'Outbound Messaging (WhatsApp)', 'messaging', 'messaging', 1999, 'message_sent', 0.5, 1000, '{whatsapp,broadcast,templates,auto_reply,human_handover}', true, 101),
('telecalling_sim', 'Telecalling — SIM Based', 'telecalling', 'telecalling', 999, null, null, null, '{telecalling.dialer,telecalling.scheduled,telecalling.notes}', false, 102),
('telecalling_telecmi', 'Telecalling — Tele-CMI', 'telecalling', 'telecalling', 1999, 'call_minute', 1, 500, '{telecalling.dialer,telecalling.scheduled,telecalling.notes,telecalling.scripts,telecalling.attendance,telecalling.performance,telecalling.qa,tc_recording}', true, 103),
('bulk_lead_upload', 'Bulk Lead Upload', 'telecalling', 'telecalling', 299, null, null, null, '{telecalling.upload}', false, 104),
('telecaller_seats', 'Telecaller Seats', 'telecalling', 'telecalling', 0, 'team_seat_active', 199, 1, '{}', true, 105),
('numbers_pool', 'Numbers Pool', 'channels', 'messaging', 0, 'phone_number', 299, 1, '{}', true, 106),
('notifications', 'Notifications', 'automation', 'shared', 499, null, null, null, '{push_notifications,callbacks,dnc,webhook_health,token_expiry_alerts}', false, 107)
on conflict (feature_key) do nothing;

-- 7. Grandfather every existing tenant so they are never gated — the cart
--    only applies to tenants created after this migration. Note: if a
--    tenant already has a tenant_subscriptions row (e.g. from the ordinary
--    create_client flow) with a non-'active' status, this insert is a
--    no-op for that row (ON CONFLICT DO NOTHING) — such rows must be
--    reconciled to 'active' by hand, scoped to the specific tenant_ids
--    involved, never with a broad status-based predicate that could also
--    catch deliberately 'suspended'/'past_due' tenants.
insert into tenant_subscriptions (tenant_id, status)
select id, 'active' from tenants
on conflict (tenant_id) do nothing;

-- 8. RLS for the two new tables.
alter table tenant_subscription_items enable row level security;
alter table subscription_requests enable row level security;

drop policy if exists "tenant_subscription_items_admin_all" on tenant_subscription_items;
create policy "tenant_subscription_items_admin_all" on tenant_subscription_items for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);
drop policy if exists "tenant_subscription_items_tenant_read" on tenant_subscription_items;
create policy "tenant_subscription_items_tenant_read" on tenant_subscription_items for select using (
    exists (select 1 from tenant_users tu where tu.tenant_id = tenant_subscription_items.tenant_id and tu.user_id = auth.uid())
);

drop policy if exists "subscription_requests_admin_all" on subscription_requests;
create policy "subscription_requests_admin_all" on subscription_requests for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);
drop policy if exists "subscription_requests_tenant_read" on subscription_requests;
create policy "subscription_requests_tenant_read" on subscription_requests for select using (
    exists (select 1 from tenant_users tu where tu.tenant_id = subscription_requests.tenant_id and tu.user_id = auth.uid())
);
drop policy if exists "subscription_requests_tenant_insert" on subscription_requests;
create policy "subscription_requests_tenant_insert" on subscription_requests for insert with check (
    exists (select 1 from tenant_users tu where tu.tenant_id = subscription_requests.tenant_id and tu.user_id = auth.uid() and tu.role = 'owner')
);
