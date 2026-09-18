# Knowledge Auto-Sort — one upload, split into Description and RAG

Status: design approved in chat, awaiting review of this written spec.
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

**Non-goals (this spec)**
- Renaming the tabs ("How Aira behaves" / "What Aira looks up").
- A warning when a pasted AI transcript is saved as the Description.
- Undoing a document delete.
- Relaxing the 2026-09-09 upload gate (description + rubric must exist before uploading).
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
  "These look like rules, but this file is for one campaign only" and left out. (Open question,
  §15.)
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
This is the normal flow in §3. If a document with the **same name** already exists, the client is
asked: **"Replace '<name>'?"** or **"Keep both"**.
- **Replace:** the proposal also removes the old document's machine lines that the new version
  no longer contains. On Apply, the old document's facts are replaced and the old row is deleted.
- **Keep both:** the new file is sorted as a separate document.

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
| `status` values | — | adds `processing`, `review_pending` alongside `indexed`, `failed` |

New `knowledge_reviews`:
`id, tenant_id, document_id → knowledge_documents ON DELETE CASCADE, base_version_id,
proposed_description, proposed_facts, conflicts jsonb, unverified jsonb, left_out jsonb,
left_out_rules jsonb, truncated bool, replaces_document_id null, status (pending|applied|
discarded), created_by, created_at`.

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
| `POST` | `/upload-document` | Unchanged signature, plus optional `replace_document_id`. Sorting replaces direct indexing. |
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
- tenant isolation on every new route

Frontend: `npm run typecheck` **and** `npm run lint` clean. Review screen, History, RAG preview
and delete dialog rendered and screenshotted in Chrome before handover.

Live: sort the two Astro Tamil documents on a non-production copy and check that the proposed
Description and facts match the manual analysis in §1.

## 14. Follow-ups (not in this spec)
- Rename the tabs by what they do: "How Aira behaves" / "What Aira looks up".
- Warn when a pasted AI transcript is saved as the Description.
- Undo a document delete (soft delete; retrieval RPCs would need a `deleted_at` filter).

## 15. Open questions
1. **Campaign-scoped rules:** v1 leaves them out (§4.5). Should campaigns eventually get their own
   Description add-on?
2. **Upload gate:** now that uploads can write the Description, should a brand-new client still
   need to write a Description by hand before their first upload?
