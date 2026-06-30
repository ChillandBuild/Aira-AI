-- SIM sync token for mobile app authentication + deduplication index for SIM CDR.
-- sync_token: unique token per caller used to authenticate SIM CDR webhook calls.
-- The unique index prevents duplicate call_logs from the same SIM caller.

alter table public.callers add column if not exists sync_token text unique;

create unique index if not exists uq_call_logs_caller_sim_entry
  on public.call_logs (caller_id, call_sid)
  where provider = 'sim_basic' and call_sid is not null;