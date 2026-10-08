-- 222_partner_sends_log.sql
-- The partner door (POST /partner/send-template, used by apps such as AstroTamil) now writes
-- every send, sent or failed, into the Auto Messages send log so the owner sees it next to
-- website-form and API sends. Such a row has source 'partner', no lead, and an event only when
-- the app sent an event key (a template_code send has none).
-- Widens CHECKs and drops one NOT NULL: nothing existing can break. Safe to apply BEFORE the
-- backend that writes these rows is deployed (old code never writes 'partner' or a NULL event).
-- Idempotent: re-running changes nothing.

SET LOCAL lock_timeout = '5s';

-- 215 declared the CHECK inline on the column, so Postgres named it <table>_<column>_check.
-- 'store' stays allowed for the one historical shop-counter row.
ALTER TABLE auto_message_sends DROP CONSTRAINT IF EXISTS auto_message_sends_source_check;
ALTER TABLE auto_message_sends ADD CONSTRAINT auto_message_sends_source_check
  CHECK (source IN ('website', 'api', 'store', 'partner'));

-- 215 made event NOT NULL; a template_code send has no event. (Dropping NOT NULL twice is a no-op.)
ALTER TABLE auto_message_sends ALTER COLUMN event DROP NOT NULL;

-- lead_id was already nullable in 215 (REFERENCES leads ON DELETE SET NULL, no NOT NULL),
-- and partner sends never create a lead, so nothing to change there.

-- "Has this event ever sent?" (221): partner template_code sends have a NULL event, which
-- would otherwise come back as a NULL row. Same function, same grants, NULL events left out.
CREATE OR REPLACE FUNCTION auto_message_sent_events(p_tenant uuid)
RETURNS SETOF text
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT DISTINCT s.event FROM auto_message_sends s
   WHERE s.tenant_id = p_tenant AND s.status = 'sent' AND s.event IS NOT NULL;
$$;

REVOKE EXECUTE ON FUNCTION auto_message_sent_events(uuid) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION auto_message_sent_events(uuid) TO service_role;
