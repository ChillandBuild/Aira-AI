# Paid Expert Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a lead who needs a real human expert (astrologer, trainer, doctor, etc.) opt in, give their details in free-flowing WhatsApp conversation, pay in-chat via Razorpay, and have the AI go silent for that lead — all driven by a per-tenant config, no code changes needed to onboard a new client.

**Architecture:** One new backend service (`expert_handoff.py`) drives a small per-lead state machine (`offer_pending → collecting → awaiting_confirmation → awaiting_payment → paid → resolved`) stored in a new `expert_handoff_sessions` table. Detection and field extraction are separate, dedicated LLM calls (not embedded in the main conversational prompt — see rationale below), so the flow can't derail the AI's normal replies and vice versa. Payment reuses Razorpay Payment Links via a service ported in from `feature/client-requirements` unchanged. Config (fields/fee/messages) lives in the existing per-tenant `app_settings` key/value store and is edited from a new dashboard settings panel.

**Tech Stack:** FastAPI (backend/app), Supabase/Postgres, Gemini (`gemini_chat_completion_json`) for detection/extraction, Razorpay Payment Links API, Next.js 14 (frontend/app/dashboard/settings).

## Global Constraints

- No changes to `ai_reply.py`'s main conversational system prompt. Detection and extraction are separate LLM calls, deliberately decoupled — this codebase already tried and fully removed `[COLLECT_DONE]{json}`, a mechanism that had the model emit a hidden extraction tag *inside* its normal reply (migration `130_drop_legacy_booking_artifacts.sql`, `.agents/decisions/log.md` 2026-07-05 entries). Repeating that shape is out of scope for this plan.
- Feature is **off by default** per tenant (`enabled: false` until a tenant admin configures it) — never opt-out.
- Do not modify `payment_razorpay.py` once ported — it is already generic (tenant-scoped via `get_setting(tenant_id=...)`, no astrology-specific fields). Its Razorpay `notes` payload uses the literal keys `booking_id`/`booking_ref` regardless of caller — callers passing a non-booking ID (our session id) into `booking_id` is expected and fine, not a naming bug to fix.
- Mute uses the existing `leads.ai_enabled` column and its existing check in `generate_reply` (`ai_reply.py:1164`) — no new mute mechanism.
- Astrologer/expert delivery adapter (pushing the paid session to Astrotamil's dashboard, relaying their reply back) is **out of scope for this plan** — blocked on Astrotamil's integration surface being unknown. `expert_handoff_sessions.status = 'paid'` is the hand-off point a future adapter will consume; nothing here builds that adapter.
- Follow this repo's existing per-domain settings-panel pattern exactly (`InboxConfigPanel`/`TelecallingConfigPanel` + `app_settings.py`'s `/inbox-config`/`/telecalling-config` GET/PATCH routes) rather than inventing a new config plumbing shape.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/supabase/migrations/168_expert_handoff_sessions.sql` | New table for per-lead handoff sessions |
| `backend/app/services/payment_razorpay.py` | **New** (ported unchanged from `feature/client-requirements`) — Razorpay Payment Links wrapper |
| `backend/app/services/expert_handoff.py` | **New** — config get/save, detection, extraction, state machine, payment confirmation |
| `backend/app/routes/expert_handoff.py` | **New** — public Razorpay webhook route only |
| `backend/app/routes/app_settings.py` | **Modify** — add `ExpertHandoffConfigUpdate` model + GET/PATCH `/expert-handoff-config` |
| `backend/app/routes/webhook.py` | **Modify** — call `route_expert_handoff` before `generate_reply` in `_process_inbound_message_background` |
| `backend/app/main.py` | **Modify** — register the new public router |
| `backend/tests/test_payment_razorpay.py` | **New** (ported from branch) |
| `backend/tests/test_expert_handoff.py` | **New** — config, detection, extraction, state machine |
| `backend/tests/test_expert_handoff_webhook.py` | **New** — Razorpay webhook route |
| `frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx` | **New** — tenant admin config UI |
| `frontend/app/dashboard/settings/page.tsx` | **Modify** — mount the new panel |

---

## Task 1: Migration — `expert_handoff_sessions` table

**Files:**
- Create: `backend/supabase/migrations/168_expert_handoff_sessions.sql`

**Interfaces:**
- Produces: table `expert_handoff_sessions` with columns `id, tenant_id, lead_id, status, collected_data, trigger_reason, amount_paise, payment_link, razorpay_payment_id, paid_at, resolved_at, created_at, updated_at`. `status` values: `offer_pending | collecting | awaiting_confirmation | awaiting_payment | paid | resolved | cancelled`.

- [ ] **Step 1: Write the migration**

```sql
-- 168_expert_handoff_sessions.sql
-- Generic per-tenant "paid expert handoff" flow: a lead opts in to pay for a
-- human consultation, details are collected in free-flowing conversation
-- (LLM slot-filling, not a rigid step order), payment happens in-chat via
-- Razorpay. One row per lead per attempt.

