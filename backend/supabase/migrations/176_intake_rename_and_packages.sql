-- 176_intake_rename_and_packages.sql
-- Renames the Paid Expert Handoff feature to "Intake" and adds per-row
-- snapshots so later config edits never rewrite historical rows.

BEGIN;

ALTER TABLE expert_handoff_sessions RENAME TO intake_sessions;

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS field_schema jsonb,
  ADD COLUMN IF NOT EXISTS package_key text,
  ADD COLUMN IF NOT EXISTS package_name text,
  ADD COLUMN IF NOT EXISTS package_amount_paise integer;

-- The old CHECK travelled with the rename but still carries the old name and
-- lacks the new status.
ALTER TABLE intake_sessions
  DROP CONSTRAINT IF EXISTS expert_handoff_sessions_status_check;

ALTER TABLE intake_sessions
  ADD CONSTRAINT intake_sessions_status_check CHECK (status = ANY (ARRAY[
    'offer_pending'::text,
    'awaiting_package_choice'::text,
    'collecting'::text,
    'awaiting_confirmation'::text,
    'awaiting_payment'::text,
    'paid'::text,
    'resolved'::text,
    'cancelled'::text
  ]));

-- Keyset paging index: (tenant_id, created_at DESC, id DESC).
CREATE INDEX IF NOT EXISTS idx_intake_sessions_tenant_created
  ON intake_sessions (tenant_id, created_at DESC, id DESC);

UPDATE app_settings SET key = 'intake_config' WHERE key = 'expert_handoff_config';

-- Backfill field_schema from each tenant's current configured fields.
UPDATE intake_sessions s
SET field_schema = (a.value::jsonb -> 'fields')
FROM app_settings a
WHERE a.tenant_id = s.tenant_id
  AND a.key = 'intake_config'
  AND s.field_schema IS NULL
  AND (a.value::jsonb -> 'fields') IS NOT NULL;

-- Backfill the package snapshot from the old single-fee config.
UPDATE intake_sessions s
SET package_key = 'standard',
    package_name = 'Consultation',
    package_amount_paise = COALESCE(s.amount_paise, (a.value::jsonb ->> 'amount_paise')::int)
FROM app_settings a
WHERE a.tenant_id = s.tenant_id
  AND a.key = 'intake_config'
  AND s.package_key IS NULL;

COMMIT;
