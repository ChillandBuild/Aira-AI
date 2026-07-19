# Master Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split AI prompt ownership — the developer writes a behaviour "master prompt" per client in the operator console, the client writes only a plain-language business description in the Knowledge Base.

**Architecture:** The four per-channel `ai_prompts` rows collapse into one row named `master` per tenant. At reply time `ai_reply.py` assembles: master prompt → channel line → business description, then the existing untouched layers (campaign, RAG, lead context, language, accuracy, escalation, catalog). A platform-wide template lives in a new `platform_defaults` table and is copied into each new client at creation.

**Tech Stack:** FastAPI (`backend/app/`), Next.js 14 App Router (`frontend/app/`), Supabase Postgres, pytest.

**Spec:** `docs/superpowers/specs/2026-07-19-master-prompt-design.md`

## Global Constraints

- Layers 5-8 (`_language_rule_block`, `_ACCURACY_RULE`, `_escalation_prompt_block`, catalog block) must not be edited. Their wording is live-tested; changing it is out of scope. Task 3's test is the regression guard.
- All DB access goes through `get_supabase()` — never a raw client.
- Every tenant-scoped query filters on `tenant_id`. No exceptions.
- Backend tests: `cd backend && pytest`. Frontend verify is **both** `npm run lint` **and** `npm run typecheck` — lint alone is what CI enforces on unused imports and `any`.
- Migrations are numbered sequentially in `backend/supabase/migrations/`. The next free number is **143**.
- No new npm or pip dependencies.
- Commit after each task.

---

### Task 1: Migration — `platform_defaults`, seed `master` rows, drop `ai_tune_suggestions`

**Files:**
- Create: `backend/supabase/migrations/143_master_prompt.sql`

**Interfaces:**
- Produces: table `platform_defaults(key text pk, value text, updated_at timestamptz)` with one row `key = 'default_master_prompt'`; an `ai_prompts` row with `name = 'master'` for every tenant that already had a `whatsapp_reply` row.

- [ ] **Step 1: Write the migration**

Create `backend/supabase/migrations/143_master_prompt.sql`:

```sql
-- Master prompt: developer-owned behaviour prompt per client, plus a platform-wide
-- default template copied into new clients at creation.

-- 1. Platform-level defaults. Deliberately NOT app_settings: save_setting(tenant_id=None)
-- writes against _DEFAULT_TENANT_ID (a real tenant), so app_settings has no global scope.
create table if not exists platform_defaults (
  key text primary key,
  value text,
  updated_at timestamptz not null default now()
);

-- Operator-only. No policies are created, so anon/authenticated clients are denied;
-- the backend reaches it with the service role, which bypasses RLS.
alter table platform_defaults enable row level security;

insert into platform_defaults (key, value) values (
  'default_master_prompt',
  'You are the AI assistant for this business.

YOUR ROLE
Your role, expertise, and subject matter are defined entirely by the BUSINESS
DESCRIPTION section below. Adopt that role fully — speak as a knowledgeable member
of that business, never as a generic chatbot. Never say you are an AI, a bot, or a
language model.

REPLY LENGTH
Keep every reply to 2-3 short lines. No paragraphs, no bullet lists, no markdown.
This is a messaging app — write the way a real person texts.

TONE
Warm, confident, and direct. Use the customer''s name when you know it. Ask one
question at a time — never stack multiple questions into one message.

NEXT STEP
End most replies by moving the conversation forward: offer to share details,
suggest booking, or ask the one thing you need in order to help them.

WHAT YOU MUST NOT DO
- Do not invent facts about the business. If it is not in your knowledge base, say
  you will connect them with the team.
- Do not repeat what you already said earlier in the conversation.
- Do not greet again mid-conversation.

EXAMPLES OF GOOD REPLIES
Customer: "hi"
You: "Hi! Welcome. What can I help you with today?"

Customer: "do you do this online or only in person?"
You: "Both work — online over video call, or in person at our office. Which suits
you better?"

Customer: "I''ll think about it"
You: "Of course, take your time. I''ll be right here if anything comes up."'
) on conflict (key) do nothing;

-- 2. Seed one master row per tenant from its existing whatsapp_reply prompt, so live
-- accounts behave identically on deploy day. Tenants with no whatsapp_reply row get
-- no master row and fall back to FALLBACK_PROMPT in ai_reply.py.
insert into ai_prompts (tenant_id, name, content)
select tenant_id, 'master', content
from ai_prompts
where name = 'whatsapp_reply'
on conflict (tenant_id, name) do nothing;

-- 3. Drop the unreachable AI Tune suggestions feature. No frontend caller exists
-- (frontend/lib/api.ts exposes only aiTune.prompts and aiTune.updatePrompt).
drop table if exists ai_tune_suggestions;
```

- [ ] **Step 2: Apply the migration to Supabase**

Apply `143_master_prompt.sql` via the Supabase SQL editor or MCP `execute_sql`.

