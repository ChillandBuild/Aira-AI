-- Extend pending_whatsapp_alerts to carry escalation alerts alongside
-- segment-change alerts. One queue, one scheduler job, one incident path.

ALTER TABLE public.pending_whatsapp_alerts
    ADD COLUMN IF NOT EXISTS alert_type text NOT NULL DEFAULT 'segment_change',
    ADD COLUMN IF NOT EXISTS handover_id uuid REFERENCES public.chat_handovers(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS assigned_to_at_queue uuid,
    ADD COLUMN IF NOT EXISTS escalation_reason text;

-- Escalation rows have no segment transition, so to_segment can no longer be
-- mandatory. Existing rows are unaffected.
ALTER TABLE public.pending_whatsapp_alerts
    ALTER COLUMN to_segment DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pending_wa_alert_type_check'
    ) THEN
        ALTER TABLE public.pending_whatsapp_alerts
            ADD CONSTRAINT pending_wa_alert_type_check
            CHECK (alert_type IN ('segment_change', 'escalation'));
    END IF;

    -- A segment_change row must carry a segment; an escalation row must carry
    -- a handover. Guards against half-populated rows from a future code path.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pending_wa_shape_check'
    ) THEN
        ALTER TABLE public.pending_whatsapp_alerts
            ADD CONSTRAINT pending_wa_shape_check
            CHECK (
                (alert_type = 'segment_change' AND to_segment IS NOT NULL)
                OR (alert_type = 'escalation' AND handover_id IS NOT NULL)
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_pending_wa_handover
    ON public.pending_whatsapp_alerts (handover_id)
    WHERE handover_id IS NOT NULL;
