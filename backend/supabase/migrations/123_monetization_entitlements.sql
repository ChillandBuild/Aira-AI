-- Migration 123: Monetization entitlement tables

-- Feature catalog - every toggleable module
create table if not exists feature_catalog (
    feature_key text primary key,
    display_name text not null,
    category text not null check (category in ('channels', 'messaging', 'ai', 'telecalling', 'automation', 'ops')),
    pillar text not null check (pillar in ('messaging', 'telecalling', 'shared')),
    monthly_price numeric not null default 0,
    usage_metric text references feature_catalog(feature_key) on delete set null,
    unit_price numeric,
    included_qty int,
    depends_on text[] default '{}',
    is_metered boolean not null default false,
    sort_order int not null default 0
);

-- Plans - named presets of catalog rows + quotas
create table if not exists plans (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    pillar text not null check (pillar in ('messaging', 'telecalling', 'shared')),
    tier text not null check (tier in ('basic', 'standard', 'pro')),
    monthly_price numeric not null default 0,
    ai_tier text check (ai_tier in ('off', 'basic', 'standard', 'premium', 'byo')),
    included jsonb not null default '{"feature_keys":[],"quotas":{}}',
    active boolean not null default true,
    created_at timestamptz default now()
);

-- Tenant subscriptions - links tenant to plans + overrides
create table if not exists tenant_subscriptions (
    tenant_id uuid primary key references tenants(id) on delete cascade,
    status text not null check (status in ('trial', 'active', 'past_due', 'suspended', 'cancelled')) default 'trial',
    messaging_plan_id uuid references plans(id),
    telecalling_plan_id uuid references plans(id),
    ai_tier text check (ai_tier in ('off', 'basic', 'standard', 'premium', 'byo')),
    custom_overrides jsonb default '{}',
    mrr numeric default 0,
    period_start date,
    period_end date,
    trial_ends date
);

-- Tenant usage counters - metered events tracking
create table if not exists tenant_usage_counters (
    tenant_id uuid references tenants(id) on delete cascade,
    period text not null,
    metric text not null check (metric in ('message_sent', 'ai_reply', 'call_minute', 'team_seat_active', 'storage_gb', 'ai_call_summary', 'ai_call_scoring')),
    used numeric not null default 0,
    included numeric not null default 0,
    hard_cap numeric,
    primary key (tenant_id, period, metric)
);

-- Enable RLS on all monetization tables
alter table feature_catalog enable row level security;
alter table plans enable row level security;
alter table tenant_subscriptions enable row level security;
alter table tenant_usage_counters enable row level security;

-- RLS policies: system_admins can manage all, tenants can read plans
create policy if not exists "feature_catalog_admin_all" on feature_catalog for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);

create policy if not exists "plans_admin_all" on plans for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);

create policy if not exists "plans_tenant_read" on plans for select using (
    exists (select 1 from tenants where id = tenant_subscriptions.tenant_id)
);

create policy if not exists "tenant_subscriptions_admin_all" on tenant_subscriptions for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);

create policy if not exists "tenant_subscriptions_tenant_read" on tenant_subscriptions for select using (
    exists (select 1 from tenants where id = tenant_id)
);

create policy if not exists "tenant_usage_counters_admin_all" on tenant_usage_counters for all using (
    exists (select 1 from system_admins where user_id = auth.uid())
);

create policy if not exists "tenant_usage_counters_tenant_read" on tenant_usage_counters for select using (
    exists (select 1 from tenants where id = tenant_id)
);