- [ ] **Step 3: Verify it applied**

Run this SQL and confirm all three results:

```sql
select count(*) as template_rows from platform_defaults where key = 'default_master_prompt';
select count(*) as master_rows from ai_prompts where name = 'master';
select to_regclass('public.ai_tune_suggestions') as should_be_null;
```

Expected: `template_rows` = 1, `master_rows` = the number of tenants that had a
`whatsapp_reply` row, `should_be_null` = NULL.

- [ ] **Step 4: Commit**

```bash
git add backend/supabase/migrations/143_master_prompt.sql
git commit -m "feat: add platform_defaults, seed master prompts, drop ai_tune_suggestions"
```

---

### Task 2: Backend — assemble master prompt + channel + description

**Files:**
- Modify: `backend/app/services/ai_reply.py` (add `_CHANNEL_LABELS`, `_build_base_prompt`; change the call at line 1184)
- Test: `backend/tests/test_master_prompt.py` (create)

**Interfaces:**
- Consumes: `ai_prompts` row `name='master'` and `app_settings` key `business_description` from Task 1.
- Produces: `_build_base_prompt(channel: str, tenant_id: str | None) -> str` in `app.services.ai_reply`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_master_prompt.py`:

```python
from unittest.mock import patch

from app.services import ai_reply


def test_build_base_prompt_includes_master_channel_and_description():
    with patch.object(ai_reply, "_get_prompt", return_value="MASTER BEHAVIOUR"), \
         patch.object(ai_reply, "get_setting", return_value="We sell birth-chart readings."):
        result = ai_reply._build_base_prompt("whatsapp", "tenant-1")

    assert "MASTER BEHAVIOUR" in result
    assert "WhatsApp" in result
    assert "BUSINESS DESCRIPTION:" in result
    assert "We sell birth-chart readings." in result
    # Description must come after the master prompt, never before it.
    assert result.index("MASTER BEHAVIOUR") < result.index("BUSINESS DESCRIPTION:")


def test_build_base_prompt_omits_description_block_when_unset():
    with patch.object(ai_reply, "_get_prompt", return_value="MASTER BEHAVIOUR"), \
         patch.object(ai_reply, "get_setting", return_value=None):
        result = ai_reply._build_base_prompt("telegram", "tenant-1")

    assert "MASTER BEHAVIOUR" in result
    assert "Telegram" in result
    assert "BUSINESS DESCRIPTION:" not in result


def test_build_base_prompt_reads_the_master_row():
    with patch.object(ai_reply, "_get_prompt", return_value="M") as mock_get, \
         patch.object(ai_reply, "get_setting", return_value=None):
        ai_reply._build_base_prompt("instagram", "tenant-9")

    mock_get.assert_called_once_with("master", tenant_id="tenant-9")


def test_build_base_prompt_labels_every_channel():
    labels = {
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "instagram": "Instagram",
        "facebook": "Facebook Messenger",
    }
    for channel, label in labels.items():
        with patch.object(ai_reply, "_get_prompt", return_value="M"), \
             patch.object(ai_reply, "get_setting", return_value=None):
            assert label in ai_reply._build_base_prompt(channel, "t")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_master_prompt.py -v`
Expected: FAIL — `AttributeError: module 'app.services.ai_reply' has no attribute '_build_base_prompt'`

- [ ] **Step 3: Implement `_build_base_prompt`**

In `backend/app/services/ai_reply.py`, add immediately after the `invalidate_prompt_cache`
function (around line 192):

```python
_CHANNEL_LABELS = {
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "instagram": "Instagram",
    "facebook": "Facebook Messenger",
}


def _build_base_prompt(channel: str, tenant_id: str | None) -> str:
    """Assemble the developer-owned master prompt with the channel label and the
    client-owned business description.

    The master prompt (operator console) defines HOW to behave; the description
    (client's Knowledge Base page) defines WHO the assistant is and what the business
    sells. The description is always injected in full and never goes through RAG --
    a retrieval miss would leave the assistant with no role at all.

    The channel label is appended unconditionally rather than substituted into a
    placeholder, so it works regardless of how the developer writes the master text.
    """
    prompt = _get_prompt("master", tenant_id=tenant_id)
    prompt += f"\n\nCHANNEL: You are replying over {_CHANNEL_LABELS.get(channel, channel)}."

    description = (get_setting("business_description", tenant_id=tenant_id) or "").strip()
    if description:
        prompt += "\n\nBUSINESS DESCRIPTION:\n" + description

    return prompt
```

`get_setting` is already imported at module level (line 26) — no new import needed.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_master_prompt.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Wire it into `generate_reply`**

In `backend/app/services/ai_reply.py` line 1184, replace:

```python
        system_prompt = _get_prompt(f"{channel}_reply", tenant_id=lead_data.get("tenant_id"))
