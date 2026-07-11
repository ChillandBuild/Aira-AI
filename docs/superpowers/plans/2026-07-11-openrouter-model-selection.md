# OpenRouter Model Selection (Conversational Reply + Reengagement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Aira operator pick, per client, which LLM generates conversational auto-replies and reengagement messages — Sarvam (default) or any model reachable through OpenRouter (OpenAI, Google Gemini, Groq/Llama) — from a dropdown in the operator console, with no redeploy required to change it.

**Architecture:** Reuse the existing per-tenant dynamic-settings system (`config_dynamic.py`'s `get_setting`/`save_setting`, already backing `app_settings`) to store one new key, `ai_reply_model`, per tenant. `ai_reply.py`'s two LLM-calling functions look up that key and dispatch: a value starting with `"sarvam"` calls the existing direct Sarvam integration unchanged; anything else is sent to a new, thin OpenRouter client using the OpenAI-compatible Chat Completions shape. The operator console's existing client-config screen (`GET/PATCH /api/v1/operator/clients/{tenant_id}/config`, already generic over arbitrary `app_settings` keys) gets one more field and one more UI section — no new route needed.

**Tech Stack:** FastAPI (backend/app/), Next.js 14 (frontend/app/operator/), Supabase (`app_settings` table), OpenRouter HTTP API, pytest + `unittest.mock`.

## Global Constraints

- **Scope is conversational auto-reply and reengagement messages only** — both already route through `ai_reply.py`'s `_llm_complete`/`_llm_chat`, confirmed by reading the source (`generate_reengagement_message` calls `_llm_complete` at line 468; the main WhatsApp reply path calls `_llm_chat` at line 984). Voice reply, speech-to-text, call transcription, and document OCR are explicitly **out of scope** — separate plan later.
- **The tool-calling reply path stays Sarvam-only.** `ai_reply.py` line ~936 calls `sarvam_chat_completion_with_tools` directly for the catalog/product-recommendation flow — this plan does not touch it or add an OpenRouter tool-calling equivalent.
- **Model selection is operator-only.** No client-facing API route, no client dashboard UI. Only `backend/app/routes/operator.py` (guarded by `get_system_admin`) and the operator console frontend are touched.
- **OpenRouter runs in BYOK mode with one platform-level API key** — not a per-tenant credential. Only the *model choice* varies per tenant; the OpenRouter account and its key are Aira's own.
- **Model slugs are locked to what OpenRouter's public API actually returned when this plan was written** (`curl https://openrouter.ai/api/v1/models`, 2026-07-11): `meta-llama/llama-3.3-70b-instruct`, `openai/gpt-5-mini`, `openai/gpt-5`, `google/gemini-2.5-flash`, `google/gemini-2.5-pro`. Do not substitute newer-sounding names without re-checking that endpoint — OpenRouter's catalog changes frequently and stale slugs 400 at request time, not at build time.

## Pre-requisite (manual, not a code task)

Before Task 1 can work end-to-end in production:
1. Create an OpenRouter account (openrouter.ai) for Aira.
2. Under OpenRouter's account settings, add BYOK keys for OpenAI, Google (Gemini), and Groq — this is what lets OpenRouter bill those providers directly through Aira's own accounts instead of OpenRouter's shared credit pool.
3. Generate an OpenRouter API key and set it as `OPENROUTER_API_KEY` in Render's environment variables for the backend service.

Tasks 1–4 below can be written and unit-tested without this (all provider calls are mocked), but the feature will 401 in production until this is done.

## File Structure

- **Create** `backend/app/services/openrouter_client.py` — thin OpenRouter Chat Completions client, mirrors `sarvam_client.py`/`groq_client.py`.
- **Create** `backend/tests/test_openrouter_client.py` — unit tests for the above.
- **Modify** `backend/app/config.py` — add `openrouter_api_key` platform setting.
- **Modify** `backend/app/services/ai_reply.py` — `_llm_complete`/`_llm_chat` dispatch on the tenant's `ai_reply_model` setting instead of a hardcoded constant.
- **Modify** `backend/tests/test_ai_reply_llm_wiring.py` — replace the tests that assumed a hardcoded `_REPLY_MODEL`.
- **Modify** `backend/app/routes/operator.py` — expose `ai_reply_model` in `GET .../config`, accept it via the existing generic `PATCH .../config`.
- **Modify** `backend/tests/test_operator_client_config.py` — cover the new field.
- **Modify** `frontend/app/operator/(console)/client/[id]/views/config.tsx` — new "Conversational Reply Model" picker section.

---

### Task 1: OpenRouter client service

**Files:**
- Create: `backend/app/services/openrouter_client.py`
- Create: `backend/tests/test_openrouter_client.py`
- Modify: `backend/app/config.py:14` (insert new field right after `sarvam_api_key`)

**Interfaces:**
- Produces: `get_openrouter_api_key() -> str` (raises `RuntimeError("OpenRouter API key not configured")` if unset). `async def openrouter_chat_completion(messages: list[dict], model: str, temperature: float = 0.4, max_tokens: int = 300) -> str`.

- [ ] **Step 1: Add the platform setting field**

In `backend/app/config.py`, insert immediately after line 14 (`sarvam_api_key: str | None = None`):

```python
    openrouter_api_key: str | None = None
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_openrouter_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import openrouter_client
from app.services.openrouter_client import openrouter_chat_completion


def test_openrouter_api_key_raises_when_missing():
    with patch("app.services.openrouter_client.settings") as mock_settings:
        mock_settings.openrouter_api_key = None
        with pytest.raises(RuntimeError, match="OpenRouter API key not configured"):
            openrouter_client.get_openrouter_api_key()


def test_openrouter_api_key_returns_platform_key():
    with patch("app.services.openrouter_client.settings") as mock_settings:
        mock_settings.openrouter_api_key = "platform-or-key"
        assert openrouter_client.get_openrouter_api_key() == "platform-or-key"


@pytest.mark.asyncio
async def test_openrouter_chat_completion_returns_stripped_message_content():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "  Hello there!  "}}]}
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=resp)

    with patch("app.services.openrouter_client.get_openrouter_api_key", return_value="test-key"), \
         patch("app.services.openrouter_client.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        text = await openrouter_chat_completion(
            messages=[{"role": "user", "content": "Hi"}], model="openai/gpt-5-mini"
        )

    assert text == "Hello there!"
    call_args, call_kwargs = mock_instance.post.call_args
    assert call_args[0] == "https://openrouter.ai/api/v1/chat/completions"
    assert call_kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert call_kwargs["json"]["model"] == "openai/gpt-5-mini"
    assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "Hi"}]
    assert call_kwargs["json"]["temperature"] == 0.4
    assert call_kwargs["json"]["max_tokens"] == 300


@pytest.mark.asyncio
async def test_openrouter_chat_completion_raises_when_api_key_missing():
    with patch(
        "app.services.openrouter_client.get_openrouter_api_key",
        side_effect=RuntimeError("OpenRouter API key not configured"),
    ):
        with pytest.raises(RuntimeError, match="not configured"):
            await openrouter_chat_completion(messages=[{"role": "user", "content": "Hi"}], model="openai/gpt-5-mini")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_openrouter_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.openrouter_client'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/openrouter_client.py`:

```python
# backend/app/services/openrouter_client.py
import httpx

from app.config import settings

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_openrouter_api_key() -> str:
    if not settings.openrouter_api_key:
        raise RuntimeError("OpenRouter API key not configured")
    return settings.openrouter_api_key


async def openrouter_chat_completion(
    messages: list[dict],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 300,
) -> str:
    """OpenRouter's Chat Completions API (OpenAI-compatible request/response shape).
    `model` is an OpenRouter model slug, e.g. "openai/gpt-5-mini" or
    "google/gemini-2.5-flash" or "meta-llama/llama-3.3-70b-instruct". OpenRouter
    routes to the underlying provider using the BYOK keys configured on the
    platform's openrouter.ai account -- no per-provider credentials in this app."""
    api_key = get_openrouter_api_key()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            OPENROUTER_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_openrouter_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/openrouter_client.py backend/tests/test_openrouter_client.py
git commit -m "feat: add OpenRouter chat completion client"
```

---

### Task 2: Per-tenant model dispatch in ai_reply.py

**Files:**
- Modify: `backend/app/services/ai_reply.py:20-41`
- Modify: `backend/tests/test_ai_reply_llm_wiring.py:1-39`

**Interfaces:**
- Consumes: `openrouter_chat_completion(messages, model, temperature, max_tokens) -> str` (Task 1). `get_setting(key: str, fallback: str | None = None, tenant_id: str | None = None) -> str | None` (existing, `app/config_dynamic.py`).
- Produces: `_DEFAULT_REPLY_MODEL = "sarvam-30b"` (replaces the old `_REPLY_MODEL` constant — later tasks/UI default to this string). `_llm_complete`/`_llm_chat` keep their existing signatures unchanged.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `backend/tests/test_ai_reply_llm_wiring.py` lines 1-39 (everything up to but not including `test_send_whatsapp_voice_reply_uses_sarvam_tts_and_meta_audio_upload`) with:

```python
import pytest
from unittest.mock import AsyncMock, patch

from app.services import ai_reply


@pytest.mark.asyncio
async def test_llm_complete_defaults_to_sarvam_when_no_tenant_setting():
    with patch.object(ai_reply, "get_setting", return_value=None), \
         patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=120,
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_llm_complete_routes_to_openrouter_for_non_sarvam_model():
    with patch.object(ai_reply, "get_setting", return_value="openai/gpt-5-mini"), \
         patch.object(ai_reply, "openrouter_chat_completion", AsyncMock(return_value="a poem")) as mock_call:
        text = await ai_reply._llm_complete("write a poem", max_tokens=120, tenant_id="tenant-1")

    assert text == "a poem"
    mock_call.assert_called_once_with(
        messages=[{"role": "user", "content": "write a poem"}],
        model="openai/gpt-5-mini",
        temperature=0.4,
        max_tokens=120,
    )


@pytest.mark.asyncio
async def test_llm_chat_defaults_to_sarvam_when_no_tenant_setting():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "get_setting", return_value=None), \
         patch.object(ai_reply, "sarvam_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="sarvam-30b",
        temperature=0.4,
        max_tokens=600,
        tenant_id="tenant-2",
    )


@pytest.mark.asyncio
async def test_llm_chat_routes_to_openrouter_for_non_sarvam_model():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    with patch.object(ai_reply, "get_setting", return_value="google/gemini-2.5-flash"), \
         patch.object(ai_reply, "openrouter_chat_completion", AsyncMock(return_value="a reply")) as mock_call:
        text = await ai_reply._llm_chat(messages, max_tokens=600, tenant_id="tenant-2")

    assert text == "a reply"
    mock_call.assert_called_once_with(
        messages=messages,
        model="google/gemini-2.5-flash",
        temperature=0.4,
        max_tokens=600,
    )


def test_default_reply_model_is_sarvam_30b():
    assert ai_reply._DEFAULT_REPLY_MODEL == "sarvam-30b"
```

Leave the rest of the file (`test_send_whatsapp_voice_reply_uses_sarvam_tts_and_meta_audio_upload` onward) untouched.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_ai_reply_llm_wiring.py -v`
Expected: FAIL — `AttributeError: <module 'app.services.ai_reply'> does not have the attribute 'openrouter_chat_completion'` (and `_DEFAULT_REPLY_MODEL` not found)

- [ ] **Step 3: Write the implementation**

In `backend/app/services/ai_reply.py`, replace lines 20-41 (the `sarvam_client` import through the end of `_llm_chat`) with:

```python
from app.config_dynamic import get_setting
from app.services.sarvam_client import sarvam_chat_completion, sarvam_chat_completion_with_tools
from app.services.openrouter_client import openrouter_chat_completion

_DEFAULT_REPLY_MODEL = "sarvam-30b"


def _resolve_reply_model(tenant_id: str | None) -> str:
    return get_setting("ai_reply_model", fallback=_DEFAULT_REPLY_MODEL, tenant_id=tenant_id) or _DEFAULT_REPLY_MODEL


async def _llm_complete(prompt: str, max_tokens: int = 300, tenant_id: str | None = None) -> str:
    model = _resolve_reply_model(tenant_id)
    if model.startswith("sarvam"):
        return await sarvam_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.4,
            max_tokens=max_tokens,
            tenant_id=tenant_id,
        )
    return await openrouter_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.4,
        max_tokens=max_tokens,
    )


