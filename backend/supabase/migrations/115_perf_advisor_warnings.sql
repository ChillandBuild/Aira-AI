-- 115_perf_advisor_warnings.sql
-- Fix all 18 Performance Advisor warnings:
--   5x auth_rls_initplan (wrap auth.uid() in subselect)
--  12x multiple_permissive_policies (replace FOR ALL with separate INSERT/UPDATE/DELETE)
--   1x duplicate_index (drop one of two identical indexes)

-- =========================================================================
-- 1. Fix auth_rls_initplan — wrap auth.uid() in (select auth.uid())
-- =========================================================================

-- employee_todos: "Users can manage their own todos" (ALL)
drop policy if exists "Users can manage their own todos" on public.employee_todos;
create policy "Users can manage their own todos"
    on public.employee_todos for all to authenticated
    using (((select auth.uid()) = user_id));

-- app_notifications: "Users can view their own notifications" (SELECT)
drop policy if exists "Users can view their own notifications" on public.app_notifications;
create policy "Users can view their own notifications"
    on public.app_notifications for select to authenticated
    using ((user_id = (select auth.uid())));

-- app_notifications: "Users can update their own notifications" (UPDATE)
drop policy if exists "Users can update their own notifications" on public.app_notifications;
create policy "Users can update their own notifications"
    on public.app_notifications for update to authenticated
    using ((user_id = (select auth.uid())));

-- tenant_users: "tenant_users_member_select" (SELECT)
drop policy if exists "tenant_users_member_select" on public.tenant_users;
create policy "tenant_users_member_select"
    on public.tenant_users for select to authenticated
    using (((user_id = (select auth.uid())) OR is_tenant_owner(tenant_id) OR is_system_admin()));

-- system_admins: "system_admins_self_select" (SELECT)
drop policy if exists "system_admins_self_select" on public.system_admins;
create policy "system_admins_self_select"
    on public.system_admins for select to authenticated
    using ((user_id = (select auth.uid())));

-- =========================================================================
-- 2. Fix multiple_permissive_policies — replace FOR ALL with separate
--    INSERT + UPDATE + DELETE so the _member_select policy doesn't overlap.
-- =========================================================================
do $$
declare
    tbl text;
begin
    foreach tbl in array array[
        'app_settings',
        'automation_steps',
        'automations',
        'bot_flows',
        'broadcast_tags',
        'call_scripts',
        'conversations',
        'knowledge_documents',
        'message_templates',
        'meta_templates',
        'reengagement_steps',
        'telecalling_upload_batches'
    ] loop
        -- Drop the old FOR ALL policy
        execute format('drop policy if exists %I on public.%I',
            tbl || '_tenant_owner_write', tbl);

        -- Create separate INSERT, UPDATE, DELETE policies
        execute format(
            'create policy %I on public.%I for insert to authenticated with check (public.is_tenant_owner(tenant_id))',
            tbl || '_tenant_owner_insert', tbl);

        execute format(
            'create policy %I on public.%I for update to authenticated using (public.is_tenant_owner(tenant_id)) with check (public.is_tenant_owner(tenant_id))',
            tbl || '_tenant_owner_update', tbl);

        execute format(
            'create policy %I on public.%I for delete to authenticated using (public.is_tenant_owner(tenant_id))',
            tbl || '_tenant_owner_delete', tbl);
    end loop;
end $$;

-- =========================================================================
-- 3. Fix duplicate_index — drop one of the identical indexes on
--    caller_status_logs (keep the more descriptive name)
-- =========================================================================
drop index if exists public.csl_tenant_idx;