```

with:

```python
        system_prompt = _build_base_prompt(channel, lead_data.get("tenant_id"))
```

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest`
Expected: PASS, no new failures versus the pre-change baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_master_prompt.py
git commit -m "feat: assemble reply prompt from master prompt plus business description"
```

---

### Task 3: Backend — regression guard for layers 5-8

**Files:**
- Test: `backend/tests/test_master_prompt.py` (append)

**Interfaces:**
- Consumes: `_build_base_prompt` from Task 2.
- Produces: nothing consumed by later tasks. This task exists solely to prove the spec's "layers 5-8 unchanged" claim, so a future edit to the language or accuracy rule fails loudly.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_master_prompt.py`:

```python
def test_language_rule_mirror_mode_wording_is_unchanged():
    """The mirror-mode LANGUAGE RULE wording is live-tested (12/12 on Gemini 3.1 Flash
    Lite; an aggressive rewording made gpt-5-nano return empty replies 0/8). If this
    test fails, the wording was edited -- re-run that live test before accepting it."""
    block = ai_reply._language_rule_block("mirror", "hello")
    assert "LANGUAGE RULE: Reply in the SAME language style the user just wrote in." in block
    assert "Tanglish" in block
    assert "CUSTOMER'S LATEST MESSAGE SCRIPT:" in block


def test_language_rule_forced_modes_still_present():
    assert "Your reply style is always Tanglish" in ai_reply._language_rule_block("tanglish", "hi")
    assert "Always reply in English only" in ai_reply._language_rule_block("english", "hi")
    assert "Always reply in native Tamil script" in ai_reply._language_rule_block("tamil", "hi")


def test_accuracy_rule_still_forbids_stating_prices():
    assert "ACCURACY RULE:" in ai_reply._ACCURACY_RULE
    assert "Never state a specific price, fee, or payment method" in ai_reply._ACCURACY_RULE
```

- [ ] **Step 2: Run the test**

Run: `cd backend && pytest tests/test_master_prompt.py -v`
Expected: PASS immediately — these assert on code that Tasks 1-2 did not touch. A
failure here means an earlier task edited a protected layer and must be reverted.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_master_prompt.py
git commit -m "test: guard language and accuracy rule wording against edits"
```

---

### Task 4: Backend — replace AI Tune with description endpoints

**Files:**
- Modify: `backend/app/routes/ai_tune.py` (delete lines 19-36, 43-83, 130-273; rewrite as below)
- Modify: `backend/app/routes/operator.py:2065` (remove `ai_tune_suggestions` from the table list)
- Test: `backend/tests/test_ai_tune_routes.py` (create)

**Interfaces:**
- Consumes: `app_settings` key `business_description`; `_auto_generate_rubric` (kept, input changed).
- Produces: `GET /api/v1/ai-tune/description` → `{"description": str}`; `PUT /api/v1/ai-tune/description` with body `{"description": str}` → `{"description": str}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_ai_tune_routes.py`:

```python
from app.routes import ai_tune


def test_removed_endpoints_are_gone():
    """The analyze/suggestions endpoints were unreachable dead code -- no frontend
    caller existed. Assert they are not re-added."""
    paths = {route.path for route in ai_tune.router.routes}
    assert "/analyze" not in paths
    assert "/suggestions" not in paths
    assert not any("suggestions" in p for p in paths)
    assert not hasattr(ai_tune, "META_PROMPT")


def test_description_endpoints_exist():
    paths = {route.path for route in ai_tune.router.routes}
    assert "/description" in paths


def test_rubric_prompt_is_built_from_the_description():
    """The rubric captures THIS business's conversion signals, which now live in the
    client's description, not in the developer's generic master prompt."""
    built = ai_tune._rubric_prompt("We are a Vedic astrology consultancy.")
    assert "We are a Vedic astrology consultancy." in built
    assert "9-10" in built
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_ai_tune_routes.py -v`
Expected: FAIL — `/analyze` is still present and `_rubric_prompt` does not exist.

- [ ] **Step 3: Rewrite `ai_tune.py`**

Replace the entire contents of `backend/app/routes/ai_tune.py` with:

```python
import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config_dynamic import get_setting, save_setting, invalidate_cache
from app.dependencies.tenant import get_tenant_id, require_owner
from app.services.groq_client import get_groq_client

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_owner)])

_TUNE_MODEL = "llama-3.3-70b-versatile"


class DescriptionUpdate(BaseModel):
    description: str


