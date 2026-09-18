-- 190_knowledge_auto_sort.sql
-- Knowledge Auto-Sort (docs/superpowers/specs/2026-09-18-knowledge-auto-sort-design.md).
--
-- An uploaded document is split into RULES (merged into the Description), FACTS
-- (indexed into RAG) and JUNK, and parked as a pending review until the client
-- approves it. After sorting, knowledge_documents.full_text holds the FACTS ONLY:
-- retrieval's full-text fallback injects every indexed document's full_text, so a raw
-- rulebook left there would come back into the prompt on every retrieval miss.
--
-- source_text  -- raw extraction (<= 50,000 chars), the input for re-sorting.
-- rule_lines   -- normalised Description lines this document contributed, as applied.
--                 A Description line no document claims is the client's own.
-- sorted_at    -- NULL = legacy document, never sorted; behaves exactly as before.
-- sort_state   -- sorting / review / failed. Lets an indexed legacy document be
--                 re-sorted while it keeps serving replies (status stays 'indexed').
--
-- Additive only: existing rows get NULL / '[]' and keep working unchanged.

ALTER TABLE knowledge_documents
  ADD COLUMN IF NOT EXISTS source_text text,
  ADD COLUMN IF NOT EXISTS rule_lines jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS sorted_at timestamptz,
  ADD COLUMN IF NOT EXISTS sort_state text;

ALTER TABLE knowledge_documents
  DROP CONSTRAINT IF EXISTS knowledge_documents_sort_state_check;
ALTER TABLE knowledge_documents
  ADD CONSTRAINT knowledge_documents_sort_state_check
  CHECK (sort_state IS NULL OR sort_state IN ('sorting', 'review', 'failed'));

-- Version history for the Description and for each document's facts (spec §7).
-- created_at uses clock_timestamp() so two versions written in one transaction
-- (a baseline immediately followed by an edit) still order correctly.
CREATE TABLE IF NOT EXISTS knowledge_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  kind text NOT NULL CHECK (kind IN ('description', 'facts')),
  document_id uuid REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  content text NOT NULL DEFAULT '',
  reason text NOT NULL CHECK (reason IN ('baseline', 'edit', 'upload', 'delete_document', 'resort', 'restore')),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT knowledge_versions_kind_document_check CHECK (
    (kind = 'description' AND document_id IS NULL)
    OR (kind = 'facts' AND document_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_versions_lookup
  ON knowledge_versions (tenant_id, kind, document_id, created_at DESC);

-- A sort result waiting for the client's approval (spec §5). At most one 'pending'
-- row per document -- a new sort marks the older one 'discarded'.
CREATE TABLE IF NOT EXISTS knowledge_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  document_id uuid NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
  base_version_id uuid REFERENCES knowledge_versions(id) ON DELETE SET NULL,
  proposed_description text NOT NULL DEFAULT '',
  proposed_facts text NOT NULL DEFAULT '',
  proposed_rule_lines jsonb NOT NULL DEFAULT '[]'::jsonb,
  conflicts jsonb NOT NULL DEFAULT '[]'::jsonb,
  fact_disagreements jsonb NOT NULL DEFAULT '[]'::jsonb,
  unverified jsonb NOT NULL DEFAULT '[]'::jsonb,
  left_out jsonb NOT NULL DEFAULT '[]'::jsonb,
  left_out_rules jsonb NOT NULL DEFAULT '[]'::jsonb,
  truncated boolean NOT NULL DEFAULT false,
  replaces_document_id uuid REFERENCES knowledge_documents(id) ON DELETE SET NULL,
  origin text NOT NULL DEFAULT 'upload' CHECK (origin IN ('upload', 'resort')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'discarded')),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_reviews_document
  ON knowledge_reviews (tenant_id, document_id, created_at DESC);

-- RLS mirrors knowledge_documents: members read, owners write. The backend uses the
-- service role and filters by tenant_id itself; these policies cover direct access.
ALTER TABLE knowledge_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS knowledge_versions_tenant_member_select ON knowledge_versions;
CREATE POLICY knowledge_versions_tenant_member_select ON knowledge_versions
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS knowledge_versions_tenant_owner_insert ON knowledge_versions;
CREATE POLICY knowledge_versions_tenant_owner_insert ON knowledge_versions
  FOR INSERT TO authenticated WITH CHECK (public.is_tenant_owner(tenant_id));
DROP POLICY IF EXISTS knowledge_versions_tenant_owner_update ON knowledge_versions;
CREATE POLICY knowledge_versions_tenant_owner_update ON knowledge_versions
  FOR UPDATE TO authenticated USING (public.is_tenant_owner(tenant_id)) WITH CHECK (public.is_tenant_owner(tenant_id));
DROP POLICY IF EXISTS knowledge_versions_tenant_owner_delete ON knowledge_versions;
CREATE POLICY knowledge_versions_tenant_owner_delete ON knowledge_versions
  FOR DELETE TO authenticated USING (public.is_tenant_owner(tenant_id));

DROP POLICY IF EXISTS knowledge_reviews_tenant_member_select ON knowledge_reviews;
CREATE POLICY knowledge_reviews_tenant_member_select ON knowledge_reviews
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS knowledge_reviews_tenant_owner_insert ON knowledge_reviews;
CREATE POLICY knowledge_reviews_tenant_owner_insert ON knowledge_reviews
  FOR INSERT TO authenticated WITH CHECK (public.is_tenant_owner(tenant_id));
DROP POLICY IF EXISTS knowledge_reviews_tenant_owner_update ON knowledge_reviews;
CREATE POLICY knowledge_reviews_tenant_owner_update ON knowledge_reviews
  FOR UPDATE TO authenticated USING (public.is_tenant_owner(tenant_id)) WITH CHECK (public.is_tenant_owner(tenant_id));
DROP POLICY IF EXISTS knowledge_reviews_tenant_owner_delete ON knowledge_reviews;
CREATE POLICY knowledge_reviews_tenant_owner_delete ON knowledge_reviews
  FOR DELETE TO authenticated USING (public.is_tenant_owner(tenant_id));
