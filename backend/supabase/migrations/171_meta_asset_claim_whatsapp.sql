-- 171: Extend the Meta asset-ownership registry for unified WhatsApp signup.
-- Migration 162 is already deployed, so this is deliberately a forward change.
ALTER TABLE public.meta_asset_claims
  DROP CONSTRAINT IF EXISTS meta_asset_claims_asset_type_check;

ALTER TABLE public.meta_asset_claims
  ADD CONSTRAINT meta_asset_claims_asset_type_check
  CHECK (asset_type IN (
    'facebook_page',
    'instagram_account',
    'ad_account',
    'catalog',
    'whatsapp_business_account',
    'whatsapp_phone_number'
  ));

CREATE OR REPLACE FUNCTION public.claim_meta_assets(
  p_tenant_id uuid,
  p_assets jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  has_conflict boolean;
BEGIN
  IF jsonb_typeof(p_assets) <> 'array' THEN
    RAISE EXCEPTION 'assets must be an array' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
    WHERE asset.asset_type IS NULL
       OR asset.asset_type NOT IN (
         'facebook_page', 'instagram_account', 'ad_account', 'catalog',
         'whatsapp_business_account', 'whatsapp_phone_number'
       )
       OR asset.asset_id IS NULL
       OR length(trim(asset.asset_id)) = 0
  ) THEN
    RAISE EXCEPTION 'invalid Meta asset claim' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.meta_asset_claims (asset_type, asset_id, tenant_id)
  SELECT DISTINCT asset.asset_type, asset.asset_id, p_tenant_id
  FROM jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
  ORDER BY asset.asset_type, asset.asset_id
  ON CONFLICT (asset_type, asset_id) DO NOTHING;

  SELECT EXISTS (
    SELECT 1
    FROM public.meta_asset_claims claim
    JOIN jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
      ON claim.asset_type = asset.asset_type AND claim.asset_id = asset.asset_id
    WHERE claim.tenant_id <> p_tenant_id
  ) INTO has_conflict;

  IF has_conflict THEN
    RAISE EXCEPTION 'Meta asset is already connected to another tenant' USING ERRCODE = '23505';
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_meta_assets(uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_meta_assets(uuid, jsonb) TO service_role;

-- Claim legacy Meta assets only when a value belongs to exactly one workspace.
-- Ambiguous legacy rows are intentionally left unclaimed for manual resolution.
INSERT INTO public.meta_asset_claims (asset_type, asset_id, tenant_id)
SELECT 'whatsapp_business_account', value, (array_agg(tenant_id ORDER BY tenant_id))[1]
FROM public.app_settings
WHERE key = 'meta_waba_id' AND nullif(trim(value), '') IS NOT NULL
GROUP BY value
HAVING count(DISTINCT tenant_id) = 1
ON CONFLICT (asset_type, asset_id) DO NOTHING;

INSERT INTO public.meta_asset_claims (asset_type, asset_id, tenant_id)
SELECT 'whatsapp_phone_number', value, (array_agg(tenant_id ORDER BY tenant_id))[1]
FROM public.app_settings
WHERE key = 'meta_phone_number_id' AND nullif(trim(value), '') IS NOT NULL
GROUP BY value
HAVING count(DISTINCT tenant_id) = 1
ON CONFLICT (asset_type, asset_id) DO NOTHING;
