-- 172: Claims made by claim_meta_assets had no release path, so a tenant could
-- never move a WhatsApp number or Page to another Aira workspace. Disconnect
-- calls this to free the assets it owns — and only the ones it owns.
CREATE OR REPLACE FUNCTION public.release_meta_assets(
  p_tenant_id uuid,
  p_assets jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
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
    RAISE EXCEPTION 'invalid Meta asset release' USING ERRCODE = '22023';
  END IF;

  -- The tenant_id predicate is the security property: a workspace can only ever
  -- release a claim it holds, even if it guesses another workspace's asset id.
  DELETE FROM public.meta_asset_claims claim
  USING jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
  WHERE claim.asset_type = asset.asset_type
    AND claim.asset_id = asset.asset_id
    AND claim.tenant_id = p_tenant_id;
END;
$$;

REVOKE ALL ON FUNCTION public.release_meta_assets(uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.release_meta_assets(uuid, jsonb) TO service_role;