CREATE TABLE IF NOT EXISTS expert_handoff_sessions (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid        NOT NULL,
  lead_id        uuid        NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  status         text        NOT NULL DEFAULT 'offer_pending'
                   CHECK (status IN (
                     'offer_pending', 'collecting', 'awaiting_confirmation',
                     'awaiting_payment', 'paid', 'resolved', 'cancelled'
                   )),
  collected_data jsonb       NOT NULL DEFAULT '{}',
  trigger_reason text,
  amount_paise   integer,
  payment_link   text,
  razorpay_payment_id text,
  paid_at        timestamptz,
  resolved_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS expert_handoff_lead_idx   ON expert_handoff_sessions (lead_id, tenant_id);
CREATE INDEX IF NOT EXISTS expert_handoff_status_idx ON expert_handoff_sessions (status, tenant_id);

-- Backend-only table (service role), same pattern as platform_defaults
-- (migration 143): RLS enabled, no client policies, so anon/authenticated
-- clients are denied and only the service role (used by the FastAPI backend)
-- can read/write it.
ALTER TABLE expert_handoff_sessions ENABLE ROW LEVEL SECURITY;
```

- [ ] **Step 2: Apply the migration to the local/dev Supabase project and verify**

Run: `cd backend && supabase db push` (or the project's existing migration-apply command — check `backend/supabase/config.toml` / existing CI step if `supabase db push` isn't the local convention).
Expected: migration applies with no errors; `expert_handoff_sessions` visible via `list_tables`.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/168_expert_handoff_sessions.sql
git commit -m "feat: add expert_handoff_sessions table"
```

---

## Task 2: Port `payment_razorpay.py`

**Files:**
- Create: `backend/app/services/payment_razorpay.py`
- Test: `backend/tests/test_payment_razorpay.py`

**Interfaces:**
- Produces: `async def create_payment_link(booking_id: str, booking_ref: str, amount_paise: int, customer_name: str, customer_phone: str, description: str, tenant_id: str | None = None) -> dict[str, Any]` returning `{"payment_link_url": str, "razorpay_payment_link_id": str}`.
- Produces: `def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool`.
- Consumes: `app.config_dynamic.get_setting` (already on main, already stores `razorpay_key_id`/`razorpay_key_secret`/`razorpay_webhook_secret` per tenant per migration `034_seed_tenant_app_settings.sql`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_payment_razorpay.py
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import payment_razorpay as pr


def test_get_key_id_raises_when_not_configured():
    with patch.object(pr, "get_setting", return_value=None):
        with pytest.raises(RuntimeError, match="razorpay_key_id"):
            pr._get_key_id(tenant_id="t-1")


def test_verify_webhook_signature_accepts_matching_hmac():
    with patch.object(pr, "get_setting", return_value="whsec_test"):
        body = b'{"event":"payment_link.paid"}'
        sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
        assert pr.verify_webhook_signature(body, sig) is True


def test_verify_webhook_signature_rejects_mismatched_hmac():
    with patch.object(pr, "get_setting", return_value="whsec_test"):
        assert pr.verify_webhook_signature(b"{}", "deadbeef") is False


@pytest.mark.asyncio
async def test_create_payment_link_returns_url_and_id():
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {"short_url": "https://rzp.io/abc", "id": "plink_123"}

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch.object(pr, "get_setting", side_effect=["key_id", "key_secret"]), \
         patch("httpx.AsyncClient", return_value=fake_client):
        result = await pr.create_payment_link(
            booking_id="session-1",
            booking_ref="EH-ABC123",
            amount_paise=2900,
            customer_name="Priya",
            customer_phone="+919876543210",
            description="Consultation — Priya (EH-ABC123)",
            tenant_id="t-1",
        )
    assert result == {"payment_link_url": "https://rzp.io/abc", "razorpay_payment_link_id": "plink_123"}


@pytest.mark.asyncio
async def test_create_payment_link_raises_on_failed_response():
    fake_resp = MagicMock()
    fake_resp.is_success = False
    fake_resp.status_code = 400
    fake_resp.text = "bad request"

    fake_client = AsyncMock()
    fake_client.post.return_value = fake_resp
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch.object(pr, "get_setting", side_effect=["key_id", "key_secret"]), \
         patch("httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(RuntimeError, match="Razorpay payment link creation failed"):
            await pr.create_payment_link(
                booking_id="session-1", booking_ref="EH-ABC123", amount_paise=2900,
                customer_name="Priya", customer_phone="+919876543210",
                description="x", tenant_id="t-1",
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_payment_razorpay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.payment_razorpay'`

- [ ] **Step 3: Create the file — port unchanged from `feature/client-requirements`**

```bash
git show feature/client-requirements:backend/app/services/payment_razorpay.py > backend/app/services/payment_razorpay.py
```

Verify the file matches exactly this content (the branch version, imports `get_setting` from `app.config_dynamic`, defines `_get_key_id`, `_get_key_secret`, `_get_webhook_secret`, `create_payment_link`, `verify_webhook_signature`):

```python
# backend/app/services/payment_razorpay.py
import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config_dynamic import get_setting

logger = logging.getLogger(__name__)

_RAZORPAY_BASE = "https://api.razorpay.com/v1"


def _get_key_id(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_key_id", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_key_id not configured in app settings")
    return v


def _get_key_secret(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_key_secret", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_key_secret not configured in app settings")
    return v


def _get_webhook_secret(tenant_id: str | None = None) -> str:
    v = get_setting("razorpay_webhook_secret", tenant_id=tenant_id)
    if not v:
        raise RuntimeError("razorpay_webhook_secret not configured in app settings")
    return v


async def create_payment_link(
    booking_id: str,
    booking_ref: str,
    amount_paise: int,
    customer_name: str,
    customer_phone: str,
    description: str,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a Razorpay Payment Link and return the short URL.

    Returns dict with keys:
      - payment_link_url: str
      - razorpay_payment_link_id: str
    """
    key_id = _get_key_id(tenant_id)
    key_secret = _get_key_secret(tenant_id)

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description,
        "customer": {
            "name": customer_name,
            "contact": customer_phone,
        },
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "notes": {
            "booking_id": booking_id,
            "booking_ref": booking_ref,
        },
        "callback_url": "",
        "callback_method": "get",
    }

    async with httpx.AsyncClient(auth=(key_id, key_secret), timeout=15.0) as client:
        resp = await client.post(
            f"{_RAZORPAY_BASE}/payment_links",
            json=payload,
            headers={"X-Razorpay-Idempotency-Key": f"booking:{booking_id}:payment_link"},
        )

    if not resp.is_success:
        raise RuntimeError(
            f"Razorpay payment link creation failed: {resp.status_code} {resp.text}"
        )

    data = resp.json()
    return {
        "payment_link_url": data["short_url"],
        "razorpay_payment_link_id": data["id"],
    }


def verify_webhook_signature(raw_body: bytes, received_signature: str) -> bool:
    """Verify Razorpay webhook payload using HMAC-SHA256."""
    try:
        secret = _get_webhook_secret()
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received_signature)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_payment_razorpay.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/payment_razorpay.py backend/tests/test_payment_razorpay.py
git commit -m "feat: port generic Razorpay payment link service"
```

---

## Task 3: Expert handoff config — get/save + settings API

**Files:**
- Create: `backend/app/services/expert_handoff.py` (config functions only this task)
- Modify: `backend/app/routes/app_settings.py`
- Test: `backend/tests/test_expert_handoff.py` (config section only this task)

**Interfaces:**
- Produces: `_DEFAULT_CONFIG: dict` = `{"enabled": False, "trigger_description": "", "offer_message": "", "fields": [], "amount_paise": 0}`
- Produces: `get_expert_handoff_config(tenant_id: str, db=None) -> dict`
- Produces: `save_expert_handoff_config(tenant_id: str, config: dict, db=None) -> None`
- Consumes (route): both functions above; `require_permission` from `app.dependencies.tenant`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_expert_handoff.py
from unittest.mock import MagicMock

from app.services import expert_handoff as eh


def _db_with_config(stored_json: str | None):
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": stored_json} if stored_json is not None else None
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    return db


def test_get_expert_handoff_config_returns_defaults_when_unset():
    db = _db_with_config(None)
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config == eh._DEFAULT_CONFIG


def test_get_expert_handoff_config_merges_stored_over_defaults():
    db = _db_with_config('{"enabled": true, "amount_paise": 2900}')
    config = eh.get_expert_handoff_config("t-1", db=db)
    assert config["enabled"] is True
    assert config["amount_paise"] == 2900
    assert config["fields"] == []  # default preserved


def test_save_expert_handoff_config_upserts_json_value():
    db = MagicMock()
    eh.save_expert_handoff_config("t-1", {"enabled": True, "amount_paise": 2900}, db=db)
    db.table.assert_called_with("app_settings")
    upsert_call = db.table.return_value.upsert
    upsert_call.assert_called_once()
    payload = upsert_call.call_args[0][0]
    assert payload["key"] == "expert_handoff_config"
    assert payload["tenant_id"] == "t-1"
    assert '"enabled": true' in payload["value"] or '"enabled":true' in payload["value"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.expert_handoff'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/expert_handoff.py
"""Generic, per-tenant paid expert handoff: a lead opts in to pay for a human
consultation, details are collected via LLM slot-filling (not a rigid step
order — see docs/superpowers/specs/2026-08-07-paid-expert-handoff-design.md
for why), payment happens in-chat via Razorpay, and the AI mutes for that
lead once paid.
"""
import json
import logging

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "enabled": False,
    "trigger_description": "",
    "offer_message": "",
    "fields": [],  # list of {"key": str, "label": str, "type": "text"|"date"|"choice", "options": list[str]?}
    "amount_paise": 0,
}


def get_expert_handoff_config(tenant_id: str, db=None) -> dict:
    """Return expert_handoff_config from app_settings, merged with defaults."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    row = (
        db.table("app_settings")
        .select("value")
        .eq("tenant_id", tenant_id)
        .eq("key", "expert_handoff_config")
        .maybe_single()
        .execute()
    )
    if row and row.data:
        try:
            stored = json.loads(row.data["value"])
            return {**_DEFAULT_CONFIG, **stored}
        except Exception:
            logger.warning(f"Failed to parse expert_handoff_config for tenant {tenant_id}")
    return dict(_DEFAULT_CONFIG)


def save_expert_handoff_config(tenant_id: str, config: dict, db=None) -> None:
    """Persist expert_handoff_config to app_settings."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    db.table("app_settings").upsert(
        {
            "key": "expert_handoff_config",
            "value": json.dumps(config),
            "tenant_id": tenant_id,
            "is_secret": False,
        },
        on_conflict="tenant_id,key",
    ).execute()
```

Now add the route. In `backend/app/routes/app_settings.py`, add to the `TelecallingConfigUpdate` class block (near the other `*Update` models, after `BusinessHoursUpdate`):

```python
class ExpertHandoffFieldUpdate(BaseModel):
    key: str
    label: str
    type: Literal["text", "date", "choice"]
    options: list[str] | None = None


class ExpertHandoffConfigUpdate(BaseModel):
    enabled: bool | None = None
    trigger_description: str | None = None
    offer_message: str | None = None
    fields: list[ExpertHandoffFieldUpdate] | None = None
    amount_paise: int | None = None
```

Add the import at the top of `app_settings.py`, alongside the existing `assignment` import block:

```python
from app.services.expert_handoff import get_expert_handoff_config, save_expert_handoff_config
```

Add the routes, placed after the existing `/telecalling-config` PATCH route (`app_settings.py:1146` area):

```python
@router.get("/expert-handoff-config")
async def get_expert_handoff_config_route(ctx: dict = Depends(require_settings_read)):
    return get_expert_handoff_config(ctx["tenant_id"])


@router.patch("/expert-handoff-config")
async def patch_expert_handoff_config(
    payload: ExpertHandoffConfigUpdate, ctx: dict = Depends(require_settings_manage)
):
    tenant_id = ctx["tenant_id"]
    current = get_expert_handoff_config(tenant_id)
    patch = payload.model_dump(exclude_none=True)
    if "amount_paise" in patch and patch["amount_paise"] < 0:
        raise HTTPException(status_code=400, detail="amount_paise must be >= 0")
    if "fields" in patch:
        keys = [f["key"] for f in patch["fields"]]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=400, detail="Duplicate field keys")
    merged = {**current, **patch}
    save_expert_handoff_config(tenant_id, merged)
    return merged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Sanity-check the route module still imports cleanly**

Run: `cd backend && python -c "from app.routes import app_settings"`
Expected: no errors (catches typos in the new Pydantic models / route wiring before runtime)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/expert_handoff.py backend/app/routes/app_settings.py backend/tests/test_expert_handoff.py
git commit -m "feat: expert handoff tenant config + settings API"
```

---

## Task 4: Detection — is this lead's message a handoff trigger?

**Files:**
- Modify: `backend/app/services/expert_handoff.py`
- Test: `backend/tests/test_expert_handoff.py` (append)

**Interfaces:**
- Consumes: `app.services.gemini_client.gemini_chat_completion_json(system_prompt, user_prompt, temperature, max_tokens, tenant_id, purpose) -> dict`
- Produces: `async def detect_expert_handoff_intent(message: str, trigger_description: str, tenant_id: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_expert_handoff.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_true_on_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": True})):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is True


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_false_on_no_match():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"matches": False})):
        result = await eh.detect_expert_handoff_intent(
            "What are your opening hours?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False


@pytest.mark.asyncio
async def test_detect_expert_handoff_intent_fails_closed_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.detect_expert_handoff_intent(
            "Will I get married this year?",
            trigger_description="Lead asks a personal astrology question",
            tenant_id="t-1",
        )
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -k detect_expert_handoff_intent -v`
Expected: FAIL with `AttributeError: module 'app.services.expert_handoff' has no attribute 'detect_expert_handoff_intent'`

- [ ] **Step 3: Write minimal implementation**

Add the import at the top of `expert_handoff.py`:

```python
from app.services.gemini_client import gemini_chat_completion_json
```

Add below `save_expert_handoff_config`:

```python
_DETECTION_SYSTEM_PROMPT = """You are a classifier. Given a business's description of what
kind of message should trigger a paid human-expert handoff, and one incoming customer
message, decide if THIS message matches that description.

Respond with JSON only: {"matches": true} or {"matches": false}. No other text."""


async def detect_expert_handoff_intent(message: str, trigger_description: str, tenant_id: str) -> bool:
    """Fail closed: any error, empty trigger_description, or unparseable response -> False.
    A missed offer is recoverable (the lead can ask again); a wrongly-triggered paid
    flow from a classifier hiccup is not."""
    if not trigger_description:
        return False
    user_prompt = f"Trigger description: {trigger_description}\n\nCustomer message: {message}"
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_DETECTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=50,
            tenant_id=tenant_id,
            purpose="expert_handoff_detection",
        )
        return bool(data.get("matches") is True)
    except Exception as e:
        logger.warning(f"Expert handoff detection failed, defaulting to no-match: {e}")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -k detect_expert_handoff_intent -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/expert_handoff.py backend/tests/test_expert_handoff.py
