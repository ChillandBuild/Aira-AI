-- Advisor follow-up for migration 155:
-- 1. Cover the lead_id foreign key for fast lead deletion/cascade.
-- 2. Use one SELECT policy for tenant members and system admins.

CREATE INDEX IF NOT EXISTS idx_lead_meta_ad_attributions_lead
  ON public.lead_meta_ad_attributions (lead_id);

DROP POLICY IF EXISTS lead_meta_ad_attributions_tenant_read
  ON public.lead_meta_ad_attributions;
DROP POLICY IF EXISTS lead_meta_ad_attributions_admin_all
  ON public.lead_meta_ad_attributions;

CREATE POLICY lead_meta_ad_attributions_read
  ON public.lead_meta_ad_attributions
  FOR SELECT TO authenticated
  USING (
    public.is_tenant_member(tenant_id)
    OR public.is_system_admin()
  );
