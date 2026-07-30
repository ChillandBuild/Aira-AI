-- 153: IST-bucketed daily aggregates for the analytics comparison feature.
-- Aggregating in SQL (one row per day) instead of selecting raw rows into
-- Python is mandatory here: PostgREST caps result sets at 1000 rows and
-- returns no error, which was silently truncating the messages chart
-- (1250 rows in a 7-day window, 2143 in 30 days). Same reasoning as 146.
-- All day bucketing is Asia/Kolkata to match the telecalling endpoint.

-- p_channel is NULL for "all channels". It exists here (not only on
-- analytics_reply_sources) because /messaging supports a channel filter and
-- the daily series must honour it, not silently return every channel.
--
-- p_timezone lets /overview keep its existing UTC day keys (its response shape
-- is consumed by the dashboard home and operator console, so it must not
-- shift) while /compare buckets by IST. New surfaces should use the default.
CREATE OR REPLACE FUNCTION public.analytics_daily_messages(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz,
  p_channel text DEFAULT NULL,
  p_timezone text DEFAULT 'Asia/Kolkata'
)
RETURNS TABLE (
  day date,
  inbound bigint,
  outbound bigint,
  ai bigint,
  human bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (created_at AT TIME ZONE p_timezone)::date AS day,
    count(*) FILTER (WHERE direction = 'inbound')                                   AS inbound,
    count(*) FILTER (WHERE direction = 'outbound')                                  AS outbound,
    count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS TRUE)      AS ai,
    count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS NOT TRUE)  AS human
  FROM messages
  WHERE tenant_id = p_tenant_id
    AND created_at >= p_start
    AND created_at <  p_end
    AND (p_channel IS NULL OR channel = p_channel)
  GROUP BY 1
  ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.analytics_daily_leads(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  day date,
  inbound bigint,
  outbound bigint,
  hot bigint,
  warm bigint,
  cold bigint,
  disqualified bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (created_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
    count(*) FILTER (WHERE source IN ('whatsapp','instagram','facebook','telegram')) AS inbound,
    count(*) FILTER (WHERE source IN ('upload','manual'))                            AS outbound,
    count(*) FILTER (WHERE segment = 'A') AS hot,
    count(*) FILTER (WHERE segment = 'B') AS warm,
    count(*) FILTER (WHERE segment = 'C') AS cold,
    count(*) FILTER (WHERE segment = 'D') AS disqualified
  FROM leads
  WHERE tenant_id = p_tenant_id
    AND deleted_at IS NULL
    AND created_at >= p_start
    AND created_at <  p_end
  GROUP BY 1
  ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.analytics_period_summary(
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
  converted bigint
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
  )
  SELECT
    l.new_leads, l.inbound_leads, l.outbound_leads,
    l.hot, l.warm, l.cold, l.disqualified, l.avg_score,
    m.messages_in, m.messages_out, m.ai_replies, m.human_replies,
    c.converted
  FROM l, m, c;
$$;

-- Reply-source split for /messaging. Aggregated here rather than pulling rows
-- because the raw fetch was hitting the same 1000-row cap, and because the
-- Python bucketing was silently discarding 'reengagement' (365 messages, 29%
-- of outbound) by matching no branch.
CREATE OR REPLACE FUNCTION public.analytics_reply_sources(
  p_tenant_id uuid, p_start timestamptz, p_end timestamptz, p_channel text DEFAULT NULL
)
RETURNS TABLE (reply_source text, is_ai_generated boolean, total bigint)
LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT reply_source, is_ai_generated, count(*)
  FROM messages
  WHERE tenant_id = p_tenant_id
    AND direction = 'outbound'
    AND created_at >= p_start AND created_at < p_end
    AND (p_channel IS NULL OR channel = p_channel)
  GROUP BY 1, 2;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_daily_messages(uuid, timestamptz, timestamptz, text, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_reply_sources(uuid, timestamptz, timestamptz, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_daily_leads(uuid, timestamptz, timestamptz)    FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_period_summary(uuid, timestamptz, timestamptz) FROM anon, authenticated;
