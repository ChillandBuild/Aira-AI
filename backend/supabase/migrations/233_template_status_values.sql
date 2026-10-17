-- Template statuses Meta actually reports (2026-10-17).
--
-- message_template_status_update can also say DISABLED, ARCHIVED and DELETED
-- (PENDING_DELETION is stored as DELETED). The old check only allowed
-- PENDING/APPROVED/REJECTED/PAUSED, so those events were dropped and Anril kept
-- showing a template as usable after Meta had turned it off.
-- Only APPROVED templates are sent anywhere.
--
-- Widening only; safe to apply before the backend that writes the new values.

ALTER TABLE message_templates DROP CONSTRAINT IF EXISTS message_templates_status_check;

ALTER TABLE message_templates
  ADD CONSTRAINT message_templates_status_check
    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'PAUSED', 'DISABLED', 'ARCHIVED', 'DELETED'));
