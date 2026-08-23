-- 182: Daily count of RETURNING leads that came back through an ad.
--
-- The dashboard's "New Leads Today" only ever counted leads by created_at, so
-- a lead from three months ago who clicks a fresh ad today was invisible --
-- the ad spend that produced that conversation showed up nowhere. This splits
-- the card into Fresh (created today) + Returned (older lead, ad-tagged
-- message today).
--
-- Counted per (day, lead), not per message: six clicks on the same ad in one
-- day is one returning lead, not six. A returning lead does count again on a
-- later day, because that is a separate ad win.
--
-- Aggregated in SQL for the same reason as 146/157: PostgREST silently caps
-- raw row fetches at 1000 and returns no error, which has already
-- under-reported this endpoint's message counts once.
--
-- messages.via_ad_referral (migration 150) is the ad signal. It is stamped at
-- webhook time on every inbound message, existing leads included -- not only
-- on lead creation -- which is what makes "old lead, new ad click" detectable.
CREATE OR REPLACE FUNCTION public.analytics_daily_returning_ad_leads(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz,
  p_timezone text DEFAULT 'Asia/Kolkata'
)
RETURNS TABLE (
  day date,
  returning_leads bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (m.created_at AT TIME ZONE p_timezone)::date AS day,
    count(DISTINCT m.lead_id)                    AS returning_leads
  FROM messages m
  JOIN leads l
    ON l.id = m.lead_id
   AND l.tenant_id = m.tenant_id
  WHERE m.tenant_id = p_tenant_id
    AND m.lead_id IS NOT NULL
    AND m.direction = 'inbound'
    AND m.via_ad_referral IS TRUE
    AND m.created_at >= p_start
    AND m.created_at <  p_end
    AND l.deleted_at IS NULL
    -- "Returning" means the lead existed before the day they clicked. A lead
    -- created today via an ad is Fresh and is already counted there; without
    -- this they would be counted in both halves and the card would not add up.
    AND (l.created_at AT TIME ZONE p_timezone)::date
      < (m.created_at AT TIME ZONE p_timezone)::date
  GROUP BY 1
  ORDER BY 1;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_daily_returning_ad_leads(uuid, timestamptz, timestamptz, text) FROM anon, authenticated;