git commit -m "feat: expert handoff intent detection"
```

---

## Task 5: Slot-filling extraction

**Files:**
- Modify: `backend/app/services/expert_handoff.py`
- Test: `backend/tests/test_expert_handoff.py` (append)

**Interfaces:**
- Produces: `async def extract_fields(message: str, fields: list[dict], collected_data: dict, tenant_id: str) -> dict` — returns a **new** dict (existing `collected_data` merged with anything newly found this turn; never drops previously-collected values).
- Produces: `def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_expert_handoff.py
_FIELDS = [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "birthplace", "label": "Birthplace", "type": "text"},
]


def test_missing_field_labels_returns_unfilled_only():
    collected = {"name": "Priya"}
    assert eh.missing_field_labels(_FIELDS, collected) == ["Date of birth", "Birthplace"]


def test_missing_field_labels_empty_when_all_filled():
    collected = {"name": "Priya", "date_of_birth": "5 March 1995", "birthplace": "Chennai"}
    assert eh.missing_field_labels(_FIELDS, collected) == []


@pytest.mark.asyncio
async def test_extract_fields_merges_new_values_over_existing():
    llm_response = {"name": "Priya", "date_of_birth": "5 March 1995"}
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value=llm_response)):
        result = await eh.extract_fields(
            "I'm Priya, born 5 March 1995",
            fields=_FIELDS,
            collected_data={"birthplace": "Chennai"},  # already had this from an earlier turn
            tenant_id="t-1",
        )
    assert result == {"birthplace": "Chennai", "name": "Priya", "date_of_birth": "5 March 1995"}


