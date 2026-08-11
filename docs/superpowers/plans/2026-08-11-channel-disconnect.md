# Channel Disconnect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give tenants a self-service way to disconnect any channel — with webhook unsubscribe, credential deletion, and an opt-in asset-claim release — plus three small polish fixes on the Channels page.

**Architecture:** A new `release_meta_assets` RPC mirrors `claim_meta_assets` with a `tenant_id` guard. A single `POST /api/v1/settings/disconnect` route dispatches per-channel teardown through a table-driven map. The frontend adds a confirm dialog reachable from the embedded header and from per-channel overflow menus.

**Tech Stack:** FastAPI + Supabase, Next.js 14 App Router + Tailwind, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-08-11-channel-disconnect-design.md`

## Global Constraints

- Migration `172_release_meta_assets.sql` is written and committed but **NOT applied to the live Supabase project** during implementation. Applying it is a separate, explicitly authorised step.
- `release_meta_assets` must include `AND tenant_id = p_tenant_id` in its DELETE. Without it, any workspace can free another workspace's Meta assets. This is the security property of the whole feature.
- `meta_app_secret` and `meta_webhook_verify_token` are shared by WhatsApp, Instagram and Messenger. Delete them only when no Meta channel has credentials left.
- Instagram disconnect makes **no** Meta API call — Instagram rides the Facebook Page subscription, so unsubscribing would kill Messenger.
- A failed remote unsubscribe must not abort the local teardown.
- Backend tests use mocked Supabase (`MagicMock`) exactly as `backend/tests/test_facebook_embedded_signup.py` does. Never call a live Meta endpoint.
- Run the backend venv as `backend/venv/bin/python -m pytest` — bare `python`/`pytest` are not on PATH.
- The dev server serves under basePath `/aira` (`next.config.js`), so preview URLs are `http://localhost:3000/aira/...`.

---

### Task 1: Polish — zephyr sizing, mirrored gradients, tab rename

**Files:**
- Modify: `frontend/app/dashboard/settings/connect-channels/ui.tsx` (drop `compact`)
- Modify: `frontend/app/dashboard/settings/connect-channels/ManualSection.tsx`
- Modify: `frontend/app/dashboard/settings/connect-channels/EmbeddedSection.tsx`
- Modify: `frontend/app/dashboard/settings/page.tsx:425`

**Interfaces:**
- Consumes: nothing.
- Produces: `ZephyrCourier({ variant }: { variant: "embedded" | "manual" })` — the `compact` prop is removed again, so every caller passes only `variant`.

- [ ] **Step 1: Remove the compact size from `ZephyrCourier`**

```tsx
export function ZephyrCourier({ variant }: { variant: "embedded" | "manual" }) {
  const isEmbedded = variant === "embedded";

  return (
    <div className="relative h-36 w-full sm:h-48">
```

Everything below that line stays as it is.

- [ ] **Step 2: Let the Manual zephyr overhang its header band**

In `ManualSection.tsx`, add `relative` to the header band's className and replace the zephyr wrapper:

```tsx
<div className="pointer-events-none absolute bottom-0 right-5 hidden w-[190px] sm:block">
  <ZephyrCourier variant="manual" />
</div>
```

Move it out of the flex row so it no longer contributes to the band's height, and give the copy column `sm:pr-[210px]` so text never runs under the art.

- [ ] **Step 3: Mirror the gradients**

`EmbeddedSection.tsx` header band:

```tsx
className="... bg-gradient-to-r from-emerald-50 via-white to-emerald-50/40 ..."
```

`ManualSection.tsx` header band:

```tsx
className="... bg-gradient-to-r from-violet-50 via-white to-violet-50/40 ..."
```

- [ ] **Step 4: Rename the tab**

