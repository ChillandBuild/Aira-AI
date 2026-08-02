create or replace function template_performance_range(
    p_tenant_id uuid,
    p_start timestamptz,
    p_end timestamptz
)
returns table (
    template_name text,
    broadcasts    bigint,
    sent          bigint,
    read          bigint,
    replied       bigint,
    hot_leads     bigint,
    last_sent     timestamptz
)
language sql
stable
as $$
    with sb as (
        select id, template_name,
               coalesce(executed_at, fire_at, created_at) as sent_at
        from scheduled_broadcasts
        where tenant_id = p_tenant_id
          and template_name is not null
          and coalesce(executed_at, fire_at, created_at) >= p_start
          and coalesce(executed_at, fire_at, created_at) < p_end
    ),
    recip as (
        select sb.template_name,
               count(*) filter (where br.send_status = 'sent') as sent,
               count(*) filter (where br.reply_sentiment is not null) as replied
        from sb
        join broadcast_recipients br on br.broadcast_id = sb.id
        group by sb.template_name
    ),
    reads as (
        select sb.template_name, count(distinct br.id) as read
        from sb
        join broadcast_recipients br on br.broadcast_id = sb.id
        join messages m on m.meta_message_id = br.meta_message_id
                       and m.delivery_status = 'read'
        group by sb.template_name
    ),
    hot as (
        select sb.template_name, count(*) as hot_leads
        from sb
        join broadcast_lead_scores bls on bls.broadcast_id = sb.id
                                      and bls.segment = 'A'
        group by sb.template_name
    ),
    meta as (
        select template_name, count(*) as broadcasts, max(sent_at) as last_sent
        from sb
        group by template_name
    )
    select
        meta.template_name,
        meta.broadcasts,
        coalesce(recip.sent, 0) as sent,
        coalesce(reads.read, 0) as read,
        coalesce(recip.replied, 0) as replied,
        coalesce(hot.hot_leads, 0) as hot_leads,
        meta.last_sent
    from meta
    left join recip on recip.template_name = meta.template_name
    left join reads on reads.template_name = meta.template_name
    left join hot on hot.template_name = meta.template_name
    order by meta.last_sent desc nulls last;
$$;
