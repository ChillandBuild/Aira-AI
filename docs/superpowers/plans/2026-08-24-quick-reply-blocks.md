# Quick Reply Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a client save a named WhatsApp message with up to 3 reply buttons, which the AI sends when a lead's question matches the client's "use when" description.

**Architecture:** All decision logic lives in a new `services/quick_replies.py` as pure functions, so it is unit-testable without a database. `ai_reply.py` gains a thin wiring layer: build the tool, merge it into the existing `tools=` list beside the catalog tool, and on a tool call swap the outbound send for a button send. The block flows through the *existing* send/store/score pipeline rather than short-circuiting it.

**Tech Stack:** FastAPI (`backend/app/`), pytest + `unittest.mock`, Supabase/Postgres, Next.js 14 (`frontend/app/dashboard/`), WhatsApp Cloud API.

**Spec:** [docs/superpowers/specs/2026-08-24-quick-reply-blocks-design.md](../specs/2026-08-24-quick-reply-blocks-design.md)

## Global Constraints

- WhatsApp reply buttons: **max 3 per message**, **title max 20 characters**. `send_interactive_buttons` already raises on violations — do not re-truncate.
- WhatsApp interactive body: **max 1024 characters**.
- **Max 10 blocks per tenant**, enforced in the API.
- **Do not edit `backend/app/services/intake.py` or any intake file.** This feature is deliberately standalone; the intake variant was reverted on 2026-08-24. Suppressing blocks during intake is done in `ai_reply.py` by dropping the tool, never by touching intake code.
- `messages.reply_source` is a CHECK-constrained column. Current values: `knowledge, ai, automation, reengagement, expert_handoff, silence_nudge`. Inserting `quick_reply_block` **fails** until Task 1's migration runs.
- Backend tests: `cd backend && pytest`. Frontend verification is **both** `npm run lint` and `npm run typecheck`.
- 3 tests fail on `main` already (`test_ai_reply_llm_wiring`, `test_outbound_number_routing`, `test_whatsapp_audio_webhook`). They are pre-existing and unrelated — do not try to fix them, but do not add to them either.
- Do not `git push`. Local commits only.

## Correction to the spec

Spec section 7.4 step 5 says to send the block and **return**. Do not do that. In
`generate_reply`, storing the outbound message (line ~1784) and lead scoring (line ~1827)
both run *after* the send, so an early return would silently stop scoring inbound messages
whenever a block fires. Instead the block overrides `reply_text` / `reply_source` and swaps
the send call, letting the rest of the pipeline run untouched. Tasks 4 implements it this way.

---

### Task 1: Migration — table and reply_source constraint

**Files:**
- Create: `backend/supabase/migrations/184_quick_reply_blocks.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: table `quick_reply_blocks (id, tenant_id, name, use_when, body_text, buttons jsonb, is_active, created_at, updated_at)`; `messages.reply_source` accepts `'quick_reply_block'`.

- [ ] **Step 1: Write the migration**

Create `backend/supabase/migrations/184_quick_reply_blocks.sql`:

```sql
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
-- generate_reply fails for every block send.
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN (
    'knowledge','ai','automation','reengagement','expert_handoff',
    'silence_nudge','quick_reply_block'
  ));
```

- [ ] **Step 2: Apply it to Supabase**

Run the SQL against the project (Supabase SQL editor, or the `apply_migration` MCP tool if connected). It must run before Task 4 is verified, because the outbound insert fails without the constraint change.

- [ ] **Step 3: Verify the constraint took**

Run in the SQL editor:

```sql
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'messages_reply_source_check';
```

Expected: the returned definition includes `'quick_reply_block'`.

- [ ] **Step 4: Commit**

```bash
git add backend/supabase/migrations/184_quick_reply_blocks.sql
git commit -m "feat(db): add quick_reply_blocks table and reply_source value"
```

---

### Task 2: Decision logic in `services/quick_replies.py`

Every decision lives here as a pure function so it is testable without a database or an LLM. Task 4's wiring then carries almost no untested logic.

**Files:**
- Create: `backend/app/services/quick_replies.py`
- Test: `backend/tests/test_quick_replies.py` (create)

**Interfaces:**
- Consumes: `BUTTON_TITLE_MAX`, `BUTTON_COUNT_MAX` from `app.services.meta_cloud`.
- Produces:
  - `MAX_BLOCKS_PER_TENANT: int = 10`, `BODY_TEXT_MAX: int = 1024`, `QUICK_REPLY_TOOL_NAME: str = "send_quick_reply_block"`
  - `load_active_blocks(db, tenant_id: str) -> list[dict]`
  - `build_quick_reply_tool(blocks: list[dict]) -> list[dict]`
  - `resolve_block(blocks: list[dict], name: str | None) -> dict | None`
  - `last_outbound_was_block(blocks: list[dict], recent_thread: list[dict]) -> bool`
  - `should_offer_quick_replies(channel: str, intake_active: bool, blocks: list[dict], recent_thread: list[dict]) -> bool`
  - `format_block_log(block: dict) -> str`
  - `to_send_buttons(block: dict) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_quick_replies.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.quick_replies import (
    QUICK_REPLY_TOOL_NAME,
    build_quick_reply_tool,
    format_block_log,
    last_outbound_was_block,
    load_active_blocks,
    resolve_block,
    should_offer_quick_replies,
    to_send_buttons,
)


