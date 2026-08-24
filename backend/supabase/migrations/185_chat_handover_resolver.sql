-- 185: resolver attribution on chat_handovers, for the Escalations History tab.
--
-- Applied to the live project (ayftynkgmfkaqmmnlmoc) via the Supabase MCP tool
-- on 2026-08-24 as `add_resolver_attribution_to_chat_handovers`; this file is
-- the repo's record of it.
--
-- Nothing to backfill: the rows already resolved were closed before anyone was
-- recorded, and there is no audit trail to recover the resolver from. The
-- History tab renders those as "Not recorded" rather than guessing.

alter table public.chat_handovers
  add column if not exists resolved_by uuid,
  add column if not exists resolved_by_name text;

comment on column public.chat_handovers.resolved_by is
  'auth user id of whoever resolved the handover. NULL for rows resolved before attribution shipped -- the UI renders those as "Not recorded".';
comment on column public.chat_handovers.resolved_by_name is
  'Display-name snapshot taken at resolve time (callers.name, else tenant_users.full_name). Snapshotted so history survives a caller being renamed or deleted.';

-- History lists are tenant + status scoped and ordered by resolved_at desc.
create index if not exists idx_chat_handovers_tenant_resolved
  on public.chat_handovers (tenant_id, status, resolved_at desc);
