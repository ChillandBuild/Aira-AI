-- 209_call_wrapup_v2_narrow.sql
-- Call wrap-up v2, step 2 of 2. Apply ONLY AFTER the new code is deployed (the old
-- code writes values this migration removes). Maps old rows, narrows the checks to
-- the new sets, and drops the replaced columns.

-- Tap 2 (outcome): old business outcomes -> new; no_answer was never a human result.
UPDATE public.call_logs SET outcome = 'interested_needs_time' WHERE outcome = 'interested';
UPDATE public.call_logs SET outcome = 'call_later' WHERE outcome = 'callback';
UPDATE public.call_logs SET outcome = NULL WHERE outcome = 'no_answer';

-- Old SIM wrap-ups put the result in manual_status: move it to outcome, tap 1 = connected.
UPDATE public.call_logs
SET outcome = COALESCE(outcome, CASE manual_status
      WHEN 'interested' THEN 'interested_needs_time'
      WHEN 'not_interested' THEN 'not_interested'
      WHEN 'callback' THEN 'call_later'
      WHEN 'wrong_number' THEN 'wrong_number'
    END),
    manual_status = 'connected'
WHERE manual_status IN ('interested', 'not_interested', 'callback', 'wrong_number');

UPDATE public.call_logs
SET next_action_at = wrapup_callback_at
WHERE next_action_at IS NULL AND wrapup_callback_at IS NOT NULL;

UPDATE public.leads SET call_status = 'trying' WHERE call_status = 'in_progress';

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_outcome_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_outcome_check CHECK (
  outcome IS NULL OR outcome IN (
    'interested_booked', 'interested_needs_time', 'maybe_later', 'call_later', 'converted',
    'not_interested', 'disqualified', 'wrong_number', 'language_barrier', 'do_not_call'));

ALTER TABLE public.call_logs DROP CONSTRAINT IF EXISTS call_logs_manual_status_check;
ALTER TABLE public.call_logs ADD CONSTRAINT call_logs_manual_status_check CHECK (
  manual_status IS NULL OR manual_status IN ('connected', 'not_picked', 'busy', 'switched_off'));

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_call_status_check;
ALTER TABLE public.leads ADD CONSTRAINT leads_call_status_check CHECK (
  call_status IN (
    'new', 'trying', 'unreachable', 'hot', 'warm', 'cold', 'callback', 'converted',
    'not_interested', 'disqualified', 'wrong_number', 'language_barrier', 'dnc'));

ALTER TABLE public.call_logs
  DROP COLUMN IF EXISTS wrapup_callback_at,
  DROP COLUMN IF EXISTS quality_rating;