def _block(name="Menu options", use_when="lead asks about food", body="What would you like?"):
    return {
        "id": "b1",
        "name": name,
        "use_when": use_when,
        "body_text": body,
        "buttons": [{"id": "menu", "label": "Menu card"}, {"id": "book", "label": "Book table"}],
        "is_active": True,
    }


# --- build_quick_reply_tool ---

def test_tool_is_empty_without_blocks():
    assert build_quick_reply_tool([]) == []


def test_tool_lists_names_as_enum():
    tools = build_quick_reply_tool([_block(), _block(name="Location", use_when="asks address")])
    fn = tools[0]["function"]
    assert fn["name"] == QUICK_REPLY_TOOL_NAME
    assert fn["parameters"]["properties"]["block_name"]["enum"] == ["Menu options", "Location"]


def test_tool_description_carries_use_when():
    tools = build_quick_reply_tool([_block()])
    assert "lead asks about food" in tools[0]["function"]["description"]
    assert "Menu options" in tools[0]["function"]["description"]


# --- resolve_block ---

def test_resolve_block_is_case_insensitive():
    blocks = [_block()]
    assert resolve_block(blocks, "menu OPTIONS")["name"] == "Menu options"


def test_resolve_block_returns_none_for_hallucinated_name():
    assert resolve_block([_block()], "Nonexistent") is None


def test_resolve_block_returns_none_for_empty_name():
    assert resolve_block([_block()], None) is None
    assert resolve_block([_block()], "") is None


# --- to_send_buttons ---

def test_to_send_buttons_maps_label_to_title():
    assert to_send_buttons(_block()) == [
        {"id": "menu", "title": "Menu card"},
        {"id": "book", "title": "Book table"},
    ]


# --- format_block_log ---

def test_format_block_log_appends_labels():
    assert format_block_log(_block()) == "What would you like?\n\n[Menu card] [Book table]"


# --- last_outbound_was_block ---

def test_last_outbound_was_block_true_when_body_matches():
    thread = [
        {"direction": "outbound", "content": "What would you like?\n\n[Menu card] [Book table]"},
        {"direction": "inbound", "content": "hi"},
    ]
    assert last_outbound_was_block([_block()], thread) is True


def test_last_outbound_was_block_false_for_ordinary_reply():
    thread = [
        {"direction": "outbound", "content": "Sure, we open at 9am."},
        {"direction": "inbound", "content": "what time"},
    ]
    assert last_outbound_was_block([_block()], thread) is False


def test_last_outbound_was_block_ignores_inbound_messages():
    # The lead echoing the body text back must not suppress the block.
    thread = [
        {"direction": "inbound", "content": "What would you like?"},
        {"direction": "outbound", "content": "Sure, we open at 9am."},
    ]
    assert last_outbound_was_block([_block()], thread) is False


def test_last_outbound_was_block_false_on_empty_thread():
    assert last_outbound_was_block([_block()], []) is False


# --- should_offer_quick_replies ---

def test_offer_true_on_whatsapp_with_blocks():
    assert should_offer_quick_replies("whatsapp", False, [_block()], []) is True


def test_offer_false_when_intake_active():
    assert should_offer_quick_replies("whatsapp", True, [_block()], []) is False


def test_offer_false_on_other_channels():
    for ch in ("instagram", "telegram", "facebook"):
        assert should_offer_quick_replies(ch, False, [_block()], []) is False


def test_offer_false_without_blocks():
    assert should_offer_quick_replies("whatsapp", False, [], []) is False


def test_offer_false_when_block_was_just_sent():
    thread = [{"direction": "outbound", "content": "What would you like?\n\n[Menu card] [Book table]"}]
    assert should_offer_quick_replies("whatsapp", False, [_block()], thread) is False


# --- load_active_blocks ---

def test_load_active_blocks_returns_rows():
    db = MagicMock()
    chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
    chain.execute.return_value = MagicMock(data=[_block()])
    assert load_active_blocks(db, "t1")[0]["name"] == "Menu options"


def test_load_active_blocks_returns_empty_on_db_error():
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")
    assert load_active_blocks(db, "t1") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_quick_replies.py -v`

Expected: FAIL at import — `No module named 'app.services.quick_replies'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/quick_replies.py`:

```python
"""Client-authored WhatsApp button messages ("quick reply blocks").

A tenant saves a named message with up to 3 reply buttons plus a `use_when` line;
the AI selects one via a tool call, the same mechanism the product catalog uses.
Every decision is a pure function here so it can be tested without a DB or an LLM
-- ai_reply.py holds only the wiring.
"""
import logging

from app.services.meta_cloud import BUTTON_COUNT_MAX, BUTTON_TITLE_MAX

logger = logging.getLogger(__name__)

# The block list rides in every reply's prompt for that tenant, roughly 25 tokens
# each. Ten is negligible; fifty would not be. Raising this without adding
# embedding-based shortlisting first is a mistake.
MAX_BLOCKS_PER_TENANT = 10
BODY_TEXT_MAX = 1024

QUICK_REPLY_TOOL_NAME = "send_quick_reply_block"


