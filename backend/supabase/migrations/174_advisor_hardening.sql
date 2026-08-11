-- Fix mutable search_path on 4 functions flagged by Supabase security advisor
ALTER FUNCTION public.update_catalog_item_embedding(uuid, uuid, text) SET search_path = public, pg_temp;
ALTER FUNCTION public.match_catalog_items(text, uuid, integer) SET search_path = public, pg_temp;
ALTER FUNCTION public.get_conversation_leads(uuid, integer, integer, text) SET search_path = public, pg_temp;
ALTER FUNCTION public.template_performance_range(uuid, timestamptz, timestamptz) SET search_path = public, pg_temp;

-- Explicit deny-all policies for tables with RLS enabled but no policy (documents intent: service_role-only access, same pattern as rest of schema)
CREATE POLICY "expert_handoff_sessions_deny_all" ON public.expert_handoff_sessions FOR ALL TO anon, authenticated USING (false);
CREATE POLICY "meta_asset_claims_deny_all" ON public.meta_asset_claims FOR ALL TO anon, authenticated USING (false);
CREATE POLICY "platform_defaults_deny_all" ON public.platform_defaults FOR ALL TO anon, authenticated USING (false);
