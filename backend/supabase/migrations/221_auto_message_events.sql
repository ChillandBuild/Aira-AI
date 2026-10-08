-- 221_auto_message_events.sql
-- Auto Messages v2: clients add their own events ("Kundli ready") next to the three
-- built-ins (interested / signed_up / purchased). Built-ins stay in code; only custom
-- events live here. Additive plus two dropped CHECKs. Safe to apply BEFORE the backend
-- that uses it is deployed (old code only ever writes the three built-in keys).
-- Live state when written (2026-10-07): 0 rules, 1 failed test send, so nothing is lost.

SET LOCAL lock_timeout = '5s';

-- ---------------------------------------------------------------- custom events
-- key = the code the client's app sends in "event" (never changes); label = what the owner sees.
CREATE TABLE IF NOT EXISTS auto_message_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  key         text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{1,39}$'),
  label       text NOT NULL CHECK (char_length(label) BETWEEN 1 AND 60),
  description text CHECK (description IS NULL OR char_length(description) <= 200),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key)
);

-- Same pattern as 215: writes come from the backend's service role only; members may read.
-- Same grant hygiene as 218 (private_send_keys): strip every table privilege from the API
-- roles first, then give back SELECT only, so a stray default grant can never let a tenant
-- member (or anon) insert, update or delete events straight through PostgREST. RLS still
-- scopes that SELECT to the member's own tenant.
ALTER TABLE auto_message_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auto_message_events_tenant_member_select ON auto_message_events;
CREATE POLICY auto_message_events_tenant_member_select ON auto_message_events
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));
REVOKE ALL ON auto_message_events FROM anon, authenticated;
GRANT SELECT ON auto_message_events TO authenticated;

-- ---------------------------------------------------------------- lift the 3-event lock
-- Rules may now use any custom key. The backend validates the key against the built-ins
-- and auto_message_events. The unique (tenant_id, event) index from 216 stays.
-- 215 declared the CHECK inline, so Postgres named it <table>_<column>_check.
ALTER TABLE auto_message_rules DROP CONSTRAINT IF EXISTS auto_message_rules_event_check;
-- auto_message_sends.event had no CHECK in 215 (old sends keep their key as plain text);
-- dropped here only in case one was added by hand.
ALTER TABLE auto_message_sends DROP CONSTRAINT IF EXISTS auto_message_sends_event_check;

-- ---------------------------------------------------------------- send-log index
-- Serves auto_message_sent_events() below and the status/event filters of the send log.
CREATE INDEX IF NOT EXISTS auto_message_sends_tenant_status_event_idx
  ON auto_message_sends (tenant_id, status, event);

-- ---------------------------------------------------------------- "has this event ever sent?"
-- One round trip for the rules list (the PostgREST row cap would hide events behind a busy one).
CREATE OR REPLACE FUNCTION auto_message_sent_events(p_tenant uuid)
RETURNS SETOF text
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT DISTINCT s.event FROM auto_message_sends s
   WHERE s.tenant_id = p_tenant AND s.status = 'sent';
$$;

REVOKE EXECUTE ON FUNCTION auto_message_sent_events(uuid) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION auto_message_sent_events(uuid) TO service_role;