def load_active_blocks(db, tenant_id: str) -> list[dict]:
    """Active blocks for a tenant. Returns [] on any error -- a retrieval hiccup
    must degrade to an ordinary text reply, never break the conversation."""
    try:
        result = (
            db.table("quick_reply_blocks")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .order("created_at")
            .limit(MAX_BLOCKS_PER_TENANT)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.warning("Quick reply block load failed for tenant %s", tenant_id)
        return []


def build_quick_reply_tool(blocks: list[dict]) -> list[dict]:
    """The tool definition offered to the model, or [] when there is nothing to offer."""
    if not blocks:
        return []
    lines = "\n".join(f"  - {b['name']}: {b['use_when']}" for b in blocks)
    return [{
        "type": "function",
        "function": {
            "name": QUICK_REPLY_TOOL_NAME,
            "description": (
                "Send a saved button message when the lead's question matches one of "
                "these. Call this INSTEAD of writing your own reply -- the saved message "
                "is sent exactly as written. Do NOT call more than once per reply. "
                "Available blocks:\n" + lines
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "block_name": {
                        "type": "string",
                        "enum": [b["name"] for b in blocks],
                        "description": "The exact name of the block to send",
                    }
                },
                "required": ["block_name"],
            },
        },
    }]


def resolve_block(blocks: list[dict], name: str | None) -> dict | None:
    """Find a block by name. Returns None for a hallucinated or empty name so the
    caller falls through to an ordinary reply rather than sending an arbitrary block."""
    if not name:
        return None
    cleaned = name.strip().lower()
    for b in blocks:
        if (b.get("name") or "").strip().lower() == cleaned:
            return b
    return None


def to_send_buttons(block: dict) -> list[dict]:
    """Block buttons in the shape send_interactive_buttons expects.

    No truncation: send_interactive_buttons raises on an over-long title, and the
    API rejects one at write time, so anything stored here already fits.
    """
    return [
        {"id": b["id"], "title": b["label"]}
        for b in (block.get("buttons") or [])[:BUTTON_COUNT_MAX]
    ]


def format_block_log(block: dict) -> str:
    """What gets written to messages.content -- the body plus the offered labels, so
    the thread the AI reads back and the operator inbox both show what the lead saw."""
    labels = " ".join(f"[{b['label']}]" for b in (block.get("buttons") or []))
    body = block.get("body_text") or ""
    return f"{body}\n\n{labels}" if labels else body


def last_outbound_was_block(blocks: list[dict], recent_thread: list[dict]) -> bool:
    """True when the most recent OUTBOUND message was one of these blocks.

    recent_thread is newest-first, as generate_reply fetches it. Only the newest
    outbound row is considered: a lead who did not tap should not be handed the
    identical buttons again, but one older block send should not mute the feature.
    Inbound rows are skipped so a lead quoting the body text back cannot suppress it.
    """
    bodies = [(b.get("body_text") or "").strip() for b in blocks]
    bodies = [b for b in bodies if b]
    if not bodies:
        return False
    for row in recent_thread:
        if row.get("direction") != "outbound":
            continue
        content = (row.get("content") or "").strip()
        return any(content.startswith(body) for body in bodies)
    return False


def should_offer_quick_replies(
    channel: str, intake_active: bool, blocks: list[dict], recent_thread: list[dict]
) -> bool:
    """Whether to hand the model the quick-reply tool this turn.

    intake_active drops it for the same reason the catalog tool is dropped: a prompt
    instruction has no effect on a live tool definition the model can still call, so
    the tool itself has to go. Non-WhatsApp channels have no button format at all.
    """
    if channel != "whatsapp":
        return False
    if intake_active:
        return False
    if not blocks:
        return False
    return not last_outbound_was_block(blocks, recent_thread)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_quick_replies.py -v`

Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quick_replies.py backend/tests/test_quick_replies.py
git commit -m "feat(quick-replies): add block selection and guard logic"
```

---

### Task 3: CRUD API

**Files:**
- Create: `backend/app/routes/quick_replies.py`
- Modify: `backend/app/main.py` (router registration, near line 655)
- Test: `backend/tests/test_quick_replies_routes.py` (create)

**Interfaces:**
- Consumes: `MAX_BLOCKS_PER_TENANT`, `BODY_TEXT_MAX` from Task 2; `BUTTON_TITLE_MAX`, `BUTTON_COUNT_MAX` from `meta_cloud`.
- Produces: `validate_block(name, use_when, body_text, buttons) -> None` (raises `HTTPException` 400); REST endpoints under `/api/v1/quick-replies`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_quick_replies_routes.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.routes.quick_replies import slugify_label, validate_block

_OK_BUTTONS = [{"id": "menu", "label": "Menu card"}]


def test_validate_accepts_a_good_block():
    validate_block("Menu options", "lead asks about food", "What would you like?", _OK_BUTTONS)


def test_validate_rejects_blank_name():
    with pytest.raises(HTTPException) as e:
        validate_block("  ", "lead asks about food", "Body", _OK_BUTTONS)
    assert e.value.status_code == 400


def test_validate_rejects_blank_use_when():
    with pytest.raises(HTTPException):
        validate_block("Menu", "", "Body", _OK_BUTTONS)


