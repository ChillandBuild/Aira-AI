ALTER TABLE callers
  ADD COLUMN IF NOT EXISTS shift_start_hour smallint,
  ADD COLUMN IF NOT EXISTS shift_end_hour smallint;