async def _llm_chat(messages: list[dict], max_tokens: int = 300, tenant_id: str | None = None) -> str:
    model = _resolve_reply_model(tenant_id)
    if model.startswith("sarvam"):
        return await sarvam_chat_completion(
            messages=messages,
            model=model,
            temperature=0.4,
            max_tokens=max_tokens,
            tenant_id=tenant_id,
        )
    return await openrouter_chat_completion(
        messages=messages,
        model=model,
        temperature=0.4,
        max_tokens=max_tokens,
    )
```

Every other reference to `_REPLY_MODEL` in the file (there should be none outside the block just replaced — confirm with `grep -n "_REPLY_MODEL" backend/app/services/ai_reply.py` returning no matches) stays as-is; `sarvam_chat_completion_with_tools` keeps being called directly and unconditionally at its existing call site (~line 936), unaffected by this change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_ai_reply_llm_wiring.py -v`
Expected: 6 passed (4 new + `test_send_whatsapp_voice_reply_uses_sarvam_tts_and_meta_audio_upload` + `test_generate_reply_uses_voice_only_for_audio_inbound_whatsapp_dispatch`)

Also run the full backend suite to catch any other test that imported `ai_reply._REPLY_MODEL`:

Run: `cd backend && grep -rn "_REPLY_MODEL" tests/ app/`
Expected: no output (confirms nothing else referenced the removed constant)

