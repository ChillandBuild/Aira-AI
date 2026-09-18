# Knowledge Auto-Sort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One upload place. Each document is split into rules (Description), facts (RAG) and junk, the client reviews the result before anything goes live, and every change is versioned.

**Architecture:** Three pure modules (sectioning and fact checks, Description line diffs, version storage) sit under one orchestration service, `knowledge_sort.py`. That service calls the tenant's own model through `_llm_chat`, writes a pending `knowledge_reviews` row, and applies it on approval. `full_text` becomes facts-only for sorted documents, so retrieval, the full-text fallback and the preview never see the rules. The frontend adds three colocated modals plus a pure `descriptionDiff.ts` that mirrors the backend diff for previews.

**Tech Stack:** FastAPI, supabase-py, pytest + pytest-asyncio, Next.js 14, TypeScript, vitest, Tailwind, lucide-react, sonner.

**Spec:** `docs/superpowers/specs/2026-09-18-knowledge-auto-sort-design.md`

**Code location:** the complete implementation for each task is the committed file named in its **Files** block. This plan is kept compact (tests, interfaces and exact behaviour) so it stays readable. Executors read the spec together with this plan.

## Global Constraints

- `tenant_id` always comes from `get_tenant_id`, never from a request body. Every query filters by `tenant_id`.
- Reads need `knowledge.view`. Writes need `knowledge.manage`, **plus** `role == "owner"` whenever the Description text changes.
- Error statuses: `409` stale · `422` Description would be empty · `403` owner required · `404` missing · `400` other. `detail` is a plain-language **string** (the frontend's `apiFetch` does `new Error(err.detail)`).
- Facts are never rewritten. Every number, URL and email in an extracted fact must appear in its source section.
- Soft Description limit: 1,200 words. Warn, never block.
- LLM calls: `_llm_chat(..., purpose="knowledge_sort", temperature=0.1)`. JSON parsed with one retry.
- New migration: `backend/supabase/migrations/190_knowledge_auto_sort.sql`. Live latest is `189_ad_creative_delivery_status`.
- Frontend: `npm run typecheck` **and** `npm run lint` both clean. Render and screenshot before handover.
- No `git push`. Commits are scoped with an explicit pathspec.

## File Map

| File | Responsibility |
|---|---|
| `backend/supabase/migrations/190_knowledge_auto_sort.sql` | new columns + `knowledge_versions` + `knowledge_reviews` + RLS |
| `backend/app/services/knowledge_sections.py` | `split_sections`, `critical_tokens`, `unverified_tokens`, `verify_fact` (pure) |
| `backend/app/services/description_diff.py` | `lines_of`, `normalize`, `diff_hunks`, `apply_hunks`, `insert_under_heading`, `replace_exact_line`, `remove_lines`, `client_lines`, `closest_line` (pure) |
| `backend/app/services/knowledge_versions.py` | `current_description_version`, `save_description`, `save_facts_version`, `list_versions`, `get_version` |
| `backend/app/services/knowledge_sort.py` | errors, LLM prompts, `run_sort`, `sort_document`, `prepare_resort`, `build_review_payload`, `apply_review`, `discard_review`, `update_facts`, `build_delete_preview`, `delete_document`, `restore_version`, `index_facts` |
| `backend/app/services/ai_reply.py` | `_llm_chat` gains keyword-only `purpose`, `temperature` (defaults unchanged) |
| `backend/app/services/knowledge_service.py` | `DOCS_BUCKET`; `process_document` extracts, then hands off to `sort_document` |
| `backend/app/routes/knowledge.py` | new endpoints; trimmed list payload; upload `replaces_document_id`; delete via preview |
| `backend/app/routes/ai_tune.py` | `PUT /description` via `save_description`; `queue_rubric_for_description` |
| `backend/tests/fake_supabase.py` | in-memory supabase-py query fake for service tests |
| `frontend/lib/api.ts` | review/version/delete-preview types and methods |
| `frontend/app/dashboard/knowledge/descriptionDiff.ts` (+ `.test.ts`) | mirror of the diff helpers + `lineDiff` + `buildFinalDescription` |
| `frontend/app/dashboard/knowledge/KnowledgeReviewModal.tsx` | review screen (spec §5) |
| `frontend/app/dashboard/knowledge/KnowledgeHistoryModal.tsx` | version history + restore (spec §7) |
| `frontend/app/dashboard/knowledge/DeleteDocumentModal.tsx` | delete preview (spec §6.3) |
| `frontend/app/dashboard/knowledge/page.tsx` | wiring: statuses, replace picker, new lock, facts preview/edit, History, copy |

---

### Task 1: Migration 190

**Files:** Create `backend/supabase/migrations/190_knowledge_auto_sort.sql`

- `knowledge_documents` gains `source_text text`, `rule_lines jsonb not null default '[]'`, `sorted_at timestamptz`, `sort_state text check (sort_state in ('sorting','review','failed'))`.
- `knowledge_versions`: `id`, `tenant_id → tenants`, `kind in ('description','facts')`, `document_id → knowledge_documents on delete cascade`, `content`, `reason in ('baseline','edit','upload','delete_document','resort','restore')`, `created_by uuid`, `created_at default clock_timestamp()` (strictly increasing inside one transaction). Check: description ⇔ `document_id is null`. Index `(tenant_id, kind, document_id, created_at desc)`.
- `knowledge_reviews`: the columns from spec §9, including `origin in ('upload','resort')` and `status in ('pending','applied','discarded')`. `replaces_document_id on delete set null`, `base_version_id on delete set null`.
- RLS on both tables mirrors `knowledge_documents`: select `is_tenant_member(tenant_id)`; insert/update/delete `is_tenant_owner(tenant_id)`.
- [ ] Write the file. Applied live in Task 12, after review.
- [ ] Commit `feat(db): migration 190 knowledge auto-sort`.

### Task 2: `knowledge_sections.py`

**Interfaces — Produces:** `Section(id: str, text: str)`, `split_sections(text, max_chars=2500) -> list[Section]`, `critical_tokens(text) -> set[str]`, `unverified_tokens(candidate, *sources) -> set[str]`, `verify_fact(fact, source) -> bool`.

- [ ] Tests `backend/tests/test_knowledge_sections.py`:
  - blank-line blocks are packed into sections ≤ max; ids are `s1..sN`
  - a block longer than max is hard-split on a newline or sentence boundary
  - a heading-looking first line starts a new section once the current one is ≥ 400 chars
  - `critical_tokens("Starts ₹29. https://x.in/a/. Call 98400 12345, 1,10,000+")` ⊇ `{"29","https://x.in/a/","98400","12345","110000"}`
  - `verify_fact("from ₹49", "from ₹29")` is False; `verify_fact("from ₹29", "Charges ₹29-lendhu")` is True; a changed URL fails
- [ ] Run and fail → implement → pass → commit.

### Task 3: `description_diff.py`

**Produces:** `normalize`, `normalize_text`, `lines_of`, `Hunk(id, kind, start, old_lines, new_lines, touches_client_lines)` + `to_dict()`, `client_lines(desc, machine)`, `diff_hunks(current, proposed, machine) -> list[Hunk]`, `apply_hunks(current, hunks, accepted_ids) -> str`, `is_heading_line`, `insert_under_heading(text, heading, line)`, `replace_exact_line(text, old, new) -> str | None`, `remove_lines(text, normalized_set) -> str`, `closest_line(target, candidates, cutoff=0.6)`.

Heading = stripped, ≤ 60 chars, contains an ASCII capital, equals its own uppercase. The same rule is used in the TypeScript mirror.

- [ ] Tests `backend/tests/test_description_diff.py`:
  - applying all hunks yields the proposed text; applying none yields the current text
  - whitespace-only differences produce no hunk
  - a hunk that edits a line absent from `machine` has `touches_client_lines=True`
  - `insert_under_heading` places the line at the end of that section, before the next heading and trailing blanks; a missing heading appends at the end
  - `replace_exact_line` returns None when the line is gone
  - `remove_lines` collapses doubled blank lines
- [ ] Fail → implement → pass → commit.

### Task 4: `_llm_chat` purpose and temperature

**Files:** Modify `backend/app/services/ai_reply.py:65`. Test `backend/tests/test_ai_reply_llm_wiring.py`.

- [ ] Test: patch `_resolve_provider` → `("groq","m")` and `groq_chat_completion` (AsyncMock); calling `_llm_chat(msgs, max_tokens=9, tenant_id="t", purpose="knowledge_sort", temperature=0.1)` passes `purpose="knowledge_sort", temperature=0.1`. A default call still passes `purpose="ai_reply", temperature=0.4`.
- [ ] Implement keyword-only params → pass → commit.

### Task 5: Fake DB, versions service, `ai_tune` write path

**Files:** Create `backend/tests/fake_supabase.py`, `backend/app/services/knowledge_versions.py`, `backend/tests/test_knowledge_versions.py`. Modify `backend/app/routes/ai_tune.py`.

**Produces:**
- `current_description(tenant_id) -> str`
- `current_description_version(db, tenant_id) -> dict` (writes a `baseline` row when there is none, or when the live text differs from the latest version)
- `save_description(db, tenant_id, text, reason, user_id) -> dict`
- `save_facts_version(db, tenant_id, document_id, text, reason, user_id) -> dict`
- `latest_version`, `list_versions(db, tenant_id, kind, document_id=None, limit=50)`, `get_version(db, tenant_id, version_id)`
- `ai_tune.queue_rubric_for_description(tenant_id, description, *, base_was_empty=False) -> bool`: auto-update on → force regenerate; else base was empty → fill only if missing; else nothing.

The fake supports `table().select/insert/update/delete/eq/neq/is_(…,"null")/in_/order/limit/execute`, sequential `created_at`, per-table defaults, cascade delete from `knowledge_documents`, and `storage` as a MagicMock.

- [ ] Tests:
  - the first `save_description` writes baseline + edit (2 rows); the second writes 1
  - an out-of-band settings change creates a new baseline
  - `list_versions` returns newest first
  - `queue_rubric_for_description` covers its three branches (patch `_auto_generate_rubric` and `asyncio.create_task`)
- [ ] Implement; `PUT /description` calls `save_description(get_supabase(), tenant_id, text, "edit", ctx["user_id"])`, then `queue_rubric_for_description(tenant_id, text)`. The response is unchanged.
- [ ] Run the new tests plus `test_ai_tune_routes.py` → commit.

### Task 6: Sorting: labels, buckets, compile, disagreements, `run_sort`

**Files:** Create `backend/app/services/knowledge_sort.py` (first half) and `backend/tests/test_knowledge_sort.py`.

**Produces:**
- Errors: `KnowledgeError(status)`, `SortError` 400, `NotFoundError` 404, `StaleError` 409, `EmptyDescriptionError` 422, `OwnerRequiredError` 403. Also `NO_MODEL_MESSAGE`.
- `_llm_json(system, user, *, tenant_id, max_tokens) -> dict`: a `not configured` RuntimeError → `SortError(NO_MODEL_MESSAGE)`; two bad parses → `SortError`.
- `Label(label, facts, note)`; `label_sections(tenant_id, sections) -> dict[str, Label]`, batched at 12,000 chars.
- `Buckets(facts, rules, unverified, left_out)`; `bucket_sections(sections, labels) -> Buckets` (unlabelled → left out).
- `compile_description(tenant_id, current, rules) -> tuple[str, list[dict]]`, batched at 16,000 chars. Conflicts get ids `c1…`.
- `validate_disagreements(items, *, new_facts, description, other_docs, client_line_set) -> list[dict]`, ids `d1…`.
- `machine_lines(db, tenant_id, exclude=frozenset()) -> set[str]`
- `run_sort(db, *, tenant_id, document_id, source_text, truncated, campaign_tag_id, replaces_document_id, origin, user_id) -> dict` (the review row)

- [ ] Tests (LLM faked by monkeypatching `ks._llm_json`, dispatching on the system prompt constant):
  - buckets: FACT verbatim, RULE, MIXED with a verified fact and a ₹49 unverified fact, JUNK, unlabelled
  - an all-facts document → compile never called, proposed == current, facts == source
  - an all-rules document → facts empty
  - a campaign-scoped document → rules moved to `left_out_rules`, compile not called
  - replace → the old document's non-shared machine lines are stripped from the compile input
  - disagreements: invented values dropped; a description disagreement needs an exact existing line; `client_line` flag set; a `file` disagreement needs a known file name
  - a second `run_sort` marks the older pending review `discarded`
- [ ] Fail → implement → pass → commit.

### Task 7: Review lifecycle and upload hookup

**Files:** Modify `knowledge_sort.py` and `backend/app/services/knowledge_service.py`. Test `backend/tests/test_knowledge_sort_apply.py`.

**Produces:**
- `ApplyChoices(base_version_id, accepted_hunk_ids, conflict_choices, accepted_update_ids)`
- `compute_final_description(review, base_text, machine, choices) -> tuple[str, list[str]]`
- `build_review_payload(db, tenant_id, document_id) -> dict`, with keys: `review_id, document_id, document_name, origin, stale, base_version_id, base_description, proposed_description, hunks, conflicts, fact_disagreements, facts, unverified, left_out, left_out_rules, truncated, replaces_document, word_count, soft_word_limit`
- `apply_review(db, tenant_id, document_id, choices, *, user_id, is_owner) -> dict` with keys `description_changed, base_was_empty, final_description, facts, campaign_tag_id`
- `discard_review`, `sort_document(*, tenant_id, document_id, user_id, replaces_document_id=None)`, `prepare_resort(db, tenant_id, document_id)`, `index_facts(tenant_id, document_id, facts, campaign_tag_id)`, `delete_document_row(db, tenant_id, document_id)`
- `knowledge_service.DOCS_BUCKET`; `process_document(..., replaces_document_id=None, user_id=None)`

- [ ] Tests:
  - stale base → `StaleError`; empty result → `EmptyDescriptionError`; a changed Description as non-owner → `OwnerRequiredError`; a facts-only apply by a non-owner succeeds
  - apply writes exactly one description version (reason `upload`) and one facts version; sets `full_text` = facts, `rule_lines`, `sorted_at`, `status='indexed'`; deletes the old chunks; marks the review `applied`
  - a conflict choice is inserted under its heading; an accepted description disagreement swaps its line and is skipped when the line is gone
  - replace deletes the old document and inherits its still-present lines
  - discard on a new upload deletes the doc; on a legacy doc it only clears `sort_state`
  - `sort_document` failure: a new upload → `status='failed'` + message; an indexed legacy doc stays `indexed` with `sort_state='failed'`
- [ ] Fail → implement → pass → commit.

### Task 8: Facts edit, delete preview/delete, restore

**Files:** Modify `knowledge_sort.py`. Test `backend/tests/test_knowledge_sort_manage.py`.

**Produces:**
- `update_facts(db, tenant_id, document_id, text, user_id) -> dict`
- `build_delete_preview(db, tenant_id, document_id) -> dict` with keys `base_version_id, document_name, chunk_count, has_facts, remove_lines, edited_lines, description_will_change`
- `delete_document(db, tenant_id, document_id, *, base_version_id, remove_edited, user_id, is_owner) -> dict` with keys `description_changed, final_description`
- `restore_version(db, tenant_id, version_id, *, user_id, is_owner) -> dict`

- [ ] Tests:
  - facts edit on an unsorted doc → `SortError`; on a sorted doc → a facts version + the chunks cleared
  - delete preview: own lines listed, lines shared with another document kept, an edited line found via `closest_line`
  - delete: edited lines kept by default, removed when requested; a stale base → 409
  - restore description: a new `restore` version; an empty version → `EmptyDescriptionError`; non-owner → `OwnerRequiredError`
- [ ] Fail → implement → pass → commit.

### Task 9: Routes

**Files:** Modify `backend/app/routes/knowledge.py`. Test `backend/tests/test_knowledge_routes.py`.

New endpoints (spec §10): `GET /documents/{id}/review`, `POST …/review/apply`, `POST …/review/discard`, `POST /documents/{id}/resort`, `PUT /documents/{id}/facts`, `GET /documents/{id}/delete-preview`, `DELETE /documents/{id}` (optional body `{base_version_id, remove_edited}`), `GET /versions?kind=&document_id=`, `POST /versions/{id}/restore`.

- `GET /documents` selects explicit columns (no `full_text`/`source_text`) plus `has_pending_review`.
- `GET /documents/{id}/content` adds `sorted` and `sort_state`.
- The upload validates `replaces_document_id` (a UUID that belongs to the tenant).

- [ ] Tests:
  - every path is registered
  - `_http(StaleError())` → 409 with a string detail, and the same for each error type
  - the upload rejects a malformed `replaces_document_id`
- [ ] Implement → pass → run the full backend suite → commit.

### Task 10: Frontend API and `descriptionDiff.ts`

**Files:** Modify `frontend/lib/api.ts`. Create `frontend/app/dashboard/knowledge/descriptionDiff.ts` and `.test.ts`.

- Types: `KnowledgeHunk`, `KnowledgeConflict`, `KnowledgeFactDisagreement`, `KnowledgeReview`, `KnowledgeApplyChoices`, `KnowledgeVersion`, `KnowledgeDeletePreview`; `KnowledgeDocContent` + `sorted`, `sort_state`.
- Methods: `getReview`, `applyReview`, `discardReview`, `resort`, `updateFacts`, `deletePreview`, `deleteDocument(id, body?)`, `listVersions(kind, documentId?)`, `restoreVersion(id)`; `uploadDocument(file, campaignTagId, replacesDocumentId?)`.
- Helpers: `normalize`, `normalizeText`, `splitLines`, `applyHunks`, `isHeadingLine`, `insertUnderHeading`, `replaceExactLine`, `wordCount`, `lineDiff`, `buildFinalDescription`.
- [ ] vitest cases mirror Task 3 plus `buildFinalDescription` (hunks + conflict + update) → `npm test -- descriptionDiff` passes → commit.

### Task 11: Modals

**Files:** Create `KnowledgeReviewModal.tsx`, `KnowledgeHistoryModal.tsx`, `DeleteDocumentModal.tsx`.

- Review: the five sections from spec §5. Defaults:
  - hunks ticked unless `touches_client_lines`
  - conflicts default to "Leave both out"
  - description updates ticked unless `client_line`

  A live preview of the final Description with its word count. Apply is disabled when the result is empty, stale, or changes the Description for a non-owner. On 409 it shows a Re-sort banner.
- History: version list plus "Changes vs now" / "Full text"; Restore hidden for the current version.
- Delete: preview, with Keep/Remove toggles on edited lines, the "can't be undone" note, and the owner note.
- [ ] `npm run typecheck` → commit.

### Task 12: Page wiring, verification, migration, docs

- `page.tsx`:
  - `DocStatusBadge` (Sorting / Review ready / Live / Not sorted / Sort failed / Failed)
  - Review, Sort this file and Re-sort actions
  - polling includes `sort_state === 'sorting'`
  - a "Replaces" picker plus a same-name prompt
  - the lock replaced by a non-blocking "start here" hint
  - the empty-state copy
  - the viewer becomes "What Aira looks up from this file" with Edit and History, plus a legacy banner
  - `DeleteDocumentModal`
  - a Description History button, a words counter, the 1,200-word copy
  - a status filter option for Review ready
- [ ] `npm run typecheck`, `npm run lint`, `npm test`, full `pytest`.
- [ ] Render the review and history modals with a temporary preview route in Chrome (Playwright `channel:'chrome'`), screenshot them, delete the route.
- [ ] Security pass on the RLS and routes against `.agents/context/security-checklist.md`.
- [ ] Apply migration 190 live (`apply_migration`) and verify the columns and policies with SQL.
- [ ] Update `.agents/context/subsystem-notes.md` (Knowledge base) and `.agents/decisions/log.md`. Commit.