@pytest.mark.asyncio
async def test_extract_fields_ignores_unknown_keys_from_llm():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(return_value={"name": "Priya", "favorite_color": "blue"})):
        result = await eh.extract_fields("I'm Priya", fields=_FIELDS, collected_data={}, tenant_id="t-1")
    assert result == {"name": "Priya"}
    assert "favorite_color" not in result


@pytest.mark.asyncio
async def test_extract_fields_returns_unchanged_on_llm_error():
    with patch.object(eh, "gemini_chat_completion_json", new=AsyncMock(side_effect=RuntimeError("timeout"))):
        result = await eh.extract_fields("random unrelated text", fields=_FIELDS, collected_data={"name": "Priya"}, tenant_id="t-1")
    assert result == {"name": "Priya"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -k "extract_fields or missing_field_labels" -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write minimal implementation**

Add below `detect_expert_handoff_intent`:

```python
def missing_field_labels(fields: list[dict], collected_data: dict) -> list[str]:
    return [f["label"] for f in fields if not collected_data.get(f["key"])]


_EXTRACTION_SYSTEM_PROMPT = """You extract structured field values from one customer chat
message. You are given a list of fields the business needs and the values already
collected from earlier turns. Read the new message and return ONLY the fields you can
confidently find IN THIS MESSAGE, as flat JSON: {"field_key": "value", ...}.

Rules:
- Only include a key if this message actually contains that value.
- Never guess or invent a value that isn't stated.
- Do not repeat values that weren't in this message, even if already collected.
- If this message contains none of the requested fields, return {}.
- JSON only, no other text."""


async def extract_fields(message: str, fields: list[dict], collected_data: dict, tenant_id: str) -> dict:
    """Never drops already-collected data: the LLM only ever contributes additions
    for THIS message, which are merged on top of (never replacing) collected_data."""
    field_list = "\n".join(f"- {f['key']}: {f['label']} ({f['type']})" for f in fields)
    already = ", ".join(f"{k}={v}" for k, v in collected_data.items()) or "(none yet)"
    user_prompt = (
        f"Fields needed:\n{field_list}\n\n"
        f"Already collected: {already}\n\n"
        f"New message: {message}"
    )
    try:
        data = await gemini_chat_completion_json(
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=300,
            tenant_id=tenant_id,
            purpose="expert_handoff_extraction",
        )
    except Exception as e:
        logger.warning(f"Expert handoff extraction failed, keeping existing collected_data: {e}")
        return dict(collected_data)

    valid_keys = {f["key"] for f in fields}
    new_values = {k: v for k, v in data.items() if k in valid_keys and v}
    return {**collected_data, **new_values}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -k "extract_fields or missing_field_labels" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/expert_handoff.py backend/tests/test_expert_handoff.py
git commit -m "feat: expert handoff LLM slot-filling extraction"
```

---

## Task 6: Session state machine + payment link

**Files:**
- Modify: `backend/app/services/expert_handoff.py`
- Test: `backend/tests/test_expert_handoff.py` (append)

**Interfaces:**
- Consumes: `detect_expert_handoff_intent`, `extract_fields`, `missing_field_labels`, `get_expert_handoff_config` (Tasks 3-5); `payment_razorpay.create_payment_link` (Task 2).
- Produces: `async def route_expert_handoff(lead_id: str, tenant_id: str, phone: str, body: str, db=None) -> bool` — the single webhook entry point, `True` means "message consumed, caller must skip `generate_reply` for this turn."
- Produces (internal, used by Task 7's webhook route too): `def confirm_expert_handoff_payment(session_id: str, razorpay_payment_id: str, db=None) -> tuple[str, str, str, str] | None` returning `(phone, tenant_id, lead_id, session_name)` on success, `None` if not found or already paid (idempotent).

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_expert_handoff.py
def _session_db(existing_session=None, lead=None):
    """Builds a MagicMock db where .table('expert_handoff_sessions') and
    .table('leads') and .table('app_settings') and .table('messages') all
    behave plausibly for route_expert_handoff's queries."""
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            active_row = MagicMock()
            active_row.data = [existing_session] if existing_session else []
            t.select.return_value.eq.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = active_row

            insert_result = MagicMock()
            created = {**(existing_session or {}), "id": "sess-1", "status": "offer_pending", "collected_data": {}}
            insert_result.data = [created]
            t.insert.return_value.execute.return_value = insert_result

            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "app_settings":
            row = MagicMock()
            row.data = {"value": '{"enabled": true, "trigger_description": "personal question", "offer_message": "Talk to our expert?", "fields": [{"key": "name", "label": "Full name", "type": "text"}], "amount_paise": 2900}'}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
        elif name == "leads":
            row = MagicMock()
            row.data = lead or {"id": "lead-1", "ai_enabled": True}
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "messages":
            t.insert.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector
    return db


@pytest.mark.asyncio
async def test_route_expert_handoff_sends_offer_on_new_matching_intent():
    db = _session_db()
    with patch.object(eh, "detect_expert_handoff_intent", new=AsyncMock(return_value=True)), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is True
    send.assert_awaited_once()
    assert "Talk to our expert" in send.call_args[0][1]


@pytest.mark.asyncio
async def test_route_expert_handoff_ignores_when_feature_disabled():
    db = MagicMock()
    row = MagicMock()
    row.data = {"value": '{"enabled": false}'}
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
    active_row = MagicMock()
    active_row.data = []
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = active_row

    consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "Will I get married?", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_expert_handoff_starts_collecting_on_affirmative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "yes, I'm Priya", db=db)
    assert consumed is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_expert_handoff_cancels_on_negative_reply():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "offer_pending", "collected_data": {}}
    db = _session_db(existing_session=session)
    consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "no thanks", db=db)
    assert consumed is False


