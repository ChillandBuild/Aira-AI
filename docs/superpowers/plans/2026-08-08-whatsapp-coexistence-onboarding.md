# WhatsApp Coexistence Onboarding (Approach A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant connect an existing WhatsApp Business app number via Meta's Coexistence Embedded Signup path, and make sure messages a human sends from that phone app show up in Aira's conversation history.

**Architecture:** Add a second Embedded Signup trigger on the frontend that passes Meta's `featureType: 'whatsapp_business_app_onboarding'` extra, handle the distinct `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` postMessage event, skip the (wrong, for this path) phone-number-registration call on the backend, and add a `smb_message_echoes` webhook handler that records phone-app-sent messages the same way an operator's manual reply is recorded today.

**Tech Stack:** FastAPI (`backend/app/`), pytest, Next.js/TypeScript (`frontend/app/dashboard/settings/`).

## Global Constraints

- Multi-tenancy: every DB read/write must be scoped by `tenant_id` (Hard Invariant 6).
- WhatsApp webhooks must already be past `X-Hub-Signature-256` verification before any field-specific logic runs — this plan adds a branch *inside* that already-verified path, no changes to signature checks (Hard Invariant 9).
- No hardcoded platform-key fallbacks — this plan doesn't touch provider keys, but any new config read must stay per-tenant.

---

### Task 1: Skip phone registration on the coexistence Embedded Signup path

