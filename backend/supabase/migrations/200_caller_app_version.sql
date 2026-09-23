-- Aira Sync app build (versionCode) each telecaller's phone last reported.
-- Nullable: phones on Aira Sync 1.1 and earlier don't send it.
ALTER TABLE callers
  ADD COLUMN IF NOT EXISTS app_version integer;
