-- 154: the three "why am I paying for this" analytics blocks, aggregated in
-- SQL for the same reason as 153 (PostgREST silently caps result sets at
-- 1000 rows). All three are period-scoped so they ride the existing
-- /compare period-over-period machinery for free.

-- 1. Money. Ad spend joined to attributed leads gives cost per lead and cost
--    per HOT lead -- the number a business owner actually asks about.
--    ad_insights_daily carries tenant_id directly, so no join is needed to
--    scope spend; leads.ad_campaign_id marks attribution on the lead side.
CREATE OR REPLACE FUNCTION public.analytics_period_money(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  spend numeric,
  impressions bigint,
  clicks bigint,
  ad_leads bigint,
  ad_hot_leads bigint,
  cost_per_lead numeric,
  cost_per_hot_lead numeric
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  WITH s AS (
    SELECT
      COALESCE(round(sum(spend), 2), 0) AS spend,
      COALESCE(sum(impressions), 0)     AS impressions,
      COALESCE(sum(clicks), 0)          AS clicks
    FROM ad_insights_daily
    WHERE tenant_id = p_tenant_id
      AND insight_date >= (p_start AT TIME ZONE 'Asia/Kolkata')::date
      AND insight_date <  (p_end   AT TIME ZONE 'Asia/Kolkata')::date
  ),
  l AS (
    SELECT
      count(*) FILTER (WHERE ad_campaign_id IS NOT NULL)                     AS ad_leads,
      count(*) FILTER (WHERE ad_campaign_id IS NOT NULL AND segment = 'A')   AS ad_hot_leads
    FROM leads
    WHERE tenant_id = p_tenant_id
      AND deleted_at IS NULL
      AND created_at >= p_start
      AND created_at <  p_end
  )
  SELECT
    s.spend, s.impressions, s.clicks, l.ad_leads, l.ad_hot_leads,
    round(s.spend / NULLIF(l.ad_leads, 0), 2)     AS cost_per_lead,
    round(s.spend / NULLIF(l.ad_hot_leads, 0), 2) AS cost_per_hot_lead
  FROM s, l;
$$;

-- 2. Segment movement -- what the scoring engine actually did. Only
--    event_type='segment_changed' counts: 'score_updated' rows fire on every
--    inbound message and mostly leave the segment where it was, so counting
--    them would wildly overstate movement.
CREATE OR REPLACE FUNCTION public.analytics_segment_movement(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  from_segment text,
  to_segment text,
  total bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT from_segment, to_segment, count(*)
  FROM lead_stage_events
  WHERE tenant_id = p_tenant_id
    AND event_type = 'segment_changed'
    AND from_segment IS NOT NULL
    AND from_segment IS DISTINCT FROM to_segment
    AND created_at >= p_start
    AND created_at <  p_end
  GROUP BY 1, 2;
$$;

-- 3. First-response time. For every inbound message, how long until we
--    replied. Percentiles rather than a mean: one 3-hour outlier would drag
--    an average past the point of usefulness.
--    The LATERAL is deliberately unbounded on the right so a reply that
--    lands after the period end still counts against the message it answers.
CREATE OR REPLACE FUNCTION public.analytics_response_times(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  inbound_total bigint,
  answered bigint,
  p50_seconds numeric,
  p90_seconds numeric
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  WITH pairs AS (
    SELECT r.out_at, m.created_at AS in_at
    FROM messages m
    CROSS JOIN LATERAL (
      SELECT min(o.created_at) AS out_at
      FROM messages o
      WHERE o.lead_id = m.lead_id
        AND o.direction = 'outbound'
        AND o.created_at > m.created_at
    ) r
    WHERE m.tenant_id = p_tenant_id
      AND m.direction = 'inbound'
      AND m.lead_id IS NOT NULL
      AND m.created_at >= p_start
      AND m.created_at <  p_end
  )
  SELECT
    count(*)                                                                         AS inbound_total,
    count(out_at)                                                                    AS answered,
    round(percentile_cont(0.5) WITHIN GROUP (
      ORDER BY extract(epoch FROM (out_at - in_at)))::numeric, 1)                    AS p50_seconds,
    round(percentile_cont(0.9) WITHIN GROUP (
      ORDER BY extract(epoch FROM (out_at - in_at)))::numeric, 1)                    AS p90_seconds
  FROM pairs;
$$;

-- Serves the LATERAL above: "next outbound message for this lead after T".
-- Without it the planner scans messages once per inbound row -- measured at
-- 243ms on a 2k-row table, dropping to 18ms with the index, and the gap
-- widens quadratically as message volume grows.
CREATE INDEX IF NOT EXISTS idx_messages_lead_outbound_created
  ON public.messages (lead_id, created_at)
  WHERE direction = 'outbound';

REVOKE EXECUTE ON FUNCTION public.analytics_period_money(uuid, timestamptz, timestamptz)    FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_segment_movement(uuid, timestamptz, timestamptz) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_response_times(uuid, timestamptz, timestamptz)   FROM anon, authenticated;
