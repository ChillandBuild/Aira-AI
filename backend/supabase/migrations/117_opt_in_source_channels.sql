-- Expand opt_in_source CHECK to include inbound channel sources.
-- QA fix added opt_in_source to webhook lead inserts (whatsapp/instagram/facebook/telegram)
-- but the original constraint (migration 010) only allowed 6 values.
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
    'csv'
));
