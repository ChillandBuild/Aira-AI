-- 201_knowledge_review_handover.sql
-- Knowledge Auto-Sort: the compiled Description must never contain a "call/contact
-- a person" line (handover is a separate per-tenant setting). run_sort now extracts
-- one such line, if any, from the uploaded rules and stores it here for the client's
-- review screen to offer -- apply_review does NOT save it anywhere; the client decides.
--
-- Additive only: existing rows get '' and keep working unchanged.

ALTER TABLE knowledge_reviews
  ADD COLUMN IF NOT EXISTS suggested_handover text NOT NULL DEFAULT '';
