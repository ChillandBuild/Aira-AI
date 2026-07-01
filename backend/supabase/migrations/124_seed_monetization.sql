-- Migration 124: Seed feature_catalog and plans with pricing from Part 0

-- WhatsApp channels
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, sort_order) values
('whatsapp', 'WhatsApp', 'channels', 'messaging', 0, false, 1),
('instagram', 'Instagram', 'channels', 'messaging', 0, false, 2),
('facebook', 'Facebook', 'channels', 'messaging', 0, false, 3),
('telegram', 'Telegram', 'channels', 'messaging', 0, false, 4);

-- Messaging modules
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, sort_order) values
('broadcast', 'Broadcast Messaging', 'messaging', 'messaging', 0, false, 5),
('templates', 'Message Templates', 'messaging', 'messaging', 0, false, 6),
('template_sync', 'Template Sync', 'messaging', 'messaging', 0, false, 7),
('auto_reply', 'Auto Reply', 'messaging', 'messaging', 0, false, 8),
('re_engagement', 'Re-engagement', 'messaging', 'messaging', 0, false, 9),
('human_handover', 'Human Handover', 'messaging', 'messaging', 0, false, 10),
('media_upload', 'Media Upload', 'messaging', 'messaging', 0, false, 11),
('advanced_analytics', 'Advanced Analytics', 'messaging', 'messaging', 0, false, 12);

-- AI features
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, usage_metric, included_qty, sort_order) values
('ai_tier.off', 'AI Off', 'ai', 'shared', 0, false, null, 0, 20),
('ai_tier.basic', 'AI Basic', 'ai', 'shared', 500, true, 'ai_reply', 1000, 21),
('ai_tier.standard', 'AI Standard', 'ai', 'shared', 900, true, 'ai_reply', 2500, 22),
('ai_tier.premium', 'AI Premium', 'ai', 'shared', 1500, true, 'ai_reply', 12000, 23),
('ai_tier.byo', 'AI BYO Key', 'ai', 'shared', 999, false, null, 0, 24),
('kb_ai', 'Knowledge Base AI', 'ai', 'shared', 0, false, null, 0, 25),
('sentiment', 'Sentiment Analysis', 'ai', 'shared', 0, false, null, 0, 26),
('multi_language', 'Multi-language', 'ai', 'shared', 0, false, null, 0, 27),
('custom_prompt', 'Custom Prompt', 'ai', 'shared', 0, false, null, 0, 28);

-- Telecalling features
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, sort_order) values
('telecalling.dialer', 'Dialer', 'telecalling', 'telecalling', 0, false, 30),
('telecalling.scheduled', 'Scheduled Calls', 'telecalling', 'telecalling', 0, false, 31),
('telecalling.notes', 'Call Notes', 'telecalling', 'telecalling', 0, false, 32),
('telecalling.scripts', 'Call Scripts', 'telecalling', 'telecalling', 0, false, 33),
('telecalling.attendance', 'Attendance', 'telecalling', 'telecalling', 0, false, 34),
('telecalling.performance', 'Performance', 'telecalling', 'telecalling', 0, false, 35),
('telecalling.qa', 'QA', 'telecalling', 'telecalling', 0, false, 36),
('tc_recording', 'Call Recording', 'telecalling', 'telecalling', 0, false, 37),
('tc_recording.summary', 'AI Summary', 'telecalling', 'telecalling', 0, false, null, 0, 38),
('tc_recording.scoring', 'AI Scoring', 'telecalling', 'telecalling', 0, false, null, 0, 39);

-- Automation features
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, sort_order) values
('business_hours', 'Business Hours', 'automation', 'shared', 0, false, 50),
('escalation', 'Escalation', 'automation', 'shared', 0, false, 51),
('lead_assignment', 'Lead Assignment', 'automation', 'shared', 0, false, 52),
('callbacks', 'Callbacks', 'automation', 'shared', 0, false, 53),
('push_notifications', 'Push Notifications', 'automation', 'shared', 0, false, 54),
('dnc', 'Do Not Call', 'automation', 'shared', 0, false, 55),
('webhook_health', 'Webhook Health', 'automation', 'shared', 0, false, 56),
('token_expiry_alerts', 'Token Expiry Alerts', 'automation', 'shared', 0, false, 57);

-- Ops features
insert into feature_catalog (feature_key, display_name, category, pillar, monthly_price, is_metered, sort_order) values
('maintenance_mode', 'Maintenance Mode', 'ops', 'shared', 0, false, 70),
('read_only_mode', 'Read Only Mode', 'ops', 'shared', 0, false, 71),
('feature_freeze', 'Feature Freeze', 'ops', 'shared', 0, false, 72),
('sandbox_trial', 'Sandbox/Trial', 'ops', 'shared', 0, false, 73);

-- Messaging Plans (Pricing in INR)
-- Basic: ₹4,999/mo, 1 channel, 2 seats, 1,000 messages, 500 AI replies, AI Basic incl
insert into plans (name, pillar, tier, monthly_price, ai_tier, included) values
('Messaging Basic', 'messaging', 'basic', 4999, 'basic', '{"feature_keys":["broadcast","templates","auto_reply"],"quotas":{"messages":1000,"ai_replies":500,"seats":2}}'),

-- Standard: ₹14,999/mo, 3 channels, 5 seats, 5,000 messages, 2,500 AI replies, AI Standard incl
('Messaging Standard', 'messaging', 'standard', 14999, 'standard', '{"feature_keys":["broadcast","templates","auto_reply","re_engagement","human_handover"],"quotas":{"messages":5000,"ai_replies":2500,"seats":5}}'),

-- Pro: ₹39,999/mo, all channels, 15 seats, 25,000 messages, 12,000 AI replies, AI Premium incl
('Messaging Pro', 'messaging', 'pro', 39999, 'premium', '{"feature_keys":["broadcast","templates","auto_reply","re_engagement","human_handover","media_upload","advanced_analytics"],"quotas":{"messages":25000,"ai_replies":12000,"seats":15}}');

-- Telecalling Plans
-- Basic (SIM): ₹2,999/mo, SIM manual, 2 caller seats
insert into plans (name, pillar, tier, monthly_price, included) values
('Telecalling Basic', 'telecalling', 'basic', 2999, '{"feature_keys":["telecalling.dialer","telecalling.scheduled","telecalling.notes"],"quotas":{"caller_seats":2}}'),

-- Standard (SIM+): ₹9,999/mo, SIM + dialer, 5 caller seats
('Telecalling Standard', 'telecalling', 'standard', 9999, '{"feature_keys":["telecalling.dialer","telecalling.scheduled","telecalling.notes","telecalling.scripts","telecalling.attendance"],"quotas":{"caller_seats":5}}'),

-- Pro (TeleCMI): ₹19,999/mo, TeleCMI cloud, 5 caller seats, 1,000 min incl, recording/summary/score as add-on
('Telecalling Pro', 'telecalling', 'pro', 19999, '{"feature_keys":["telecalling.dialer","telecalling.scheduled","telecalling.notes","telecalling.scripts","telecalling.attendance","telecalling.performance","telecalling.qa"],"quotas":{"caller_seats":5,"call_minutes":1000}}');