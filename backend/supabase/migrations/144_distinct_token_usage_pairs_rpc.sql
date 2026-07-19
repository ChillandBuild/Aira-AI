-- 144: distinct (provider, model) pairs ever recorded in tenant_token_usage,
-- for the rate-management screen to know which models still need a rate.
-- A plain SELECT + Python set() would risk silent truncation on a large,
-- growing table (REST result caps); DISTINCT at the DB layer avoids that.
CREATE OR REPLACE FUNCTION public.distinct_token_usage_pairs()
RETURNS TABLE (provider text, model text)
LANGUAGE sql
SET search_path = public
AS $$
  SELECT DISTINCT provider, model FROM tenant_token_usage;
$$;

REVOKE EXECUTE ON FUNCTION public.distinct_token_usage_pairs() FROM anon, authenticated;
