-- 110_telecalling_analytics_optimization.sql
-- Optimizes telecalling analytics by adding compound indexes on date filters
-- and an RPC for database-side metrics aggregation.
--
-- NOTE: CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
-- Apply this file WITHOUT a wrapping transaction (e.g. `supabase db push`
-- runs statement-by-statement; if your runner wraps migrations in a txn,
-- run the two index statements separately first).

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_call_logs_tenant_created ON public.call_logs (tenant_id, created_at DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_caller_status_logs_tenant_started ON public.caller_status_logs (tenant_id, started_at DESC);

CREATE OR REPLACE FUNCTION public.get_telecalling_all_time_stats(p_tenant_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_avg_duration integer;
    v_outcome_breakdown jsonb;
    v_caller_stats jsonb;
BEGIN
    -- 1. Average duration
    SELECT COALESCE(round(avg(duration_seconds)), 0)
    INTO v_avg_duration
    FROM public.call_logs
    WHERE tenant_id = p_tenant_id AND duration_seconds IS NOT NULL;

    -- 2. Outcome breakdown
    SELECT jsonb_object_agg(outcome, count)
    INTO v_outcome_breakdown
    FROM (
        SELECT COALESCE(outcome, 'unknown') as outcome, count(*) as count
        FROM public.call_logs
        WHERE tenant_id = p_tenant_id
        GROUP BY outcome
    ) t;

    -- 3. Per-caller stats
    SELECT jsonb_object_agg(caller_id, stats)
    INTO v_caller_stats
    FROM (
        SELECT caller_id::text, jsonb_build_object(
            'total', count(*),
            'converted', count(*) FILTER (WHERE outcome = 'converted')
        ) as stats
        FROM public.call_logs
        WHERE tenant_id = p_tenant_id AND caller_id IS NOT NULL
        GROUP BY caller_id
    ) t;

    RETURN jsonb_build_object(
        'avg_duration_seconds', v_avg_duration,
        'outcome_breakdown', COALESCE(v_outcome_breakdown, '{}'::jsonb),
        'caller_stats', COALESCE(v_caller_stats, '{}'::jsonb)
    );
END;
$$;

-- SECURITY DEFINER bypasses RLS and trusts p_tenant_id, so it must not be
-- callable directly by client roles — only the backend service key invokes it.
REVOKE EXECUTE ON FUNCTION public.get_telecalling_all_time_stats(uuid) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_telecalling_all_time_stats(uuid) TO service_role;