In `frontend/app/dashboard/settings/page.tsx:425`, change the button text `Messaging Channels` to `Channels`. Do not touch the `?tab=channels` query value or the `activeTab === "channels"` comparison — both are already correct.

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: clean. Then render both sections and confirm by looking at the screenshot that the Manual band no longer has an empty strip and both gradients read as a matched pair.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/settings/
git commit -m "fix: match channel section gradients and restore full-size illustration"
```

---

### Task 2: Migration — `release_meta_assets`

**Files:**
- Create: `backend/supabase/migrations/172_release_meta_assets.sql`

**Interfaces:**
- Consumes: the `meta_asset_claims` table from migration 162 / 171.
- Produces: `public.release_meta_assets(p_tenant_id uuid, p_assets jsonb) RETURNS void`, callable by `service_role` only. Task 3 calls it through `db.rpc("release_meta_assets", {...})`.

- [ ] **Step 1: Write the migration**

```sql
-- 172: Claims made by claim_meta_assets had no release path, so a tenant could
-- never move a WhatsApp number or Page to another Aira workspace. Disconnect
-- calls this to free the assets it owns — and only the ones it owns.
CREATE OR REPLACE FUNCTION public.release_meta_assets(
  p_tenant_id uuid,
  p_assets jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  IF jsonb_typeof(p_assets) <> 'array' THEN
    RAISE EXCEPTION 'assets must be an array' USING ERRCODE = '22023';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
    WHERE asset.asset_type IS NULL
       OR asset.asset_type NOT IN (
         'facebook_page', 'instagram_account', 'ad_account', 'catalog',
         'whatsapp_business_account', 'whatsapp_phone_number'
       )
       OR asset.asset_id IS NULL
       OR length(trim(asset.asset_id)) = 0
  ) THEN
    RAISE EXCEPTION 'invalid Meta asset release' USING ERRCODE = '22023';
  END IF;

  -- The tenant_id predicate is the security property: a workspace can only ever
  -- release a claim it holds, even if it guesses another workspace's asset id.
  DELETE FROM public.meta_asset_claims claim
  USING jsonb_to_recordset(p_assets) AS asset(asset_type text, asset_id text)
  WHERE claim.asset_type = asset.asset_type
    AND claim.asset_id = asset.asset_id
    AND claim.tenant_id = p_tenant_id;
END;
$$;

