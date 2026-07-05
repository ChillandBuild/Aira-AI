-- Create public.pending_whatsapp_alerts table to support crash-proof delayed WhatsApp notifications
CREATE TABLE IF NOT EXISTS public.pending_whatsapp_alerts (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE NOT NULL,
    lead_id uuid REFERENCES public.leads(id) ON DELETE CASCADE NOT NULL,
    from_segment text,
    to_segment text NOT NULL,
    send_at timestamp with time zone NOT NULL,
    status text DEFAULT 'pending' NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.pending_whatsapp_alerts ENABLE ROW LEVEL SECURITY;

-- Define RLS policies
CREATE POLICY "Tenants can select their own pending alerts"
    ON public.pending_whatsapp_alerts FOR SELECT
    USING (tenant_id = (SELECT tenant_id FROM public.tenant_users WHERE user_id = auth.uid() LIMIT 1));

-- Define Indexes for fast lookup by status and send_at
CREATE INDEX IF NOT EXISTS idx_pending_wa_status_send_at ON public.pending_whatsapp_alerts (status, send_at);
CREATE INDEX IF NOT EXISTS idx_pending_wa_lead_status ON public.pending_whatsapp_alerts (lead_id, status);
