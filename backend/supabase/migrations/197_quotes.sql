-- 197_quotes.sql
-- Quote-and-pay inside the WhatsApp thread that created the intent, instead
-- of a document that leaves the system (the DealConverter pattern this whole
-- build has been the opposite of). Extends the payment machinery the intake
-- flow already has (create_payment_link, the razorpay_webhook) to catalog
-- items instead of only intake packages.
--
-- items is a SNAPSHOT taken at send time -- {name, qty, price_paise} per
-- line -- and is never re-read live. A later catalog price edit must not
-- rewrite what this lead was actually quoted and may already have paid.

CREATE TABLE IF NOT EXISTS quotes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  lead_id uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  items jsonb NOT NULL,
  total_paise bigint NOT NULL CHECK (total_paise >= 0),
  status text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'paid', 'expired', 'cancelled')),
  payment_link text,
  razorpay_payment_link_id text,
  razorpay_payment_id text,
  sent_at timestamptz NOT NULL DEFAULT now(),
  paid_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_quotes_tenant_lead ON quotes (tenant_id, lead_id);
-- The webhook resolves tenant purely from notes.quote_id (see
-- get_quote_tenant_id in services/quotes.py) -- this is the lookup it runs
-- on every payment_link.paid delivery, so it needs its own index rather than
-- relying on the tenant_id+lead_id composite above.
CREATE INDEX IF NOT EXISTS idx_quotes_id_tenant ON quotes (id, tenant_id);

-- RLS: same posture as catalog_quotes/deals this session -- members read,
-- only the backend (service role) writes. No owner-write policy: lead_id
-- doesn't check tenancy on its own, so a directly-inserted row could point
-- at another tenant's lead.
ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS quotes_tenant_member_select ON quotes;
CREATE POLICY quotes_tenant_member_select ON quotes
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
