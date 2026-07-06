alter table tenant_usage_counters drop constraint if exists tenant_usage_counters_metric_check;

alter table tenant_usage_counters add constraint tenant_usage_counters_metric_check
    check (metric in (
        'message_sent',
        'ai_reply',
        'call_minute',
        'team_seat_active',
        'storage_gb',
        'ai_call_summary',
        'ai_call_scoring',
        'phone_number',
        'ai_speech_to_text',
        'ai_text_to_speech'
    ));
