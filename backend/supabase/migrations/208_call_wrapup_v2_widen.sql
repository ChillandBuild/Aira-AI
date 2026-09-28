-- 208_call_wrapup_v2_widen.sql
-- Call wrap-up v2, step 1 of 2. Safe to apply BEFORE the new code deploys:
-- adds the new call_logs columns and widens the three check constraints to
-- old ∪ new values, so the old code (live until deploy) and the new code can
-- both write. 209_call_wrapup_v2_narrow.sql maps old rows and narrows the
-- checks AFTER the deploy.

ALTER TABLE public.call_logs
  ADD COLUMN IF NOT EXISTS outcome_reason text,
  ADD COLUMN IF NOT EXISTS preferred_language text,
  ADD COLUMN IF NOT EXISTS next_action_at timestamptz,
  ADD COLUMN IF NOT EXISTS ai_call_status text;

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_reason_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_reason_check CHECK (
  outcome_reason IS NULL OR outcome_reason IN (
    'price', 'already_bought', 'no_need', 'other',
    'never_enquired', 'not_a_fit', 'not_decision_maker'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_preferred_language_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_preferred_language_check CHECK (
  preferred_language IS NULL OR preferred_language IN (
    'tamil', 'english', 'hindi', 'telugu', 'malayalam', 'kannada', 'other'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_ai_call_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_ai_call_status_check CHECK (
  ai_call_status IS NULL OR ai_call_status IN ('hot', 'warm', 'cold', 'none'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_check CHECK (
  outcome IS NULL OR outcome IN (
    'converted', 'interested', 'callback', 'not_interested', 'no_answer',
    'interested_booked', 'interested_needs_time', 'maybe_later', 'call_later',
    'disqualified', 'wrong_number', 'language_barrier', 'do_not_call'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_manual_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_manual_status_check CHECK (
  manual_status IS NULL OR manual_status IN (
    'connected', 'not_picked', 'busy', 'wrong_number', 'interested', 'not_interested', 'callback',
    'switched_off'));

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_call_status_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_call_status_check CHECK (
  call_status IN (
    'new', 'in_progress', 'callback', 'converted', 'not_interested', 'dnc', 'unreachable',
    'trying', 'hot', 'warm', 'cold', 'disqualified', 'wrong_number', 'language_barrier'));
