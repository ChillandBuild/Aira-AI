-- Inbox folders (Inbox / Archived / Blocked) and the caller's own-leads rule move
-- into get_conversation_leads, so `total` and LIMIT/OFFSET count only the rows
-- the folder actually shows.
--
-- Before: the function paged across every conversation and the API dropped the
-- other folders afterwards. `total` was always the all-folders count (697 on the
-- Blocked tab showing 1 chat, so "Load more" never went away), Archived/Blocked
-- only ever searched the 50 newest conversations, and Inbox "Load more" offsets
-- drifted by the number of hidden rows.
--
-- New overload with two extra parameters; the 4-argument version is left alone
-- so the running API keeps working until the new one is deployed.

CREATE OR REPLACE FUNCTION public.get_conversation_leads(
  p_tenant_id uuid,
  p_limit integer,
  p_offset integer,
  p_search text,
  p_folder text,
  p_caller_id uuid DEFAULT NULL
)
 RETURNS TABLE(lead_id uuid, last_reply_at timestamp with time zone, last_message_content text, total bigint)
 LANGUAGE sql
 STABLE
 SET search_path = public, pg_temp
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
    -- One row per lead_id (see migration 152).
    select
      coalesce(cl.lead_id, pl.lead_id) as lead_id,
      cl.last_reply_at,
      cl.last_message_content
    from pinned_leads pl
    full outer join conversation_leads cl on cl.lead_id = pl.lead_id
  ),
  filtered as (
    select c.lead_id, c.last_reply_at, c.last_message_content, l.pinned_at
    from combined c
    join leads l on l.id = c.lead_id and l.tenant_id = p_tenant_id
    where l.deleted_at is null
      and case coalesce(p_folder, 'chats')
            when 'archived' then l.archived_at is not null
            when 'blocked' then l.blocked_at is not null
            else l.archived_at is null and l.blocked_at is null
          end
      -- Callers see their own leads plus the shared escalation pool.
      and (p_caller_id is null or l.assigned_to = p_caller_id or l.needs_human_attention is true)
      and (
        p_search is null or p_search = ''
        or l.name ilike '%' || p_search || '%'
        or l.phone ilike '%' || p_search || '%'
        or l.tg_username ilike '%' || p_search || '%'
      )
  )
  select
    lead_id,
    last_reply_at,
    last_message_content,
    count(*) over () as total
  from filtered
  order by pinned_at desc nulls last, last_reply_at desc nulls last
  limit p_limit
  offset p_offset;
$function$;
