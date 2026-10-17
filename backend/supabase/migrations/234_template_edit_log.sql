-- Meta's edit limit for approved templates (2026-10-17).
--
-- Meta: "Approved templates can be edited up to 10 times in a 30-day window,
-- or 1 time in a 24-hour window." (Rejected/paused: unlimited.) One row per
-- edit of an APPROVED template -- made in Anril, or reported by Meta's
-- message_template_components_update webhook (edits in WhatsApp Manager count
-- toward Meta's limit too). Anril blocks the Edit button once a limit is hit.
-- Backend-only (service role): RLS on, no policies.
--
-- Additive. Apply BEFORE deploying the backend that reads/writes it.

CREATE TABLE IF NOT EXISTS public.template_edit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  template_id uuid NOT NULL REFERENCES message_templates(id) ON DELETE CASCADE,
  edited_at timestamptz NOT NULL DEFAULT now(),
  source text NOT NULL CHECK (source IN ('anril', 'meta_webhook'))
);

CREATE INDEX IF NOT EXISTS template_edit_log_template_edited_at
  ON public.template_edit_log (template_id, edited_at);

ALTER TABLE public.template_edit_log ENABLE ROW LEVEL SECURITY;
