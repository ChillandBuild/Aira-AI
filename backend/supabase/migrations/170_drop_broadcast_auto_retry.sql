-- Migration 170: Reverses migration 104 (broadcast auto-retry) — feature fully removed from app code this session.

ALTER TABLE scheduled_broadcasts
    DROP COLUMN IF EXISTS retry_enabled,
    DROP COLUMN IF EXISTS retry_time,
    DROP COLUMN IF EXISTS retry_max_attempts,
    DROP COLUMN IF EXISTS retry_of,
    DROP COLUMN IF EXISTS retry_attempt,
    DROP COLUMN IF EXISTS retry_completed_at;

-- broadcast_recipients.extra_cols kept: used on every send (upload.py) for
-- template personalization, not retry-specific despite originating in migration 104.
