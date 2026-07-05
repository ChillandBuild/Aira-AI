insert into app_settings (tenant_id, key, value, is_secret)
select id, 'ai_voice_reply_enabled', 'false', false
from tenants
on conflict (tenant_id, key) do nothing;
