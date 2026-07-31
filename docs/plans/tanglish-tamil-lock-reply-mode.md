# New reply-language mode: Tanglish, lock to Tamil once the lead texts Tamil script

**Requested for:** Astro Thermal client (operator console), but shipped as a general 5th mode so any tenant can pick it.

**Behavior:** Default reply style is Tanglish (as today's fixed `tanglish` mode). If the lead ever sends a message that is dominantly pure Tamil Unicode script, the AI permanently switches to native Tamil script for the rest of that conversation — even if the lead later goes back to Tanglish or English. A lead texting English or Tanglish never triggers a switch; only pure Tamil script does. This is NOT a request to reply in Tamil (e.g. "tamil la sollunga" does not trigger it) — only the script of what the lead actually writes does.

This does not touch the existing `mirror` / `tanglish` / `english` / `tamil` modes — it is purely additive.

## Why a DB column, not just a smarter prompt

The conversation history fed to the LLM is capped at the last 8 messages (`_recent_thread(db, lead_id, limit=8)`, called at `backend/app/services/ai_reply.py:1132`). A prompt-only "look at history and infer if Tamil was ever used" approach would silently un-lock once the triggering message ages out of that window. The lock must be a persisted per-lead flag, checked once and then trusted for the rest of the conversation.

## Global constraints (bind every task)

- **Stack:** FastAPI (`backend/app/`), Next.js 14 App Router (`frontend/app/operator/(console)`), Supabase Postgres.
- **Language-mode prompt wording is live-tested — do not touch the existing declarative phrasing.** See the docstring on `_language_rule_block` (`backend/app/services/ai_reply.py:391-399`): aggressive "no matter what / never" framing measurably broke gpt-5-nano in production testing (0/8 reliable). The `tanglish` and `tamil` blocks already exist and are already tested — this feature reuses them verbatim by picking which one applies per-turn. Do not rewrite their wording.
- **`_dominant_script()` is the correct primitive for script detection** (`backend/app/services/ai_reply.py:285-306`) — Unicode-block counting, `"ta"` for dominant Tamil script. Do not use `_detect_lang()` for the trigger check — that function also does Tanglish-keyword guessing via Latin-script heuristics, which is the wrong tool here (a Tanglish message must never trigger the lock, only actual Tamil Unicode).
- **Backend tests:** `cd backend && pytest` must stay green, in particular `backend/tests/test_ai_reply_lang_detection.py`.
- **Frontend checks:** `cd frontend && npm run typecheck && npm run lint` must stay clean for touched files.
- **Design tokens only** in the config.tsx addition — no raw Tailwind grays, match the existing `REPLY_LANGUAGE_MODES` list styling exactly (it's rendered generically from the array, so no new JSX should be needed beyond the array entry — verify this in Task 4).
- **Do not apply the migration to the live Supabase project, and do not flip Astro Thermal's live `reply_language_mode` setting.** Write the migration file only. Live application requires separate operator/user authorization and is out of scope for this execution pass.

---

## Task 1: Migration — `leads.tamil_locked`

**New file:** `backend/supabase/migrations/163_leads_tamil_locked.sql` (check `ls backend/supabase/migrations | sort -V | tail -5` first in case a higher number has landed since this plan was written — use the next free integer).

```sql
-- Migration 163: Add tamil_locked to leads for the "Tanglish, lock to Tamil on Tamil script" reply-language mode
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tamil_locked BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN leads.tamil_locked IS 'Set true the first time this lead sends a pure-Tamil-script message under the tanglish_escalate_tamil reply_language_mode; once true, replies stay in Tamil for the rest of the conversation.';
```

Do not run this against the live DB (see Global Constraints). Just create the file matching the repo's existing migration style (see e.g. `backend/supabase/migrations/072_leads_collected_data.sql` for the pattern of a single additive column + comment).

---

## Task 2: Backend — new mode + lock resolution in `ai_reply.py`

**File:** `backend/app/services/ai_reply.py`

**2a. Register the mode.** Line 380:

```python
_LANGUAGE_MODES = {"mirror", "tanglish", "english", "tamil"}
```

becomes:

```python
_LANGUAGE_MODES = {"mirror", "tanglish", "english", "tamil", "tanglish_escalate_tamil"}
```

**2b. Include the new column in the lead select.** Line 1096 currently:

```python
        .select("ai_enabled,score,segment,phone,converted_at,tenant_id,assigned_to,name,blocked_at,needs_human_attention")
```

Add `tamil_locked`:

```python
        .select("ai_enabled,score,segment,phone,converted_at,tenant_id,assigned_to,name,blocked_at,needs_human_attention,tamil_locked")
```

**2c. Resolve the effective mode before building the prompt.** Around lines 1252-1253, currently:

```python
        reply_language_mode = _resolve_reply_language_mode(tenant_id)
        system_prompt += _language_rule_block(reply_language_mode, message)
```

Replace with:

```python
        reply_language_mode = _resolve_reply_language_mode(tenant_id)
        if reply_language_mode == "tanglish_escalate_tamil":
            reply_language_mode = _resolve_tamil_lock(db, lead_id, lead_data, message)
        system_prompt += _language_rule_block(reply_language_mode, message)
```

Note `_language_rule_block` itself needs NO new branch — `_resolve_tamil_lock` below returns either `"tamil"` or `"tanglish"`, both of which `_language_rule_block` already handles (lines 400-417). This keeps the live-tested prompt wording completely untouched, per Global Constraints.

**2d. Add the resolver function.** Place it directly above `_resolve_reply_language_mode` (near line 383), so both are colocated:

```python
def _resolve_tamil_lock(db, lead_id: str, lead_data: dict, message: str) -> str:
    """For the 'tanglish_escalate_tamil' mode: returns 'tamil' once this lead has ever
    sent a pure-Tamil-script message (persisted via leads.tamil_locked, since the
    _recent_thread() history window used for the LLM prompt is only 8 messages and
    can't be trusted to remember a script switch from many turns ago). Returns
    'tanglish' otherwise. Uses _dominant_script(), not _detect_lang() -- a Tanglish
    message (Latin script with Tamil keywords) must never trigger this, only actual
    Tamil Unicode script."""
    if lead_data.get("tamil_locked"):
        return "tamil"
    if _dominant_script(message) == "ta":
        try:
            db.table("leads").update({"tamil_locked": True}).eq("id", str(lead_id)).execute()
        except Exception:
            logger.exception("Failed to persist tamil_locked for lead %s", lead_id)
        return "tamil"
    return "tanglish"
```

Use the module's existing `logger` (already imported/used elsewhere in this file, e.g. line 1103's `logger.info`). Follow the existing `db.table("leads").update({...}).eq("id", str(lead_id)).execute()` pattern already used at lines 825, 1159, 1535 — same style, same error handling posture (log and continue; a failed write to lock the flag should not block the reply going out this turn — it'll just re-evaluate next turn since Tamil script will likely recur).

**2e. Update the `_resolve_reply_language_mode` docstring** (lines 383-388) to mention the console now offers 5 modes, not 4, if it references a count — check current wording and adjust only if it explicitly says "four" or lists all mode names; do not otherwise touch its logic (it already generically falls back to `"mirror"` for any value not in `_LANGUAGE_MODES`, so no logic change needed there beyond Task 2a's set update).

---

## Task 3: Frontend — operator console mode picker

**File:** `frontend/app/operator/(console)/client/[id]/views/config.tsx`

**3a.** Line 23:

```typescript
type ReplyLanguageMode = "mirror" | "tanglish" | "english" | "tamil";
```

becomes:

```typescript
type ReplyLanguageMode = "mirror" | "tanglish" | "english" | "tamil" | "tanglish_escalate_tamil";
```

**3b.** Add an entry to `REPLY_LANGUAGE_MODES` (lines 73-78), after the existing `tanglish` entry:

```typescript
  { id: "tanglish_escalate_tamil", label: "Tanglish, lock to Tamil on request", desc: "Replies in Tanglish by default. If the lead ever sends a message in pure Tamil script, permanently switches to native Tamil script for the rest of that conversation." },
```

**3c.** Verify the rest of the file (the render block around line 866-872 that maps over `REPLY_LANGUAGE_MODES`) needs no further changes — it's already generic over the array. Confirm this by reading lines 855-880 before assuming; if the render block has any mode-specific branching (e.g. hides a warning only for `"mirror"`), extend it consistently, but do not add new UI beyond matching the existing per-option treatment.

**3d.** `npm run typecheck && npm run lint` from `frontend/` must be clean.

---

## Task 4: Tests

**File:** `backend/tests/test_ai_reply_lang_detection.py`

Add `_resolve_tamil_lock` to the import block (alongside `_resolve_reply_language_mode` etc). Add tests covering:

1. `_resolve_tamil_lock` returns `"tanglish"` for a Tanglish message (e.g. `"eppo varuvinga"`) when `lead_data.get("tamil_locked")` is falsy, and does NOT call `db.table(...).update` (use a stub/mock `db` object and assert `.table` was never invoked, or a minimal fake that raises if called with anything other than expected — match whatever mocking convention the rest of this test file / `backend/tests/` already uses for `db`; check e.g. `backend/tests/conftest.py` or other tests that touch `db.table("leads")` for the existing fixture pattern before inventing a new one).
2. `_resolve_tamil_lock` returns `"tamil"` and issues an update when the message is pure Tamil script (e.g. `"என் ஜாதகம் பார்க்கணும்"`) and `tamil_locked` is falsy.
3. `_resolve_tamil_lock` returns `"tamil"` without touching `db` when `lead_data["tamil_locked"]` is already `True`, even if the current message is plain English or Tanglish (proves the lock persists regardless of the current turn's script).
4. `"tanglish_escalate_tamil"` is present in `_LANGUAGE_MODES` and survives `_resolve_reply_language_mode`'s fallback check (i.e. it is not silently rejected back to `"mirror"`).

Run `cd backend && pytest backend/tests/test_ai_reply_lang_detection.py -v` and the full `cd backend && pytest` before considering this task done.

---

## Explicitly out of scope for this execution pass

- Applying migration 163 to the live Supabase project.
- Flipping Astro Thermal's `reply_language_mode` setting to `tanglish_escalate_tamil` in production.
- Any change to the `mirror`, `tanglish`, `english`, or `tamil` mode behavior or prompt wording.
- Any change to `_language_rule_block`'s branching — it should require zero edits.

Both of the first two are for the plan owner (Prem) to trigger manually after code review, per standing policy of not mutating live infra without explicit per-instance authorization.
