-- 162: A Meta asset (Page, Instagram account, ad account, or catalog) may belong
-- to exactly one Aira tenant. The RPC claims the complete selected asset set in
-- one transaction so concurrent onboarding cannot split webhook ownership.
CREATE TABLE IF NOT EXISTS public.meta_asset_claims (
  asset_type text NOT NULL CHECK (asset_type IN ('facebook_page', 'instagram_account', 'ad_account', 'catalog')),
  asset_id text NOT NULL,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (asset_type, asset_id)
);

ALTER TABLE public.meta_asset_claims ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.meta_asset_claims FROM anon, authenticated;

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
       OR asset.asset_type NOT IN ('facebook_page', 'instagram_account', 'ad_account', 'catalog')
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
