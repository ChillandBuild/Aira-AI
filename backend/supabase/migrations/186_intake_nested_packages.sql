-- 186_intake_nested_packages.sql
-- Packages can now nest (sub-options at unlimited depth) and carry optional
-- addons on a leaf. These columns snapshot the lead's actual path through the
-- tree and the final charged total, same reasoning as package_key/package_name/
-- package_amount_paise in 176: editing packages later must never rewrite what a
-- past lead was actually offered or charged.

BEGIN;

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS package_path jsonb,
  ADD COLUMN IF NOT EXISTS selected_addons jsonb,
  ADD COLUMN IF NOT EXISTS total_amount_paise integer,
  ADD COLUMN IF NOT EXISTS package_draft_path jsonb,
  ADD COLUMN IF NOT EXISTS addon_draft_selection jsonb;

ALTER TABLE intake_sessions
  DROP CONSTRAINT IF EXISTS intake_sessions_status_check;

ALTER TABLE intake_sessions
  ADD CONSTRAINT intake_sessions_status_check CHECK (status = ANY (ARRAY[
    'offer_pending'::text,
    'awaiting_package_choice'::text,
    'awaiting_addon_choice'::text,
    'collecting'::text,
    'awaiting_confirmation'::text,
    'awaiting_payment'::text,
    'paid'::text,
    'resolved'::text,
    'cancelled'::text
  ]));

COMMIT;