Run: `cd backend && pytest tests/ -k "ai_reply" -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_ai_reply_llm_wiring.py
git commit -m "feat: dispatch conversational reply model per-tenant via OpenRouter"
```

---

### Task 3: Expose and persist `ai_reply_model` in the operator config route

**Files:**
- Modify: `backend/app/routes/operator.py:1011` (inside the `settings` dict of `client_config`)
- Modify: `backend/tests/test_operator_client_config.py`

**Interfaces:**
- Consumes: nothing new — `update_client_config` (existing, unchanged) already upserts any key present in `payload.settings: dict[str, str | bool]`, so `{"settings": {"ai_reply_model": "openai/gpt-5-mini"}}` already works against it once the frontend sends it.
- Produces: `GET /api/v1/operator/clients/{tenant_id}/config` response gains `settings.ai_reply_model: str`, defaulting to `"sarvam-30b"` when no row exists.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_operator_client_config.py`, inside `test_get_client_config`'s mocked `app_settings` rows list (the list under `elif name == "app_settings":`), add a new row:

```python
                    {"key": "ai_reply_model", "value": "openai/gpt-5-mini"},
```

And add this assertion after the existing `self.assertEqual(body["settings"]["kb_retrieval_mode"], "hybrid")` line:

```python
        self.assertEqual(body["settings"]["ai_reply_model"], "openai/gpt-5-mini")
