-- 160: inbound-lead arrival heatmap for the Compare tab -- when leads
-- actually reach out, by IST day-of-week x hour. Same shape and dow
-- convention (0=Monday) as meta_ads_analytics.py's _build_heatmap, so the
-- two heatmaps read the same way if a user has seen both.
CREATE OR REPLACE FUNCTION public.analytics_lead_arrival_heatmap(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  dow int,
  hour int,
  total bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (extract(isodow FROM (created_at AT TIME ZONE 'Asia/Kolkata'))::int - 1) AS dow,
    extract(hour FROM (created_at AT TIME ZONE 'Asia/Kolkata'))::int        AS hour,
    count(*)                                                                AS total
  FROM leads
  WHERE tenant_id = p_tenant_id
    AND deleted_at IS NULL
    AND source IN ('whatsapp','instagram','facebook','telegram')
    AND created_at >= p_start
    AND created_at <  p_end
  GROUP BY 1, 2
  ORDER BY 1, 2;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_lead_arrival_heatmap(uuid, timestamptz, timestamptz) FROM anon, authenticated;