@pytest.mark.asyncio
async def test_route_expert_handoff_moves_to_confirmation_when_all_fields_filled():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "collecting", "collected_data": {}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "extract_fields", new=AsyncMock(return_value={"name": "Priya"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "I'm Priya", db=db)
    assert consumed is True
    assert "Priya" in send.call_args[0][1]  # summary shown


@pytest.mark.asyncio
async def test_route_expert_handoff_sends_payment_link_on_confirmation_yes():
    session = {"id": "sess-1", "tenant_id": "t-1", "lead_id": "lead-1", "status": "awaiting_confirmation", "collected_data": {"name": "Priya"}}
    db = _session_db(existing_session=session)
    with patch.object(eh, "create_payment_link", new=AsyncMock(return_value={"payment_link_url": "https://rzp.io/x", "razorpay_payment_link_id": "plink_1"})), \
         patch.object(eh, "_send_and_log", new=AsyncMock()) as send:
        consumed = await eh.route_expert_handoff("lead-1", "t-1", "+91999", "yes correct", db=db)
    assert consumed is True
    assert "https://rzp.io/x" in send.call_args[0][1]


def test_confirm_expert_handoff_payment_mutes_ai_and_marks_paid():
    session_row = {"id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {"name": "Priya"}}
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "leads":
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector

    result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)
    assert result == ("+91999" if False else result[0], "t-1", "lead-1", "Priya")  # phone asserted loosely below
    db.table("leads").update.assert_any_call({"ai_enabled": False})


def test_confirm_expert_handoff_payment_idempotent_when_already_paid():
    db = MagicMock()
    fetch = MagicMock()
    fetch.data = {"id": "sess-1", "status": "paid", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {}}
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
    assert eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db) is None
```

The `test_confirm_expert_handoff_payment_mutes_ai_and_marks_paid` assertion on `phone` is loose because phone isn't stored on the session row in this mock — fix it in Step 3 by deciding (and testing precisely) how phone is sourced. Rewrite that one assertion once the implementation is written:

```python
def test_confirm_expert_handoff_payment_mutes_ai_and_marks_paid():
    session_row = {"id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {"name": "Priya"}}
    lead_row = {"id": "lead-1", "phone": "+919876543210", "name": "Priya"}
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "leads":
            fetch = MagicMock()
            fetch.data = lead_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector

    result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)
    assert result == ("+919876543210", "t-1", "lead-1", "Priya")
    db.table("leads").update.assert_any_call({"ai_enabled": False})
```

(Replace the earlier loose version of this test with this one before running.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -k "route_expert_handoff or confirm_expert_handoff_payment" -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write minimal implementation**

Add imports at the top of `expert_handoff.py`:

```python
import uuid
from app.services.payment_razorpay import create_payment_link
```

Add below `extract_fields`:

```python
_ACTIVE_STATUSES = ("offer_pending", "collecting", "awaiting_confirmation", "awaiting_payment")


