-- Fix is_secret flag on keys that were incorrectly stored as non-secret.
-- These keys contain tokens/secrets but were missing from _SECRET_KEYS,
-- so they were saved with is_secret=false and returned in plaintext.

UPDATE app_settings
SET is_secret = true
WHERE key IN (
    'meta_app_secret',
    'telecmi_webhook_secret',
    'telegram_bot_token',
    'instagram_access_token',
    'facebook_access_token'
)
AND is_secret = false;
