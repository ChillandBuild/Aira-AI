-- Add optional server-side search to get_conversation_leads so searching the
-- inbox can match conversations outside the currently loaded page — the
-- frontend previously only filtered whatever page was already fetched.

DROP FUNCTION IF EXISTS get_conversation_leads(uuid,integer,integer);

create or replace function get_conversation_leads(
  p_tenant_id uuid,
  p_limit integer default 50,
  p_offset integer default 0,
  p_search text default null
)
returns table(lead_id uuid, last_reply_at timestamptz, last_message_content text, total bigint)
language sql
stable
as $$
  with conversation_leads as (
    select
      m.lead_id,
      max(m.created_at) as last_reply_at,
      (select m2.content from messages m2 where m2.lead_id = m.lead_id and m2.tenant_id = p_tenant_id order by m2.created_at desc limit 1) as last_message_content
    from messages m
    where m.tenant_id = p_tenant_id
      and m.lead_id is not null
      -- Only include leads that have at least one inbound message
      -- OR at least one outbound message that is NOT a bulk broadcast template
      and exists (
        select 1 from messages mx
        where mx.lead_id = m.lead_id
          and mx.tenant_id = p_tenant_id
          and (
            mx.direction = 'inbound'
            or (mx.direction = 'outbound' and mx.content not like '[Template:%]')
          )
      )
    group by m.lead_id
  ),
  pinned_leads as (
    select
      l.id as lead_id,
      null::timestamptz as last_reply_at,
      null::text as last_message_content
    from leads l
    where l.tenant_id = p_tenant_id
      and l.pinned_at is not null
      and l.opted_out is not true
      and l.deleted_at is null
  ),
  combined as (
    select lead_id, last_reply_at, last_message_content from conversation_leads
    union
    select lead_id, last_reply_at, last_message_content from pinned_leads
  ),
  filtered as (
    select c.lead_id, c.last_reply_at, c.last_message_content
    from combined c
    where p_search is null or p_search = '' or exists (
      select 1 from leads l
      where l.id = c.lead_id
        and (
          l.name ilike '%' || p_search || '%'
          or l.phone ilike '%' || p_search || '%'
          or l.tg_username ilike '%' || p_search || '%'
        )
    )
  ),
  with_total as (
    select
      lead_id,
      last_reply_at,
      last_message_content,
      count(*) over () as total
    from filtered
  )
  select
    lead_id,
    last_reply_at,
    last_message_content,
    total
  from with_total
  order by
    (select l.pinned_at from leads l where l.id = lead_id) desc nulls last,
    last_reply_at desc nulls last
  limit p_limit
  offset p_offset;
$$;
