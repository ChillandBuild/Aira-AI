-- 161: the stalest segment-A (hot) leads, for an actionable "reply to these
-- now" list on the Overview tab. A lead with no outbound message at all
-- (o.last_outbound_at IS NULL) is treated as maximally stale and sorts
-- first via NULLS FIRST.
CREATE OR REPLACE FUNCTION public.analytics_stale_hot_leads(
  p_tenant_id uuid,
  p_min_hours int,
  p_limit int DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  name text,
  phone text,
  score numeric,
  created_at timestamptz,
  last_outbound_at timestamptz
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT l.id, l.name, l.phone, l.score, l.created_at, o.last_outbound_at
  FROM leads l
  LEFT JOIN LATERAL (
    SELECT max(m.created_at) AS last_outbound_at
    FROM messages m
    WHERE m.lead_id = l.id AND m.direction = 'outbound'
  ) o ON true
  WHERE l.tenant_id = p_tenant_id
    AND l.deleted_at IS NULL
    AND l.segment = 'A'
    AND (o.last_outbound_at IS NULL OR o.last_outbound_at < now() - make_interval(hours => p_min_hours))
  ORDER BY o.last_outbound_at ASC NULLS FIRST
  LIMIT p_limit;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_stale_hot_leads(uuid, int, int) FROM anon, authenticated;
