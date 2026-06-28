-- First-class SIM/manual call statuses.
-- SIM Basic still writes to call_logs so analytics can aggregate one source;
-- manual_status preserves the telecaller's exact wrap-up selection.

alter table public.call_logs
  add column if not exists manual_status text;

alter table public.call_logs
  drop constraint if exists call_logs_manual_status_check;

alter table public.call_logs
  add constraint call_logs_manual_status_check
  check (
    manual_status is null
    or manual_status in (
      'connected',
      'not_picked',
      'busy',
      'wrong_number',
      'interested',
      'not_interested',
      'callback'
    )
  );

alter table public.call_logs
  drop constraint if exists call_logs_outcome_check;

alter table public.call_logs
  add constraint call_logs_outcome_check
  check (
    outcome is null
    or outcome in ('converted', 'interested', 'callback', 'not_interested', 'no_answer')
  );

alter table public.call_logs
  drop constraint if exists call_logs_status_check;

alter table public.call_logs
  add constraint call_logs_status_check
  check (status in ('initiated', 'in_progress', 'sim_started', 'completed', 'failed', 'missed', 'no_answer'));

create index if not exists idx_call_logs_tenant_manual_status_created
  on public.call_logs (tenant_id, manual_status, created_at desc);

create or replace function public.get_telecalling_all_time_stats(p_tenant_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_avg_duration integer;
    v_outcome_breakdown jsonb;
    v_manual_status_breakdown jsonb;
    v_caller_stats jsonb;
begin
    select coalesce(round(avg(duration_seconds)), 0)
    into v_avg_duration
    from public.call_logs
    where tenant_id = p_tenant_id and duration_seconds is not null;

    select jsonb_object_agg(outcome, count)
    into v_outcome_breakdown
    from (
        select coalesce(outcome, 'unknown') as outcome, count(*) as count
        from public.call_logs
        where tenant_id = p_tenant_id
        group by outcome
    ) t;

    select jsonb_object_agg(manual_status, count)
    into v_manual_status_breakdown
    from (
        select coalesce(manual_status, 'unknown') as manual_status, count(*) as count
        from public.call_logs
        where tenant_id = p_tenant_id
        group by manual_status
    ) t;

    select jsonb_object_agg(caller_id, stats)
    into v_caller_stats
    from (
        select caller_id::text, jsonb_build_object(
            'total', count(*),
            'converted', count(*) filter (where outcome = 'converted')
        ) as stats
        from public.call_logs
        where tenant_id = p_tenant_id and caller_id is not null
        group by caller_id
    ) t;

    return jsonb_build_object(
        'avg_duration_seconds', v_avg_duration,
        'outcome_breakdown', coalesce(v_outcome_breakdown, '{}'::jsonb),
        'manual_status_breakdown', coalesce(v_manual_status_breakdown, '{}'::jsonb),
        'caller_stats', coalesce(v_caller_stats, '{}'::jsonb)
    );
end;
$$;

revoke execute on function public.get_telecalling_all_time_stats(uuid) from public, anon, authenticated;
grant execute on function public.get_telecalling_all_time_stats(uuid) to service_role;
