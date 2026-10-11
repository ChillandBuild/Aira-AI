-- Removes the 4-argument get_conversation_leads (migrations 152/174). Since
-- migration 223 the API calls the 6-argument version, which also takes the inbox
-- folder and the caller. Nothing else calls the old one (checked code + every
-- public function body on 2026-10-12).
--
-- APPLY ONLY AFTER the backend that passes p_folder is live on Render: the API
-- before that commit still calls the 4-argument version.

DROP FUNCTION IF EXISTS public.get_conversation_leads(uuid, integer, integer, text);