def test_validate_rejects_blank_body():
    with pytest.raises(HTTPException):
        validate_block("Menu", "asks food", "   ", _OK_BUTTONS)


def test_validate_rejects_zero_buttons():
    with pytest.raises(HTTPException, match="1 and 3"):
        validate_block("Menu", "asks food", "Body", [])


def test_validate_rejects_four_buttons():
    buttons = [{"id": f"b{i}", "label": f"B{i}"} for i in range(4)]
    with pytest.raises(HTTPException, match="1 and 3"):
        validate_block("Menu", "asks food", "Body", buttons)


def test_validate_rejects_long_button_label():
    with pytest.raises(HTTPException, match="20 characters"):
        validate_block("Menu", "asks food", "Body", [{"id": "a", "label": "A" * 21}])


def test_validate_rejects_blank_button_label():
    with pytest.raises(HTTPException, match="empty"):
        validate_block("Menu", "asks food", "Body", [{"id": "a", "label": "   "}])


def test_validate_rejects_body_over_1024():
    with pytest.raises(HTTPException, match="1024"):
        validate_block("Menu", "asks food", "x" * 1025, _OK_BUTTONS)


def test_slugify_label_makes_a_stable_id():
    assert slugify_label("Menu card") == "menu_card"
    assert slugify_label("Book a Table!") == "book_a_table"


def test_slugify_label_falls_back_when_nothing_survives():
    assert slugify_label("!!!") == "option"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_quick_replies_routes.py -v`

Expected: FAIL at import — `No module named 'app.routes.quick_replies'`.

- [ ] **Step 3: Write the route module**

Create `backend/app/routes/quick_replies.py`:

```python
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_and_role, require_owner
from app.services.meta_cloud import BUTTON_COUNT_MAX, BUTTON_TITLE_MAX
from app.services.quick_replies import BODY_TEXT_MAX, MAX_BLOCKS_PER_TENANT

logger = logging.getLogger(__name__)
router = APIRouter()


class QuickReplyButton(BaseModel):
    id: str | None = None
    label: str


class CreateBlock(BaseModel):
    name: str
    use_when: str
    body_text: str
    buttons: list[QuickReplyButton]
    is_active: bool = True


class UpdateBlock(BaseModel):
    name: str | None = None
    use_when: str | None = None
    body_text: str | None = None
    buttons: list[QuickReplyButton] | None = None
    is_active: bool | None = None


