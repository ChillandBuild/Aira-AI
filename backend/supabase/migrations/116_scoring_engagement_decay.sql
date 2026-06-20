-- Migration 116: Add explicit engagement score column + widen decay range
-- score_engagement: rule-based engagement signal (0..+2), computed on each inbound
-- score_engagement_delta (existing): repurposed as bidirectional decay (-4..+3)

ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_engagement smallint DEFAULT 0;

-- Rejection payload also zeroes the new column (already DEFAULT 0, but explicit)
