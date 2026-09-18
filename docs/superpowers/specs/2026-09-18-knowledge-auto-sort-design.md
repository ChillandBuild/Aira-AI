# Knowledge Auto-Sort — one upload, split into Description and RAG

Status: approved 2026-09-18 (Q1 → option A, Q2 → description-or-upload, three price gaps added). Implementing.
Date: 2026-09-18

## 1. Problem

Aira learns about a client's business from two places:

| | Description | Documents (RAG) |
|---|---|---|
| Stored in | `app_settings.business_description` | `knowledge_documents` + `knowledge_chunks` |
| Read | On **every** reply, in full ([ai_reply.py:295](../../../backend/app/services/ai_reply.py#L295)) | Only when a message matches ([knowledge_service.py:251](../../../backend/app/services/knowledge_service.py#L251)) |
| Right home for | How Aira behaves: identity, rules, tone | What Aira looks up: prices, FAQs, policies |

Clients sort their material by **file type**, not by **what it is**. A rulebook written as a
`.docx` goes into Documents, because it's a document. Checked on the live database on 2026-09-18
for Astro Tamil:

- `business_description` is 2,005 characters of a pasted ChatGPT reply ("Yes. If you want the
  backend trigger → WhatsApp consultation package list flow, I would use a clear prompt like
  this: …"). It contains nothing about the business.
- The two uploaded documents (14,114 + 46,501 = 60,615 characters, 56 chunks) are roughly 95%
  behaviour rules. The actual facts in them (features, ₹29 starting price, 7-day free question,
  25 lucky users, reward points, both privacy policies, the consultation link) fit in about
  2,500 characters.
- Those rules contradict each other within the same files (the greeting rule is overridden three
  times; the pricing rule forbids mentioning the free question and the offers rule requires it). They
  also contain an unresolved editorial comment and a literal placeholder
  (`👉 attach the link we provide earlier`).

`subsystem-notes.md` already records that rule documents in RAG make replies worse. The
retriever matches the example customer messages inside them and gives the model lists of
forbidden phrases labelled as facts.

Hand-writing a good description for each client does not scale. This feature lets the client
upload everything in one place, and Aira does the sorting.

## 2. Goals and non-goals

**Goals**
1. One upload place. Aira splits each document into **rules** (merged into the Description),
   **facts** (indexed into RAG) and **junk** (left out, shown to the client).
2. Nothing reaches the Description or RAG until the client approves it on a review screen.
3. The client can always edit the Description, edit or delete facts, and delete a document.
   Their own edits are never overwritten without their say.
4. Every change to the Description or to a document's facts can be undone (version history).
5. The RAG preview shows only what Aira will look up from that file, not the whole original.
6. The Description guide's "Around 200 to 350 words" copy is updated to match the 1,200-word
   soft limit (§4.4), so the screen doesn't contradict what the sorter produces.
7. Updated prices can't silently disagree: across files, or between a file and the Description (§6.5).
8. The upload lock is satisfied by a Description the client writes **or** one built from their
   upload (§6.6).

**Non-goals (this spec)**
- Renaming the tabs ("How Aira behaves" / "What Aira looks up").
- A warning when a pasted AI transcript is saved as the Description.
- Undoing a document delete.
These are listed in §14.

## 3. The flow

```
Client uploads file
   ↓
Extract text (unchanged: extract_text_from_file, 50,000-char cap)
   ↓
Sort (background)                                   status: processing
   1. Cut into sections
   2. Label each section: RULE / FACT / MIXED / JUNK
   3. Check extracted facts against the source
   4. If any rules: write a proposed Description
   ↓
Review screen                                       status: review_pending
   Client ticks what to keep, picks answers to conflicts
   ↓
Apply                                               status: indexed
   Description saved (new version)
   Facts saved as the document's full_text (new version), chunked and embedded
```

While a document is `processing` or `review_pending`, it contributes nothing to replies. It has
no chunks, and `_full_text_context` only reads `status = 'indexed'`
([knowledge_service.py:183](../../../backend/app/services/knowledge_service.py#L183)).

## 4. How sorting works

### 4.1 Cutting into sections (no AI)
Split the extracted text on headings and blank-line blocks into sections of at most ~2,500
characters, the same boundary preference as `_chunk_text`. Each section gets a stable id.

### 4.2 Labelling (AI)
Sections are sent in batches. The model returns JSON, one entry per section:

| Label | Meaning | Where it goes |
|---|---|---|
| `RULE` | Tells Aira how to behave: tone, language, what never to say, flows | Description compile |
| `FACT` | Something a customer could ask about: price, feature, policy, FAQ, address | RAG, **word for word** |
| `MIXED` | Both, e.g. an "approved response" containing the free-question policy | Rule part → compile; facts copied out in the source's own words |
| `JUNK` | Pasted AI chat, editorial notes, placeholders, duplicates | Left out, listed on the review screen |

Facts are **never rewritten** by the model. A `FACT` section goes to RAG as-is, and a `MIXED`
section contributes sentences copied from it.

### 4.3 Checking facts (no AI)
For every fact the model copied out of a `MIXED` section, every number, ₹/currency amount, URL,
phone number and email in it must appear in the source section. A fact that fails this check is
dropped and listed under **"Couldn't verify — check this yourself"**. This stops a price from
changing on the way through.

### 4.4 Writing the proposed Description (AI, only if rules were found)
Input: the **current** Description plus all `RULE` and `MIXED` rule text. Output (JSON):
- `proposed_description`: the full new text, using the same section headings as the existing
  template in [page.tsx](../../../frontend/app/dashboard/knowledge/page.tsx) (`ABOUT US`,
  `WHAT WE OFFER`, …). The model is told to keep existing text unless a new rule contradicts it,
  and to resolve overrides inside the upload ("this rule overrides all previous greeting rules").
- `conflicts`: places where the upload disagrees with the current Description, or with itself,
  and the model cannot tell which is right. Each item has a topic, option A and option B (with
  their sources), and the heading it belongs under. The model puts **neither** option into
  `proposed_description`.

Soft length limit: **1,200 words**. Over that, the review screen shows the word count and a
warning. It does not block.

### 4.5 Special cases
- **All facts (e.g. an FAQ sheet):** no compile step runs. The whole document goes to RAG and the
  review screen says "Nothing in this file changes your Description."
- **All rules:** nothing goes to RAG. The document is still stored so it can be deleted or re-sorted
  later, with empty `full_text` and zero chunks.
- **Campaign-scoped upload (`campaign_tag_id` set):** facts go to RAG with that scope, as today.
  Rules are **not** merged, because the Description applies to every campaign. They are listed as
  "These look like rules, but this file is for one campaign only" and left out. (Decided
  2026-09-18, option A. A per-campaign Description is a possible follow-up, §14.)
- **Text over 50,000 characters:** truncated as today, but the review screen now says "Only the
  first 50,000 characters were read" instead of truncating silently.

### 4.6 Which AI model
The client's own configured reply model, dispatched through the existing `_llm_chat` path
([ai_reply.py:65](../../../backend/app/services/ai_reply.py#L65)). It is not tied to Groq the way
`ai_tune.py` is: on 2026-09-18, two of the three Astro Tamil tenants had Gemini but no Groq key.
The existing provider clients already handle each provider's quirks (Gemini thinking level,
GPT-5 reasoning params). `_llm_chat` needs a larger `max_tokens` for the compile step
(~2,000). JSON is parsed with one retry on a parse failure, the same approach as
`gemini_chat_completion_json`. Usage is metered through `token_meter` under the label
`knowledge_sort`. Batch size is set during implementation after a live test against each
provider's per-request limit.

## 5. The review screen

Opened from a document row showing **"Review ready"**. It has four parts.

**1. Changes to your Description.** A line-level diff of current vs proposed, cut into hunks.
Each hunk has a tick box:
- ➕ added lines: ticked by default
- ✏️ changed lines: ticked by default, **except** when the hunk touches a line the client
  wrote (see §6.1). Those are unticked and labelled "This changes something you wrote."
- ➖ removed lines: same rule as changed lines

**2. Conflicts: pick one.** Each conflict shows option A, option B and where each came from. The
client picks one, or "Leave both out". The chosen line is added at the end of its heading's
section, or at the end of the Description if that heading doesn't exist.

**3. What Aira will look up from this file.** The facts text, the number of facts, and any
"Couldn't verify" items.

**4. Left out.** The junk list, collapsed by default, read-only in v1.

Buttons: **Apply** and **Discard**. Discard deletes the document row, since nothing was ever
indexed.

**Stale reviews.** Every review stores the Description version it was built on. If the Description
has changed since then (the client edited it, or applied another review), Apply is refused with
"Your Description changed since this review was prepared" and a **Re-sort** button that rebuilds
the proposal against the current text.

## 6. The four things a client can do

### 6.1 Edit the Description
The Description stays a plain text box, saved through `PUT /api/v1/ai-tune/description` as today. Every
save now writes a version (§7).

**Machine lines vs the client's lines.** Each indexed document stores the Description lines it
contributed (`rule_lines`, §9). A line in the current Description is a *machine line* if it
matches, whitespace-trimmed, a line in any document's `rule_lines`. Any other line is the
client's own, whether they typed it or edited a machine line. The review screen (§5) and the
delete preview (§6.3) use this to protect the client's lines by default.

### 6.2 Delete one thing
- **A Description line:** the client edits the text box and removes it.
- **A fact:** the RAG preview has an **Edit** mode. The client edits or removes facts and saves.
  This writes a facts version, replaces `full_text`, and re-chunks and re-embeds that document
  (`_index_chunks`).

A deleted line or fact **comes back if the same file is uploaded again**. Nothing remembers it
was deleted. It comes back through the review screen as an ➕ added hunk, so the client sees it
return.

### 6.3 Delete a whole document
Clicking delete first calls a preview that returns:
- the number of facts that will leave lookup
- machine lines from this document still in the Description, which will be removed
- lines this document contributed that the client has since changed. These are listed with
  **"Keep"** (the default) or **"Remove"**.

On confirm, the chunks and the document row are deleted as today, and the Description is saved
without the removed lines as a new version with reason `delete_document`. This is refused if the
Description changed after the preview was fetched (same version check as §5).

### 6.4 Upload a new or updated file
This is the normal flow in §3. The upload form asks **"Does this replace an existing file?"** with
a picker of the tenant's documents (default: none). It does **not** rely on the file name:
clients rename versions ("…v9…Final.docx" → "…v10…"). If a document with the exact same
name exists, the picker pre-selects it, and the client can change that.
- **Replaces a file:** the proposal also removes the old document's machine lines that the new
  version no longer contains. The old document's facts are excluded from the price check
  (§6.5), since they're being removed. On Apply, the old row and its chunks are deleted and the
  new document takes its place.
- **Doesn't replace anything:** the new file is sorted as a separate document.

### 6.5 Price and fact disagreements
Checked at sort time, after the facts are extracted, in one AI call. Input: the new facts, the
current Description, and the facts of every **other sorted** document in the same scope (a
replaced document is excluded). Sorted documents' facts are compact, and legacy (unsorted)
documents are not included, because their raw text can be ~50,000 characters. Output: a list of
disagreements, each tagged with where it is:

| Where | Example | What the review screen does |
|---|---|---|
| `description` | Description says "₹29", new file says "₹49" | Shows **"Your Description still says ₹29. Update it?"** with the exact current line and a proposed replacement. Choosing *Update* swaps that one line. The server applies it only if the exact line is still present. Unticked by default when the line is the client's own (§6.1), ticked when it is a machine line. |
| `file` | Another file "Pricing.pdf" says "₹29" | A warning: **"'Pricing.pdf' says ₹29. Aira may quote either. Replace that file or edit its facts."** Doesn't block Apply. |

Every value the AI reports is checked by the same no-AI check as §4.3: the quoted "new" value
must appear in the new facts and the quoted "existing" value must appear in the Description or
that file. Anything that fails the check is dropped rather than shown, so a made-up conflict never
reaches the client.

### 6.6 The upload lock (changed from 2026-09-09)
The Documents tab used to be locked until **both** a Description and a scoring rubric were saved.
Now:
- **Uploading is allowed with an empty Description.** The client either writes a short
  Description first, or uploads a file and the Description is built from it.
- **Apply requires a non-empty Description.** If the Description is empty and the review would
  leave it empty (for example an FAQ-only first upload), Apply is disabled with: "This file
  doesn't describe your business, so Aira still wouldn't know who it is. Write a short
  Description first, or upload a file that describes your business." Discard still works.
- **The rubric no longer blocks uploads.** It is used for lead scoring, never for replies or RAG.
  When an Apply fills a previously empty Description and no rubric exists, the rubric is
  generated from the new Description by the existing `_auto_generate_rubric(force=False)`, the
  same best-effort path as saving a Description. The Documents checklist still shows the
  rubric as a recommended step.

## 7. Safety net: version history

Every write to the Description or to a document's facts writes a row to `knowledge_versions`
(§9) with who made the change, when, and why:
`edit`, `upload`, `delete_document`, `resort`, `restore`, `baseline`.

- **Description tab → "History".** A list of versions, newest first. Opening one shows the full
  text and a diff against the current version. **Restore** saves that text as a new version with
  reason `restore`, so history is never rewritten and a restore can itself be undone.
- **RAG preview → "History".** The same for one document's facts. Restoring re-chunks and
  re-embeds.
- **Baseline.** The first time a tenant's Description is written through the new path, the
  existing value is saved first as a `baseline` version, so the pre-feature text is recoverable.
- **Retention:** keep everything. It is small text. The UI lists the latest 50.
- **Limit, stated in the delete dialog:** deleting a document cannot be undone in v1. Its facts
  versions are deleted with it. The Description lines it removed can still be restored from
  Description history.

**One write path.** All Description writes (manual save, apply review, delete document, restore)
go through a single `save_description(tenant_id, text, reason, user_id)`. It writes
`app_settings`, inserts the version row, calls `invalidate_cache("business_description")`, and
queues rubric regeneration when `rubric_auto_update` is on, exactly as the current `PUT`
handler does ([ai_tune.py:94](../../../backend/app/routes/ai_tune.py#L94)).

## 8. RAG preview shows facts only, and why `full_text` must change meaning

When nothing matches a search, retrieval falls back to injecting **every indexed document's
`full_text`** ([knowledge_service.py:173](../../../backend/app/services/knowledge_service.py#L173)).
If `full_text` kept the raw document after sorting, every retrieval miss would put all the rules
back into the prompt, labelled as facts.

So after sorting, **`full_text` holds the facts text only**, and the raw extraction moves to a new
`source_text` column. Chunking, the fallback and the preview all read `full_text`, so they always
show the same thing. The retrieval code does not change.

The document viewer (currently the full extracted text, [page.tsx:2037](../../../frontend/app/dashboard/knowledge/page.tsx#L2037))
becomes **"What Aira looks up from this file"** and shows `full_text`. The original file stays
downloadable through the existing signed-URL route.

## 9. Data changes (one new migration)

`knowledge_documents` (verified live 2026-09-18: `status` is free text with no CHECK constraint, so
new values need no constraint change):
| Column | Type | Purpose |
|---|---|---|
| `source_text` | text | Raw extraction (≤ 50,000 chars). Input for re-sort. |
| `rule_lines` | jsonb, default `'[]'` | Description lines this document contributed, as applied |
| `sorted_at` | timestamptz null | `null` = legacy document, never sorted (§11) |
| `sort_state` | text null | `sorting` / `review` / `failed` / null. Lets an already-indexed legacy document be re-sorted while it keeps serving replies (its `status` stays `indexed`). |
| `status` values | — | adds `processing`, `review_pending` alongside `indexed`, `failed` |

New `knowledge_reviews`:
`id, tenant_id, document_id → knowledge_documents ON DELETE CASCADE, base_version_id,
proposed_description, proposed_facts, proposed_rule_lines jsonb, conflicts jsonb (rule
conflicts, §4.4), fact_disagreements jsonb (§6.5), unverified jsonb, left_out jsonb,
left_out_rules jsonb, truncated bool, replaces_document_id null, origin (upload|resort),
status (pending|applied|discarded), created_by, created_at`. At most one `pending` review per
document; a new sort discards the older one.

New `knowledge_versions`:
`id, tenant_id, kind (description|facts), document_id null → knowledge_documents ON DELETE
CASCADE, content, reason, created_by, created_at`, with an index on
`(tenant_id, kind, document_id, created_at desc)`.

Both new tables: `tenant_id not null`, RLS enabled with the same tenant policy as
`knowledge_documents`. **RLS on the new tables goes to the `security-reviewer` agent before
merge** (security-checklist).

## 10. API

All under the existing knowledge router (`/api/v1/knowledge`). Reads need `knowledge.view`, writes need
`knowledge.manage`. `tenant_id` always comes from `get_tenant_id`, never from the request body.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/upload-document` | Unchanged signature, plus optional form field `replaces_document_id`. Sorting replaces direct indexing. |
| `GET` | `/documents/{id}/review` | Review payload: hunks (with ids and "yours" flags), conflicts, facts, unverified, left out |
| `POST` | `/documents/{id}/review/apply` | `{base_version_id, accepted_hunk_ids, conflict_choices}` |
| `POST` | `/documents/{id}/review/discard` | Deletes the pending document |
| `POST` | `/documents/{id}/resort` | Rebuilds the proposal (stale review, or legacy document) |
| `PUT` | `/documents/{id}/facts` | Edit facts (§6.2) |
| `GET` | `/documents/{id}/delete-preview` | §6.3 |
| `DELETE` | `/documents/{id}` | Now takes `{base_version_id, keep_line_ids}` |
| `GET` | `/versions?kind=&document_id=` | History list |
| `POST` | `/versions/{id}/restore` | §7 |

`PUT /api/v1/ai-tune/description` keeps its contract and now routes through `save_description`.

**Who can change the Description.** Today only an owner can save it (`ai_tune` router is
`require_owner`). That stays true: apply, delete and restore need `knowledge.manage`, **plus** the
owner role whenever the result changes the Description. A manager can still apply an FAQ-only
upload.

**Error statuses** (the frontend's `apiFetch` exposes `status` and a plain-text `detail`):
`409` = Description changed since the review/preview was built; `422` = the result would leave the
Description empty; `403` = owner required.

**List payload.** `GET /documents` stops returning `select("*")`. It drops the large
`full_text`/`source_text` columns and adds `has_pending_review`.

**Apply speed.** Apply does the database writes and returns. Chunking and embedding the facts run
as a background task, and until the chunks exist the full-text fallback serves the new
`full_text`. This keeps apply inside the frontend's 15-second mutation timeout.

## 11. Existing documents

Documents with `sorted_at = null` work **exactly as today**: `full_text` is still the raw text and
is still chunked. Their row gets a **"Sort this file"** action that copies `full_text` into
`source_text` and runs the normal sort → review → apply.

**Astro Tamil after release:**
1. Replace the broken Description by hand with the drafted ~820-word text. Every current line
   counts as the client's own, so the review screen would otherwise keep the pasted ChatGPT reply.
2. Run "Sort this file" on both documents and review.
Both steps change live client data and need the go-ahead from you before they're done.

## 12. Errors

| Situation | What happens |
|---|---|
| No AI model/key configured | `failed`: "Aira couldn't sort this file because no AI model is set up for your account." Nothing is indexed. |
| Model returns bad JSON twice | `failed` with a plain message; **Re-sort** available |
| Text extraction empty | `failed`, as today |
| Apply against a changed Description | Refused, **Re-sort** offered (§5) |
| Embedding fails on apply | Description is still saved; facts stay in `full_text`, so the existing full-text fallback covers them (same behaviour as today's `process_document`) |

## 13. Testing

Backend (`pytest`, LLM mocked):
- sectioning boundaries; the fact check drops a changed ₹ amount and a changed URL
- all-facts document skips compile; all-rules document indexes nothing
- hunk diff and apply with accepted/rejected hunks; "yours" detection from `rule_lines`
- conflict choice inserted under the right heading, or at the end when the heading is missing
- a stale `base_version_id` is refused on apply and on delete
- every Description write path inserts exactly one version; baseline is written once
- restore creates a new version and does not rewrite history
- delete preview: machine lines removed, edited lines kept by default
- replace flow removes lines the new version dropped
- legacy document is untouched until "Sort this file"
- §6.5: a `description` disagreement swaps exactly one line; it is skipped if that line is gone;
  a disagreement whose quoted values aren't in the source texts is dropped
- §6.6: upload allowed with an empty Description; Apply refused when the result is still empty;
  rubric generated only when it was missing
- tenant isolation on every new route

Frontend: `npm run typecheck` **and** `npm run lint` clean. Review screen, History, RAG preview
and delete dialog rendered and screenshotted in Chrome before handover.

Live: sort the two Astro Tamil documents on a non-production copy and check that the proposed
Description and facts match the manual analysis in §1.

## 14. Follow-ups (not in this spec)
- Rename the tabs by what they do: "How Aira behaves" / "What Aira looks up".
- Warn when a pasted AI transcript is saved as the Description.
- Undo a document delete (soft delete; retrieval RPCs would need a `deleted_at` filter).
- A per-campaign Description add-on for campaign-scoped rules.

## 15. Decisions (2026-09-18)
1. **Campaign-scoped rules:** option A, left out and shown to the client (§4.5).
2. **Upload lock:** a written Description **or** one built from an upload (§6.6).
3. **Price gaps:** a replace-file picker instead of name matching (§6.4), plus the disagreement
   checks in §6.5.
