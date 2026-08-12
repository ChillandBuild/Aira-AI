ALTER TABLE intake_sessions ADD COLUMN IF NOT EXISTS amount_mismatch boolean NOT NULL DEFAULT false;
