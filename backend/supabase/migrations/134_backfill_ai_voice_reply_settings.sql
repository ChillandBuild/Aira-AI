insert into app_settings (tenant_id, key, value, is_secret)
select t.id, defaults.key, defaults.value, false
from tenants t
cross join (
    values
        ('ai_voice_reply_speaker', 'shubh'),
        ('ai_voice_reply_pace', '1.0'),
        ('ai_voice_reply_language_mode', 'auto'),
        ('ai_voice_reply_language_code', 'en-IN')
) as defaults(key, value)
on conflict (tenant_id, key) do nothing;