def _get_active_session(lead_id: str, tenant_id: str, db) -> dict | None:
    result = (
        db.table("expert_handoff_sessions")
        .select("*")
        .eq("lead_id", lead_id)
        .eq("tenant_id", tenant_id)
        .neq("status", "resolved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    active = [r for r in rows if r["status"] in _ACTIVE_STATUSES]
    return active[0] if active else None


def _create_session(lead_id: str, tenant_id: str, db) -> dict:
    result = (
        db.table("expert_handoff_sessions")
        .insert({"lead_id": lead_id, "tenant_id": tenant_id, "status": "offer_pending", "collected_data": {}})
        .execute()
    )
    return result.data[0]


def _update_session(session_id: str, patch: dict, db) -> None:
    db.table("expert_handoff_sessions").update(patch).eq("id", session_id).execute()


async def _send_and_log(phone: str, text: str, tenant_id: str, lead_id: str, db) -> None:
    from app.services.ai_reply import send_whatsapp
    mid = await send_whatsapp(phone, text, tenant_id=tenant_id)
    db.table("messages").insert({
        "lead_id": lead_id,
        "tenant_id": tenant_id,
        "direction": "outbound",
        "channel": "whatsapp",
        "content": text,
        "is_ai_generated": True,
        "meta_message_id": mid,
        "reply_source": "expert_handoff",
    }).execute()


_AFFIRMATIVE_RE_WORDS = frozenset({
    "yes", "yeah", "yep", "sure", "ok", "okay", "correct", "right",
    "ஆம்", "சரி",  # Tamil yes/okay
    "हाँ", "ठीक",   # Hindi yes/okay
})


def _is_affirmative(message: str) -> bool:
    import re
    tokens = set(re.findall(r"[\w஀-௿ऀ-ॿ]+", message.strip().lower()))
    return bool(tokens & _AFFIRMATIVE_RE_WORDS)


def _summary_text(fields: list[dict], collected_data: dict) -> str:
    lines = [f"{f['label']}: {collected_data.get(f['key'], '—')}" for f in fields]
    return "Here's what I've got:\n\n" + "\n".join(lines) + "\n\nIs that correct?"


async def route_expert_handoff(lead_id: str, tenant_id: str, phone: str, body: str, db=None) -> bool:
    """Webhook-level routing for the expert handoff session. Returns True if the
    inbound message was consumed (caller must skip generate_reply for this turn)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    if not body:
        return False

    try:
        config = get_expert_handoff_config(tenant_id, db=db)
        if not config.get("enabled"):
            return False

        session = _get_active_session(lead_id, tenant_id, db)

        if session is None:
            matched = await detect_expert_handoff_intent(body, config["trigger_description"], tenant_id)
            if not matched:
                return False
            new_session = _create_session(lead_id, tenant_id, db)
            await _send_and_log(phone, config["offer_message"], tenant_id, lead_id, db)
            _update_session(new_session["id"], {"trigger_reason": body[:500]}, db)
            return True

        status = session["status"]

        if status == "offer_pending":
            if not _is_affirmative(body):
                _update_session(session["id"], {"status": "cancelled"}, db)
                return False
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            if missing:
                _update_session(session["id"], {"status": "collecting", "collected_data": collected}, db)
                await _send_and_log(phone, f"Great! Could you share your {missing[0].lower()}?", tenant_id, lead_id, db)
            else:
                _update_session(session["id"], {"status": "awaiting_confirmation", "collected_data": collected}, db)
                await _send_and_log(phone, _summary_text(config["fields"], collected), tenant_id, lead_id, db)
            return True

        if status == "collecting":
            collected = await extract_fields(body, config["fields"], session.get("collected_data") or {}, tenant_id)
            missing = missing_field_labels(config["fields"], collected)
            if missing:
                _update_session(session["id"], {"collected_data": collected}, db)
                await _send_and_log(phone, f"Thanks! And your {missing[0].lower()}?", tenant_id, lead_id, db)
            else:
                _update_session(session["id"], {"status": "awaiting_confirmation", "collected_data": collected}, db)
                await _send_and_log(phone, _summary_text(config["fields"], collected), tenant_id, lead_id, db)
            return True

        if status == "awaiting_confirmation":
            if not _is_affirmative(body):
                # Let the AI/human sort out a correction request; stay put.
                return False
            ref = f"EH-{uuid.uuid4().hex[:8].upper()}"
            collected = session.get("collected_data") or {}
            customer_name = collected.get("name", "Customer")
            try:
                link = await create_payment_link(
                    booking_id=session["id"],
                    booking_ref=ref,
                    amount_paise=config["amount_paise"],
                    customer_name=customer_name,
                    customer_phone=phone,
                    description=f"Consultation — {customer_name} ({ref})",
                    tenant_id=tenant_id,
                )
                _update_session(session["id"], {
                    "status": "awaiting_payment",
                    "amount_paise": config["amount_paise"],
                    "payment_link": link["payment_link_url"],
                }, db)
                await _send_and_log(
                    phone,
                    f"Great, here's your payment link:\n{link['payment_link_url']}",
                    tenant_id, lead_id, db,
                )
            except Exception as e:
                logger.error(f"Expert handoff payment link creation failed for session {session['id']}: {e}")
                await _send_and_log(
                    phone,
                    "We've received your details — our team will send the payment link shortly.",
                    tenant_id, lead_id, db,
                )
            return True

        # awaiting_payment: nothing to do here, wait for the Razorpay webhook.
        return False
    except Exception as e:
        logger.error(f"route_expert_handoff failed for lead {lead_id}: {e}")
        return False


def confirm_expert_handoff_payment(session_id: str, razorpay_payment_id: str, db=None) -> tuple[str, str, str, str] | None:
    """Mark a session paid and mute the AI for its lead. Returns
    (phone, tenant_id, lead_id, customer_name) on success, None if the session
    doesn't exist or was already paid (idempotent — Razorpay may retry webhooks)."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()

    from datetime import datetime, timezone

    existing = (
        db.table("expert_handoff_sessions")
        .select("id,status,lead_id,tenant_id,collected_data")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not existing or not existing.data or existing.data.get("status") == "paid":
        return None

    session = existing.data
    now_iso = datetime.now(timezone.utc).isoformat()
    db.table("expert_handoff_sessions").update({
        "status": "paid",
        "razorpay_payment_id": razorpay_payment_id,
        "paid_at": now_iso,
    }).eq("id", session_id).execute()

    lead_id = session["lead_id"]
    tenant_id = session["tenant_id"]
    db.table("leads").update({"ai_enabled": False}).eq("id", lead_id).execute()

    lead_row = (
        db.table("leads")
        .select("phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"
    return (phone, tenant_id, lead_id, customer_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_expert_handoff.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/expert_handoff.py backend/tests/test_expert_handoff.py
git commit -m "feat: expert handoff session state machine and payment confirmation"
```

---

## Task 7: Razorpay webhook route + main.py registration

**Files:**
- Create: `backend/app/routes/expert_handoff.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_expert_handoff_webhook.py`

**Interfaces:**
- Consumes: `payment_razorpay.verify_webhook_signature` (Task 2), `expert_handoff.confirm_expert_handoff_payment` (Task 6), `ai_reply.send_whatsapp`.
- Produces: `public_router: APIRouter` with `POST /razorpay-webhook`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_expert_handoff_webhook.py
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.expert_handoff import public_router

app = FastAPI()
app.include_router(public_router, prefix="/api/v1/expert-handoff")
client = TestClient(app)


def _payload(session_id="sess-1", event="payment_link.paid"):
    return {
        "event": event,
        "payload": {
            "payment_link": {"entity": {"notes": {"booking_id": session_id, "booking_ref": "EH-ABC123"}}},
            "payment": {"entity": {"id": "pay_abc123"}},
        },
    }


def test_webhook_rejects_invalid_signature():
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=False):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "bad"})
    assert res.status_code == 400


def test_webhook_ignores_non_paid_events():
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(event="payment_link.cancelled"), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"


def test_webhook_confirms_payment_and_sends_receipt():
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True), \
         patch("app.routes.expert_handoff.confirm_expert_handoff_payment", return_value=("+919876543210", "t-1", "lead-1", "Priya")), \
         patch("app.routes.expert_handoff.send_whatsapp", new=AsyncMock(return_value="wamid.123")) as send:
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=_payload(), headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    send.assert_awaited_once()
    assert "Priya" in send.call_args[0][1]


def test_webhook_missing_session_id_returns_error_status():
    payload = _payload()
    payload["payload"]["payment_link"]["entity"]["notes"] = {}
    with patch("app.routes.expert_handoff.verify_webhook_signature", return_value=True):
        res = client.post("/api/v1/expert-handoff/razorpay-webhook", json=payload, headers={"x-razorpay-signature": "ok"})
    assert res.status_code == 200
    assert res.json()["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_expert_handoff_webhook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routes.expert_handoff'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/routes/expert_handoff.py
import logging

from fastapi import APIRouter, HTTPException, Request

from app.services.ai_reply import send_whatsapp
from app.services.expert_handoff import confirm_expert_handoff_payment
from app.services.payment_razorpay import verify_webhook_signature

logger = logging.getLogger(__name__)
public_router = APIRouter()


@public_router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    if not verify_webhook_signature(raw_body, signature):
        logger.warning("Expert handoff Razorpay webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = payload.get("event", "")
    if event != "payment_link.paid":
        return {"status": "ignored", "event": event}

    entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = entity.get("notes", {})
    session_id = notes.get("booking_id")  # payment_razorpay.py's notes key is literally "booking_id"
    razorpay_payment_id = (
        payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
    )

    if not session_id:
        logger.error("Expert handoff webhook: no session id in notes")
        return {"status": "error", "detail": "no session id"}

    result = confirm_expert_handoff_payment(session_id, razorpay_payment_id)
    if result:
        phone, tenant_id, lead_id, customer_name = result
        receipt = (
            f"Payment received, thank you {customer_name}! 🎉\n\n"
            f"Your consultation is confirmed — our expert will be in touch here on WhatsApp shortly."
        )
        try:
            await send_whatsapp(phone, receipt, tenant_id=tenant_id)
        except Exception as e:
            logger.error(f"Expert handoff receipt send failed for {phone}: {e}")

    return {"status": "ok"}
```

Register in `backend/app/main.py` — add the import near the other route imports and the include near `calls_public_router` (`main.py:547` area):

```python
from app.routes.expert_handoff import public_router as expert_handoff_public_router
```

```python
app.include_router(expert_handoff_public_router, prefix="/api/v1/expert-handoff", tags=["expert-handoff-webhook"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_expert_handoff_webhook.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Sanity-check `main.py` still boots**

Run: `cd backend && python -c "from app.main import app"`
Expected: no import errors

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/expert_handoff.py backend/app/main.py backend/tests/test_expert_handoff_webhook.py
git commit -m "feat: expert handoff Razorpay webhook route"
```

---

## Task 8: Wire into the WhatsApp inbound webhook

**Files:**
- Modify: `backend/app/routes/webhook.py`
- Test: `backend/tests/test_webhook_expert_handoff_routing.py`

**Interfaces:**
- Consumes: `expert_handoff.route_expert_handoff` (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_webhook_expert_handoff_routing.py
import inspect

from app.routes import webhook


def test_process_inbound_message_calls_route_expert_handoff_before_generate_reply():
    """Static check: route_expert_handoff must run, and generate_reply must be
    skipped when it returns True. Mirrors the style of
    test_ai_reply_lang_detection.py's inspect.getsource checks — this is a wiring
    concern, better verified statically than via a heavy background-task mock."""
    source = inspect.getsource(webhook._process_inbound_message_background)
    assert "route_expert_handoff" in source
    idx_route = source.index("route_expert_handoff")
    idx_generate = source.index("generate_reply(")
    assert idx_route < idx_generate, "route_expert_handoff must be checked before generate_reply is called"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_webhook_expert_handoff_routing.py -v`
Expected: FAIL — `route_expert_handoff` not found in source

- [ ] **Step 3: Modify `_process_inbound_message_background`**

In `backend/app/routes/webhook.py`, replace the block at the section starting `# Route text-like inbound content...` (around line 309-324):

```python
        # Route text-like inbound content, including transcribed audio, into the reply engine.
        if msg_type in ("text", "button", "interactive", "audio") and body:
            try:
                from app.services.expert_handoff import route_expert_handoff
                consumed = await route_expert_handoff(lead_id=lead_id, tenant_id=tenant_id, phone=phone, body=body, db=db)
                if consumed:
                    return
            except Exception as e:
                logger.error(f"Expert handoff routing failed for lead {lead_id}: {e}")
            try:
                from app.services.context_builder import build_scorer_context
                context_block = build_scorer_context(lead_id, db)
                from app.services.ai_reply import generate_reply
                await generate_reply(
                    lead_id=lead_id,
                    message=body,
                    phone=phone,
                    context_block=context_block,
                    phone_number_id=meta_phone_number_id or None,
                    inbound_media_type=msg_type,
                )
            except Exception as e:
                logger.error(f"Reply routing failed for lead {lead_id}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_webhook_expert_handoff_routing.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite to check for regressions**

Run: `cd backend && python -m pytest -v`
Expected: all tests pass, including the pre-existing `webhook.py`/`ai_reply.py` tests

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/webhook.py backend/tests/test_webhook_expert_handoff_routing.py
git commit -m "feat: route inbound WhatsApp messages through expert handoff before AI reply"
```

---

## Task 9: Frontend config panel

**Files:**
- Create: `frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx`
- Modify: `frontend/app/dashboard/settings/page.tsx`

**Interfaces:**
- Consumes: `GET/PATCH /api/v1/settings/expert-handoff-config` (Task 3); `API_URL`, `getAuthHeaders` from `@/lib/api`; `useAuthRole` from `../contexts/AuthRoleContext`.
- Produces: `export function ExpertHandoffConfigPanel({ canManage }: { canManage?: boolean }): JSX.Element`

- [ ] **Step 1: Write the component**

```tsx
// frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx
"use client";
import { useEffect, useState, useCallback } from "react";
import { UserCheck, ChevronDown, Save, Loader2, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type FieldType = "text" | "date" | "choice";

interface HandoffField {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
}

interface ExpertHandoffConfig {
  enabled: boolean;
  trigger_description: string;
  offer_message: string;
  fields: HandoffField[];
  amount_paise: number;
}

const DEFAULT: ExpertHandoffConfig = {
  enabled: false,
  trigger_description: "",
  offer_message: "",
  fields: [],
  amount_paise: 0,
};

function slugify(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "field";
}

export function ExpertHandoffConfigPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<ExpertHandoffConfig>(DEFAULT);
  const [draft, setDraft] = useState<ExpertHandoffConfig>(DEFAULT);
  const [collapsed, setCollapsed] = useState(true);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/expert-handoff-config`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setDraft(data);
      }
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(config);

  async function handleSave() {
    if (!canManage) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/expert-handoff-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify(draft),
      });
      if (!res.ok) throw new Error("Save failed");
      const saved = await res.json();
      setConfig(saved);
      setDraft(saved);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("idle");
    }
  }

  function addField() {
    setDraft({
      ...draft,
      fields: [...draft.fields, { key: `field_${draft.fields.length + 1}`, label: "", type: "text" }],
    });
  }

  function updateField(index: number, patch: Partial<HandoffField>) {
    const fields = draft.fields.map((f, i) => (i === index ? { ...f, ...patch } : f));
    setDraft({ ...draft, fields });
  }

  function removeField(index: number) {
    setDraft({ ...draft, fields: draft.fields.filter((_, i) => i !== index) });
  }

  return (
    <div className="card rounded-3xl">
      <button type="button" onClick={() => setCollapsed((c) => !c)} className="w-full flex items-center gap-3 text-left">
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 bg-violet-100">
          <UserCheck size={18} className="text-violet-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
              Paid Expert Handoff
            </h2>
            {draft.enabled ? (
              <span className="badge badge-green inline-flex items-center gap-1">
                <CheckCircle2 size={10} /> Enabled
              </span>
            ) : (
              <span className="badge badge-gray">Disabled</span>
            )}
          </div>
          <p className="font-body text-sm text-ink-muted mt-0.5">
            Offer a paid consultation in WhatsApp when a lead's message needs a real human expert.
          </p>
        </div>
        <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${collapsed ? "" : "rotate-180"}`} />
      </button>

      {!collapsed && (
        <div className="mt-6 space-y-6">
          <label className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              className="mt-0.5 accent-violet-600"
            />
            <div>
              <div className="font-label text-sm font-semibold text-ink">Enable Paid Expert Handoff</div>
              <div className="font-body text-xs text-ink-muted mt-0.5">
                Off by default. Turn on once trigger, fields, and fee below are configured.
              </div>
            </div>
          </label>

          <div>
            <div className="font-label text-sm font-semibold text-ink mb-1">When should this trigger?</div>
            <div className="font-body text-xs text-ink-muted mb-2">
              Describe the kind of message that should offer a paid consultation, e.g. &quot;Lead asks a personal astrology question about marriage, career, health, or timing.&quot;
            </div>
            <textarea
              value={draft.trigger_description}
              onChange={(e) => setDraft({ ...draft, trigger_description: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink bg-white"
            />
          </div>

          <div>
            <div className="font-label text-sm font-semibold text-ink mb-1">Offer message</div>
            <div className="font-body text-xs text-ink-muted mb-2">Sent to the lead when the trigger matches.</div>
            <textarea
              value={draft.offer_message}
              onChange={(e) => setDraft({ ...draft, offer_message: e.target.value })}
              rows={2}
              className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink bg-white"
            />
          </div>

          <div>
            <div className="font-label text-sm font-semibold text-ink mb-1">Consultation fee (₹)</div>
            <input
              type="number"
              min={0}
              value={draft.amount_paise / 100}
              onChange={(e) => setDraft({ ...draft, amount_paise: Math.round(Number(e.target.value) * 100) })}
              className="w-32 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="font-label text-sm font-semibold text-ink">Fields to collect</div>
              <button
                type="button"
                onClick={addField}
                className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
              >
                <Plus size={14} /> Add field
              </button>
            </div>
            <div className="font-body text-xs text-ink-muted mb-3">
              Collected in free-flowing conversation, in any order — no fixed script.
            </div>
            <div className="space-y-2">
              {draft.fields.map((field, index) => (
                <div key={index} className="flex items-center gap-2 p-3 rounded-xl border border-border bg-surface-subtle">
                  <input
                    type="text"
                    placeholder="Label (e.g. Date of birth)"
                    value={field.label}
                    onChange={(e) => updateField(index, { label: e.target.value, key: slugify(e.target.value) })}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  />
                  <select
                    value={field.type}
                    onChange={(e) => updateField(index, { type: e.target.value as FieldType })}
                    className="px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  >
                    <option value="text">Text</option>
                    <option value="date">Date</option>
                    <option value="choice">Choice</option>
                  </select>
                  <button type="button" onClick={() => removeField(index)} className="text-ink-muted hover:text-red-600">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              {draft.fields.length === 0 && (
                <p className="font-body text-xs text-ink-muted italic">No fields yet — add at least one before enabling.</p>
              )}
            </div>
          </div>

          <div className="flex justify-end pt-2 border-t border-border">
            <button
              onClick={handleSave}
              disabled={!canManage || saveState === "saving" || saveState === "saved" || !isDirty}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                saveState === "saved"
                  ? "bg-emerald-100 text-emerald-700 cursor-default"
                  : canManage && isDirty
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-surface-subtle text-ink-muted cursor-default"
              }`}
            >
              {saveState === "saving" ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Saving…
                </>
              ) : saveState === "saved" ? (
                <>
                  <CheckCircle2 size={14} />
                  Saved
                </>
              ) : (
                <>
                  <Save size={14} />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Mount it in `settings/page.tsx`**

Add the import near the other panel imports (`page.tsx:14` area):

```tsx
import { ExpertHandoffConfigPanel } from "./ExpertHandoffConfigPanel";
```

Add the render call next to `<TelecallingConfigPanel canManage={canManageSettings} />` (`page.tsx:743` area):

```tsx
<ExpertHandoffConfigPanel canManage={canManageSettings} />
```

- [ ] **Step 3: Typecheck and lint**

Run: `cd frontend && npm run typecheck`
Expected: no errors

Run: `cd frontend && npm run lint`
Expected: no errors (no unused imports/vars — this repo's `npm run lint` fails the build on unused-var warnings)

- [ ] **Step 4: Manual verification in the browser**

Run: `cd frontend && npm run dev`, navigate to the Settings tab that renders `InboxConfigPanel`/`TelecallingConfigPanel`, confirm the new "Paid Expert Handoff" card appears, expands/collapses, add/remove a field, toggle enabled, Save button enables only when dirty and saves successfully (check Network tab for a 200 on PATCH).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/ExpertHandoffConfigPanel.tsx frontend/app/dashboard/settings/page.tsx
git commit -m "feat: expert handoff config panel in settings dashboard"
```

---

## Task 10: Live LLM verification (Astrotamil config)

This is not optional per this repo's rule: LLM-dependent behavior (detection, extraction) needs a real live test against the actual Gemini API, not just mocked unit tests, before it's trusted with real leads.

**Files:** none (manual verification task, no code changes)

- [ ] **Step 1: Configure a real test tenant**

Via the Settings panel built in Task 9 (or directly through `PATCH /api/v1/settings/expert-handoff-config`), set on a test/staging tenant:
```json
{
  "enabled": true,
  "trigger_description": "Lead asks a personal astrology question (marriage, career, health, timing) that needs a real astrologer's reading, not a generic answer.",
  "offer_message": "That's something our astrologer can help with directly — ₹29 for a consultation, right here on WhatsApp. Want to go ahead?",
  "fields": [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "date_of_birth", "label": "Date of birth", "type": "date"},
    {"key": "birthplace", "label": "Birthplace", "type": "text"}
  ],
  "amount_paise": 2900
}
```

- [ ] **Step 2: Send real WhatsApp messages to a test lead and observe**

Test cases to run live and record actual results:
1. A clearly personal astrology question → offer should fire.
2. A neutral/unrelated message ("what are your hours?") → offer should NOT fire.
3. Reply "yes" to the offer → collection should start.
4. Send name + DOB in one message ("I'm Priya, born 5 March 1995") → both should be extracted in one turn.
5. Send an off-topic aside mid-collection ("also is Friday good for a haircut?") with no field data in it → session should stay at the same missing field, not lose progress.
6. Complete all fields → summary should list all three correctly, then confirm → payment link should arrive.
7. Pay via the real Razorpay test-mode link → receipt should arrive, and a subsequent message from that lead should get **zero** AI auto-reply (verify `leads.ai_enabled` flipped to `false` in the DB).

- [ ] **Step 3: Record results**

Add a dated entry to `.agents/decisions/log.md` summarizing what was live-tested, what passed, and any prompt-tuning needed for `_DETECTION_SYSTEM_PROMPT` / `_EXTRACTION_SYSTEM_PROMPT` in `expert_handoff.py` based on real Tamil/Tanglish/English message behavior — same category of follow-up this repo already tracks for other LLM-dependent features (see the 2026-07-05 Sarvam migration entry for the expected format).

- [ ] **Step 4: Commit any prompt fixes found necessary**

```bash
git add backend/app/services/expert_handoff.py .agents/decisions/log.md
git commit -m "fix: tune expert handoff detection/extraction prompts based on live test"
```

(Skip this commit if no fixes were needed.)
