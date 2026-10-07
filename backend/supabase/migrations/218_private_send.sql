-- 218_private_send.sql
-- Private Send: the client's own server runs an Aira plug-in that downloads signed
-- rules + templates from Aira and sends the WhatsApp templates to Meta itself, so
-- Aira never sees a lead's name or number. Aira holds the license keys and counts
-- usage for billing. Contract: sdk/spec/CONTRACT.md. Additive only.
-- NOTE: no table below has a phone / name column, on purpose.

SET LOCAL lock_timeout = '5s';

-- ---------------------------------------------------------------- license keys
-- Only the sha256 of the full key is stored; key_prefix (first 13 chars) is for display.
CREATE TABLE IF NOT EXISTS private_send_keys (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  key_prefix     text NOT NULL,
  key_hash       text NOT NULL UNIQUE,
  status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  revoked_at     timestamptz,
  last_seen_at   timestamptz,
  plugin_version text
);
CREATE INDEX IF NOT EXISTS private_send_keys_tenant_idx ON private_send_keys (tenant_id);

-- ---------------------------------------------------------------- reported usage
-- Cumulative totals per (day, event, template) as reported by the plug-in. A row only
-- ever grows (record_private_send_usage keeps the GREATEST), so resending is safe and a
-- plug-in reinstall (counters back to 0) can't be metered twice.
CREATE TABLE IF NOT EXISTS private_send_usage (
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  day             date NOT NULL,
  event           text NOT NULL,
  template_id     uuid NOT NULL,
  reported_sent   integer NOT NULL DEFAULT 0 CHECK (reported_sent >= 0),
  reported_failed integer NOT NULL DEFAULT 0 CHECK (reported_failed >= 0),
  meta_volume     integer,  -- reserved; Meta's daily count is in private_send_meta_daily
  updated_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, day, event, template_id)
);
CREATE INDEX IF NOT EXISTS private_send_usage_tenant_day_idx ON private_send_usage (tenant_id, day DESC);

-- ---------------------------------------------------------------- Meta's own count
-- Meta's pricing_analytics volume is per day for the whole WABA (not per event or
-- template), so it lives here. aira_sent = outbound messages Aira itself sent that
-- day; volume - aira_sent is what the client's plug-in sent.
CREATE TABLE IF NOT EXISTS private_send_meta_daily (
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  day        date NOT NULL,
  volume     integer NOT NULL DEFAULT 0,
  aira_sent  integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, day)
);

-- ---------------------------------------------------------------- RLS + grants
-- Everything is read and written by the backend's service role only (the tenant API
-- route enforces settings.view itself). No tenant member or anon client may touch these
-- tables through PostgREST: the key table holds credential hashes and the usage tables
-- are billing evidence.
ALTER TABLE private_send_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE private_send_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE private_send_meta_daily ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS private_send_usage_tenant_member_select ON private_send_usage;
DROP POLICY IF EXISTS private_send_meta_daily_tenant_member_select ON private_send_meta_daily;

REVOKE ALL ON private_send_keys FROM anon, authenticated;
REVOKE ALL ON private_send_usage FROM anon, authenticated;
REVOKE ALL ON private_send_meta_daily FROM anon, authenticated;

-- ---------------------------------------------------------------- atomic usage upsert
-- Called by the backend for every POST /usage. p_rows is a jsonb array of
-- {day, event, template_id, sent, failed} cumulative totals. Each row is upserted with
-- GREATEST(existing, new) and the function returns the total growth in reported_sent
-- (the only part that may be billed). Row locks make two concurrent calls serialise, so
-- the same messages can't be counted twice. Rows are processed in key order so two
-- callers can't deadlock. Plain invoker-rights function: it runs as the service role.
CREATE OR REPLACE FUNCTION record_private_send_usage(p_tenant uuid, p_rows jsonb)
RETURNS integer
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  v_row     record;
  v_old     integer;
  v_new     integer;
  v_total   integer := 0;
BEGIN
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'p_rows must be a jsonb array';
  END IF;

  FOR v_row IN
    SELECT (r->>'day')::date            AS day,
           r->>'event'                  AS event,
           (r->>'template_id')::uuid    AS template_id,
           max((r->>'sent')::integer)   AS sent,
           max((r->>'failed')::integer) AS failed
      FROM jsonb_array_elements(p_rows) AS r
     GROUP BY 1, 2, 3
     ORDER BY 1, 2, 3
  LOOP
    INSERT INTO private_send_usage AS u (tenant_id, day, event, template_id, reported_sent, reported_failed, updated_at)
    VALUES (p_tenant, v_row.day, v_row.event, v_row.template_id, v_row.sent, v_row.failed, now())
    ON CONFLICT (tenant_id, day, event, template_id) DO NOTHING;

    IF FOUND THEN
      v_total := v_total + v_row.sent;  -- brand new row: everything reported is growth
      CONTINUE;
    END IF;

    -- Row already exists (possibly inserted by a concurrent call a moment ago): lock it,
    -- read the latest committed value, and only ever raise it.
    SELECT u.reported_sent INTO v_old
      FROM private_send_usage u
     WHERE u.tenant_id = p_tenant AND u.day = v_row.day
       AND u.event = v_row.event AND u.template_id = v_row.template_id
       FOR UPDATE;

    v_new := GREATEST(v_old, v_row.sent);
    UPDATE private_send_usage u
       SET reported_sent   = v_new,
           reported_failed = GREATEST(u.reported_failed, v_row.failed),
           updated_at      = now()
     WHERE u.tenant_id = p_tenant AND u.day = v_row.day
       AND u.event = v_row.event AND u.template_id = v_row.template_id;

    v_total := v_total + (v_new - v_old);
  END LOOP;

  RETURN v_total;
END;
$$;

REVOKE EXECUTE ON FUNCTION record_private_send_usage(uuid, jsonb) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION record_private_send_usage(uuid, jsonb) TO service_role;

-- ---------------------------------------------------------------- billing metric
-- Same list as 133_voice_usage_metrics.sql plus 'private_send_message'.
ALTER TABLE tenant_usage_counters DROP CONSTRAINT IF EXISTS tenant_usage_counters_metric_check;
ALTER TABLE tenant_usage_counters ADD CONSTRAINT tenant_usage_counters_metric_check
  CHECK (metric IN (
    'message_sent', 'ai_reply', 'call_minute', 'team_seat_active', 'storage_gb',
    'ai_call_summary', 'ai_call_scoring', 'phone_number',
    'ai_speech_to_text', 'ai_text_to_speech',
    'private_send_message'
  ));

-- ---------------------------------------------------------------- sellable feature
-- Price is set per client by the operator (starts at 0); usage is metered per message.
INSERT INTO feature_catalog (feature_key, display_name, category, pillar, monthly_price, usage_metric, unit_price, included_qty, depends_on, is_metered, sort_order)
VALUES ('private_send', 'Private Send (WhatsApp from your own server)', 'messaging', 'messaging', 0, 'private_send_message', 0, 0, '{whatsapp,templates}', true, 108)
ON CONFLICT (feature_key) DO NOTHING;