def _rubric_prompt(description: str) -> str:
    """Build the rubric-generation prompt from the client's business description.

    Input is the DESCRIPTION, not the master prompt: the rubric is meant to capture
    this specific business's conversion signals (a hot lead for an astrologer looks
    nothing like one for a real-estate agent). The master prompt is generic behaviour
    shared across clients and would produce an identical, useless rubric for everyone.
    """
    return f"""You are configuring a lead scoring system for a B2B sales team.

Based on this business's own description of what it does, write a lead scoring rubric
(1-10 scale). The rubric should reflect THIS specific business's conversion signals —
not generic ones.

Business description:
{description[:1500]}

Write a rubric in this exact format (5 lines, one per score band):
- 9-10: [High intent signals specific to this business]
- 7-8: [Warm signals specific to this business]
- 5-6: [Neutral signals]
- 3-4: [Low engagement signals]
- 1-2: [Disqualified / not interested signals]

Reply with ONLY the 5 rubric lines. No explanation, no preamble."""


async def _auto_generate_rubric(description: str, tenant_id: str, force: bool = False) -> None:
    """Generate a domain-appropriate scoring rubric from the tenant's business
    description. Best-effort: a failure here must never fail the description save."""
    try:
        if not force:
            existing_rubric = get_setting("scoring_rubric", tenant_id=tenant_id)
            if existing_rubric and existing_rubric.strip():
                logger.info(f"Scoring rubric already exists for tenant {tenant_id} — skipping auto-generation")
                return

        try:
            client = get_groq_client(tenant_id, is_async=True)
        except Exception:
            return

        resp = await client.chat.completions.create(
            model=_TUNE_MODEL,
            messages=[{"role": "user", "content": _rubric_prompt(description)}],
            temperature=0.3,
            max_tokens=300,
        )
        rubric = resp.choices[0].message.content.strip()
        if rubric and "9-10" in rubric:
            save_setting("scoring_rubric", rubric, tenant_id=tenant_id)
            logger.info(f"Auto-generated scoring rubric for tenant {tenant_id}")
    except Exception as e:
        logger.warning(f"Auto-rubric generation failed for tenant {tenant_id}: {e}")


@router.get("/description")
async def get_description(tenant_id: str = Depends(get_tenant_id)):
    return {"description": get_setting("business_description", tenant_id=tenant_id) or ""}


@router.put("/description")
async def update_description(
    payload: DescriptionUpdate, tenant_id: str = Depends(get_tenant_id)
):
    description = payload.description.strip()
    save_setting("business_description", description, tenant_id=tenant_id)
    invalidate_cache("business_description")

    if description:
        _task = asyncio.create_task(_auto_generate_rubric(description, tenant_id, force=True))
        _task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {"description": description}
```

- [ ] **Step 4: Remove the dropped table from the operator table list**

In `backend/app/routes/operator.py` line 2065, delete `"ai_tune_suggestions", ` from the
list so data-ops purge/export does not query a dropped relation:

```python
    "ad_campaigns", "ai_prompts", "app_notifications",
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && pytest tests/test_ai_tune_routes.py -v`
Expected: PASS, 3 passed

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest`
Expected: PASS. If a test referenced the removed `/analyze` route or the old
`_auto_generate_rubric(system_prompt, ...)` signature, delete that test — the feature it
covered is gone by design.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/ai_tune.py backend/app/routes/operator.py backend/tests/test_ai_tune_routes.py
git commit -m "feat: replace AI Tune prompt editing with business description endpoints"
```

---

### Task 5: Backend — operator endpoints for the template and per-client master

**Files:**
- Modify: `backend/app/routes/operator.py` (add template routes; extend `client_config` GET at line 1011 and `update_client_config` PATCH at line 1041; seed master row in `create_client` at line 239)
- Test: `backend/tests/test_operator_master_prompt.py` (create)

**Interfaces:**
- Consumes: `platform_defaults` and the `master` `ai_prompts` row from Task 1; `invalidate_prompt_cache` from `app.services.ai_reply`.
- Produces:
  - `GET /api/v1/operator/prompt-template` → `{"template": str}`
  - `PUT /api/v1/operator/prompt-template` body `{"template": str}` → `{"template": str}`
  - `GET /api/v1/operator/clients/{tenant_id}/config` gains `master_prompt: str` and `business_description: str` at the top level of the response
  - `PATCH /api/v1/operator/clients/{tenant_id}/config` accepts `master_prompt: str | None`
  - `get_default_master_prompt() -> str` in `app.routes.operator`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_operator_master_prompt.py`:

```python
from unittest.mock import MagicMock, patch

from app.routes import operator
from app.services.ai_reply import FALLBACK_PROMPT


def test_template_routes_exist():
    paths = {route.path for route in operator.router.routes}
    assert "/prompt-template" in paths


def test_get_default_master_prompt_returns_stored_template():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"value": "STORED TEMPLATE"}
    ]
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == "STORED TEMPLATE"


def test_get_default_master_prompt_falls_back_when_table_unreadable():
    """Client creation must never fail on a template read."""
    db = MagicMock()
    db.table.side_effect = Exception("relation does not exist")
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == FALLBACK_PROMPT


def test_get_default_master_prompt_falls_back_when_row_missing():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch.object(operator, "get_supabase", return_value=db):
        assert operator.get_default_master_prompt() == FALLBACK_PROMPT
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_operator_master_prompt.py -v`
Expected: FAIL — `AttributeError: module 'app.routes.operator' has no attribute 'get_default_master_prompt'`