```

Then add a new test method in the same `OperatorClientConfigTests` class (after `test_get_client_config`) covering the no-row-yet default:

```python
    @patch("app.routes.operator.get_supabase")
    def test_get_client_config_defaults_ai_reply_model_to_sarvam(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "tenants":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
                    "id": "tenant-1",
                    "enabled_features": []
                }
            elif name == "app_settings":
                tbl.select.return_value.eq.return_value.execute.return_value.data = []
            elif name == "tenant_subscriptions":
                tbl.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
            elif name == "tenant_usage_counters":
                tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            return tbl

        db.table.side_effect = table
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/operator/clients/tenant-1/config")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["settings"]["ai_reply_model"], "sarvam-30b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_operator_client_config.py -v`
Expected: FAIL — `KeyError: 'ai_reply_model'` on both the modified and new test

- [ ] **Step 3: Write the implementation**

In `backend/app/routes/operator.py`, inside `client_config`'s returned `"settings"` dict (the block starting at line 1001), add one line after the `kb_retrieval_mode` entry (line 1011):

```python
            "ai_reply_model": settings_map.get("ai_reply_model") or "sarvam-30b",
```

No change to `update_client_config` — it already generically upserts whatever keys are present in `payload.settings`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_operator_client_config.py -v`
Expected: all pass (existing `test_patch_client_config` untouched and still green, since it doesn't reference `ai_reply_model`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/operator.py backend/tests/test_operator_client_config.py
git commit -m "feat: expose ai_reply_model in operator client config endpoint"
```

---

### Task 4: Operator console UI — Conversational Reply Model picker

**Files:**
- Modify: `frontend/app/operator/(console)/client/[id]/views/config.tsx`

**Interfaces:**
- Consumes: `GET/PATCH /api/v1/operator/clients/{tenantId}/config` (Task 3) — `settings.ai_reply_model: string` on read, `{settings: {ai_reply_model: string}}` on write, via the file's existing `apiFetch<T>` helper.
- Produces: nothing consumed elsewhere — this is a leaf UI component.

- [ ] **Step 1: Add the new type and settings field**

In `config.tsx`, after the existing `type MediaRecommendationSettingKey = ...` (line 24), add:

```typescript
type ReplyModelId =
  | "sarvam-30b"
  | "meta-llama/llama-3.3-70b-instruct"
  | "openai/gpt-5-mini"
  | "google/gemini-2.5-flash"
  | "openai/gpt-5"
  | "google/gemini-2.5-pro";

const REPLY_MODELS: { id: ReplyModelId; label: string; provider: string; costTier: "$" | "$$" | "$$$"; desc: string }[] = [
  { id: "sarvam-30b", label: "Sarvam 30B", provider: "Sarvam", costTier: "$", desc: "Default. Best fit for Tamil/Hindi/Hinglish conversations." },
  { id: "meta-llama/llama-3.3-70b-instruct", label: "Llama 3.3 70B", provider: "Groq via OpenRouter", costTier: "$", desc: "Cheapest option. Fast, strong in English, weaker on Indic-language nuance." },
  { id: "openai/gpt-5-mini", label: "GPT-5 Mini", provider: "OpenAI via OpenRouter", costTier: "$$", desc: "Balanced quality and cost." },
  { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash", provider: "Google via OpenRouter", costTier: "$$", desc: "Balanced quality and cost, strong multimodal support." },
  { id: "openai/gpt-5", label: "GPT-5", provider: "OpenAI via OpenRouter", costTier: "$$$", desc: "Highest quality, highest cost." },
  { id: "google/gemini-2.5-pro", label: "Gemini 2.5 Pro", provider: "Google via OpenRouter", costTier: "$$$", desc: "Highest quality, highest cost." },
];
```

In the `ConfigData["settings"]` interface (lines 84-95), add after `kb_retrieval_mode: RetrievalMode;`:

```typescript
    ai_reply_model: ReplyModelId;
```

- [ ] **Step 2: Add saving state and the update handler**

After the existing `const [sarvamSaving, setSarvamSaving] = useState(false);` (line 168), add:

```typescript
  const [replyModelSaving, setReplyModelSaving] = useState<ReplyModelId | null>(null);
```

After the existing `updateRetrievalMode` function (after line 198), add:

```typescript
  async function updateReplyModel(model: ReplyModelId) {
    if (!config || config.settings.ai_reply_model === model) return;
    setReplyModelSaving(model);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { ai_reply_model: model }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          ai_reply_model: model
        }
      });
      toast.success(`Conversational reply model set to "${REPLY_MODELS.find(m => m.id === model)?.label}".`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update reply model");
      toast.error("Failed to update reply model. Please try again.");
    } finally {
      setReplyModelSaving(null);
    }
  }
