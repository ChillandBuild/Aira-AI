-- Scope cached WhatsApp templates to the connected Meta WhatsApp Business Account.
-- Without this, changing meta_waba_id leaves templates from the previous WABA
-- visible because message_templates is only tenant-scoped.

ALTER TABLE message_templates
  ADD COLUMN IF NOT EXISTS meta_waba_id TEXT;

CREATE INDEX IF NOT EXISTS idx_message_templates_tenant_waba
  ON message_templates (tenant_id, meta_waba_id);
