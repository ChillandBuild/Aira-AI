-- Fix get_conversation_leads() returning a lead twice when it is both pinned
-- and has real conversation activity. The `combined` CTE previously did
-- `conversation_leads UNION pinned_leads`, but UNION only dedupes identical
-- *whole rows* — the pinned branch always emits NULL last_reply_at/
-- last_message_content, so a lead present in both branches produced two
-- distinct (lead_id, ..., ...) tuples that both survived the union.
-- conversations.py trusts this RPC to return at most one row per lead_id
-- (it builds its lead_ids list with no dedup), so the duplicate row was
-- surfaced verbatim as a byte-identical duplicate card in the Shared Inbox.
--
-- Fix: replace the UNION with a FULL OUTER JOIN keyed on lead_id, which is
-- structurally guaranteed to produce exactly one row per lead_id.
CREATE OR REPLACE FUNCTION public.get_conversation_leads(p_tenant_id uuid, p_limit integer DEFAULT 50, p_offset integer DEFAULT 0, p_search text DEFAULT NULL::text)
 RETURNS TABLE(lead_id uuid, last_reply_at timestamp with time zone, last_message_content text, total bigint)
 LANGUAGE sql
 STABLE
AS $function$
  with conversation_leads as (
    select
      m.lead_id,
      max(m.created_at) as last_reply_at,
      (select m2.content from messages m2 where m2.lead_id = m.lead_id and m2.tenant_id = p_tenant_id order by m2.created_at desc limit 1) as last_message_content
    from messages m
    where m.tenant_id = p_tenant_id
      and m.lead_id is not null
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
    select l.id as lead_id
    from leads l
    where l.tenant_id = p_tenant_id
      and l.pinned_at is not null
      and l.opted_out is not true
      and l.deleted_at is null
  ),
  combined as (
    -- One row per lead_id: a lead that is both pinned and has real conversation
    -- activity must not appear twice (previously a UNION of full rows let the
    -- pinned CTE's NULL last_reply_at/last_message_content survive alongside
    -- conversation_leads' real values for the same lead_id, since UNION only
    -- dedupes identical whole rows).
    select
      coalesce(cl.lead_id, pl.lead_id) as lead_id,
      cl.last_reply_at,
      cl.last_message_content
    from pinned_leads pl
    full outer join conversation_leads cl on cl.lead_id = pl.lead_id
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
$function$;