**Files:**
- Modify: `backend/app/routes/app_settings.py:35-39` (`EmbeddedSignupRequest`), `backend/app/routes/app_settings.py:655-757` (`whatsapp_embedded_signup`)
- Test: `backend/tests/test_whatsapp_embedded_signup_coexistence.py` (new)

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `EmbeddedSignupRequest.is_coexistence: bool = False` — Task 3 (frontend) sends this field in the POST body.

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_coexistence_signup_skips_phone_registration():
    from app.routes.app_settings import EmbeddedSignupRequest, whatsapp_embedded_signup

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp({"success": True})
        async def get(self, url, **kwargs):
            return _Resp({"display_phone_number": "+919999999999", "verified_name": "Bloom Matrix"})

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock()) as register, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        result = await whatsapp_embedded_signup(
            EmbeddedSignupRequest(
                code="single-use-code",
                waba_id="waba-1",
                phone_number_id="phone-1",
                is_coexistence=True,
            ),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    register.assert_not_called()
    assert result["success"] is True
    assert result["phone_number"] == "+919999999999"


@pytest.mark.asyncio
async def test_standard_signup_still_registers_the_phone_number():
    from app.routes.app_settings import EmbeddedSignupRequest, whatsapp_embedded_signup

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            return _Resp({"success": True})
        async def get(self, url, **kwargs):
            return _Resp({"display_phone_number": "+919999999999", "verified_name": "Bloom Matrix"})

    with patch("app.services.meta_cloud.exchange_embedded_signup_code", new=AsyncMock(return_value={"access_token": "token-1"})), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})) as register, \
         patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_Client()), \
         patch("app.routes.app_settings.record_audit_event"), \
         patch("app.config_dynamic.invalidate_cache"):
        await whatsapp_embedded_signup(
            EmbeddedSignupRequest(
                code="single-use-code",
                waba_id="waba-1",
                phone_number_id="phone-1",
            ),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    register.assert_awaited_once()
```

Add both functions to `backend/tests/test_whatsapp_embedded_signup_coexistence.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_whatsapp_embedded_signup_coexistence.py -v`
Expected: FAIL — `EmbeddedSignupRequest` has no field `is_coexistence` (Pydantic validation error), and/or `register.assert_not_called()` fails because registration always runs today.

- [ ] **Step 3: Add the field and branch the registration call**

In `backend/app/routes/app_settings.py`, change:

```python
class EmbeddedSignupRequest(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str
    business_id: str | None = None
```

to:

```python
class EmbeddedSignupRequest(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str
    business_id: str | None = None
    is_coexistence: bool = False
```

Then in `whatsapp_embedded_signup`, replace:

```python
    pin = "".join(secrets.choice("0123456789") for _ in range(6))
    reg_result = await register_phone_number(payload.phone_number_id, access_token, pin)
    if "error" in reg_result:
        logger.warning(f"Embedded Signup: phone registration failed tenant={tenant_id}: {reg_result['error']}")
```

with:

```python
    if payload.is_coexistence:
        # Number is already registered on the phone's WhatsApp Business app —
        # calling register_phone_number here would be wrong for this path.
        logger.info(f"Embedded Signup: coexistence path — skipping phone registration tenant={tenant_id}")
    else:
        pin = "".join(secrets.choice("0123456789") for _ in range(6))
        reg_result = await register_phone_number(payload.phone_number_id, access_token, pin)
        if "error" in reg_result:
            logger.warning(f"Embedded Signup: phone registration failed tenant={tenant_id}: {reg_result['error']}")
```

Also extend the audit event metadata a few lines below so the connection type is visible in the audit log — change:

```python
        metadata={"channel": "whatsapp", "waba_id": payload.waba_id, "subscribed": subscribed},
```

to:

```python
        metadata={"channel": "whatsapp", "waba_id": payload.waba_id, "subscribed": subscribed, "is_coexistence": payload.is_coexistence},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_whatsapp_embedded_signup_coexistence.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Run the full existing app_settings test suite to check for regressions**

Run: `cd backend && pytest tests/ -k embedded_signup -v`
Expected: PASS (includes `test_facebook_embedded_signup.py`, unaffected by this change)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/app_settings.py backend/tests/test_whatsapp_embedded_signup_coexistence.py
git commit -m "feat(whatsapp): skip phone registration on coexistence Embedded Signup"
```

---

### Task 2: Handle `smb_message_echoes` in the WhatsApp webhook

**Files:**
- Modify: `backend/app/routes/webhook.py:365-383` (add a new `elif` branch before the existing `elif field == "messages":`)
- Test: `backend/tests/test_whatsapp_coexistence_echo_webhook.py` (new)

**Interfaces:**
- Consumes: `_get_tenant_id_for_meta_number(phone_number_id: str, db) -> str | None` (`webhook.py:46`, already defined).
- Produces: nothing new consumed elsewhere in this plan.

- [ ] **Step 1: Write the failing test**

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request

from app.routes import webhook


class _Result:
    def __init__(self, data):
        self.data = data


class _RouteTable:
    def __init__(self, name, captured_messages, existing_message_ids=(), lead_exists=True):
        self.name = name
        self.captured_messages = captured_messages
        self.existing_message_ids = existing_message_ids
        self.lead_exists = lead_exists
        self.operation = "select"
        self._last_eq_values = []

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def insert(self, row):
        self.operation = "insert"
        if self.name == "messages":
            self.captured_messages.append(row)
        return self

    def eq(self, _col, value=None, **_kwargs):
        self._last_eq_values.append(value)
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self.name == "phone_numbers":
            return _Result({"tenant_id": "tenant-1"})
        if self.name == "messages" and self.operation == "select":
            msg_id = self._last_eq_values[0] if self._last_eq_values else None
            found = [{"id": "existing"}] if msg_id in self.existing_message_ids else []
            return _Result(found)
        if self.name == "messages" and self.operation == "insert":
            return _Result([{"id": "message-1"}])
        if self.name == "leads" and self.operation == "select":
            return _Result([{"id": "lead-1"}] if self.lead_exists else [])
        return _Result([])


def _route_db(captured_messages, existing_message_ids=(), lead_exists=True):
    db = MagicMock()
    db.table.side_effect = lambda name: _RouteTable(name, captured_messages, existing_message_ids, lead_exists)
    return db


def _echo_payload(echo_id="wamid.echo.1", to="919999999999", body="Sure, I'll call you back"):
    return {
        "entry": [{
            "changes": [{
                "field": "smb_message_echoes",
                "value": {
                    "metadata": {"phone_number_id": "phone-number-1"},
                    "message_echoes": [{
                        "from": "918888888888",
                        "to": to,
                        "id": echo_id,
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
            }],
        }],
    }


async def _post_webhook(db, payload):
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=json.dumps(payload).encode("utf-8"))
    request.headers = {"x-hub-signature-256": "sha256=test"}
    background_tasks = MagicMock(spec=BackgroundTasks)
    with patch("app.routes.webhook.get_supabase", return_value=db), \
         patch("app.routes.webhook.verify_meta_signature", return_value=True):
        return await webhook.whatsapp_webhook(request, background_tasks)


@pytest.mark.asyncio
async def test_smb_message_echo_is_recorded_as_outbound_message():
    captured: list[dict] = []
    db = _route_db(captured)

    response = await _post_webhook(db, _echo_payload())

    assert response == {"status": "ok"}
    assert captured == [{
        "lead_id": "lead-1",
        "tenant_id": "tenant-1",
        "direction": "outbound",
        "channel": "whatsapp",
        "content": "Sure, I'll call you back",
        "is_ai_generated": False,
        "meta_message_id": "wamid.echo.1",
    }]


@pytest.mark.asyncio
async def test_smb_message_echo_is_not_duplicated_on_replay():
    captured: list[dict] = []
    db = _route_db(captured, existing_message_ids={"wamid.echo.1"})

    await _post_webhook(db, _echo_payload())

    assert captured == []


@pytest.mark.asyncio
async def test_smb_message_echo_drops_when_no_lead_matches():
    captured: list[dict] = []
    db = _route_db(captured, lead_exists=False)

    await _post_webhook(db, _echo_payload())

    assert captured == []
```

Add these to `backend/tests/test_whatsapp_coexistence_echo_webhook.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_echo_webhook.py -v`
Expected: FAIL — no branch handles `field == "smb_message_echoes"` today, so nothing is inserted and `captured` stays empty for the first test.

- [ ] **Step 3: Add the handler**

In `backend/app/routes/webhook.py`, insert a new `elif` branch immediately before `elif field == "messages":` (`webhook.py:383`):

```python
            elif field == "smb_message_echoes":
                meta_phone_number_id = value.get("metadata", {}).get("phone_number_id", "")
                db = get_supabase()
                tenant_id = _get_tenant_id_for_meta_number(meta_phone_number_id, db) if meta_phone_number_id else None
                if not tenant_id:
                    logger.warning(f"No tenant for meta phone_number_id={meta_phone_number_id}, dropping smb_message_echoes payload")
                    continue
                for echo in value.get("message_echoes", []):
                    echo_type = echo.get("type")
                    echo_id = echo.get("id", "")
                    if echo_type != "text":
                        logger.info(f"smb_message_echoes: skipping unsupported type={echo_type}")
                        continue
                    body = (echo.get("text") or {}).get("body", "").strip()
                    wa_id = echo.get("to", "")
                    phone = f"+{wa_id}" if wa_id and not wa_id.startswith("+") else wa_id
                    if not phone or not body or not echo_id:
                        continue

                    already = db.table("messages").select("id").eq("meta_message_id", echo_id).eq("tenant_id", tenant_id).limit(1).execute()
                    if already.data:
                        continue

                    lead = db.table("leads").select("id").eq("phone", phone).eq("tenant_id", tenant_id).limit(1).execute()
                    if not lead.data:
                        logger.warning(f"smb_message_echoes: no lead for phone={phone} tenant={tenant_id}, dropping")
                        continue
                    lead_id = lead.data[0]["id"]

                    db.table("messages").insert({
                        "lead_id": lead_id,
                        "tenant_id": tenant_id,
                        "direction": "outbound",
                        "channel": "whatsapp",
                        "content": body,
                        "is_ai_generated": False,
                        "meta_message_id": echo_id,
                    }).execute()
                    logger.info(f"smb_message_echoes: recorded phone-app message for lead {lead_id}")

```

Note the `already.data` dedup check needs the `_RouteTable.eq` fake above to track the value passed to the *first* `.eq(...)` call (`meta_message_id`) — that's what `_last_eq_values[0]` reads in the test fake.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_whatsapp_coexistence_echo_webhook.py -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Run the full webhook test suite to check for regressions**

Run: `cd backend && pytest tests/test_whatsapp_audio_webhook.py tests/test_meta_webhook_verify.py tests/test_expert_handoff_webhook.py tests/test_webhook_expert_handoff_routing.py -v`
Expected: PASS — the new branch sits before the existing `messages`/`phone_number_quality_update` branches and doesn't change their behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/webhook.py backend/tests/test_whatsapp_coexistence_echo_webhook.py
git commit -m "feat(whatsapp): record smb_message_echoes as outbound messages"
```

---

### Task 3: Frontend — coexistence Embedded Signup trigger

**Files:**
- Modify: `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx:18-29` (`window.FB` type), `:50` (`EmbeddedSignupSession` type), `:740-823` (`finishEmbeddedSignup`, the `message` listener, `handleConnectWithFacebook`), `:979-986` (button JSX)

**Interfaces:**
- Consumes: `POST /api/v1/settings/whatsapp/embedded-signup` now accepts an optional `is_coexistence` boolean in its JSON body (Task 1).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Widen the `window.FB.login` type to accept `extras`**

In `ConnectChannelsPanel.tsx`, change:

```typescript
      login: (
        callback: (response: { authResponse?: { code?: string } }) => void,
        options: { config_id: string; response_type: string; override_default_response_type: boolean }
      ) => void;
```

to:

```typescript
      login: (
        callback: (response: { authResponse?: { code?: string } }) => void,
        options: {
          config_id: string;
          response_type: string;
          override_default_response_type: boolean;
          extras?: { featureType?: string; sessionInfoVersion?: string };
        }
      ) => void;
```

- [ ] **Step 2: Track coexistence on the session ref**

Change:

```typescript
type EmbeddedSignupSession = { waba_id?: string; phone_number_id?: string; business_id?: string };
```

to:

```typescript
type EmbeddedSignupSession = { waba_id?: string; phone_number_id?: string; business_id?: string; is_coexistence?: boolean };
```

- [ ] **Step 3: Send `is_coexistence` in the finish request**

In `finishEmbeddedSignup` (around line 757), change the `body: JSON.stringify({...})` from:

```typescript
        body: JSON.stringify({
          code,
          waba_id: session.waba_id,
          phone_number_id: session.phone_number_id,
          business_id: session.business_id,
        }),
```

to:

```typescript
        body: JSON.stringify({
          code,
          waba_id: session.waba_id,
          phone_number_id: session.phone_number_id,
          business_id: session.business_id,
          is_coexistence: session.is_coexistence ?? false,
        }),
```

- [ ] **Step 4: Handle the coexistence finish event**

In the `handleMessage` function inside the `message`-listener `useEffect` (around line 784), change:

```typescript
        if (data?.type === "WA_EMBEDDED_SIGNUP" && data?.event === "FINISH") {
          esSessionRef.current = {
            waba_id: data.data?.waba_id,
            phone_number_id: data.data?.phone_number_id,
            business_id: data.data?.business_id,
          };
          finishEmbeddedSignup();
        }
```

to:

```typescript
        if (
          data?.type === "WA_EMBEDDED_SIGNUP" &&
          (data?.event === "FINISH" || data?.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING")
        ) {
          esSessionRef.current = {
            waba_id: data.data?.waba_id,
            phone_number_id: data.data?.phone_number_id,
            business_id: data.data?.business_id,
            is_coexistence: data.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
          };
          finishEmbeddedSignup();
        }
```

- [ ] **Step 5: Add the coexistence trigger function**

Immediately after `handleConnectWithFacebook` (after line 823's closing `}`), add:

```typescript
  async function handleConnectCoexistence() {
    if (!canManage) return;
    setEsState("connecting");
    setEsError(null);
    await loadFacebookSdk();
    window.FB?.login(
      (response) => {
        const code = response?.authResponse?.code;
        if (!code) {
          setEsState("idle");
          return;
        }
        esCodeRef.current = code;
        finishEmbeddedSignup();
      },
      {
        config_id: META_CONFIG_ID,
        response_type: "code",
        override_default_response_type: true,
        extras: { featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" },
      }
    );
  }
```

- [ ] **Step 6: Add the secondary button in the Embedded Onboarding card**

In the JSX around line 976-987, change:

```tsx
                    <div>
                      {esError && <p className="mb-3 rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{esError}</p>}
                      {activateResult?.success && <p className="mb-3 rounded-xl bg-emerald-50 px-3 py-2 font-body text-xs text-emerald-700">{activateResult.message}</p>}
                      <button
                        type="button"
                        onClick={handleConnectWithFacebook}
                        disabled={!canManage || esState === "connecting" || esState === "finishing"}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-label text-sm font-bold text-white shadow-[0_8px_20px_rgba(16,185,129,0.22)] transition-all hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {esState === "connecting" || esState === "finishing" ? <><Loader2 size={16} className="animate-spin" />Connecting…</> : <>Connect with Meta <ArrowRight size={16} /></>}
                      </button>
                    </div>
```

to:

```tsx
                    <div>
                      {esError && <p className="mb-3 rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{esError}</p>}
                      {activateResult?.success && <p className="mb-3 rounded-xl bg-emerald-50 px-3 py-2 font-body text-xs text-emerald-700">{activateResult.message}</p>}
                      <button
                        type="button"
                        onClick={handleConnectWithFacebook}
                        disabled={!canManage || esState === "connecting" || esState === "finishing"}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-label text-sm font-bold text-white shadow-[0_8px_20px_rgba(16,185,129,0.22)] transition-all hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {esState === "connecting" || esState === "finishing" ? <><Loader2 size={16} className="animate-spin" />Connecting…</> : <>Connect with Meta <ArrowRight size={16} /></>}
                      </button>
                      <button
                        type="button"
                        onClick={handleConnectCoexistence}
                        disabled={!canManage || esState === "connecting" || esState === "finishing"}
                        className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-xl px-4 py-2 font-label text-xs font-semibold text-emerald-700 transition-all hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Already using the WhatsApp Business app? Connect without switching <ArrowRight size={12} />
                      </button>
                    </div>
```

- [ ] **Step 7: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS, no new errors.

- [ ] **Step 8: Lint**

Run: `cd frontend && npm run lint`
Expected: PASS, no new errors (per project convention, CI runs `next lint` and tsc alone is not sufficient).

- [ ] **Step 9: Commit**

```bash
git add frontend/app/dashboard/settings/ConnectChannelsPanel.tsx
git commit -m "feat(whatsapp): add coexistence Embedded Signup entry point"
```

---

## Manual verification (not automatable in this environment)

After all three tasks are merged and deployed:
1. Click "Already using the WhatsApp Business app? Connect without switching" as the pilot tenant, complete the QR-scan flow on the client's phone, and confirm the dashboard shows "WhatsApp connected" without a `register_phone_number` call in the Render logs.
2. Send a message from the phone app during a live conversation and confirm it appears in the dashboard conversation view with the correct content.
3. Confirm `history` and `smb_app_state_sync` webhook deliveries (already subscribed) don't cause any errors in the logs — they should be silently ignored per Task 2 leaving the `if/elif` chain's implicit no-op for unmatched fields.
