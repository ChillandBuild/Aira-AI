-- Calling provider split + Web Push subscriptions.
-- TeleCMI remains the automatic provider; SIM Basic records manual feedback into
-- the same call_logs table so analytics can continue to aggregate one source.

alter table public.call_logs
  add column if not exists provider text not null default 'telecmi',
  add column if not exists feedback_source text not null default 'automatic',
  add column if not exists manual_started_at timestamptz,
  add column if not exists manual_ended_at timestamptz;

alter table public.call_logs
  drop constraint if exists call_logs_provider_check;

alter table public.call_logs
  add constraint call_logs_provider_check
  check (provider in ('telecmi', 'sim_basic'));

alter table public.call_logs
  drop constraint if exists call_logs_feedback_source_check;

alter table public.call_logs
  add constraint call_logs_feedback_source_check
  check (feedback_source in ('automatic', 'manual'));

create index if not exists idx_call_logs_tenant_provider_created
  on public.call_logs (tenant_id, provider, created_at desc);

create table if not exists public.push_subscriptions (
  id uuid primary key default uuid_generate_v4(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  endpoint text not null,
  p256dh text not null,
  auth text not null,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, endpoint)
);

create index if not exists idx_push_subscriptions_tenant_user
  on public.push_subscriptions (tenant_id, user_id);

alter table public.push_subscriptions enable row level security;

drop policy if exists push_subscriptions_self_select on public.push_subscriptions;
create policy push_subscriptions_self_select
  on public.push_subscriptions for select to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists push_subscriptions_self_insert on public.push_subscriptions;
create policy push_subscriptions_self_insert
  on public.push_subscriptions for insert to authenticated
  with check (user_id = (select auth.uid()));

drop policy if exists push_subscriptions_self_update on public.push_subscriptions;
create policy push_subscriptions_self_update
  on public.push_subscriptions for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists push_subscriptions_self_delete on public.push_subscriptions;
create policy push_subscriptions_self_delete
  on public.push_subscriptions for delete to authenticated
  using (user_id = (select auth.uid()));
