-- 114_rls_launch_blocker.sql
-- Close every remaining RLS gap in the public schema.
-- Idempotent: safe to run whether or not migration 113 was applied first.

-- =========================================================================
-- 1. DROP dead tables
-- =========================================================================
drop table if exists public.faqs;
drop table if exists public.hot_lead_alerts;

-- =========================================================================
-- 2. conversations — add tenant_id, backfill, enable RLS + policies
-- =========================================================================
alter table public.conversations
    add column if not exists tenant_id uuid references tenants(id);

update conversations c
set tenant_id = l.tenant_id
from leads l
where c.lead_id = l.id
  and c.tenant_id is null;

alter table public.conversations enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'conversations'
          and policyname = 'conversations_tenant_member_select'
    ) then
        create policy conversations_tenant_member_select
            on public.conversations for select to authenticated
            using (public.is_tenant_member(tenant_id));
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'conversations'
          and policyname = 'conversations_tenant_owner_write'
    ) then
        create policy conversations_tenant_owner_write
            on public.conversations for all to authenticated
            using (public.is_tenant_owner(tenant_id))
            with check (public.is_tenant_owner(tenant_id));
    end if;
end $$;

-- =========================================================================
-- 3. bot_flows — enable RLS + policies
-- =========================================================================
alter table if exists public.bot_flows enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'bot_flows'
          and policyname = 'bot_flows_tenant_member_select'
    ) then
        create policy bot_flows_tenant_member_select
            on public.bot_flows for select to authenticated
            using (public.is_tenant_member(tenant_id));
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'bot_flows'
          and policyname = 'bot_flows_tenant_owner_write'
    ) then
        create policy bot_flows_tenant_owner_write
            on public.bot_flows for all to authenticated
            using (public.is_tenant_owner(tenant_id))
            with check (public.is_tenant_owner(tenant_id));
    end if;
end $$;

-- =========================================================================
-- 4. meta_templates — enable RLS + policies
-- =========================================================================
alter table if exists public.meta_templates enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'meta_templates'
          and policyname = 'meta_templates_tenant_member_select'
    ) then
        create policy meta_templates_tenant_member_select
            on public.meta_templates for select to authenticated
            using (public.is_tenant_member(tenant_id));
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'meta_templates'
          and policyname = 'meta_templates_tenant_owner_write'
    ) then
        create policy meta_templates_tenant_owner_write
            on public.meta_templates for all to authenticated
            using (public.is_tenant_owner(tenant_id))
            with check (public.is_tenant_owner(tenant_id));
    end if;
end $$;

-- =========================================================================
-- 5. Tables overlapping with migration 113 (idempotent)
--    reengagement_steps, reengagement_logs, call_scripts,
--    telecalling_upload_batches
-- =========================================================================
alter table if exists public.reengagement_steps enable row level security;
alter table if exists public.reengagement_logs enable row level security;
alter table if exists public.call_scripts enable row level security;
alter table if exists public.telecalling_upload_batches enable row level security;

-- SELECT policies (member) — all four tables
do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'reengagement_steps',
        'reengagement_logs',
        'call_scripts',
        'telecalling_upload_batches'
    ] loop
        if to_regclass('public.' || tbl) is not null then
            if not exists (
                select 1 from pg_policies
                where schemaname = 'public'
                  and tablename  = tbl
                  and policyname = tbl || '_tenant_member_select'
            ) then
                execute format(
                    'create policy %I on public.%I for select to authenticated using (public.is_tenant_member(tenant_id))',
                    tbl || '_tenant_member_select',
                    tbl
                );
            end if;
        end if;
    end loop;
end $$;

-- WRITE policies (owner) — config/upload tables only (NOT reengagement_logs)
do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'reengagement_steps',
        'call_scripts',
        'telecalling_upload_batches'
    ] loop
        if to_regclass('public.' || tbl) is not null then
            if not exists (
                select 1 from pg_policies
                where schemaname = 'public'
                  and tablename  = tbl
                  and policyname = tbl || '_tenant_owner_write'
            ) then
                execute format(
                    'create policy %I on public.%I for all to authenticated using (public.is_tenant_owner(tenant_id)) with check (public.is_tenant_owner(tenant_id))',
                    tbl || '_tenant_owner_write',
                    tbl
                );
            end if;
        end if;
    end loop;
end $$;

-- =========================================================================
-- 6. scheduler_runs — deny-all policy (system table, no tenant_id)
-- =========================================================================
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename  = 'scheduler_runs'
          and policyname = 'scheduler_runs_deny_all'
    ) then
        create policy scheduler_runs_deny_all
            on public.scheduler_runs for all to anon, authenticated
            using (false);
    end if;
end $$;

-- =========================================================================
-- 7. Revoke EXECUTE from anon on SECURITY DEFINER helpers
--    Must revoke from public role (which anon inherits), then re-grant to authenticated.
-- =========================================================================
revoke execute on function public.is_system_admin() from public;
revoke execute on function public.is_tenant_member(p_tenant_id uuid) from public;
revoke execute on function public.is_tenant_owner(p_tenant_id uuid) from public;

grant execute on function public.is_system_admin() to authenticated;
grant execute on function public.is_tenant_member(p_tenant_id uuid) to authenticated;
grant execute on function public.is_tenant_owner(p_tenant_id uuid) to authenticated;

-- =========================================================================
-- 8. Set search_path on SECURITY DEFINER / RPC functions that lost it
--    Uses pg_proc to resolve current overload signatures automatically.
-- =========================================================================
do $$
declare
    r record;
begin
    for r in
        select p.oid::regprocedure as sig
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname in (
              'insert_knowledge_chunk',
              'match_knowledge_chunks',
              'keyword_match_chunks',
              'template_performance',
              'update_leads_assigned_at',
              'get_conversation_leads'
          )
    loop
        execute format('alter function %s set search_path = public, pg_temp', r.sig);
    end loop;
end $$;
