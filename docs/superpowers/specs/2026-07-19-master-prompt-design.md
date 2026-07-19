# Master Prompt — Developer-Owned Behaviour, Client-Owned Description

**Date:** 2026-07-19
**Status:** Approved design, ready for implementation planning

## Problem

Today the AI's system prompt is written by the **client** on the Knowledge Base → AI Tune
tab. Clients are not prompt engineers: they write vague or contradictory instructions, and
there is no way for us to guarantee baseline behaviour (reply length, tone, persona
discipline) across accounts.

The two things being mixed are genuinely different concerns:

- **How the AI should behave** — reply in 2-3 lines, never claim to be a bot, ask one
  question at a time, worked examples of good replies. This is prompt-engineering craft
  and belongs to the developer.
- **Who the AI is and what it sells** — "we are a Vedic astrology consultancy offering
  birth-chart readings and marriage matching". Only the client knows this.

## Solution

Split prompt ownership in two.

- The **developer** writes a **master prompt** per client in the operator console. It
  defines role framing, reply length, tone, next-step behaviour, and few-shot examples.
- The **client** writes a **business description** on the Knowledge Base page. Plain
  language, no instructions — just what their product/service/role is.

The master prompt supplies the skill set; the description supplies the domain. The same
master prompt over an astrology description yields an astrologer; over a real-estate
description it yields a property advisor.

## Architecture

### The layer stack

The reply prompt is assembled in `generate_reply` ([ai_reply.py:1184-1226]). Only layer 1
changes:

```
[1a] MASTER PROMPT        ← developer, operator console, per client   (NEW)
[1b] BUSINESS DESCRIPTION ← client, Knowledge Base page               (NEW)
[2]  Campaign context     ← code, unchanged
[3]  Knowledge base RAG   ← code, unchanged
[4]  Lead context         ← code, unchanged
[5]  Language rule        ← code, unchanged
[6]  Accuracy rule        ← code, unchanged
[7]  Escalation block     ← code, unchanged
[8]  Catalog block        ← code, unchanged
```

**Layers 2-8 are deliberately untouched.** Layers 5-8 stay hardcoded in Python rather than
moving into the editable master prompt. The language rule in particular carries live-test
results in its code comments (12/12 on Gemini 3.1 Flash Lite; an "aggressive" rewording
made gpt-5-nano return empty replies 0/8) — making it editable would make it breakable.
If a client ever needs a genuine exception (e.g. quoting fixed public prices, which the
accuracy rule currently forbids), that is added later as a narrow per-client toggle, not
by opening the whole rule to free-text editing.

### Channel handling

One master prompt per client, not one per channel. The four `ai_prompts` rows
(`whatsapp_reply`, `telegram_reply`, `instagram_reply`, `facebook_reply`) collapse to a
single row named `master`. The channel name is injected into the prompt at reply time, so
per-channel phrasing is still possible without four boxes to maintain.

### Description is injected, not retrieved

The business description is stored as a setting and **always injected in full**. It does
**not** go through the RAG retrieval path in `knowledge_service`. RAG stays for uploaded
documents only. Rationale: the description defines the AI's identity and must be present
on every single reply — a retrieval miss would leave the AI with no role at all.

## Data model

| What | Storage | Editor |
|---|---|---|
| Platform default template | new `platform_defaults` table, key `default_master_prompt` | Developer (operator console) |
| Per-client master prompt | `ai_prompts`, one row per tenant, `name = 'master'` | Developer (client console) |
| Business description | `app_settings`, per tenant, key `business_description` | Client (Knowledge Base) |

A dedicated `platform_defaults` table is used for the template rather than `app_settings`,
because `app_settings` has no true global scope — `save_setting(tenant_id=None)` silently
writes against `_DEFAULT_TENANT_ID` ([config_dynamic.py:51]), which is a real tenant, not
a platform row.

### Seeding

The template is **copied** into a new client's `master` row at client creation
([operator.py:205], `create_client`). It is not a live fallback. Later edits to the
template therefore do not alter the behaviour of clients already running — behaviour
changes on a live account only happen when the developer deliberately edits that client.

### Migration for existing clients

