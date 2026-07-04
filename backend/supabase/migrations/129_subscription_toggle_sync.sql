-- 129_subscription_toggle_sync.sql
-- Update inbound_messaging depends_on: instagram, facebook, telegram, inbound_leads, push_notifications, callbacks, dnc, webhook_health, token_expiry_alerts
UPDATE feature_catalog
SET depends_on = ARRAY['instagram', 'facebook', 'telegram', 'inbound_leads', 'push_notifications', 'callbacks', 'dnc', 'webhook_health', 'token_expiry_alerts']
WHERE feature_key = 'inbound_messaging';

-- Update outbound_messaging depends_on: whatsapp, broadcast, templates, auto_reply, human_handover, outbound_leads, push_notifications, callbacks, dnc, webhook_health, token_expiry_alerts
UPDATE feature_catalog
SET depends_on = ARRAY['whatsapp', 'broadcast', 'templates', 'auto_reply', 'human_handover', 'outbound_leads', 'push_notifications', 'callbacks', 'dnc', 'webhook_health', 'token_expiry_alerts']
WHERE feature_key = 'outbound_messaging';

-- Update telecalling_sim depends_on: telecalling.dialer, telecalling.scheduled, telecalling.notes, telecalling
UPDATE feature_catalog
SET depends_on = ARRAY['telecalling.dialer', 'telecalling.scheduled', 'telecalling.notes', 'telecalling']
WHERE feature_key = 'telecalling_sim';

-- Update telecalling_telecmi depends_on: telecalling.dialer, telecalling.scheduled, telecalling.notes, telecalling.scripts, telecalling.attendance, telecalling.performance, telecalling.qa, tc_recording, telecalling
UPDATE feature_catalog
SET depends_on = ARRAY['telecalling.dialer', 'telecalling.scheduled', 'telecalling.notes', 'telecalling.scripts', 'telecalling.attendance', 'telecalling.performance', 'telecalling.qa', 'tc_recording', 'telecalling']
WHERE feature_key = 'telecalling_telecmi';

-- Delete notifications reference from tenant_subscription_items
DELETE FROM tenant_subscription_items WHERE feature_key = 'notifications';

-- Delete notifications row from feature_catalog
DELETE FROM feature_catalog WHERE feature_key = 'notifications';