```

- [ ] **Step 3: Add the UI section**

Immediately before the closing `</div>` that ends the component's returned JSX (after the "Knowledge Search Mode" section's closing `</div>`, i.e. right before line 759's final `</div>`), add:

```tsx
      {/* Conversational Reply Model */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Sparkles size={16} className="text-ink-muted" />
          Conversational Reply Model
        </h3>
        <p className="mb-3 text-xs leading-relaxed text-ink-muted">
          Controls which AI model generates auto-replies and reengagement messages for this client.
        </p>
        <div className="grid gap-4 md:grid-cols-3">
          {REPLY_MODELS.map((option) => {
            const selected = config.settings.ai_reply_model === option.id;
            const saving = replyModelSaving === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => updateReplyModel(option.id)}
                disabled={!!replyModelSaving || selected}
                className={`rounded-card border p-4 text-left shadow-sm transition-all ${
                  selected
                    ? "border-primary bg-primary-light text-ink ring-1 ring-primary/10"
                    : "border-border bg-white hover:border-primary-muted"
                } ${replyModelSaving && !saving ? "opacity-70" : ""} disabled:cursor-default`}
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 justify-between">
                      <p className="text-sm font-semibold text-ink">{option.label}</p>
                      {saving && <Loader2 size={14} className="animate-spin text-primary" />}
                      {selected && !saving && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-success/10 text-success">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-[11px] font-medium text-ink-muted">{option.provider} · {option.costTier}</p>
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{option.desc}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run typecheck`
Expected: no errors

- [ ] **Step 5: Manual verification in the browser**

This view has no existing per-component unit test in this codebase (`client/[id]/views/*` is intentionally outside the Vitest sweep per the project's own conventions) — verify manually:

Run: `cd frontend && npm run dev`

1. Log into `/operator/login`, open any client's detail page, go to the Config tab.
2. Confirm a "Conversational Reply Model" section renders with 6 options, "Sarvam 30B" shown as Active by default.
3. Click "GPT-5 Mini" — confirm a loading spinner shows on that card, then it becomes Active and a success toast appears.
4. Refresh the page — confirm "GPT-5 Mini" is still shown as Active (persisted).
5. Click "Sarvam 30B" to switch back.

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/operator/(console)/client/[id]/views/config.tsx"
git commit -m "feat: add conversational reply model picker to operator console"
```

---

## Self-Review

**Spec coverage:** Operator can assign a model per client for conversational auto-reply (Task 2 dispatch + Task 4 UI) and reengagement (same `_llm_complete` call path, Task 2 covers it automatically) → covered. OpenRouter used for non-Sarvam options, BYOK mode, one platform key → Task 1 + Global Constraints. Voice/STT/call-transcription/OCR explicitly deferred → stated in Global Constraints, not silently dropped.

**Placeholder scan:** No TBD/TODO markers; every step has complete code; no "similar to Task N" shortcuts — Task 2's Sarvam and OpenRouter branches are both written out in full in both `_llm_complete` and `_llm_chat` rather than cross-referenced.

**Type consistency:** `_DEFAULT_REPLY_MODEL` (Task 2) is the single source of truth for the fallback string `"sarvam-30b"`, matched exactly in Task 3's route default and Task 4's `REPLY_MODELS[0].id`. `openrouter_chat_completion(messages, model, temperature, max_tokens)` signature (Task 1) matches every call site in Task 2. `ReplyModelId` (Task 4, frontend) lists exactly the 6 slugs the backend can receive — any future addition needs updating both `REPLY_MODELS` (Task 4) and re-verifying the slug still exists via `curl https://openrouter.ai/api/v1/models` (Global Constraints note).
