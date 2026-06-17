-- Call Scripts
CREATE TABLE IF NOT EXISTS call_scripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  name text NOT NULL,
  segment text CHECK (segment IN ('A', 'B', 'C', 'D')),
  steps jsonb NOT NULL DEFAULT '[]'::jsonb,
  is_default boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_call_scripts_tenant ON call_scripts(tenant_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'call_scripts_updated_at'
  ) THEN
    CREATE TRIGGER call_scripts_updated_at
      BEFORE UPDATE ON call_scripts
      FOR EACH ROW EXECUTE FUNCTION update_updated_at();
  END IF;
END $$;

-- Telecalling Upload Batches (upload history)
CREATE TABLE IF NOT EXISTS telecalling_upload_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  file_name text,
  total_contacts integer NOT NULL DEFAULT 0,
  inserted integer NOT NULL DEFAULT 0,
  duplicates integer NOT NULL DEFAULT 0,
  assigned integer NOT NULL DEFAULT 0,
  segment_override text CHECK (segment_override IN ('A', 'B', 'C', 'D')),
  assignment_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
  csv_storage_path text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_telecalling_upload_batches_tenant ON telecalling_upload_batches(tenant_id);
