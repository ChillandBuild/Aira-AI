-- 219_message_templates_variable_map.sql
-- Per-template choice of what fills each {{n}} when the escalation and hot-lead
-- WhatsApp alerts send it, e.g. {"1": "lead_phone", "2": "collected:course"}.
-- NULL = the alert's fixed order (name, phone, ...), so existing templates are
-- unchanged. Aira-only setting: never sent to Meta. Values are checked in the
-- API (app/services/template_fields.py), not here.
-- Apply BEFORE the backend deploy: the alert queries select this column.
-- (218 is taken by feat/private-send's 218_private_send.sql.)

ALTER TABLE message_templates ADD COLUMN IF NOT EXISTS variable_map jsonb;
