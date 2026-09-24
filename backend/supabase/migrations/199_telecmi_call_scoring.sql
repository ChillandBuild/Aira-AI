-- 199: TeleCMI call scoring v3.
-- Removes the outcome-only telecaller scoring (callers.overall_score, the daily
-- coaching digest) and adds the recording-pipeline, score and flag state that
-- the recording-based scorer needs. call_logs.score is kept as the column for
-- the new 0-10 score, but every old outcome-only value is cleared so the two
-- scales never mix.

drop table if exists public.caller_digests;

alter table public.callers drop column if exists overall_score;

update public.call_logs set score = null where score is not null;

alter table public.call_logs
  add column if not exists recording_filename text,
  add column if not exists ai_status text,
  add column if not exists ai_attempts smallint not null default 0,
  add column if not exists ai_error text,
  add column if not exists ai_updated_at timestamptz,
  add column if not exists score_status text,
  add column if not exists score_breakdown jsonb,
  add column if not exists flag_status text,
  add column if not exists flag_reason text,
  add column if not exists flagged_at timestamptz,
  add column if not exists flag_resolved_by uuid,
  add column if not exists flag_resolved_at timestamptz;

alter table public.call_logs drop constraint if exists call_logs_ai_status_check;
alter table public.call_logs add constraint call_logs_ai_status_check
  check (ai_status is null or ai_status in ('pending', 'transcribing', 'scoring', 'done', 'failed'));

alter table public.call_logs drop constraint if exists call_logs_score_status_check;
alter table public.call_logs add constraint call_logs_score_status_check
  check (score_status is null or score_status in ('pending', 'awaiting_outcome', 'scored', 'short_call', 'no_answer', 'no_recording', 'failed'));

alter table public.call_logs drop constraint if exists call_logs_flag_status_check;
alter table public.call_logs add constraint call_logs_flag_status_check
  check (flag_status is null or flag_status in ('open', 'confirmed', 'dismissed'));

create index if not exists idx_call_logs_ai_queue
  on public.call_logs (ai_status, ai_updated_at)
  where ai_status in ('pending', 'transcribing', 'scoring');

create index if not exists idx_call_logs_tenant_flag
  on public.call_logs (tenant_id, flag_status, flagged_at desc)
  where flag_status is not null;

create index if not exists idx_call_logs_tenant_caller_created
  on public.call_logs (tenant_id, caller_id, created_at desc);

notify pgrst, 'reload schema';
