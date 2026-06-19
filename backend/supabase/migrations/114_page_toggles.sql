-- Add page_toggles JSONB column to tenants for granular feature control
-- NULL means all pages are enabled (backward compatible)
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS page_toggles jsonb DEFAULT NULL;

COMMENT ON COLUMN tenants.page_toggles IS
  'JSON object controlling per-page visibility for this tenant. NULL = all enabled.';
