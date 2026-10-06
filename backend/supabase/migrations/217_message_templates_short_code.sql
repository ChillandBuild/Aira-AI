-- 217_message_templates_short_code.sql
-- "Aira ID": a 6-digit code per WhatsApp template, unique within a tenant. A
-- partner app (AstroTamil's Django admin) stores this code instead of a Meta
-- template name and sends through POST /api/v1/intake/partner/send-template.
-- Assigned by a BEFORE INSERT trigger so every insert path (create, sync from
-- Meta, status webhook) gets one without Python changes. Additive only.

SET LOCAL lock_timeout = '5s';

ALTER TABLE message_templates ADD COLUMN IF NOT EXISTS short_code text;

CREATE OR REPLACE FUNCTION message_templates_new_short_code(p_tenant_id uuid)
RETURNS text
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  candidate text;
BEGIN
  -- Two concurrent inserts for one tenant could otherwise draw the same code
  -- and one would fail on the unique index.
  PERFORM pg_advisory_xact_lock(hashtext('message_templates_short_code:' || p_tenant_id::text));
  LOOP
    candidate := (100000 + floor(random() * 900000))::int::text;
    EXIT WHEN NOT EXISTS (
      SELECT 1 FROM message_templates
      WHERE tenant_id = p_tenant_id AND short_code = candidate
    );
  END LOOP;
  RETURN candidate;
END;
$$;

CREATE OR REPLACE FUNCTION message_templates_set_short_code()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
  IF NEW.short_code IS NULL THEN
    NEW.short_code := message_templates_new_short_code(NEW.tenant_id);
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS message_templates_short_code_trg ON message_templates;
CREATE TRIGGER message_templates_short_code_trg
  BEFORE INSERT ON message_templates
  FOR EACH ROW EXECUTE FUNCTION message_templates_set_short_code();

-- Row by row so each new code is visible to the uniqueness check of the next.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN SELECT id, tenant_id FROM message_templates WHERE short_code IS NULL LOOP
    UPDATE message_templates
    SET short_code = message_templates_new_short_code(r.tenant_id)
    WHERE id = r.id;
  END LOOP;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS message_templates_tenant_short_code_key
  ON message_templates (tenant_id, short_code);

ALTER TABLE message_templates ALTER COLUMN short_code SET NOT NULL;