- [ ] **Step 3: Add the template helper and routes**

In `backend/app/routes/operator.py`, add immediately above `@router.get("/clients/{tenant_id}/config")` (line 950):

```python
class PromptTemplateUpdate(BaseModel):
    template: str


def get_default_master_prompt() -> str:
    """Read the platform-wide master prompt template. Falls back to FALLBACK_PROMPT on
    any failure -- onboarding must never break because a template row is missing."""
    from app.services.ai_reply import FALLBACK_PROMPT
    try:
        db = get_supabase()
        row = (
            db.table("platform_defaults")
            .select("value")
            .eq("key", "default_master_prompt")
            .limit(1)
            .execute()
        )
        value = (row.data[0].get("value") if row.data else None) or ""
        return value.strip() or FALLBACK_PROMPT
    except Exception as e:
        logger.warning(f"Default master prompt read failed, using fallback: {e}")
        return FALLBACK_PROMPT


@router.get("/prompt-template")
def read_prompt_template(_admin: dict = Depends(get_system_admin)):
    return {"template": get_default_master_prompt()}


@router.put("/prompt-template")
def write_prompt_template(
    payload: PromptTemplateUpdate, _admin: dict = Depends(get_system_admin)
):
    db = get_supabase()
    db.table("platform_defaults").upsert(
        {"key": "default_master_prompt", "value": payload.template},
        on_conflict="key",
    ).execute()
    return {"template": payload.template}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_operator_master_prompt.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Seed the master row at client creation**

In `backend/app/routes/operator.py`, in `create_client`, immediately after the
`# Seed app_settings` block ends (after line 243) and before the
`# No tenant_subscriptions row is created here` comment, insert:

```python
        # Seed this client's master prompt from the platform template. The template is
        # COPIED, not referenced -- later edits to the template must not alter the
        # behaviour of clients that are already live.
        db.table("ai_prompts").insert({
            "tenant_id": tenant_id,
            "name": "master",
            "content": get_default_master_prompt(),
        }).execute()
```

Then add `ai_prompts` cleanup to the failure path. After the `app_settings` cleanup block
(lines 272-275), insert:

```python
            try:
                db.table("ai_prompts").delete().eq("tenant_id", tenant_id).execute()
            except Exception as cleanup_err:
                logger.error(f"Failed to delete orphaned ai_prompts for {tenant_id}: {cleanup_err}")
```

- [ ] **Step 6: Expose master prompt and description in the client config GET**

In `client_config`, immediately before the `return {` at line 996, insert:

```python
    master_prompt = ""
    try:
        prompt_row = (
            db.table("ai_prompts")
            .select("content")
            .eq("tenant_id", tenant_id)
            .eq("name", "master")
            .limit(1)
            .execute()
        )
        master_prompt = (prompt_row.data[0].get("content") if prompt_row.data else "") or ""
    except Exception as e:
        logger.warning("Master prompt read failed for tenant %s: %s", tenant_id, e)
```

Then add these two keys to the returned dict, directly after the `"enabled_features"` line:

```python
        "master_prompt": master_prompt,
        "business_description": settings_map.get("business_description") or "",
```

- [ ] **Step 7: Accept master prompt writes in the config PATCH**

Change the `ClientConfigUpdate` model at line 1037 to:

```python
class ClientConfigUpdate(BaseModel):
    settings: dict[str, str | bool] | None = None
    master_prompt: str | None = None
```

Then in `update_client_config`, replace the guard at lines 1047-1048:

```python
    if not payload.settings:
        raise HTTPException(status_code=400, detail="No settings to update")
```

with:

```python
    if not payload.settings and payload.master_prompt is None:
        raise HTTPException(status_code=400, detail="No settings to update")
```

And immediately after the tenant-existence check (after line 1053), insert:

```python
    if payload.master_prompt is not None:
        db.table("ai_prompts").upsert(
            {"tenant_id": tenant_id, "name": "master", "content": payload.master_prompt},
            on_conflict="tenant_id,name",
        ).execute()
        from app.services.ai_reply import invalidate_prompt_cache
        invalidate_prompt_cache("master")
        if not payload.settings:
            return {"updated": ["master_prompt"]}
```

- [ ] **Step 8: Run the full backend suite**