def slugify_label(label: str) -> str:
    """Stable button id from its label. Returned in button_reply.id on a tap."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "option"


def validate_block(name: str, use_when: str, body_text: str, buttons: list) -> None:
    """Reject anything WhatsApp or the tool contract cannot carry.

    The UI blocks these too, but the API is the boundary that actually matters --
    an over-long label stored here would raise at send time, mid-conversation.
    """
    if not (name or "").strip():
        raise HTTPException(status_code=400, detail="Block name is required")
    if not (use_when or "").strip():
        raise HTTPException(
            status_code=400,
            detail="'Use when' is required — it is what the AI reads to decide when to send this",
        )
    if not (body_text or "").strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    if len(body_text) > BODY_TEXT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Message text must be {BODY_TEXT_MAX} characters or fewer",
        )
    if not (1 <= len(buttons) <= BUTTON_COUNT_MAX):
        raise HTTPException(
            status_code=400,
            detail=f"A block needs between 1 and {BUTTON_COUNT_MAX} buttons",
        )
    for b in buttons:
        label = (b.get("label") if isinstance(b, dict) else b.label) or ""
        if not label.strip():
            raise HTTPException(status_code=400, detail="Button labels cannot be empty")
        if len(label) > BUTTON_TITLE_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"Button label {label!r} must be {BUTTON_TITLE_MAX} characters or fewer",
            )


def _normalise_buttons(buttons: list[QuickReplyButton]) -> list[dict]:
    return [
        {"id": (b.id or slugify_label(b.label)), "label": b.label.strip()}
        for b in buttons
    ]


@router.get("")
async def list_blocks(ctx: dict = Depends(get_tenant_and_role)) -> list:
    db = get_supabase()
    result = (
        db.table("quick_reply_blocks")
        .select("*")
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at")
        .execute()
    )
    return result.data or []


@router.post("", dependencies=[Depends(require_owner)])
async def create_block(payload: CreateBlock, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    validate_block(payload.name, payload.use_when, payload.body_text, payload.buttons)
    db = get_supabase()

    existing = (
        db.table("quick_reply_blocks")
        .select("id")
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    if len(existing.data or []) >= MAX_BLOCKS_PER_TENANT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"At most {MAX_BLOCKS_PER_TENANT} blocks per workspace — the list is sent "
                "to the AI on every reply, so a longer one slows and confuses matching."
            ),
        )

    result = db.table("quick_reply_blocks").insert({
        "tenant_id": ctx["tenant_id"],
        "name": payload.name.strip(),
        "use_when": payload.use_when.strip(),
        "body_text": payload.body_text,
        "buttons": _normalise_buttons(payload.buttons),
        "is_active": payload.is_active,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create block")
    return result.data[0]


@router.patch("/{block_id}", dependencies=[Depends(require_owner)])
async def update_block(
    block_id: str, payload: UpdateBlock, ctx: dict = Depends(get_tenant_and_role)
) -> dict:
    db = get_supabase()
    current = (
        db.table("quick_reply_blocks")
        .select("*")
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not current or not current.data:
        raise HTTPException(status_code=404, detail="Block not found")
    row = current.data

    name = payload.name if payload.name is not None else row["name"]
    use_when = payload.use_when if payload.use_when is not None else row["use_when"]
    body_text = payload.body_text if payload.body_text is not None else row["body_text"]
    if payload.buttons is not None:
        buttons = _normalise_buttons(payload.buttons)
    else:
        buttons = row["buttons"]
    validate_block(name, use_when, body_text, buttons)

    patch = {
        "name": name.strip(),
        "use_when": use_when.strip(),
        "body_text": body_text,
        "buttons": buttons,
    }
    if payload.is_active is not None:
        patch["is_active"] = payload.is_active

    result = (
        db.table("quick_reply_blocks")
        .update(patch)
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update block")
    return result.data[0]


@router.delete("/{block_id}", dependencies=[Depends(require_owner)])
async def delete_block(block_id: str, ctx: dict = Depends(get_tenant_and_role)) -> dict:
    db = get_supabase()
    (
        db.table("quick_reply_blocks")
        .delete()
        .eq("id", block_id)
        .eq("tenant_id", ctx["tenant_id"])
        .execute()
    )
    return {"ok": True}
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add `quick_replies` to the routes import list, then add beside the other registrations (near line 655):

```python
app.include_router(quick_replies.router, prefix="/api/v1/quick-replies", tags=["quick-replies"], dependencies=_auth)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_quick_replies_routes.py -v`

Expected: 11 passed.

- [ ] **Step 6: Verify the app still boots**

Run: `cd backend && python -c "from app.main import app; print(len(app.routes), 'routes')"`

Expected: prints a route count with no import error.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/quick_replies.py backend/app/main.py backend/tests/test_quick_replies_routes.py
git commit -m "feat(quick-replies): add CRUD API with validation"
```

---

### Task 4: Wire into `generate_reply`

Read the "Correction to the spec" section above before starting: the block must **not** early-return.

**Files:**
- Modify: `backend/app/services/ai_reply.py` — around `:1527` (tool build), `:1555` (intake guard), `:1578` (LLM call), `:1585` (tool-call handling), `:1630` (reply_source), `:1736` (send)
- Test: `backend/tests/test_quick_replies.py` (append)

**Interfaces:**
- Consumes: everything Task 2 produces.
- Produces: no new public names.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_quick_replies.py`:

```python
def test_ai_reply_wires_quick_replies_into_the_shared_tool_list():
    """Guard against the block tool being sent in a second, separate LLM call, and
    against the early-return that would skip scoring (see the plan's spec correction)."""
    source = (Path(__file__).resolve().parents[1] / "app" / "services" / "ai_reply.py").read_text(
        encoding="utf-8"
    )
    assert "should_offer_quick_replies" in source
    assert "quick_reply_tool" in source
    # One merged tool list, one LLM call.
    assert "catalog_tools + quick_reply_tool" in source
    # The block overrides the reply rather than returning early.
    assert 'reply_source = "quick_reply_block"' in source
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_quick_replies.py -k wires -v`

Expected: FAIL on the first assertion.

- [ ] **Step 3: Build the tool before the LLM call**

In `generate_reply`, directly after the `catalog_context, catalog_tools, ... = await _build_catalog_context(...)` try/except block (ends ~line 1536), insert:

```python
    # Client-authored button blocks. Loaded before the intake guard below, which may
    # drop the tool again -- see should_offer_quick_replies for why the tool has to be
    # removed rather than merely discouraged in the prompt.
    quick_reply_blocks: list[dict] = []
    quick_reply_tool: list[dict] = []
    try:
        from app.services.quick_replies import build_quick_reply_tool, load_active_blocks
        if channel == "whatsapp":
            quick_reply_blocks = load_active_blocks(db, tenant_id)
            quick_reply_tool = build_quick_reply_tool(quick_reply_blocks)
    except Exception:
        logger.warning(f"Quick reply tool build failed for tenant {tenant_id}")
```

- [ ] **Step 4: Apply the guards next to the existing intake guard**

Replace the intake guard block (currently `if intake_active: catalog_tools = []`, ~line 1555):

```python
        if intake_active:
            catalog_tools = []
```

with:

```python
        if intake_active:
            catalog_tools = []

        from app.services.quick_replies import should_offer_quick_replies
        if not should_offer_quick_replies(
            channel, intake_active, quick_reply_blocks, recent_thread
        ):
            quick_reply_tool = []
```

- [ ] **Step 5: Merge into one tool list**

Replace the LLM call condition (~line 1578):

```python
        if catalog_tools:
            reply_text, tool_calls = await _llm_chat_with_tools(
                chat_messages, tools=catalog_tools, max_tokens=600, tenant_id=tenant_id,
            )
            reply_text = reply_text.strip()
```

with:

```python
        # One call with both tools. A second call for quick replies would double
        # latency and cost on every reply for tenants using both features.
        all_tools = catalog_tools + quick_reply_tool
        if all_tools:
            reply_text, tool_calls = await _llm_chat_with_tools(
                chat_messages, tools=all_tools, max_tokens=600, tenant_id=tenant_id,
            )
            reply_text = reply_text.strip()
```

- [ ] **Step 6: Capture the chosen block from the tool calls**

Immediately before the existing `for tc in tool_calls:` loop (~line 1585), insert:

```python
            # Resolved here, applied after reply_source is assigned below. A block
            # wins over a catalog recommendation: sending both gives the lead a
            # product photo and an unrelated button menu for one question.
            from app.services.quick_replies import QUICK_REPLY_TOOL_NAME, resolve_block
            for tc in tool_calls:
                func = tc.get("function") or {}
                if func.get("name") != QUICK_REPLY_TOOL_NAME:
                    continue
                try:
                    args = json.loads(func.get("arguments") or "{}")
                except (ValueError, TypeError):
                    continue
                chosen_block = resolve_block(quick_reply_blocks, args.get("block_name"))
                if chosen_block:
                    logger.info(
                        "Quick reply block selected: lead %s -> %s", lead_id, chosen_block["name"]
                    )
                else:
                    logger.warning(
                        "Model asked for unknown quick reply block %r for lead %s; "
                        "replying normally", args.get("block_name"), lead_id,
                    )
                break

            # Diagnostic for "why didn't my buttons show?" -- the one question a
            # client will ask that logs must be able to answer. INFO, not WARNING:
            # not calling the tool is usually correct.
            if quick_reply_tool and not chosen_block:
                logger.info(
                    "Quick reply blocks offered but none selected for lead %s (%d available)",
                    lead_id, len(quick_reply_blocks),
                )
```

- [ ] **Step 7: Override the reply when a block was chosen**

Directly after `reply_source = "knowledge" if context_text else "ai"` (~line 1630), insert:

```python
        if chosen_block:
            from app.services.quick_replies import format_block_log
            reply_text = format_block_log(chosen_block)
            reply_source = "quick_reply_block"
            # The block replaces the reply, so a catalog photo from the same turn
            # would arrive as an unrelated second message.
            if catalog_images_to_send:
                logger.warning(
                    "Quick reply block and catalog recommendation both fired for lead %s; "
                    "sending the block only", lead_id,
                )
                catalog_images_to_send = []
```

- [ ] **Step 8: Swap the send call**

Replace the WhatsApp send (~line 1736):

```python
            sid = await send_whatsapp(
                _wa_phone,
                reply_text,
                tenant_id=lead_data.get("tenant_id"),
                phone_number_id=phone_number_id,
                reply_to_message_id=reply_to_message_id,
            )
```

with:

```python
            if chosen_block:
                from app.services.meta_cloud import send_interactive_buttons
                from app.services.quick_replies import to_send_buttons
                try:
                    _btn_data = await send_interactive_buttons(
                        to_number=_wa_phone,
                        body_text=chosen_block["body_text"],
                        buttons=to_send_buttons(chosen_block),
                        tenant_id=lead_data.get("tenant_id"),
                        phone_number_id=phone_number_id,
                    )
                    sid = (_btn_data.get("messages") or [{}])[0].get("id")
                except Exception:
                    # Never lose the turn over a button failure -- fall back to the
                    # block's body as ordinary text.
                    logger.exception("Quick reply block send failed for lead %s", lead_id)
                    reply_text = chosen_block["body_text"]
                    sid = await send_whatsapp(
                        _wa_phone,
                        reply_text,
                        tenant_id=lead_data.get("tenant_id"),
                        phone_number_id=phone_number_id,
                        reply_to_message_id=reply_to_message_id,
                    )
            else:
                sid = await send_whatsapp(
                    _wa_phone,
                    reply_text,
                    tenant_id=lead_data.get("tenant_id"),
                    phone_number_id=phone_number_id,
                    reply_to_message_id=reply_to_message_id,
                )
```

- [ ] **Step 9: Initialise `chosen_block` for the no-tools path**

`chosen_block` is only assigned inside `if all_tools:`, but Steps 7 and 8 read it on every
path — a tenant with no blocks and no catalog would hit `NameError` without this. Add it
directly above the existing `catalog_images_to_send: list[tuple[str, bytes]] = []`
(~line 1576), so it is initialised exactly once before either branch:

```python
        chosen_block: dict | None = None
        catalog_images_to_send: list[tuple[str, bytes]] = []  # (filename, image_bytes)
```

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && pytest -q`

Expected: all pass except the 3 known pre-existing failures listed in Global Constraints.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_quick_replies.py
git commit -m "feat(ai-reply): send client-authored button blocks via tool call"
```

---

### Task 5: Settings UI

**Files:**
- Create: `frontend/app/dashboard/settings/QuickRepliesPanel.tsx`
- Modify: `frontend/app/dashboard/settings/page.tsx` (import, and render inside the `automations` tab near line 847)

**Interfaces:**
- Consumes: `/api/v1/quick-replies` from Task 3.
- Produces: `QuickRepliesPanel({ canManage }: { canManage: boolean })`.

- [ ] **Step 1: Create the panel**

Create `frontend/app/dashboard/settings/QuickRepliesPanel.tsx`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { MessageSquareMore, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SettingsSection } from "./SettingsSection";
import { CheckField } from "@/components/ui/controls";

const BUTTON_LABEL_MAX = 20;
const BUTTON_COUNT_MAX = 3;
const BODY_TEXT_MAX = 1024;
const MAX_BLOCKS = 10;

interface QuickReplyButton {
  id?: string;
  label: string;
}

interface QuickReplyBlock {
  id?: string;
  name: string;
  use_when: string;
  body_text: string;
  buttons: QuickReplyButton[];
  is_active: boolean;
}

const EMPTY_BLOCK: QuickReplyBlock = {
  name: "",
  use_when: "",
  body_text: "",
  buttons: [{ label: "" }],
  is_active: true,
};

export function QuickRepliesPanel({ canManage }: { canManage: boolean }) {
  const [blocks, setBlocks] = useState<QuickReplyBlock[]>([]);
  const [draft, setDraft] = useState<QuickReplyBlock | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/quick-replies`, { headers: auth });
      if (res.ok) setBlocks(await res.json());
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const isEdit = Boolean(draft.id);
      const res = await fetch(
        `${API_URL}/api/v1/quick-replies${isEdit ? `/${draft.id}` : ""}`,
        {
          method: isEdit ? "PATCH" : "POST",
          headers: { ...auth, "Content-Type": "application/json" },
          body: JSON.stringify(draft),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || "Could not save this block");
        return;
      }
      setDraft(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id?: string) {
    if (!id) return;
    const auth = await getAuthHeaders();
    await fetch(`${API_URL}/api/v1/quick-replies/${id}`, { method: "DELETE", headers: auth });
    await load();
  }

  function patchDraft(patch: Partial<QuickReplyBlock>) {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  }

  function patchButton(index: number, label: string) {
    setDraft((d) => {
      if (!d) return d;
      const buttons = d.buttons.map((b, i) =>
        i === index ? { ...b, label: label.slice(0, BUTTON_LABEL_MAX) } : b,
      );
      return { ...d, buttons };
    });
  }

  return (
    <SettingsSection
      id="quick-replies"
      icon={MessageSquareMore}
      accent="violet"
      title="Quick Reply Buttons"
      description="Save a message with tappable buttons. The AI sends it when a lead asks something matching your description."
      status={{
        label: `${blocks.filter((b) => b.is_active).length} active`,
        tone: blocks.some((b) => b.is_active) ? "on" : "off",
      }}
    >
      <div className="space-y-4">
        {blocks.map((b) => (
          <div
            key={b.id}
            className="rounded-2xl border border-border bg-surface-subtle p-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="font-label text-sm font-semibold text-ink">
                {b.name}
                {!b.is_active && (
                  <span className="ml-2 font-body text-xs text-ink-muted">(paused)</span>
                )}
              </div>
              <div className="font-body text-xs text-ink-muted mt-0.5">{b.use_when}</div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {b.buttons.map((btn, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 rounded-md border border-border bg-white font-body text-xs text-ink"
                  >
                    {btn.label}
                  </span>
                ))}
              </div>
            </div>
            {canManage && (
              <div className="flex gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => setDraft({ ...b })}
                  className="font-label text-xs text-ink-muted hover:text-ink"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => remove(b.id)}
                  aria-label="Delete block"
                  className="text-ink-muted hover:text-red-600"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            )}
          </div>
        ))}

        {blocks.length === 0 && !draft && (
          <p className="font-body text-xs text-ink-muted italic">
            No blocks yet — add one to let the AI offer tappable choices.
          </p>
        )}

        {canManage && !draft && blocks.length < MAX_BLOCKS && (
          <button
            type="button"
            onClick={() => setDraft({ ...EMPTY_BLOCK })}
            className="inline-flex items-center gap-1.5 font-label text-xs text-ink-muted hover:text-ink"
          >
            <Plus size={14} /> New block
          </button>
        )}

        {canManage && !draft && blocks.length >= MAX_BLOCKS && (
          <p className="font-body text-xs text-ink-muted">
            You have the maximum of {MAX_BLOCKS} blocks. The list is sent to the AI on every
            reply, so a longer one makes matching slower and less accurate.
          </p>
        )}

        {draft && (
          <div className="rounded-2xl border border-border bg-white p-4 space-y-3">
            <input
              type="text"
              value={draft.name}
              onChange={(e) => patchDraft({ name: e.target.value })}
              placeholder="Block name (e.g. Menu options)"
              className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink"
            />

            <div>
              <div className="font-label text-sm font-semibold text-ink mb-1">
                When should the AI send this?
              </div>
              <div className="font-body text-xs text-ink-muted mb-2">
                Describe the kind of question this answers — this is what the AI reads to
                decide. e.g. &quot;Lead asks about food, dishes, or what we serve.&quot;
              </div>
              <textarea
                value={draft.use_when}
                onChange={(e) => patchDraft({ use_when: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink"
              />
            </div>

            <div>
              <div className="font-label text-sm font-semibold text-ink mb-1">Message</div>
              <textarea
                value={draft.body_text}
                onChange={(e) => patchDraft({ body_text: e.target.value.slice(0, BODY_TEXT_MAX) })}
                rows={2}
                placeholder="Sent to the lead exactly as written"
                className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink"
              />
            </div>

            <div className="space-y-2">
              <div className="font-label text-sm font-semibold text-ink">
                Buttons ({draft.buttons.length}/{BUTTON_COUNT_MAX})
              </div>
              {draft.buttons.map((btn, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={btn.label}
                    onChange={(e) => patchButton(i, e.target.value)}
                    placeholder={`Button ${i + 1}`}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink"
                  />
                  <span
                    className={`font-label text-xs tabular-nums ${
                      btn.label.length >= BUTTON_LABEL_MAX ? "text-red-600" : "text-ink-muted"
                    }`}
                  >
                    {btn.label.length}/{BUTTON_LABEL_MAX}
                  </span>
                  {draft.buttons.length > 1 && (
                    <button
                      type="button"
                      onClick={() =>
                        patchDraft({ buttons: draft.buttons.filter((_, x) => x !== i) })
                      }
                      aria-label="Remove button"
                      className="text-ink-muted hover:text-red-600"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              {draft.buttons.length < BUTTON_COUNT_MAX && (
                <button
                  type="button"
                  onClick={() => patchDraft({ buttons: [...draft.buttons, { label: "" }] })}
                  className="inline-flex items-center gap-1.5 font-label text-xs text-ink-muted hover:text-ink"
                >
                  <Plus size={14} /> Add button
                </button>
              )}
            </div>

            {/* The preview is the only place the client sees what the lead actually
                gets, and it is what makes the 20-character limit concrete. */}
            <div className="rounded-xl bg-[#e7f7d4] p-3 space-y-2">
              <div className="font-body text-sm text-ink whitespace-pre-wrap">
                {draft.body_text || "Your message will appear here"}
              </div>
              <div className="flex flex-col gap-1">
                {draft.buttons.map((btn, i) => (
                  <div
                    key={i}
                    className="text-center py-1.5 rounded-lg bg-white font-body text-sm text-[#1f7aec]"
                  >
                    {btn.label || `Button ${i + 1}`}
                  </div>
                ))}
              </div>
            </div>

            <CheckField
              checked={draft.is_active}
              onChange={(v) => patchDraft({ is_active: v })}
              label="Active"
              description="Paused blocks are never offered to the AI."
            />

            {error && <p className="font-body text-xs text-red-600">{error}</p>}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={save}
                disabled={busy}
                className="px-3 py-1.5 rounded-lg bg-ink text-white font-label text-xs disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save block"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(null);
                  setError(null);
                }}
                className="px-3 py-1.5 rounded-lg border border-border font-label text-xs text-ink"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </SettingsSection>
  );
}
```

- [ ] **Step 2: Render it in the Automations tab**

In `frontend/app/dashboard/settings/page.tsx`, add the import beside the other panel imports:

```tsx
import { QuickRepliesPanel } from "./QuickRepliesPanel";
```

and render it directly after `<IntakeConfigPanel canManage={canManageSettings} />` (~line 847):

```tsx
              <QuickRepliesPanel canManage={canManageSettings} />
```

- [ ] **Step 3: Verify with lint and typecheck**

Run both — CI runs lint, and tsc alone passes code lint rejects:

```bash
cd frontend && npm run lint && npm run typecheck
```

Expected: both clean, no new warnings in the two touched files.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/settings/QuickRepliesPanel.tsx frontend/app/dashboard/settings/page.tsx
git commit -m "feat(settings): add Quick Reply Buttons panel"
```

---

### Task 6: Live verification

Automated tests cannot prove the model actually calls the tool, that Meta accepts the payload, or that a tap round-trips. A code path is not proof the product has the behaviour.

**Files:** none — manual.

- [ ] **Step 1: Create a block**

Settings → Automations → Quick Reply Buttons → New block:

```
Name:      Menu options
Use when:  Lead asks about food, dishes, or what we serve
Message:   What would you like to see?
Buttons:   Menu card | Book table | Call us
Active:    on
```

Check the green preview matches what you expect, then save.

- [ ] **Step 2: Ask a matching question**

From a test WhatsApp number, send something that matches but uses **none of the same words** — e.g. "what all do you have to eat". This is the actual test: keyword matching would miss it, meaning matching should not.

Expected: the message arrives with three tappable buttons.

- [ ] **Step 3: Tap a button**

Expected: the conversation continues normally, and `messages` shows an inbound row with content `Menu card`.

- [ ] **Step 4: Confirm the outbound was logged**

```sql
SELECT content, reply_source FROM messages
WHERE reply_source = 'quick_reply_block' ORDER BY created_at DESC LIMIT 1;
```

Expected: content is the body plus `[Menu card] [Book table] [Call us]`. If this row is missing but the lead received the message, the migration in Task 1 did not run.

- [ ] **Step 5: Confirm no repeat**

Without tapping, send another matching question. Expected: an ordinary text reply, **not** the same buttons again.

- [ ] **Step 6: Confirm the intake guard**

With Paid Intake enabled, trigger it and get to a payment step. Ask a food question mid-flow. Expected: **no button block** — the intake flow is untouched and uninterrupted.

- [ ] **Step 7: Confirm other channels are unaffected**

Send the same matching question over Instagram or Telegram. Expected: an ordinary text reply, no errors in the logs.
