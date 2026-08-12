-- Per-field ask tracking for the intake collector.
-- Without this the collector re-asks the same field forever when the lead cannot
-- answer it (live evidence 2026-08-12: "Thanks! And your time of birth?" was sent
-- three times to the same lead after they twice said they did not know it).
ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS ask_attempts   jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS skipped_fields jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN intake_sessions.ask_attempts IS
  'Per-field count of consecutive asks that produced no extractable value: {field_key: int}';
COMMENT ON COLUMN intake_sessions.skipped_fields IS
  'Field keys given up on after _MAX_FIELD_ATTEMPTS, shown as not-provided on the summary';
