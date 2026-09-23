-- 192_marketplace_lead_sources.sql
-- Adds 'indiamart' and 'justdial' as valid leads.source values, for the two
-- Indian B2B marketplace webhook connectors. Both providers push one enquiry
-- at a time to a URL the customer configures; the ingest route lives at
-- POST /api/v1/marketplace/{provider}/{ingest_token} (marketplace_intake.py).
--
-- A marketplace enquiry is a genuine inbound request from a real prospect,
-- same as a WhatsApp or web lead, so it also qualifies for opt_in_source --
-- without that, the broadcast-send gate (hard invariant: no null
-- opt_in_source) would silently exclude every marketplace lead from
-- broadcasts and reengagement.

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_source_check
  CHECK (source IN ('whatsapp', 'instagram', 'upload', 'manual', 'telegram', 'facebook', 'indiamart', 'justdial'));

-- Extends the existing list from 117_opt_in_source_channels.sql -- do not
-- shrink it back to the leads.source values, they are deliberately not the
-- same set (opt_in_source also covers click_to_wa_ad, website_form, etc).
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_opt_in_source_check;
ALTER TABLE leads ADD CONSTRAINT leads_opt_in_source_check CHECK (opt_in_source IN (
    'click_to_wa_ad',
    'website_form',
    'offline_event',
    'previous_enquiry',
    'imported',
    'manual',
    'whatsapp',
    'instagram',
    'facebook',
    'telegram',
    'csv',
    'indiamart',
    'justdial'
));
