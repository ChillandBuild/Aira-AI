-- 184_quick_reply_blocks.sql
-- Client-authored WhatsApp button messages. The AI picks one via a tool call
-- using `use_when`; see docs/superpowers/specs/2026-08-24-quick-reply-blocks-design.md.
--
-- Backend-only table (service role), same pattern as expert_handoff_sessions
-- (migration 168): RLS enabled, no client policies, so anon/authenticated clients
-- are denied and only the FastAPI backend can read/write it.

CREATE TABLE IF NOT EXISTS quick_reply_blocks (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid        NOT NULL,
  name       text        NOT NULL,
  use_when   text        NOT NULL,
  body_text  text        NOT NULL,
  buttons    jsonb       NOT NULL DEFAULT '[]',
  is_active  boolean     NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS quick_reply_blocks_tenant_idx
  ON quick_reply_blocks (tenant_id, is_active);

-- name is the tool's enum value the model chooses by, so two blocks named
-- "Menu" for one tenant would make that choice ambiguous.
CREATE UNIQUE INDEX IF NOT EXISTS quick_reply_blocks_tenant_name_idx
  ON quick_reply_blocks (tenant_id, lower(name));

ALTER TABLE quick_reply_blocks ENABLE ROW LEVEL SECURITY;

-- reply_source is CHECK-constrained; without this the outbound insert in
-- generate_reply fails for every block send. That insert is wrapped in a
-- swallow-and-log, so the failure would be invisible: the lead receives the
-- buttons and the message never appears in the inbox.
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN (
    'knowledge','ai','automation','reengagement','expert_handoff',
    'silence_nudge','quick_reply_block'
  ));
