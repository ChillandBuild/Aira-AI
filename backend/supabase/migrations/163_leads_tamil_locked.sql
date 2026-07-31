-- Migration 163: Add tamil_locked to leads for the "Tanglish, lock to Tamil on Tamil script" reply-language mode
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tamil_locked BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN leads.tamil_locked IS 'Set true the first time this lead sends a pure-Tamil-script message under the tanglish_escalate_tamil reply_language_mode; once true, replies stay in Tamil for the rest of the conversation.';
