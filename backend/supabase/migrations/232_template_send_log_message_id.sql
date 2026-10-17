-- Un-count templates that never arrived (2026-10-17).
--
-- Meta's limit counts messages *delivered* to unique people. When Meta's
-- status webhook reports a template as failed, its template_send_log row is
-- deleted, matched by the Meta message id stored here.
--
-- Additive. Apply BEFORE deploying the backend that writes it.

ALTER TABLE public.template_send_log
  ADD COLUMN IF NOT EXISTS meta_message_id text;

CREATE INDEX IF NOT EXISTS template_send_log_meta_message_id
  ON public.template_send_log (meta_message_id)
  WHERE meta_message_id IS NOT NULL;