Each existing tenant's current `whatsapp_reply` content is copied into their new `master`
row. Live accounts behave identically on deploy day. The developer replaces them with the
template at their own pace. The three other per-channel rows are left in place but unread,
and dropped in a later cleanup once every tenant has a `master` row.

## Scoring rubric

`_auto_generate_rubric` ([ai_tune.py:85-127]) derives a per-tenant lead-scoring rubric from
the prompt text and writes `scoring_rubric`, consumed by [scoring_engine.py:211]. This
feature stays, but its **input changes**: the rubric is now generated from the **business
description**, not the master prompt.

Rationale: the rubric is meant to capture *this specific business's* conversion signals —
what a hot lead looks like for an astrologer differs from a real-estate agent. That is
domain knowledge, which now lives in the description. The master prompt is generic
behaviour and would produce a useless, identical rubric for every client.

So rubric regeneration fires when the **client saves their description**, and no longer
when a prompt is saved.

## Dead code removal

The `/analyze`, `/suggestions`, `/suggestions/{id}/apply` and `/suggestions/{id}/reject`
endpoints in `ai_tune.py` are **unreachable** — `frontend/lib/api.ts` exposes only
`aiTune.prompts` and `aiTune.updatePrompt` ([api.ts:1374-1382]), and no other caller
exists. They are removed along with the `META_PROMPT` constant, the Groq analyze client
usage, and the `ai_tune_suggestions` table.

Dropping the table also requires removing `ai_tune_suggestions` from the tenant-table list
in [operator.py:2065] (used by data-ops purge/export), or those operations will fail on a
missing relation.

This is a straight deletion of unused code, not a feature removal. It is included here
because the same file is being restructured and leaving dead endpoints behind would make
the new surface harder to read.

## UI

### Operator console — new "Default Master Prompt" page

A single textarea holding the platform template, saved to `platform_defaults`. Used only
at client creation. Includes a note stating that edits do not affect existing clients.

### Operator console — client Config tab

A "Master Prompt" section in [config.tsx]:

- Textarea for this client's master prompt, prefilled from the template at creation.
- Read-only display of the client's current business description, so the developer can
  write behaviour that fits the client's actual role.
- A "reset to template" action.

### Client dashboard — Knowledge Base

The existing "AI Tune" tab ([knowledge/page.tsx:65]) becomes **"Description"**:

- The per-channel prompt editor is removed.
- A single "Business Description" textarea, with placeholder guidance to describe their
  product, service, and role in plain language.
- Saving triggers rubric regeneration.

The client can no longer edit AI behaviour anywhere.

## Error handling

- **No master prompt row for a tenant** — fall back to the existing `FALLBACK_PROMPT`
  constant in `ai_reply.py`, as today. The AI never goes silent because of a missing row.
- **Empty business description** — the master prompt is used alone. The AI behaves
  correctly but generically; the accuracy rule (layer 6) already prevents it from
  inventing business facts.
- **`platform_defaults` unreachable at client creation** — client creation still succeeds,
  with the master row seeded from `FALLBACK_PROMPT`. Onboarding must never fail on a
  template read.
- **Prompt cache** — `invalidate_prompt_cache` must be called when the developer saves a
  master prompt, and the `app_settings` cache invalidated when the client saves a
  description, or edits take up to 60s to take effect.

## Testing

- `_get_prompt` returns the `master` row for a tenant; falls back when absent.
- Channel name is injected into the assembled prompt for all four channels.
- Business description appears in the assembled system prompt when set, and is absent
  when unset, without breaking assembly.
- Layers 5-8 still appear in the assembled prompt, in the same order, with unchanged text
  — this is the regression guard for the "nothing currently working breaks" claim.
- Client creation seeds the master row from `platform_defaults`, and from `FALLBACK_PROMPT`
  when the table read fails.
- Rubric generation fires on description save and not on master-prompt save.
- Removed endpoints return 404.

## Out of scope

- Per-client overrides of the language/accuracy/escalation/catalog rules.
- Per-channel master prompts.
- Versioning or rollback of master prompts.
- Dropping the three unused per-channel `ai_prompts` rows (deferred cleanup).
