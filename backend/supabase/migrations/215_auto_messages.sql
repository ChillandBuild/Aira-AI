-- 215_auto_messages.sql
-- Auto-Messages (docs/designs/auto-messages.md): a customer's number + an event
-- (interested / signed_up / purchased) + a product arrives from a website form,
-- an API call or the shop counter, and the matching approved template is sent,
-- once, optionally after a delay. Additive only.

SET LOCAL lock_timeout = '5s';

-- ---------------------------------------------------------------- sources
-- website = copy-paste form, api = app/billing webhook, store = shop counter quick-add.
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_source_check CHECK (source = ANY (ARRAY[
  'whatsapp','instagram','upload','manual','telegram','facebook','indiamart','justdial',
  'website','api','store'
]));
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_opt_in_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_opt_in_source_check CHECK (opt_in_source = ANY (ARRAY[
  'click_to_wa_ad','website_form','offline_event','previous_enquiry','imported','manual',
  'whatsapp','instagram','facebook','telegram','csv','indiamart','justdial','api'
]));

-- ---------------------------------------------------------------- product aliases
-- Other spellings that should match this product ("konarc s", "ather konarc").
ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS aliases text[] NOT NULL DEFAULT '{}';

-- ---------------------------------------------------------------- rules
-- catalog_item_id NULL = the default rule for the event (any / unmatched product).
-- variables: one entry per template {{n}}, in order:
--   {"source": "first_name|full_name|product|price|product_url|phone|extra|text",
--    "key": "<extra field name, for source=extra>", "value": "<fixed text, for source=text>",
--    "fallback": "<used when the source is empty>"}
-- button_param: same shape, fills the {{1}} suffix of a dynamic URL button.
CREATE TABLE IF NOT EXISTS auto_message_rules (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  event           text NOT NULL CHECK (event IN ('interested', 'signed_up', 'purchased')),
  catalog_item_id uuid REFERENCES catalog_items(id) ON DELETE CASCADE,
  template_id     uuid NOT NULL REFERENCES message_templates(id) ON DELETE CASCADE,
  delay_minutes   integer NOT NULL DEFAULT 0 CHECK (delay_minutes >= 0 AND delay_minutes <= 10080),
  variables       jsonb NOT NULL DEFAULT '[]'::jsonb,
  button_param    jsonb,
  enabled         boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS auto_message_rules_one_per_product
  ON auto_message_rules (tenant_id, event, COALESCE(catalog_item_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- ---------------------------------------------------------------- send log + queue
CREATE TABLE IF NOT EXISTS auto_message_sends (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  lead_id         uuid REFERENCES leads(id) ON DELETE SET NULL,
  phone           text NOT NULL,
  name            text,
  event           text NOT NULL,
  source          text NOT NULL CHECK (source IN ('website', 'api', 'store')),
  product_raw     text,
  catalog_item_id uuid REFERENCES catalog_items(id) ON DELETE SET NULL,
  rule_id         uuid REFERENCES auto_message_rules(id) ON DELETE SET NULL,
  template_id     uuid REFERENCES message_templates(id) ON DELETE SET NULL,
  extra           jsonb NOT NULL DEFAULT '{}'::jsonb,
  status          text NOT NULL CHECK (status IN ('queued', 'sending', 'sent', 'failed', 'skipped')),
  reason          text,
  send_at         timestamptz NOT NULL DEFAULT now(),
  sent_at         timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auto_message_sends_due_idx
  ON auto_message_sends (send_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS auto_message_sends_tenant_recent_idx
  ON auto_message_sends (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS auto_message_sends_dedup_idx
  ON auto_message_sends (tenant_id, phone, event, created_at DESC);

-- ---------------------------------------------------------------- RLS
-- Writes come from the backend's service role only; members may read their own rows.
ALTER TABLE auto_message_rules ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auto_message_rules_tenant_member_select ON auto_message_rules;
CREATE POLICY auto_message_rules_tenant_member_select ON auto_message_rules
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));

ALTER TABLE auto_message_sends ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auto_message_sends_tenant_member_select ON auto_message_sends;
CREATE POLICY auto_message_sends_tenant_member_select ON auto_message_sends
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));