REVOKE ALL ON FUNCTION public.release_meta_assets(uuid, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.release_meta_assets(uuid, jsonb) TO service_role;
```

- [ ] **Step 2: Verify the SQL parses**

Run: `cd backend && venv/bin/python -c "import pathlib; sql = pathlib.Path('supabase/migrations/172_release_meta_assets.sql').read_text(); assert 'claim.tenant_id = p_tenant_id' in sql; assert 'TO service_role' in sql; print('ok')"`
Expected: `ok`. This is a guard against the tenant predicate being dropped, not a substitute for applying the migration.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/172_release_meta_assets.sql
git commit -m "feat: add release_meta_assets RPC so claimed Meta assets can be freed"
```

---

### Task 3: Backend — the disconnect route

**Files:**
- Modify: `backend/app/routes/app_settings.py` — add `DisconnectChannelRequest` near `ActivateChannelRequest` (line 31), add the teardown map and route
- Test: `backend/tests/test_channel_disconnect.py`

**Interfaces:**
- Consumes: `_CHANNEL_CREDENTIAL_KEYS`, `_save_tenant_setting`, `_get_setting_value`, `require_settings_manage`, `record_audit_event`.
- Produces: `POST /api/v1/settings/disconnect` and the module-level `_DISCONNECT_PLAN` map. Task 4's UI calls the route.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_channel_disconnect.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _deleted_keys(db):
    """Setting keys the call deleted, across every .delete().eq().in_() chain."""
    keys = []
    for call in db.table.return_value.delete.return_value.eq.return_value.in_.call_args_list:
        keys.extend(call.args[1])
    return keys


class _StubResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _StubGraphClient:
    """Records the Graph calls disconnect makes so tests can assert on them."""

    calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def delete(self, url, **_):
        type(self).calls.append(url)
        return _StubResponse({"success": True})


@pytest.mark.asyncio
async def test_disconnecting_instagram_never_touches_the_page_subscription():
    """Breaks if dropping Instagram silently kills Messenger — they share the Page webhook."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="instagram", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert _StubGraphClient.calls == []
    assert "instagram_access_token" in _deleted_keys(db)


@pytest.mark.asyncio
async def test_shared_meta_keys_survive_while_another_meta_channel_is_connected():
    """Breaks if disconnecting Ads deletes the app secret that verifies WhatsApp webhooks."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    db = MagicMock()

    # Every lookup returns a value: WhatsApp is still fully configured.
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="meta_ads", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    deleted = _deleted_keys(db)
    assert "meta_ads_access_token" in deleted
    assert "meta_app_secret" not in deleted
    assert "meta_webhook_verify_token" not in deleted


@pytest.mark.asyncio
async def test_shared_meta_keys_go_when_the_last_meta_channel_disconnects():
    """Breaks if a full Meta teardown leaves the app secret behind as orphaned config."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    db = MagicMock()
    _StubGraphClient.calls = []

    # Nothing is configured after the teardown.
    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value=None), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="meta", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    deleted = _deleted_keys(db)
    assert "meta_app_secret" in deleted
    assert "meta_webhook_verify_token" in deleted


@pytest.mark.asyncio
async def test_assets_are_released_only_when_the_caller_opts_in():
    """Breaks if a routine disconnect frees the tenant's number for another workspace."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="asset-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )
    assert db.rpc.call_count == 0

    db2 = MagicMock()
    _StubGraphClient.calls = []
    with patch("app.routes.app_settings.get_supabase", return_value=db2), \
         patch("app.routes.app_settings._get_setting_value", return_value="asset-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=True),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    name, payload = db2.rpc.call_args.args
    assert name == "release_meta_assets"
    assert payload["p_tenant_id"] == "tenant-1"
    assert {a["asset_type"] for a in payload["p_assets"]} == {
        "whatsapp_business_account", "whatsapp_phone_number",
    }


@pytest.mark.asyncio
async def test_a_failed_meta_unsubscribe_still_completes_the_local_teardown():
    """Breaks if an already-revoked token leaves the tenant unable to disconnect at all."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    class _FailingClient(_StubGraphClient):
        async def delete(self, url, **_):
            raise RuntimeError("token revoked")

    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="value"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_FailingClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        result = await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert result["results"][0]["webhook_unsubscribed"] is False
    assert "meta_access_token" in _deleted_keys(db)


@pytest.mark.asyncio
async def test_disconnecting_whatsapp_deactivates_rather_than_deletes_its_phone_number():
    """Breaks if call and message history loses its phone_numbers foreign key."""
    from app.routes.app_settings import DisconnectChannelRequest, disconnect_channel

    _StubGraphClient.calls = []
    db = MagicMock()

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", return_value="phone-1"), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubGraphClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await disconnect_channel(
            DisconnectChannelRequest(channel="whatsapp", release_assets=False),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    update_payloads = [c.args[0] for c in db.table.return_value.update.call_args_list]
    assert {"status": "inactive", "paused_outbound": True} in update_payloads
    assert db.table.return_value.delete.return_value.eq.return_value.eq.call_count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/python -m pytest tests/test_channel_disconnect.py -v`
Expected: FAIL with `ImportError: cannot import name 'DisconnectChannelRequest'`.

- [ ] **Step 3: Add the request model**

In `backend/app/routes/app_settings.py`, after `ActivateChannelRequest` (line 31-33):

```python
class DisconnectChannelRequest(BaseModel):
    channel: str  # meta | whatsapp | instagram | facebook | meta_ads | telegram | razorpay
    release_assets: bool = False
```

- [ ] **Step 4: Add the teardown map**

Next to `_CHANNEL_CREDENTIAL_KEYS`, add the disconnect plan. Keys here are the ones a
disconnect deletes — deliberately narrower than `_CHANNEL_CREDENTIAL_KEYS`, which includes the
shared Meta keys handled separately.

```python
# What tearing down each channel means. Shared Meta keys are NOT listed here —
# they are removed only when the last Meta channel goes (see _disconnect_channel).
_DISCONNECT_PLAN: dict[str, dict] = {
    "whatsapp": {
        "keys": ("meta_access_token", "meta_phone_number_id", "meta_waba_id"),
        "assets": (("whatsapp_business_account", "meta_waba_id"), ("whatsapp_phone_number", "meta_phone_number_id")),
    },
    "instagram": {
        # No Graph call: Instagram messaging rides the Facebook Page subscription,
        # so unsubscribing here would silently kill Messenger.
        "keys": ("instagram_access_token", "instagram_page_id", "instagram_app_secret"),
        "assets": (("instagram_account", "instagram_page_id"),),
    },
    "facebook": {
        "keys": ("facebook_access_token", "facebook_page_id"),
        "assets": (("facebook_page", "facebook_page_id"),),
    },
    "meta_ads": {
        "keys": ("meta_ads_access_token", "meta_ads_account_id", "meta_ads_account_name", "meta_ads_last_sync_at"),
        "assets": (("ad_account", "meta_ads_account_id"),),
    },
    "telegram": {
        "keys": ("telegram_bot_token", "telegram_webhook_secret"),
        "assets": (),
    },
    "razorpay": {
        "keys": ("razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret"),
        "assets": (),
    },
}

_META_CHANNELS = ("whatsapp", "instagram", "facebook", "meta_ads")

# Verify inbound webhook signatures for WhatsApp, Instagram and Messenger alike.
_SHARED_META_KEYS = ("meta_app_secret", "meta_webhook_verify_token")
```

- [ ] **Step 5: Add the route**

Place it after the `activate_channel` route. `_delete_tenant_settings` is a small helper added
beside `_save_tenant_setting`.

```python
def _delete_tenant_settings(db, tenant_id: str, keys) -> None:
    key_list = list(keys)
    if not key_list:
        return
    db.table("app_settings").delete().eq("tenant_id", tenant_id).in_("key", key_list).execute()


async def _unsubscribe_channel_webhook(db, tenant_id: str, channel: str) -> bool:
    """Best-effort remote unsubscribe. Never blocks the local teardown."""
    try:
        if channel == "whatsapp":
            waba_id = _get_setting_value(db, tenant_id, "meta_waba_id")
            token = _get_setting_value(db, tenant_id, "meta_access_token")
            if not waba_id or not token:
                return False
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps",
                    params={"access_token": token},
                    timeout=10.0,
                )
            return True
        if channel == "facebook":
            page_id = _get_setting_value(db, tenant_id, "facebook_page_id")
            token = _get_setting_value(db, tenant_id, "facebook_access_token")
            if not page_id or not token:
                return False
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"https://graph.facebook.com/v25.0/{page_id}/subscribed_apps",
                    params={"access_token": token},
                    timeout=10.0,
                )
            return True
        if channel == "telegram":
            token = _get_setting_value(db, tenant_id, "telegram_bot_token")
            if not token:
                return False
            async with httpx.AsyncClient() as client:
                await client.delete(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=10.0)
            return True
    except Exception as exc:
        logger.warning("Disconnect webhook unsubscribe failed tenant=%s channel=%s: %s", tenant_id, channel, exc)
        return False
    return False


@router.post("/disconnect")
async def disconnect_channel(
    payload: DisconnectChannelRequest,
    ctx: dict = Depends(require_settings_manage),
    user: dict = Depends(get_current_user),
):
    """Tear down a channel: unsubscribe at the provider, delete credentials, optionally
    release the Meta asset claim so it can be connected to a different workspace."""
    tenant_id = ctx["tenant_id"]
    channels = list(_META_CHANNELS) if payload.channel == "meta" else [payload.channel]
    unknown = [c for c in channels if c not in _DISCONNECT_PLAN]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {unknown[0]}")

    db = get_supabase()
    results = []
    released_assets: list[dict[str, str]] = []

    for channel in channels:
        plan = _DISCONNECT_PLAN[channel]
        unsubscribed = await _unsubscribe_channel_webhook(db, tenant_id, channel)

        if payload.release_assets:
            for asset_type, source_key in plan["assets"]:
                asset_id = _get_setting_value(db, tenant_id, source_key)
                if asset_id:
                    released_assets.append({"asset_type": asset_type, "asset_id": asset_id})

        if channel == "whatsapp":
            phone_number_id = _get_setting_value(db, tenant_id, "meta_phone_number_id")
            if phone_number_id:
                # History rows reference this number — deactivate, never delete.
                db.table("phone_numbers").update({"status": "inactive", "paused_outbound": True}) \
                    .eq("tenant_id", tenant_id).eq("meta_phone_number_id", phone_number_id).execute()

        _delete_tenant_settings(
            db, tenant_id,
            list(plan["keys"]) + [f"{channel}_status", f"{channel}_connection_source"],
        )
        results.append({"channel": channel, "webhook_unsubscribed": unsubscribed})

    remaining_meta = [
        c for c in _META_CHANNELS
        if c not in channels and any(_get_setting_value(db, tenant_id, k) for k in _DISCONNECT_PLAN[c]["keys"])
    ]
    if not remaining_meta and any(c in _META_CHANNELS for c in channels):
        _delete_tenant_settings(db, tenant_id, _SHARED_META_KEYS)

    if released_assets:
        try:
            db.rpc("release_meta_assets", {"p_tenant_id": tenant_id, "p_assets": released_assets}).execute()
        except Exception as exc:
            logger.error("Meta asset release failed tenant=%s: %s", tenant_id, exc)
            raise HTTPException(
                status_code=503,
                detail="Channels were disconnected, but the Meta assets could not be released. Please try again.",
            ) from exc

    from app.config_dynamic import invalidate_cache
    invalidate_cache()
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=user.get("user_id"),
        actor_role="tenant_user",
        action="settings.channel_disconnected",
        target_type="channel",
        target_id=payload.channel,
        metadata={"channels": channels, "released_assets": len(released_assets)},
    )
    return {"success": True, "results": results, "released_assets": len(released_assets)}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && venv/bin/python -m pytest tests/test_channel_disconnect.py -v`
Expected: 6 passed.

- [ ] **Step 7: Run the settings suites for regressions**

Run: `cd backend && venv/bin/python -m pytest tests/test_connection_source.py tests/test_facebook_embedded_signup.py tests/test_whatsapp_embedded_signup_coexistence.py tests/test_telegram_settings.py -q`
Expected: 24 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/app_settings.py backend/tests/test_channel_disconnect.py
git commit -m "feat: add channel disconnect with opt-in Meta asset release"
```

---

### Task 4: Frontend — confirm dialog and disconnect entry points

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/DisconnectDialog.tsx`
- Create: `frontend/app/dashboard/settings/connect-channels/disconnect.ts`
- Create: `frontend/app/dashboard/settings/connect-channels/disconnect.test.ts`
- Modify: `EmbeddedSection.tsx`, `ChannelCard.tsx`, `ManualSection.tsx`, `Panel.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/settings/disconnect` from Task 3.
- Produces:
  - `disconnect.ts`: `type DisconnectTarget = { channel: string; label: string; stops: string[]; sharesMetaToken: boolean }`, `buildDisconnectTarget(channelId: string, settings: Setting[]): DisconnectTarget`, `disconnectChannel(channel: string, releaseAssets: boolean): Promise<void>`
  - `DisconnectDialog.tsx`: default export `DisconnectDialog({ target, busy, error, onConfirm, onCancel })` where `onConfirm: (releaseAssets: boolean) => void`

- [ ] **Step 1: Write `disconnect.ts`**

```ts
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CHANNELS, META_CHANNEL_IDS } from "./channels";
import type { Setting } from "./channels";

export type DisconnectTarget = {
  channel: string;
  label: string;
  stops: string[];
  sharesMetaToken: boolean;
};

/** What the confirm dialog must tell the user before this disconnect runs. */
export function buildDisconnectTarget(channelId: string, settings: Setting[]): DisconnectTarget {
  const isConfigured = (id: string) => {
    const channel = CHANNELS.find(c => c.id === id);
    return Boolean(channel?.fields.every(f => settings.find(s => s.key === f.key)?.is_set));
  };

  if (channelId === "meta") {
    return {
      channel: "meta",
      label: "Meta Business",
      stops: META_CHANNEL_IDS.filter(isConfigured).map(id => CHANNELS.find(c => c.id === id)!.name),
      sharesMetaToken: false,
    };
  }

  const channel = CHANNELS.find(c => c.id === channelId);
  return {
    channel: channelId,
    label: channel?.name ?? channelId,
    stops: channel ? [channel.name] : [],
    // WhatsApp's token is the one the embedded flow also used for the Page and Instagram.
    sharesMetaToken: channelId === "whatsapp",
  };
}

export async function disconnectChannel(channel: string, releaseAssets: boolean): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings/disconnect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ channel, release_assets: releaseAssets }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Disconnect failed");
  }
}
```

- [ ] **Step 2: Write the failing test**

Create `disconnect.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { buildDisconnectTarget } from "./disconnect";
import type { Setting } from "./channels";

function setting(key: string): Setting {
  return { key, display_value: "x", is_secret: false, is_set: true, updated_at: "2026-08-11T00:00:00Z" };
}

const whatsappConfigured = [
  "meta_phone_number_id", "meta_waba_id", "meta_access_token",
  "meta_webhook_verify_token", "meta_app_secret",
].map(setting);

describe("buildDisconnectTarget", () => {
  test("a whole-Meta disconnect lists only the channels that are actually connected", () => {
    const target = buildDisconnectTarget("meta", whatsappConfigured);
    expect(target.label).toBe("Meta Business");
    expect(target.stops).toEqual(["WhatsApp Cloud API"]);
  });

  test("WhatsApp warns that other Meta channels share its token", () => {
    expect(buildDisconnectTarget("whatsapp", whatsappConfigured).sharesMetaToken).toBe(true);
  });

  test("Telegram carries no shared-token warning", () => {
    const target = buildDisconnectTarget("telegram", []);
    expect(target.sharesMetaToken).toBe(false);
    expect(target.stops).toEqual(["Telegram Bot"]);
  });
});
```

Run: `cd frontend && npx vitest run app/dashboard/settings/connect-channels/disconnect.test.ts`
Expected: 3 passed once Step 1 is in place.

- [ ] **Step 3: Write `DisconnectDialog.tsx`**

```tsx
"use client";
import { useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { Portal } from "./ui";
import type { DisconnectTarget } from "./disconnect";

export default function DisconnectDialog({
  target, busy, error, onConfirm, onCancel,
}: {
  target: DisconnectTarget;
  busy: boolean;
  error: string | null;
  onConfirm: (releaseAssets: boolean) => void;
  onCancel: () => void;
}) {
  const [releaseAssets, setReleaseAssets] = useState(false);

  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[3px]">
        <div className="w-full max-w-lg overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-[#c4c7c7]/20">
          <div className="flex items-start justify-between border-b border-border-subtle p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-red-100 text-red-600">
                <AlertTriangle size={19} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold text-ink">Disconnect {target.label}?</h2>
                <p className="mt-1 font-body text-xs text-ink-muted">This stops message delivery immediately.</p>
              </div>
            </div>
            <button type="button" onClick={onCancel} aria-label="Cancel disconnect" className="rounded-lg p-1.5 text-on-surface-muted transition-colors hover:bg-surface-low hover:text-on-surface">
              <X size={18} />
            </button>
          </div>

          <div className="space-y-4 p-6">
            {error && <p className="rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{error}</p>}
            <ul className="space-y-1.5 font-body text-sm text-[#57534e]">
              {target.stops.map(name => <li key={name}>· {name} stops receiving and sending messages</li>)}
              <li>· Aira&apos;s webhooks are unsubscribed at the provider</li>
              <li>· Stored tokens are deleted from Aira</li>
            </ul>

            {target.sharesMetaToken && (
              <p className="rounded-xl bg-amber-50 px-3 py-2.5 font-body text-xs text-amber-800">
                Instagram and Messenger share this Meta token. If they were connected through
                Embedded Onboarding, reconnect them afterwards.
              </p>
            )}

            <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-border-subtle p-3">
              <input type="checkbox" checked={releaseAssets} onChange={e => setReleaseAssets(e.target.checked)} className="mt-0.5 h-4 w-4 accent-red-600" />
              <span className="font-body text-xs text-ink-secondary">
                Also release these assets so they can be connected to a different Aira workspace.
                <span className="mt-0.5 block text-ink-muted">Leave this off to keep them reserved for you.</span>
              </span>
            </label>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-low p-5">
            <button type="button" onClick={onCancel} autoFocus className="rounded-xl px-3 py-2 font-label text-sm font-semibold text-ink-muted hover:bg-white">Cancel</button>
            <button type="button" onClick={() => onConfirm(releaseAssets)} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 font-label text-sm font-bold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60">
              {busy ? <><Loader2 size={16} className="animate-spin" />Disconnecting…</> : "Disconnect"}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
```

- [ ] **Step 4: Add the entry points**

`EmbeddedSection.tsx` — add an `onDisconnect: (channelId: string) => void` prop. Beside the Reconnect button, when `isConnected`:

```tsx
<button
  type="button"
  onClick={() => onDisconnect("meta")}
  disabled={!canManage || isBusy}
  className="mt-2 rounded-xl border border-[#e8e3db] px-4 py-2 font-label text-xs font-bold text-[#78716c] transition-colors hover:border-red-200 hover:text-red-600 disabled:opacity-60 sm:ml-3 sm:mt-0"
>
  Disconnect
</button>
```

In each status row, when `configured`, add beside Manage:

```tsx
<button
  type="button"
  onClick={() => onDisconnect(channel.id)}
  className="rounded-lg px-2 py-1.5 font-label text-[10px] font-bold text-[#a8a29e] transition-colors hover:bg-red-50 hover:text-red-600"
>
  Disconnect
</button>
```

`ChannelCard.tsx` — add `onDisconnect: () => void` and, when `configured`, render the same
button to the left of the Manage/Override button. `ManualSection.tsx` passes
`onDisconnect={() => onDisconnectChannel(channel.id)}` through from a new prop of the same
shape as `onOpenChannel`.

- [ ] **Step 5: Wire `Panel.tsx`**

```tsx
const [disconnectTarget, setDisconnectTarget] = useState<DisconnectTarget | null>(null);
const [disconnecting, setDisconnecting] = useState(false);
const [disconnectError, setDisconnectError] = useState<string | null>(null);

const openDisconnect = (channelId: string) => {
  setDisconnectError(null);
  setDisconnectTarget(buildDisconnectTarget(channelId, settings));
};

async function handleDisconnect(releaseAssets: boolean) {
  if (!disconnectTarget) return;
  setDisconnecting(true);
  setDisconnectError(null);
  try {
    await disconnectChannel(disconnectTarget.channel, releaseAssets);
    setDisconnectTarget(null);
    setSelectedChannel(null);
    await load();
    loadHealth();
  } catch (e) {
    setDisconnectError(e instanceof Error ? e.message : "Disconnect failed");
  } finally {
    setDisconnecting(false);
  }
}
```

Pass `onDisconnect={openDisconnect}` to `EmbeddedSection`, `onDisconnectChannel={openDisconnect}`
to `ManualSection`, and render:

```tsx
{disconnectTarget && (
  <DisconnectDialog
    target={disconnectTarget}
    busy={disconnecting}
    error={disconnectError}
    onConfirm={handleDisconnect}
    onCancel={() => { setDisconnectTarget(null); setDisconnectError(null); }}
  />
)}
```

- [ ] **Step 6: Verify**

Run: `cd frontend && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, all tests pass including the 3 new ones.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/dashboard/settings/
git commit -m "feat: add channel disconnect UI with opt-in asset release"
```

---

### Task 5: Render and verify

**Files:** none modified — this task is verification only.

- [ ] **Step 1: Render both sections and the dialog**

Start the dev server, render the Channels sections at 1440 and 768, and open the disconnect
dialog for both a whole-Meta target and a Telegram target.

- [ ] **Step 2: Confirm by looking at the screenshots**

- Manual header band has no empty strip and the violet Zephyr matches the green one in size
- Both gradients read as a matched pair, neither bleeding into the other's colour
- Disconnect is reachable from the embedded header, every configured status row, and every configured card
- The dialog names the right channels, the checkbox is unchecked by default, and the WhatsApp variant shows the shared-token warning
- Neither breakpoint scrolls horizontally

- [ ] **Step 3: Report what was not verified**

State plainly that migration 172 was not applied to the live project and that no live Meta
disconnect was performed.

---

## Verification Summary

```bash
cd backend && venv/bin/python -m pytest tests/test_channel_disconnect.py tests/test_connection_source.py tests/test_facebook_embedded_signup.py tests/test_whatsapp_embedded_signup_coexistence.py tests/test_telegram_settings.py -v
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

Plus the rendered screenshots from Task 5. Migration 172 remains unapplied until explicitly authorised.
