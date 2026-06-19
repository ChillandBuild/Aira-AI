-- 113_security_and_new_tables_rls.sql
-- Enable RLS and define security policies for newer tables:
-- reengagement_steps, reengagement_logs, autopilot_runs, call_scripts, and telecalling_upload_batches.

-- ---------------------------------------------------------------------------
-- Enable RLS on newer tables
-- ---------------------------------------------------------------------------
alter table if exists public.reengagement_steps enable row level security;
alter table if exists public.reengagement_logs enable row level security;
alter table if exists public.autopilot_runs enable row level security;
alter table if exists public.call_scripts enable row level security;
alter table if exists public.telecalling_upload_batches enable row level security;

-- ---------------------------------------------------------------------------
-- Tenant table select policies (for tenant members)
-- ---------------------------------------------------------------------------
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'reengagement_steps',
        'reengagement_logs',
        'autopilot_runs',
        'call_scripts',
        'telecalling_upload_batches'
    ] loop
        if to_regclass('public.' || table_name) is not null then
            if not exists (
                select 1 from pg_policies
                where schemaname = 'public'
                  and tablename = table_name
                  and policyname = table_name || '_tenant_member_select'
            ) then
                execute format(
                    'create policy %I on public.%I for select to authenticated using (public.is_tenant_member(tenant_id))',
                    table_name || '_tenant_member_select',
                    table_name
                );
            end if;
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Tenant table write policies (for tenant owners on configuration/upload tables)
-- ---------------------------------------------------------------------------
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'reengagement_steps',
        'call_scripts',
        'telecalling_upload_batches'
    ] loop
        if to_regclass('public.' || table_name) is not null then
            if not exists (
                select 1 from pg_policies
                where schemaname = 'public'
                  and tablename = table_name
                  and policyname = table_name || '_tenant_owner_write'
            ) then
                execute format(
                    'create policy %I on public.%I for all to authenticated using (public.is_tenant_owner(tenant_id)) with check (public.is_tenant_owner(tenant_id))',
                    table_name || '_tenant_owner_write',
                    table_name
                );
            end if;
        end if;
    end loop;
end $$;