Run: `cd backend && pytest`
Expected: PASS, no new failures.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routes/operator.py backend/tests/test_operator_master_prompt.py
git commit -m "feat: operator endpoints for prompt template and per-client master prompt"
```

---

### Task 6: Frontend — API client methods

**Files:**
- Modify: `frontend/lib/api.ts` (replace the `aiTune` block at lines 1374-1382)

**Interfaces:**
- Consumes: the endpoints from Tasks 4 and 5.
- Produces: `api.aiTune.description()`, `api.aiTune.updateDescription(text)`. Operator calls use raw `fetch` in their own components, matching the existing pattern in `views/config.tsx`.

- [ ] **Step 1: Replace the `aiTune` block**

In `frontend/lib/api.ts`, replace lines 1374-1382 (the whole `aiTune: { ... }` block,
including `prompts` and `updatePrompt`) with:

```typescript
  aiTune: {
    description: async () => {
      const res = await apiFetch<{ description: string }>(`/api/v1/ai-tune/description`);
      return res.description || "";
    },
    updateDescription: (description: string) =>
      apiFetch<{ description: string }>(`/api/v1/ai-tune/description`, {
        method: "PUT",
        body: JSON.stringify({ description }),
      }),
  },
```

- [ ] **Step 2: Remove the now-unused `AIPrompt` type**

Search for the `AIPrompt` type definition and any remaining imports of it:

```bash
cd frontend && grep -rn "AIPrompt" --include=*.ts --include=*.tsx .
```

Delete the `AIPrompt` interface/type declaration. Leave the usages inside
`app/dashboard/knowledge/page.tsx` for now — Task 7 removes that file's prompt code, and
lint will pass again at the end of Task 7.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: errors only in `app/dashboard/knowledge/page.tsx` (it still references the
removed `api.aiTune.prompts` and `AIPrompt`). Task 7 clears these. Do not commit yet —
this task and Task 7 land in one commit at the end of Task 7.

---

### Task 7: Frontend — Knowledge Base "Description" tab

**Files:**
- Modify: `frontend/app/dashboard/knowledge/page.tsx`

**Interfaces:**
- Consumes: `api.aiTune.description` / `api.aiTune.updateDescription` from Task 6.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Replace the tab identifier**

Replace lines 64-71:

```typescript
  const rawTab = searchParams.get("tab");
  const tab = (rawTab === "ai-tune" ? "ai-tune" : "documents") as "documents" | "ai-tune";

  const setTab = (val: "documents" | "ai-tune") => {
```

with:

```typescript
  const rawTab = searchParams.get("tab");
  // "ai-tune" is still accepted so existing bookmarks and links keep working.
  const tab = (rawTab === "description" || rawTab === "ai-tune" ? "description" : "documents") as
    | "documents"
    | "description";

  const setTab = (val: "documents" | "description") => {
```

- [ ] **Step 2: Replace the prompt state with description state**

Replace lines 79-84:

```typescript
  // AI Tune
  const [prompts, setPrompts] = useState<AIPrompt[]>([]);
  const [activeName, setActiveName] = useState<string>("whatsapp_reply");
  const [draft, setDraft] = useState<string>("");
  const [tuneMsg, setTuneMsg] = useState<string | null>(null);
  const [tuneSaving, setTuneSaving] = useState(false);
```

with:

```typescript
  // Business Description
  const [description, setDescription] = useState<string>("");
  const [savedDescription, setSavedDescription] = useState<string>("");
  const [descSaving, setDescSaving] = useState(false);
```

- [ ] **Step 3: Replace the load effects**

Replace lines 104-114:

```typescript
  useEffect(() => {
    if (tab === "ai-tune") {
      if (prompts.length === 0) loadPrompts();
      loadAiTuneSettings();
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const cur = prompts.find((x) => x.name === activeName);
    if (cur) setDraft(cur.content);
  }, [activeName, prompts]);
```

with:

```typescript
  useEffect(() => {
    if (tab === "description") {
      loadDescription();
      loadAiTuneSettings();
    }
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 4: Replace `loadPrompts` and `savePrompt`**

Replace `loadPrompts` (lines 154-164) with:

```typescript
  async function loadDescription() {
    try {
      const d = await api.aiTune.description();
      setDescription(d);
      setSavedDescription(d);
    } catch {}
  }
```

Then delete `savePrompt` (lines 248-263) and the channel-selector helper immediately above
it (the function ending `setActiveName(channelId);` at line 245), and add:

```typescript
  async function saveDescription() {
    setDescSaving(true);
    try {
      await api.aiTune.updateDescription(description);
      setSavedDescription(description);
      toast.success("Description saved. Updating scoring rubric…");
      setTimeout(loadAiTuneSettings, 4000);
    } catch {
      toast.error("Failed to save description. Please try again.");
    } finally {
      setDescSaving(false);
    }
  }
```

- [ ] **Step 5: Replace the tab button and the editor JSX**

At line 285, change the tab button's `onClick` and its active check from `"ai-tune"` to
`"description"`, and its label text to `Description`.

At line 299, change `{tab !== "ai-tune" && (` to `{tab !== "description" && (`.

Then replace the prompt-editor JSX — the channel selector, the prompt textarea, and the
save button ending at line 555 (`onClick={savePrompt}`) — with:

```tsx
          <div className="bg-surface rounded-card p-6 border border-surface-mid space-y-4">
            <div>
              <h3 className="font-display font-bold text-lg text-on-surface">Business Description</h3>
              <p className="font-body text-sm text-on-surface-muted mt-1">
                Describe your business, your products or services, and the role your
                assistant plays for customers. Write it in plain language — how you would
                explain it to a new employee on their first day. Your assistant uses this
                to understand who it is and what it is talking about.
              </p>
            </div>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={!canManageKnowledge}
              rows={12}
              placeholder="Example: We are a Vedic astrology consultancy based in Chennai. We offer birth-chart readings, marriage compatibility matching, and gemstone guidance. Consultations happen online over video call or in person at our office. Most customers come to us with questions about marriage timing, career direction, or family matters."
              className="w-full px-4 py-3 rounded-xl bg-surface border border-surface-mid focus:outline-none focus:ring-2 focus:ring-primary font-body text-sm resize-y"
            />
            <div className="flex justify-end">
              <button
                onClick={saveDescription}
                disabled={descSaving || description === savedDescription || !canManageKnowledge}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white font-label text-sm font-semibold disabled:opacity-50"
              >
                <Save size={14} /> {descSaving ? "Saving…" : "Save Description"}
              </button>
            </div>
          </div>
```

The scoring-rubric block below it (lines 573-592) stays exactly as it is.

- [ ] **Step 6: Clean up unused imports**

Run: `cd frontend && npm run lint`

Remove every import the linter now reports as unused — `AIPrompt` and any icon that was
only used by the deleted channel selector. Re-run until clean. CI enforces lint, so an
unused import fails the build even though `tsc` passes.

- [ ] **Step 7: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: both PASS with no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/api.ts frontend/app/dashboard/knowledge/page.tsx
git commit -m "feat: replace client prompt editor with business description"
```

---

### Task 8: Frontend — operator "Master Prompt" section in the client Config tab

**Files:**
- Modify: `frontend/app/operator/(console)/client/[id]/views/config.tsx`
- Modify: `frontend/app/operator/(console)/client/[id]/types.ts`

**Interfaces:**
- Consumes: `GET`/`PATCH /api/v1/operator/clients/{tenant_id}/config` from Task 5, which
  now returns `master_prompt` and `business_description` and accepts `master_prompt`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Extend the config type**

In `frontend/app/operator/(console)/client/[id]/types.ts`, find the type describing the
client-config response (the one with `enabled_features`, `credentials_status`, `settings`)
and add two fields to it:

```typescript
  master_prompt: string;
  business_description: string;
```

If that type is declared locally inside `config.tsx` rather than in `types.ts`, add the
fields there instead and skip editing `types.ts`.

- [ ] **Step 2: Add state and a save handler**

In `config.tsx`, alongside the existing state declarations, add:

```typescript
  const [masterPrompt, setMasterPrompt] = useState<string>("");
  const [savedMasterPrompt, setSavedMasterPrompt] = useState<string>("");
  const [promptSaving, setPromptSaving] = useState(false);
```

After the config load populates `config`, sync the draft. Add this effect:

```typescript
  useEffect(() => {
    if (config) {
      setMasterPrompt(config.master_prompt || "");
      setSavedMasterPrompt(config.master_prompt || "");
    }
  }, [config]);
```

Then add the save handler, following the existing `fetch` + PATCH pattern used by
`updateReplyLanguageMode` in this file:

```typescript
  async function saveMasterPrompt() {
    setPromptSaving(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/operator/clients/${tenantId}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ master_prompt: masterPrompt }),
      });
      if (!res.ok) throw new Error("Save failed");
      setSavedMasterPrompt(masterPrompt);
      setPromptError(null);
    } catch {
      setPromptError("Could not save the master prompt. Please try again.");
    } finally {
      setPromptSaving(false);
    }
  }
```

Add the matching state alongside the others:

```typescript
  const [promptError, setPromptError] = useState<string | null>(null);
```

Use the same variable this file already uses for the tenant id in its other PATCH calls
(read it from the surrounding component — do not introduce a new prop).

- [ ] **Step 3: Add the UI section**

Add this section to the rendered config view, following the card markup used by the
neighbouring settings sections in this file:

```tsx
      <div className="space-y-4">
        <div>
          <h3 className="font-display font-bold text-lg">Master Prompt</h3>
          <p className="font-body text-sm text-on-surface-muted mt-1">
            Defines how this client&apos;s assistant behaves — reply length, tone, and
            worked examples. The client cannot edit this. They supply only the business
            description shown below, which tells the assistant what it is talking about.
          </p>
        </div>

        <textarea
          value={masterPrompt}
          onChange={(e) => setMasterPrompt(e.target.value)}
          rows={20}
          className="w-full px-4 py-3 rounded-xl bg-surface border border-surface-mid focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs resize-y"
        />

        {promptError && (
          <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 font-body text-sm text-red-600">
            {promptError}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={saveMasterPrompt}
            disabled={promptSaving || masterPrompt === savedMasterPrompt}
            className="px-4 py-2 rounded-xl bg-primary text-white font-label text-sm font-semibold disabled:opacity-50"
          >
            {promptSaving ? "Saving…" : "Save Master Prompt"}
          </button>
        </div>

        <div>
          <h4 className="font-label text-xs font-semibold text-on-surface-muted mb-1">
            Client&apos;s business description (read-only)
          </h4>
          <pre className="whitespace-pre-wrap px-4 py-3 rounded-xl bg-surface-low border border-surface-mid font-body text-xs text-on-surface-muted">
            {config?.business_description || "The client has not written a description yet."}
          </pre>
        </div>
      </div>
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/operator/(console)/client/[id]/views/config.tsx" "frontend/app/operator/(console)/client/[id]/types.ts"
git commit -m "feat: master prompt editor in operator client config"
```

---

### Task 9: Frontend — operator "Default Master Prompt" page

**Files:**
- Create: `frontend/app/operator/(console)/prompt-template/page.tsx`
- Modify: `frontend/app/operator/(console)/components/operator-sidebar.tsx`

**Interfaces:**
- Consumes: `GET`/`PUT /api/v1/operator/prompt-template` from Task 5.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Create the page**

Create `frontend/app/operator/(console)/prompt-template/page.tsx`:

```tsx
"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";

export default function PromptTemplatePage() {
  const [template, setTemplate] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/operator/prompt-template`, { headers: auth });
        if (!res.ok) throw new Error("Load failed");
        const data = (await res.json()) as { template: string };
        setTemplate(data.template || "");
        setSaved(data.template || "");
      } catch {
        setError("Could not load the template.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/operator/prompt-template`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ template }),
      });
      if (!res.ok) throw new Error("Save failed");
      setSaved(template);
    } catch {
      setError("Could not save the template.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="p-8 font-body text-sm text-on-surface-muted">Loading…</div>;
  }

  return (
    <div className="p-8 space-y-4 max-w-4xl">
      <div>
        <h1 className="font-display font-bold text-2xl">Default Master Prompt</h1>
        <p className="font-body text-sm text-on-surface-muted mt-1">
          This template is copied into a new client&apos;s master prompt when the client is
          created. Editing it here does <strong>not</strong> change any existing client —
          to change a live client, edit their master prompt on their Config tab.
        </p>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 font-body text-sm text-red-600">
          {error}
        </div>
      )}

      <textarea
        value={template}
        onChange={(e) => setTemplate(e.target.value)}
        rows={28}
        className="w-full px-4 py-3 rounded-xl bg-surface border border-surface-mid focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs resize-y"
      />

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving || template === saved}
          className="px-4 py-2 rounded-xl bg-primary text-white font-label text-sm font-semibold disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save Template"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the sidebar link**

