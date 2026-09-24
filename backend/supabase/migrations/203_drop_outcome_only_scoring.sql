-- 203: remove the outcome-only telecaller scoring (destructive half of 202).
-- Apply ONLY after the backend that stopped reading callers.overall_score and
-- caller_digests is live; the previous backend orders the telecaller list by
-- overall_score and writes it when creating telecallers and clients.
-- call_logs.score is kept as the column for the new 0-10 score, but every old
-- outcome-only value is cleared so the two scales never mix.

drop table if exists public.caller_digests;

alter table public.callers drop column if exists overall_score;

update public.call_logs set score = null where score is not null and score_status is null;

notify pgrst, 'reload schema';
