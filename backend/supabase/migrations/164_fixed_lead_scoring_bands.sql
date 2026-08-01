-- Fixed lead scoring bands: Not Interested (D) = 0, Cold (C) = 1-3,
-- Warm (B) = 4-7, Hot (A) = 8-10. Replaces the old per-tenant configurable
-- thresholds (scoring_segment_thresholds app_setting, now unused).

-- 1. Allow score=0 (Not Interested floor) — was CHECK (score >= 1 AND score <= 10).
ALTER TABLE leads DROP CONSTRAINT leads_score_check;
ALTER TABLE leads ADD CONSTRAINT leads_score_check CHECK (score >= 0 AND score <= 10);

-- 2. Not Interested (D) leads: renumber score to exactly 0.
UPDATE leads SET score = 0 WHERE segment = 'D';

-- 3. Recompute segment for every other lead against the new fixed bands
--    (some tenants had customized thresholds that no longer apply).
UPDATE leads
SET segment = CASE
    WHEN score >= 8 THEN 'A'
    WHEN score >= 4 THEN 'B'
    WHEN score >= 1 THEN 'C'
    ELSE 'D'
  END
WHERE segment != 'D';
