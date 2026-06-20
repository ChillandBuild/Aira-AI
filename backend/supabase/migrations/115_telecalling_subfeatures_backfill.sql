-- Migration 115: Backfill telecalling sub-features for existing tenants
-- Tenants with 'telecalling' in enabled_features get all 4 sub-features added

UPDATE tenants
SET enabled_features = enabled_features || ARRAY['telecalling.dialer', 'telecalling.upload', 'telecalling.scheduled', 'telecalling.notes']
WHERE 'telecalling' = ANY(enabled_features)
  AND NOT 'telecalling.dialer' = ANY(enabled_features);
