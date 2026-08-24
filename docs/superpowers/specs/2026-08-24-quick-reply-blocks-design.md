# Quick Reply Blocks — client-authored WhatsApp button messages

Status: approved by user, ready for implementation plan.
Date: 2026-08-24

## 1. Problem

Every AI reply on WhatsApp goes out as plain text via `send_whatsapp`
([ai_reply.py:551](../../../backend/app/services/ai_reply.py#L551)). When a reply offers the
lead a choice, the lead has to type it back — and typed replies arrive as "2", "the second
one", typos, or Tanglish that the AI then has to interpret. Leads also drop off at typing
steps.

Clients want to author a reusable message with tappable buttons ("here's our menu",
"where are you located") and have the AI send it whenever a lead asks something related.

This is a **standalone** feature. It must not touch the paid intake flow — see section 8.

## 2. What the client authors

A **block**: a saved message with buttons, plus one line telling the AI when to use it.

| Field | Example | Purpose |
|---|---|---|
| `name` | `Menu options` | How the client refers to it |
| `use_when` | "Lead asks about food, dishes, or what we serve" | **What the AI reads to decide** |
| `body_text` | `What would you like to see?` | Sent word-for-word |
| `buttons` | `Menu card` · `Book table` · `Call us` | 1–3, each ≤ 20 characters |
| `is_active` | on/off | Pause without deleting |

## 3. How the AI selects a block

The same mechanism already proven by the product catalog. `generate_reply` builds a tool
from the tenant's active blocks and passes it to `_llm_chat_with_tools`
([ai_reply.py:1579](../../../backend/app/services/ai_reply.py#L1579)); the model decides
whether to call it, exactly as it does for `recommend_catalog_item`
([ai_reply.py:1071](../../../backend/app/services/ai_reply.py#L1071)).

One tool, with the block names as an enum and the `use_when` lines in the description:

```
send_quick_reply_block(block_name)

  "Send a saved button message when the lead's question matches one of these.
   Call this INSTEAD of writing your own reply — the saved message is sent
   as-is. Do not call more than once per reply.
     - Menu options: lead asks about food, dishes, what we serve
     - Location: lead asks where we are, address, directions"
```

If no block fits, the model does not call the tool and replies normally. Nothing about
today's behaviour changes for tenants with no blocks configured.

**Why a tool and not embedding similarity:** the tool reuses machinery already in
production and adds no vector table, no similarity threshold to tune, and no re-indexing
job. Embedding-based shortlisting stays available later if a tenant's block list ever
outgrows the prompt (section 9).

## 4. What the lead receives

The client's `body_text` **verbatim**, with their buttons beneath it. The AI does not
rewrite it, prepend to it, or append to it. If the model also produced text in the same
turn, that text is discarded — the block is the reply.

```
What would you like to see?
[ Menu card ] [ Book table ] [ Call us ]
```

Rationale: the client typed that copy into a box and expects to see it delivered. A model
paraphrase makes the editor's preview a lie.

## 5. What happens on a tap

Nothing to build. [webhook.py:546-548](../../../backend/app/routes/webhook.py#L546-L548)
already maps `interactive.button_reply.title` into `body`, so a tap arrives at
`generate_reply` as though the lead typed the label. Scoring, conversation state and the
AI are untouched.

## 6. Data model

New table, migration `184_quick_reply_blocks.sql`, following the backend-only pattern of
`168_expert_handoff_sessions.sql` (RLS enabled, **no client policies** — the FastAPI
service role is the only reader/writer):

```sql
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

CREATE UNIQUE INDEX IF NOT EXISTS quick_reply_blocks_tenant_name_idx
  ON quick_reply_blocks (tenant_id, lower(name));

ALTER TABLE quick_reply_blocks ENABLE ROW LEVEL SECURITY;
```

`buttons` is `[{"id": "<slug>", "label": "<≤20 chars>"}]`. `id` is a slug of the label,
stable across edits of other fields, and is what comes back in `button_reply.id`.

The unique index on `(tenant_id, lower(name))` matters because `name` is the tool's enum
value — two blocks named "Menu" would make the model's choice ambiguous.

## 7. Changes

### 7.1 Migration
`backend/supabase/migrations/184_quick_reply_blocks.sql` as above.

### 7.2 `backend/app/routes/quick_replies.py` (new)
Tenant-scoped CRUD following `call_scripts.py`: `get_tenant_and_role` for reads,
`require_owner` for writes. Registered in `main.py` alongside the others:

```python
app.include_router(quick_replies.router, prefix="/api/v1/quick-replies",
                   tags=["quick-replies"], dependencies=_auth)
```

Server-side validation, rejecting with 400 — the UI blocks these too, but the API is the
boundary that matters:
- 1–3 buttons, each label 1–20 characters after trimming
- `name`, `use_when`, `body_text` all non-empty
- `body_text` ≤ 1024 characters (WhatsApp interactive body cap)
- at most **10 blocks per tenant** (section 9)

### 7.3 `backend/app/services/quick_replies.py` (new)

Kept out of `ai_reply.py`, which is already large:

- `load_active_blocks(db, tenant_id) -> list[dict]`
- `build_quick_reply_tool(blocks) -> list[dict]` — returns `[]` for no blocks, else the
  one-tool list shaped like `_CATALOG_RECOMMEND_TOOL`
- `resolve_block(blocks, name) -> dict | None` — case-insensitive; returns `None` for a
  hallucinated name so the caller falls through to a normal text reply

### 7.4 `backend/app/services/ai_reply.py`

In `generate_reply`, mirroring the catalog wiring at
[:1527-1596](../../../backend/app/services/ai_reply.py#L1527):

1. Load blocks and build the tool; **merge into the same `tools=` list** as
   `catalog_tools` rather than making a second LLM call.
2. Drop the tool when `intake_active`, for the reason already documented at
   [:1550-1556](../../../backend/app/services/ai_reply.py#L1550) — a prompt instruction has
   no effect on a live tool the model can still call, so the tool itself must go.
3. Drop the tool when `channel != "whatsapp"`. Instagram, Telegram and Facebook have no
   equivalent button format.
4. Drop the tool when the last outbound message in `recent_thread` (already fetched at
   step 0 — no extra query) starts with a block's `body_text`. A lead who did not tap
   should not receive the identical three buttons again.
5. On a tool call: resolve the block, send via `send_interactive_buttons`, log to
   `messages` with `content` = body plus `[Label] [Label]` and `reply_source` =
   `"quick_reply_block"`, and **return** — suppressing the model's own text for that turn.
6. On any send failure, fall back to the normal text reply path. A broken block must never
   cost the conversation.

**Precedence when both tools fire in one turn.** Both `send_quick_reply_block` and
`recommend_catalog_item` live in the same `tools=` list, so the model can call both. The
block wins: it is sent and the catalog recommendation is skipped, logged at WARNING. Doing
both would send the lead a product photo and a button menu for the same turn, which reads
as two unrelated replies. The block wins rather than the catalog because the block carries
the client's own copy and an explicit instruction to replace the reply.

### 7.5 Frontend — `QuickRepliesPanel.tsx` (new)

A `SettingsSection` in the existing **Settings → Automations** tab
([settings/page.tsx:683](../../../frontend/app/dashboard/settings/page.tsx#L683)), placed
next to the other automation panels so it relocates with them when the settings-nav
restructure lands.

List of blocks with add/edit/delete, and per block: name, `use_when`, `body_text`, 1–3
button labels each with a **hard 20-character counter**, and an active toggle.

A **live WhatsApp-style preview** of the bubble is required, not optional — it is the only
place the client sees what the lead will actually get, and it is what makes the
20-character limit legible rather than abstract.

`use_when` needs an inline hint explaining that this is what the AI reads to decide; a
client who writes "menu" there instead of a description gets poor matching and no error.

## 8. Explicitly out of scope

- **Any change to `intake.py` or the paid intake flow.** Reverted on 2026-08-24 at the
  user's direction; see [2026-08-24-intake-package-buttons-design.md](2026-08-24-intake-package-buttons-design.md).
  Blocks are suppressed while intake is active (7.4 step 2) but no intake code is edited.
- **Per-button configured replies.** A tap feeds its label back as text; the AI answers.
- **Chaining a button to another block.** That is the Bot Flow Builder removed on
  2026-06-01 ([decisions/log.md:16](../../../.agents/decisions/log.md#L16)).
- **List format (10 rows).** Three buttons covers the use cases described. `send_list_message`
  already exists if this changes.
- **Scheduling, conditions, per-segment targeting.**

## 9. Known risks

**Prompt cost grows with block count.** Each block adds roughly 25 tokens to every reply
for that tenant. Ten blocks ≈ 250 tokens — negligible; fifty would not be. Hence the cap of
10, enforced in the API. If a tenant needs more, the upgrade is embedding-based
shortlisting of the top 5 blocks before building the tool, which reuses the Jina/pgvector
retrieval already running in `knowledge_service.py`. Not built now.

**The model may not call the tool when the client expects it.** This is inherent to the
approach and the accepted trade for not maintaining a similarity threshold. Mitigation is
diagnostic, not corrective: log at INFO when blocks were available and none was called, so
a client asking "why didn't my buttons show?" can be answered from logs.

**A hallucinated block name** is handled by `resolve_block` returning `None` and the reply
falling through to normal text — never by sending an arbitrary block.