In `frontend/app/operator/(console)/components/operator-sidebar.tsx`, add a nav entry
pointing at `/operator/prompt-template` labelled "Default Prompt", following the exact
shape of the existing entries in that file (same icon import style from `lucide-react`,
same object keys). Use the `FileText` icon.

- [ ] **Step 3: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: both PASS.

- [ ] **Step 4: Manual verification**

Start both servers:

```bash
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```

Verify each of these:
1. `/operator/prompt-template` loads the seeded template, edits save, a reload shows the edit.
2. An existing client's Config tab shows their master prompt, and the read-only
   description box below it.
3. Editing and saving a client's master prompt persists across a page reload.
4. The client dashboard Knowledge Base page shows a "Description" tab (not "AI Tune"),
   with no prompt or channel selector anywhere on it.
5. Saving a description persists, and the scoring rubric below it updates within ~10s.

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/operator/(console)/prompt-template/page.tsx" "frontend/app/operator/(console)/components/operator-sidebar.tsx"
git commit -m "feat: default master prompt template page in operator console"
```

---

### Task 10: End-to-end verification

**Files:** none — verification only.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && pytest`
Expected: PASS, zero failures.

- [ ] **Step 2: Run frontend verification**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`
Expected: all three PASS.

- [ ] **Step 3: Verify a real reply end-to-end**

With the backend running, send a test inbound message to a tenant that has both a master
prompt and a business description set. Confirm in the backend logs that a reply was
generated, and that the reply reflects both the master prompt's rules (2-3 lines, in
character) and the description's domain.

- [ ] **Step 4: Confirm no orphaned references remain**

```bash
cd backend && grep -rn "ai_tune_suggestions\|whatsapp_reply\|META_PROMPT" app/
cd ../frontend && grep -rn "aiTune.prompts\|updatePrompt\|AIPrompt" .
```

Expected: no matches in `backend/app/` and none in `frontend/` outside `node_modules`.
Matches in `backend/supabase/migrations/` are historical and correct — leave them.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: master prompt end-to-end verification"
```
