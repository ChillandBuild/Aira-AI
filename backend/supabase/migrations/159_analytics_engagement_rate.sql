-- 159: adds engagement_rate to analytics_period_summary -- the fraction of
-- leads created in the period that received at least one outbound reply.
-- Postgres does not allow CREATE OR REPLACE to change a function's return
-- type, so the old signature must be dropped first; this is the same
-- function body as migration 157 plus one new CTE and one new output column.
DROP FUNCTION IF EXISTS public.analytics_period_summary(uuid, timestamptz, timestamptz);

CREATE FUNCTION public.analytics_period_summary(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  new_leads bigint,
  inbound_leads bigint,
  outbound_leads bigint,
  hot bigint,
  warm bigint,
  cold bigint,
  disqualified bigint,
  avg_score numeric,
  messages_in bigint,
  messages_out bigint,
  ai_replies bigint,
  human_replies bigint,
  converted bigint,
  engagement_rate numeric
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  WITH l AS (
    SELECT
      count(*)                                                                        AS new_leads,
      count(*) FILTER (WHERE source IN ('whatsapp','instagram','facebook','telegram')) AS inbound_leads,
      count(*) FILTER (WHERE source IN ('upload','manual'))                            AS outbound_leads,
      count(*) FILTER (WHERE segment = 'A') AS hot,
      count(*) FILTER (WHERE segment = 'B') AS warm,
      count(*) FILTER (WHERE segment = 'C') AS cold,
      count(*) FILTER (WHERE segment = 'D') AS disqualified,
      round(avg(score)::numeric, 2)         AS avg_score
    FROM leads
    WHERE tenant_id = p_tenant_id
      AND deleted_at IS NULL
      AND created_at >= p_start
      AND created_at <  p_end
  ),
  m AS (
    SELECT
      count(*) FILTER (WHERE direction = 'inbound')                                  AS messages_in,
      count(*) FILTER (WHERE direction = 'outbound')                                 AS messages_out,
      count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS TRUE)     AS ai_replies,
      count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS NOT TRUE) AS human_replies
    FROM messages
    WHERE tenant_id = p_tenant_id
      AND created_at >= p_start
      AND created_at <  p_end
  ),
  c AS (
    SELECT count(*) AS converted
    FROM leads
    WHERE tenant_id = p_tenant_id
      AND deleted_at IS NULL
      AND converted_at IS NOT NULL
      AND converted_at >= p_start
      AND converted_at <  p_end
  ),
  e AS (
    -- Leads created in the period that got at least one outbound reply.
    -- Uses idx_messages_lead_outbound_created (migration 158), which already
    -- covers (lead_id, created_at) WHERE direction = 'outbound'.
    SELECT count(*) AS engaged_leads
    FROM leads lead2
    WHERE lead2.tenant_id = p_tenant_id
      AND lead2.deleted_at IS NULL
      AND lead2.created_at >= p_start
      AND lead2.created_at <  p_end
      AND EXISTS (
        SELECT 1 FROM messages msg
        WHERE msg.lead_id = lead2.id AND msg.direction = 'outbound'
      )
  )
  SELECT
    l.new_leads, l.inbound_leads, l.outbound_leads,
    l.hot, l.warm, l.cold, l.disqualified, l.avg_score,
    m.messages_in, m.messages_out, m.ai_replies, m.human_replies,
    c.converted,
    round(e.engaged_leads::numeric / NULLIF(l.new_leads, 0) * 100) AS engagement_rate
  FROM l, m, c, e;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_period_summary(uuid, timestamptz, timestamptz) FROM anon, authenticated;
