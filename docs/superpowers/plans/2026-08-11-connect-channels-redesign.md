# Connect Channels Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Channels settings page around connection *method* — one Embedded Onboarding section and one Manual API Connection section — removing the duplicate "Connect Meta Business" CTA and labelling embedded-provisioned channels honestly.

**Architecture:** The backend gains a per-channel `<channel>_connection_source` setting (`"embedded"` / `"manual"`) written by every route that provisions credentials, so the frontend can tell a Meta-guided connection from a hand-pasted one. The 1323-line `ConnectChannelsPanel.tsx` is decomposed into a `connect-channels/` directory of focused modules, then recomposed into the two-section layout.

**Tech Stack:** FastAPI + Supabase (backend), Next.js 14 App Router + React + Tailwind (frontend), pytest (backend tests), vitest in `environment: "node"` (frontend tests — pure-logic, not render tests).

**Spec:** `docs/superpowers/specs/2026-08-11-connect-channels-redesign-design.md`

## Global Constraints

- No database migration. `app_settings` is a free-form `(tenant_id, key, value, is_secret)` table and `PATCH /api/v1/settings/` has no key allowlist — new keys need no schema change.
- `frontend/app/dashboard/settings/page.tsx:10` imports `./ConnectChannelsPanel` — that import path must keep working untouched.
- `npm run build` ignores lint. `npm run lint` must be run explicitly; unused imports left behind by a file split will fail it.
- Connection-source keys are **not** secret — do not add them to `_SECRET_KEYS` in `backend/app/routes/app_settings.py`.
- Channel ids used everywhere: `whatsapp`, `instagram`, `facebook`, `meta_ads`, `telegram`, `razorpay`. The status key is `<id>_status`; the new source key is `<id>_connection_source`.
- Never trigger a live Meta OAuth flow during implementation. Backend behaviour is proved with mocked-Supabase pytest, exactly as `backend/tests/test_facebook_embedded_signup.py` does.
- Existing Zephyr assets are reused as-is: `/aira/illustrations/aira-zephyr-embedded-3d.png` (green, embedded) and `/aira/illustrations/aira-zephyr-manual-3d.png` (violet, manual). No new images.

---

## File Structure

**Backend (modified only):**

| File | Change |
|---|---|
| `backend/app/routes/app_settings.py` | Add `_CHANNEL_CREDENTIAL_KEYS` map + `_stamp_connection_source` helper; stamp `"manual"` in `update_settings`; stamp `"embedded"` in the four Meta-guided routes |
| `backend/tests/test_connection_source.py` | New — covers both stamp directions |

**Frontend — new directory `frontend/app/dashboard/settings/connect-channels/`:**

| File | Responsibility |
|---|---|
| `channels.ts` | Types, `CHANNELS` config, `resolveConnectionSource` |
| `channels.test.ts` | Unit tests for `resolveConnectionSource` |
| `ui.tsx` | `Portal`, icons, `ChannelStatusBadge`, `HealthRefreshButton`, `ZephyrCourier`, `CopyButton`, `OutlinedField`, `SecretField`, `timeAgo` |
| `api.ts` | `fetchSettings`, `saveSettings` |
| `useMetaSignup.ts` | FB SDK load, `postMessage` listener, start/finish/complete of the unified flow |
| `WebhookConfigGuide.tsx` | The per-channel webhook setup guide |
| `ChannelConfigModal.tsx` | Token form, Activate, webhook guide, override warning |
| `MetaAssetPickerModal.tsx` | Page + ad-account selection after signup |
| `EmbeddedSection.tsx` | Meta CTA, coexistence link, four channel status rows |
| `ManualSection.tsx` | Six-card grid + header band |
| `ChannelCard.tsx` | One card, including the source badge |
| `Panel.tsx` | State, fetching, composition |

**Frontend — modified:**

| File | Change |
|---|---|
| `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx` | Reduced to a one-line re-export of `connect-channels/Panel` |

---

### Task 1: Backend — connection-source map and helper, stamped on manual saves

**Files:**
- Modify: `backend/app/routes/app_settings.py:123-133` (add map + helper), `backend/app/routes/app_settings.py:283-325` (replace the status-reset block)
- Test: `backend/tests/test_connection_source.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_CHANNEL_CREDENTIAL_KEYS: dict[str, frozenset[str]]` and
  `_stamp_connection_source(db, tenant_id: str, channel: str, source: str) -> None`
  in `app.routes.app_settings`. Task 2 imports both.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_connection_source.py`:

```python
from unittest.mock import MagicMock, patch

import pytest


def _upserted(db):
    """Every row app_settings upserted during the call, keyed by setting key."""
    rows = [call.args[0] for call in db.table.return_value.upsert.call_args_list]
    return {row["key"]: row for row in rows if "key" in row}


@pytest.mark.asyncio
async def test_manual_credential_save_marks_only_the_touched_channel_as_manual():
    """Breaks if a manual token save silently keeps an 'embedded' badge on the card."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"instagram_access_token": "IGQV-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["instagram_connection_source"]["value"] == "manual"
    assert rows["instagram_connection_source"]["is_secret"] is False
    assert "whatsapp_connection_source" not in rows
    assert "facebook_connection_source" not in rows
    assert "meta_ads_connection_source" not in rows


@pytest.mark.asyncio
async def test_manual_credential_save_still_resets_channel_status_to_configured():
    """Breaks if folding the status reset into the shared channel map loses the reset."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"meta_access_token": "EAAG-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["whatsapp_status"]["value"] == "configured"
    assert rows["whatsapp_connection_source"]["value"] == "manual"


@pytest.mark.asyncio
async def test_non_channel_settings_never_stamp_a_connection_source():
    """Breaks if unrelated settings writes pollute the channel source markers."""
    from app.routes.app_settings import SettingsUpdate, update_settings

    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"key": "x"}]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings.record_audit_event"):
        await update_settings(
            SettingsUpdate(updates={"groq_api_key": "gsk-token"}),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    assert not [key for key in _upserted(db) if key.endswith("_connection_source")]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_connection_source.py -v`
Expected: FAIL — `KeyError: 'instagram_connection_source'`.

- [ ] **Step 3: Add the shared channel map and stamp helper**

In `backend/app/routes/app_settings.py`, immediately after `_get_setting_value` (which ends at line 133), insert:

```python
# One source of truth for "which settings keys belong to which channel".
# Used to reset a channel's status and to record how it was connected.
_CHANNEL_CREDENTIAL_KEYS: dict[str, frozenset[str]] = {
    "whatsapp": frozenset({
        "meta_access_token", "meta_phone_number_id", "meta_waba_id",
        "meta_app_secret", "meta_webhook_verify_token",
    }),
    "instagram": frozenset({"instagram_access_token", "instagram_page_id", "instagram_app_secret"}),
    "facebook": frozenset({"facebook_access_token", "facebook_page_id"}),
    "meta_ads": frozenset({"meta_ads_access_token", "meta_ads_account_id"}),
}


def _stamp_connection_source(db, tenant_id: str, channel: str, source: str) -> None:
    """Record whether a channel's credentials came from a Meta-guided flow or a hand-pasted token.

    The UI uses this to label an embedded-provisioned channel instead of implying
    the tenant configured it by hand. `source` is "embedded" or "manual".
    """
    _save_tenant_setting(db, tenant_id, f"{channel}_connection_source", source)
```

`_stamp_connection_source` calls `_save_tenant_setting`, which is defined later in the module at line 791. Python resolves the name at call time, so the forward reference is fine — do not move `_save_tenant_setting`.

- [ ] **Step 4: Replace the status-reset block with the shared map**

In `update_settings`, delete the block that currently spans from the `# Reset status of the channel to "configured" if credentials are changed` comment through the fourth `if reset_ads:` upsert (lines 283-325), and replace it with:

```python
    # Credentials changed by hand: the channel must be re-validated, and it is no
    # longer whatever the embedded flow provisioned.
    for channel, credential_keys in _CHANNEL_CREDENTIAL_KEYS.items():
        if any(key in updated for key in credential_keys):
            _save_tenant_setting(db, tenant_id, f"{channel}_status", "configured")
            _stamp_connection_source(db, tenant_id, channel, "manual")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_connection_source.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the existing settings tests for regressions**

Run: `cd backend && pytest tests/test_telegram_settings.py tests/test_facebook_embedded_signup.py -v`
Expected: all pass — the status-reset refactor must not change existing behaviour.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/app_settings.py backend/tests/test_connection_source.py
git commit -m "feat: record how each channel was connected on manual saves"
```

---

### Task 2: Backend — stamp "embedded" on every Meta-guided route

**Files:**
- Modify: `backend/app/routes/app_settings.py` — `complete_unified_meta_signup` (~line 1131), `whatsapp_embedded_signup` (~line 737), `complete_meta_business_login` (~line 997), `facebook_embedded_signup` (~line 1273)
- Test: `backend/tests/test_connection_source.py`

**Interfaces:**
- Consumes: `_stamp_connection_source(db, tenant_id, channel, source)` from Task 1.
- Produces: `app_settings` rows `whatsapp_connection_source` / `instagram_connection_source` / `facebook_connection_source` / `meta_ads_connection_source` with value `"embedded"`, which Task 3's `resolveConnectionSource` reads.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_connection_source.py`:

```python
class _StubResponse:
    def __init__(self, data: dict):
        self._data = data

    def json(self):
        return self._data


class _StubMetaClient:
    """Mimics the Graph calls complete_unified_meta_signup makes, in order."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, **_):
        return _StubResponse({"success": True})

    async def get(self, url, **_):
        return _StubResponse({"display_phone_number": "+919999999999", "verified_name": "Bloom"})


@pytest.mark.asyncio
async def test_unified_signup_marks_every_provisioned_channel_as_embedded():
    """Breaks if a Meta-provisioned channel shows up in the manual grid as hand-configured."""
    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{
            "id": "page-1",
            "name": "Bloom Matrix",
            "access_token": "page-token",
            "instagram_business_account": {"id": "ig-1"},
        }],
        "ad_accounts": [{"id": "act_42", "name": "Bloom Ads"}],
        "catalogs": [],
    }
    staged_values = [
        "business-token", "session-1", "2999-01-01T00:00:00+00:00",
        "waba-1", "phone-1", None, "false",
    ]
    from unittest.mock import AsyncMock

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged_values), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=True)), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id="act_42"),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    for channel in ("whatsapp", "facebook", "instagram", "meta_ads"):
        assert rows[f"{channel}_connection_source"]["value"] == "embedded", channel


@pytest.mark.asyncio
async def test_unified_signup_without_an_ad_account_leaves_ads_unstamped():
    """Breaks if Meta Ads is labelled connected-via-Meta when no ad account was granted."""
    from unittest.mock import AsyncMock

    from app.routes.app_settings import UnifiedMetaSignupCompleteRequest, complete_unified_meta_signup

    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    discovered = {
        "pages": [{"id": "page-1", "name": "Bloom Matrix", "access_token": "page-token"}],
        "ad_accounts": [],
        "catalogs": [],
    }
    staged_values = [
        "business-token", "session-1", "2999-01-01T00:00:00+00:00",
        "waba-1", "phone-1", None, "false",
    ]

    with patch("app.routes.app_settings.get_supabase", return_value=db), \
         patch("app.routes.app_settings._get_setting_value", side_effect=staged_values), \
         patch("app.services.meta_cloud.discover_business_login_assets", new=AsyncMock(return_value=discovered)), \
         patch("app.services.meta_cloud.verify_waba_phone_number", new=AsyncMock(return_value=True)), \
         patch("app.services.meta_cloud.register_phone_number", new=AsyncMock(return_value={"success": True})), \
         patch("app.routes.app_settings.httpx.AsyncClient", return_value=_StubMetaClient()), \
         patch("app.routes.app_settings.record_audit_event"):
        await complete_unified_meta_signup(
            UnifiedMetaSignupCompleteRequest(session_id="session-1", page_id="page-1", ad_account_id=None),
            ctx={"tenant_id": "tenant-1"},
            user={"user_id": "user-1"},
        )

    rows = _upserted(db)
    assert rows["whatsapp_connection_source"]["value"] == "embedded"
    assert rows["facebook_connection_source"]["value"] == "embedded"
    assert "instagram_connection_source" not in rows
    assert "meta_ads_connection_source" not in rows
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_connection_source.py -k embedded -v`
Expected: FAIL — `KeyError: 'whatsapp_connection_source'`.

- [ ] **Step 3: Stamp the unified signup route**

In `complete_unified_meta_signup`, the credential writes are a list of `(key, value, is_secret)` tuples starting at line 1131. Add two entries to that tuple list, after `("facebook_status", ...)`:

```python
        ("whatsapp_connection_source", "embedded", False),
        ("facebook_connection_source", "embedded", False),
```

Then inside the existing `if connected_instagram:` block, after the `instagram_status` write, add:

```python
        _stamp_connection_source(db, tenant_id, "instagram", "embedded")
```

And inside the existing `if ad_account:` block, after the `meta_ads_status` write, add:

```python
        _stamp_connection_source(db, tenant_id, "meta_ads", "embedded")
```

- [ ] **Step 4: Stamp the three legacy Meta-guided routes**

In `whatsapp_embedded_signup`, immediately after the `whatsapp_status` = `"live"` upsert (~line 737-744), add:

```python
    _stamp_connection_source(db, tenant_id, "whatsapp", "embedded")
```

In `complete_meta_business_login`, after the `facebook_status` write (~line 997) and inside the existing `if connected_instagram:` / `if ad_account:` blocks, add respectively:

```python
    _stamp_connection_source(db, tenant_id, "facebook", "embedded")
```
```python
        _stamp_connection_source(db, tenant_id, "instagram", "embedded")
```
```python
        _stamp_connection_source(db, tenant_id, "meta_ads", "embedded")
```

In `facebook_embedded_signup`, after the `facebook_status` = `"live"` upsert (~line 1273) and inside its `if connected_instagram:` block, add respectively:

```python
    _stamp_connection_source(db, tenant_id, "facebook", "embedded")
```
```python
        _stamp_connection_source(db, tenant_id, "instagram", "embedded")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_connection_source.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run the full Meta signup suite for regressions**

Run: `cd backend && pytest tests/test_facebook_embedded_signup.py tests/test_whatsapp_embedded_signup_coexistence.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/app_settings.py backend/tests/test_connection_source.py
git commit -m "feat: mark Meta-provisioned channels as embedded connections"
```

---

### Task 3: Frontend — extract types, channel config, and source resolution

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/channels.ts`
- Create: `frontend/app/dashboard/settings/connect-channels/channels.test.ts`
- Read (source of the move): `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx:54-61, 114-262`

**Interfaces:**
- Consumes: the `<channel>_connection_source` rows produced by Tasks 1-2.
- Produces, from `connect-channels/channels.ts`:
  - types `Setting`, `SettingsMap`, `FieldDef`, `ActivateResult`, `ChannelHealth`, `TokenAlert`, `WebhookHealth`, `SaveState`, `ChannelConfig`, `EmbeddedSignupSession`, `MetaBusinessLoginState`, `MetaBusinessAssets`
  - `CHANNELS: ChannelConfig[]`, `WHATSAPP_CHANNEL`, `META_CHANNELS: ChannelConfig[]`, `STANDALONE_CHANNELS: ChannelConfig[]`
  - `type ConnectionSource = "embedded" | "manual"`
  - `resolveConnectionSource(channelId: string, settings: Setting[]): ConnectionSource`

- [ ] **Step 1: Create the module by moving the existing definitions**

Create `frontend/app/dashboard/settings/connect-channels/channels.ts`. Move, **verbatim and unchanged**, from `ConnectChannelsPanel.tsx`:

- lines 54-61 (`EmbeddedSignupSession`, `MetaBusinessLoginState`, `MetaBusinessAssets`)
- lines 114-167 (`Setting`, `SettingsMap`, `FieldDef`, `ActivateResult`, `ChannelHealth`, `TokenAlert`, `WebhookHealth`, `SaveState`, `ChannelConfig`)
- lines 168-259 (`const CHANNELS: ChannelConfig[] = [...]`) and line 261 (`const WHATSAPP_CHANNEL = CHANNELS[0]`)

Add `export` to every one of them. Do **not** move line 262 (`OTHER_CHANNELS`) — it is replaced below.

The file needs these imports for the `CHANNELS` icons:

```ts
import { MessageSquare, Send, Megaphone, IndianRupee } from "lucide-react";
import { InstagramIcon, FacebookIcon } from "./ui";
```

Then append the new grouping and resolution logic:

```ts
/** Channels the Meta embedded flow can provision. Order drives the status rows. */
export const META_CHANNEL_IDS = ["whatsapp", "instagram", "facebook", "meta_ads"] as const;

export const META_CHANNELS: ChannelConfig[] = META_CHANNEL_IDS
  .map(id => CHANNELS.find(c => c.id === id))
  .filter((c): c is ChannelConfig => Boolean(c));

/** Channels with no embedded path — manual configuration is the only way in. */
export const STANDALONE_CHANNELS: ChannelConfig[] = CHANNELS.filter(
  c => !META_CHANNEL_IDS.includes(c.id as (typeof META_CHANNEL_IDS)[number])
);

export type ConnectionSource = "embedded" | "manual";

/**
 * How a channel's credentials got there.
 *
 * Tenants connected before the source marker existed have no `*_connection_source`
 * row. `meta_business_access_token` is written only by Meta-guided flows and never
 * by the manual token form, so its presence is a sound fallback signal.
 */
export function resolveConnectionSource(channelId: string, settings: Setting[]): ConnectionSource {
  if (!META_CHANNEL_IDS.includes(channelId as (typeof META_CHANNEL_IDS)[number])) return "manual";

  const explicit = settings.find(s => s.key === `${channelId}_connection_source`)?.display_value;
  if (explicit === "embedded") return "embedded";
  if (explicit === "manual") return "manual";

  return settings.find(s => s.key === "meta_business_access_token")?.is_set ? "embedded" : "manual";
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/app/dashboard/settings/connect-channels/channels.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { META_CHANNELS, STANDALONE_CHANNELS, resolveConnectionSource } from "./channels";
import type { Setting } from "./channels";

function setting(key: string, display_value: string, is_set = true): Setting {
  return { key, display_value, is_secret: false, is_set, updated_at: "2026-08-11T00:00:00Z" };
}

describe("resolveConnectionSource", () => {
  test("returns embedded when the channel is explicitly marked embedded", () => {
    const settings = [setting("instagram_connection_source", "embedded")];
    expect(resolveConnectionSource("instagram", settings)).toBe("embedded");
  });

  test("explicit manual wins over the embedded fallback signal", () => {
    const settings = [
      setting("instagram_connection_source", "manual"),
      { ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true },
    ];
    expect(resolveConnectionSource("instagram", settings)).toBe("manual");
  });

  test("falls back to embedded for legacy tenants that have a Meta business token", () => {
    const settings = [{ ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true }];
    expect(resolveConnectionSource("whatsapp", settings)).toBe("embedded");
  });

  test("falls back to manual when no marker and no Meta business token exist", () => {
    expect(resolveConnectionSource("whatsapp", [setting("meta_waba_id", "123")])).toBe("manual");
  });

  test("non-Meta channels are always manual", () => {
    const settings = [{ ...setting("meta_business_access_token", "EAAG••••1234"), is_secret: true }];
    expect(resolveConnectionSource("telegram", settings)).toBe("manual");
    expect(resolveConnectionSource("razorpay", settings)).toBe("manual");
  });
});

describe("channel grouping", () => {
  test("splits the four Meta channels from the standalone ones", () => {
    expect(META_CHANNELS.map(c => c.id)).toEqual(["whatsapp", "instagram", "facebook", "meta_ads"]);
    expect(STANDALONE_CHANNELS.map(c => c.id)).toEqual(["telegram", "razorpay"]);
  });
});
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd frontend && npx vitest run app/dashboard/settings/connect-channels/channels.test.ts`
Expected: 6 passed. If `META_CHANNELS` is empty, the icon imports from `./ui` are missing — Task 4 creates that module, so create a minimal `ui.tsx` stub exporting `InstagramIcon` and `FacebookIcon` now by moving lines 74-111 of `ConnectChannelsPanel.tsx` verbatim (with `export` added); Task 4 fills in the rest.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/
git commit -m "refactor: extract channel config and connection-source resolution"
```

---

### Task 4: Frontend — extract UI primitives and settings API helpers

**Files:**
- Create/complete: `frontend/app/dashboard/settings/connect-channels/ui.tsx`
- Create: `frontend/app/dashboard/settings/connect-channels/api.ts`
- Create: `frontend/app/dashboard/settings/connect-channels/WebhookConfigGuide.tsx`
- Read (source of the move): `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx:63-111, 264-310, 312-337, 339-443, 446-552`

**Interfaces:**
- Consumes: `SettingsMap` from `./channels` (Task 3).
- Produces:
  - from `./ui`: `Portal`, `InstagramIcon`, `FacebookIcon`, `ChannelStatusBadge`, `HealthRefreshButton`, `ZephyrCourier`, `CopyButton`, `OutlinedField`, `SecretField`, `timeAgo`
  - from `./api`: `fetchSettings(): Promise<Setting[]>`, `saveSettings(updates: SettingsMap): Promise<void>`
  - from `./WebhookConfigGuide`: default export `WebhookConfigGuide({ channelId, tenantId })`

- [ ] **Step 1: Complete `ui.tsx`**

`ui.tsx` already holds `InstagramIcon` and `FacebookIcon` from Task 3. Move into it, verbatim with `export` added:

- lines 63-70 — `Portal`
- lines 264-277 — `ChannelStatusBadge`
- lines 279-291 — `HealthRefreshButton`
- lines 293-310 — `ZephyrCourier`
- lines 339-357 — `CopyButton`
- lines 359-388 — `OutlinedField`
- lines 390-432 — `SecretField`
- lines 434-443 — `timeAgo`

Header of the file:

```tsx
"use client";
import Image from "next/image";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, EyeOff, Copy, Check, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
```

Add exactly the lucide icons the moved code uses — no more, or `npm run lint` fails on unused imports.

- [ ] **Step 2: Create `api.ts`**

Move lines 312-337 verbatim, with `export` added to both functions:

```ts
import { API_URL, getAuthHeaders } from "@/lib/api";
import type { Setting, SettingsMap } from "./channels";
```

- [ ] **Step 3: Create `WebhookConfigGuide.tsx`**

Move lines 446-552 verbatim as the default export. It imports `CopyButton` and `timeAgo` from `./ui` and whatever lucide icons the moved body uses.

- [ ] **Step 4: Verify the new modules compile**

Run: `cd frontend && npm run typecheck`
Expected: no errors from `connect-channels/`. Errors still pointing at the un-split `ConnectChannelsPanel.tsx` are expected at this stage only if you have already removed code from it — if you have not, expect a clean run.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/
git commit -m "refactor: extract channel UI primitives and settings API helpers"
```

---

### Task 5: Frontend — extract the Meta signup hook

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/useMetaSignup.ts`
- Read (source of the move): `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx:13-52, 740-855`

**Interfaces:**
- Consumes: `MetaBusinessAssets`, `MetaBusinessLoginState`, `EmbeddedSignupSession` from `./channels`.
- Produces:

```ts
export function useMetaSignup(opts: {
  canManage: boolean;
  onConnected: () => void | Promise<void>;
}): {
  state: MetaBusinessLoginState;
  error: string | null;
  assets: MetaBusinessAssets | null;
  selectedPageId: string;
  selectedAdAccountId: string;
  setSelectedPageId: (id: string) => void;
  setSelectedAdAccountId: (id: string) => void;
  start: (isCoexistence?: boolean) => Promise<void>;
  complete: () => Promise<void>;
  dismissAssets: () => void;
  isBusy: boolean;
}
```

`isBusy` is `state === "connecting" || state === "finishing"` — every disabled-button check in the UI uses it, so the condition exists in one place.

- [ ] **Step 1: Create the hook**

Create `useMetaSignup.ts` containing, moved verbatim from `ConnectChannelsPanel.tsx`:

- lines 13-15 — the `META_APP_ID` / `META_UNIFIED_CONFIG_ID` constants and their comment
- lines 17-33 — the `declare global` block for `window.FB`
- lines 35-52 — `fbSdkPromise` and `loadFacebookSdk`
- lines 740-855 — `finishUnifiedMetaSignup`, the `useEffect` `postMessage` listener, `handleStartUnifiedMetaSignup`, `handleCompleteUnifiedMetaSignup`

Wrap them in the hook, moving these state declarations in from lines 570-576:

```ts
export function useMetaSignup({ canManage, onConnected }: { canManage: boolean; onConnected: () => void | Promise<void> }) {
  const [state, setState] = useState<MetaBusinessLoginState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [assets, setAssets] = useState<MetaBusinessAssets | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [selectedAdAccountId, setSelectedAdAccountId] = useState("");
  const sessionRef = useRef<EmbeddedSignupSession>({});
  const codeRef = useRef<string | null>(null);
  // ...moved bodies, with setMetaBusinessState -> setState, setMetaBusinessError -> setError,
  // setMetaBusinessAssets -> setAssets, setSelectedMetaPageId -> setSelectedPageId,
  // setSelectedMetaAdAccountId -> setSelectedAdAccountId
}
```

Replace the two `await load(); loadHealth();` calls inside `handleCompleteUnifiedMetaSignup` with a single `await onConnected();`. Keep every fetch URL, request body, error message, and `event.origin` check byte-identical — the `https://www.facebook.com` / `https://web.facebook.com` origin allowlist is a security control.

Return the object from the Interfaces block above, with:

```ts
  const dismissAssets = useCallback(() => {
    setAssets(null);
    setState("idle");
    setError(null);
  }, []);
  const isBusy = state === "connecting" || state === "finishing";
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npm run typecheck`
Expected: no errors from `useMetaSignup.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/useMetaSignup.ts
git commit -m "refactor: extract Meta embedded signup into a hook"
```

---

### Task 6: Frontend — extract both modals, with the override warning

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/MetaAssetPickerModal.tsx`
- Create: `frontend/app/dashboard/settings/connect-channels/ChannelConfigModal.tsx`
- Read (source of the move): `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx:1101-1147, 1150-1320`

**Interfaces:**
- Consumes: `Portal`, `OutlinedField`, `SecretField` from `./ui`; `WebhookConfigGuide`; `ChannelConfig`, `SettingsMap`, `Setting`, `SaveState`, `ActivateResult`, `ConnectionSource` from `./channels`; the hook return shape from Task 5.
- Produces:

```tsx
export default function MetaAssetPickerModal(props: {
  assets: MetaBusinessAssets;
  selectedPageId: string;
  selectedAdAccountId: string;
  onSelectPage: (id: string) => void;
  onSelectAdAccount: (id: string) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  isBusy: boolean;
  error: string | null;
}): JSX.Element

export default function ChannelConfigModal(props: {
  channel: ChannelConfig;
  settings: Setting[];
  drafts: SettingsMap;
  tenantId: string | null;
  canManage: boolean;
  isDirty: boolean;
  saveState: SaveState;
  activating: boolean;
  activateResult: ActivateResult | null;
  connectionSource: ConnectionSource;
  onDraftChange: (key: string, value: string) => void;
  onSave: () => void;
  onActivate: () => void;
  onClose: () => void;
}): JSX.Element
```

- [ ] **Step 1: Move `MetaAssetPickerModal`**

Move lines 1101-1147 verbatim into the new component, substituting the props above for the closed-over state. Keep the heading "Choose your Meta Business assets" and its body copy unchanged.

- [ ] **Step 2: Move `ChannelConfigModal`**

Move lines 1150-1320 verbatim, substituting the props above for the closed-over state.

- [ ] **Step 3: Add the override warning**

Inside `ChannelConfigModal`, directly beneath the modal header and above the fields, add:

```tsx
{connectionSource === "embedded" && (
  <div className="mb-5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
    <AlertCircle size={14} className="mt-0.5 shrink-0 text-amber-600" />
    <p className="font-body text-xs text-amber-800">
      This channel was connected through Meta. Saving your own credentials here replaces
      the ones Meta provisioned. You can restore them by reconnecting from Embedded Onboarding.
    </p>
  </div>
)}
```

- [ ] **Step 4: Verify it compiles**

Run: `cd frontend && npm run typecheck`
Expected: no errors from either modal file.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/
git commit -m "refactor: extract channel modals and warn before overriding Meta credentials"
```

---

### Task 7: Frontend — build the Embedded and Manual sections

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/EmbeddedSection.tsx`
- Create: `frontend/app/dashboard/settings/connect-channels/ChannelCard.tsx`
- Create: `frontend/app/dashboard/settings/connect-channels/ManualSection.tsx`

**Interfaces:**
- Consumes: `META_CHANNELS`, `STANDALONE_CHANNELS`, `CHANNELS`, `resolveConnectionSource` from `./channels`; `ChannelStatusBadge`, `HealthRefreshButton`, `ZephyrCourier`, `timeAgo` from `./ui`.
- Produces:

```tsx
export default function EmbeddedSection(props: {
  settings: Setting[];
  webhookHealth: WebhookHealth | null;
  healthLoading: boolean;
  canManage: boolean;
  isBusy: boolean;
  error: string | null;
  isConnected: boolean;
  onConnect: (isCoexistence?: boolean) => void;
  onRefreshHealth: () => void;
  onManageChannel: (channel: ChannelConfig) => void;
}): JSX.Element

export default function ChannelCard(props: {
  channel: ChannelConfig;
  configured: boolean;
  isLive: boolean;
  hasTokenAlert: boolean;
  source: ConnectionSource;
  metadata: string;
  healthLoading: boolean;
  onRefreshHealth: () => void;
  onOpen: () => void;
}): JSX.Element

export default function ManualSection(props: {
  settings: Setting[];
  webhookHealth: WebhookHealth | null;
  healthLoading: boolean;
  onRefreshHealth: () => void;
  onOpenChannel: (channel: ChannelConfig) => void;
}): JSX.Element
```

- [ ] **Step 1: Build `EmbeddedSection`**

Section shell, header band, value props, CTA, coexistence link, then the four status rows:

```tsx
<section className="overflow-hidden rounded-[28px] border border-emerald-200 bg-white shadow-[0_16px_45px_rgba(28,25,23,0.06)]">
  <div className="flex flex-col gap-4 border-b border-emerald-100 bg-gradient-to-r from-emerald-50 via-white to-[#f4f0ff] px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-7">
    <div>
      <p className="font-label text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-700">Embedded onboarding</p>
      <h2 className="mt-1 font-display text-xl font-bold text-ink">WhatsApp, Messenger, Instagram &amp; Ads</h2>
      <p className="mt-1 max-w-2xl font-body text-xs text-ink-muted">
        One secure Meta window connects WhatsApp, your Facebook Page and Messenger, linked
        Instagram, and optional read-only ad reporting.
      </p>
    </div>
    <div className="flex shrink-0 items-center gap-2">
      <span className="rounded-lg bg-emerald-500 px-2.5 py-1 font-label text-[10px] font-bold text-white shadow-sm">Recommended</span>
      <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
    </div>
  </div>

  <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
    <div>
      <ul className="space-y-3 font-body text-sm text-[#57534e]">
        {["Secure one-click connection", "Official WhatsApp Cloud API", "Business number and webhook linked automatically"].map(item => (
          <li key={item} className="flex items-center gap-2"><CheckCircle2 size={16} className="shrink-0 text-emerald-500" />{item}</li>
        ))}
      </ul>
      {error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{error}</p>}
      <button
        type="button"
        onClick={() => onConnect()}
        disabled={!canManage || isBusy}
        className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 font-label text-sm font-bold text-white shadow-[0_8px_20px_rgba(16,185,129,0.22)] transition-all hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:px-8"
      >
        {isBusy ? <><Loader2 size={16} className="animate-spin" />Connecting…</> : <>{isConnected ? "Reconnect Meta Business" : "Connect Meta Business"} <ArrowRight size={16} /></>}
      </button>
      <button
        type="button"
        onClick={() => onConnect(true)}
        disabled={!canManage || isBusy}
        className="mt-2 inline-flex items-center justify-center gap-1.5 rounded-xl px-1 py-2 font-label text-xs font-semibold text-emerald-700 transition-all hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        Already using the WhatsApp Business app? Connect without switching <ArrowRight size={12} />
      </button>
    </div>
    <ZephyrCourier variant="embedded" />
  </div>

  <div className="divide-y divide-[#f0ece4] border-t border-[#f0ece4]">
    {META_CHANNELS.map(channel => { /* status row, Step 2 */ })}
  </div>
</section>
```

- [ ] **Step 2: Build the status row inside `EmbeddedSection`**

```tsx
{META_CHANNELS.map(channel => {
  const configured = channel.fields.every(f => settings.find(s => s.key === f.key)?.is_set);
  const health = webhookHealth?.health?.[channel.id];
  const alert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);
  const statusSetting = settings.find(s => s.key === `${channel.id}_status`);
  const isLive = !channel.hasActivation || statusSetting?.display_value === "live" || Boolean(health?.last_event);

  return (
    <div key={channel.id} className="flex items-center justify-between gap-3 px-5 py-3.5 sm:px-7">
      <div className="flex min-w-0 items-center gap-3">
        <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", channel.iconBg)}>
          <channel.icon size={17} className={channel.iconColor} />
        </div>
        <div className="min-w-0">
          <p className="truncate font-display text-sm font-bold text-ink">{channel.name}</p>
          <p className="truncate font-body text-[11px] text-ink-muted">
            {health?.last_event ? `Active ${timeAgo(health.last_event)}` : configured ? "No events received yet" : "Not connected"}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <ChannelStatusBadge configured={configured} hasTokenAlert={Boolean(alert)} isLive={isLive} />
        {configured && (
          <button
            type="button"
            onClick={() => onManageChannel(channel)}
            className="rounded-lg px-2.5 py-1.5 font-label text-[10px] font-bold text-primary transition-colors hover:bg-[#f4f0ff]"
          >
            Manage
          </button>
        )}
      </div>
    </div>
  );
})}
```

- [ ] **Step 3: Build `ChannelCard`**

Move the card body from `ConnectChannelsPanel.tsx:1032-1097` verbatim, then apply the source treatment. Replace the status badge line with:

```tsx
{source === "embedded" && configured ? (
  <span className="inline-flex items-center gap-1 rounded-full bg-[#f4f0ff] px-2.5 py-1 font-label text-[10px] font-bold text-primary">
    Connected via Meta
  </span>
) : (
  <ChannelStatusBadge configured={configured} hasTokenAlert={hasTokenAlert} isLive={isLive} />
)}
```

Change the article's className to mute an embedded card, and the action button's label:

```tsx
className={cn(
  "flex min-h-[270px] flex-col justify-between rounded-3xl border bg-white p-5 shadow-sm transition-all duration-300",
  source === "embedded" && configured
    ? "border-[#ece7fb] bg-[#fdfcff]"
    : "border-[#e8e3db] hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-lg"
)}
```

```tsx
<Settings2 size={12} /> {source === "embedded" && configured ? "Override manually" : configured ? "Manage" : "Set up"}
```

The `metadata` prop carries the bottom-left line so `ChannelCard` stays free of Meta Ads special-casing — `ManualSection` computes it.

- [ ] **Step 4: Build `ManualSection`**

```tsx
<section className="overflow-hidden rounded-[28px] border border-violet-200 bg-white shadow-[0_16px_45px_rgba(28,25,23,0.06)]">
  <div className="flex flex-col gap-4 border-b border-violet-100 bg-gradient-to-r from-violet-50 via-white to-[#fbfaf8] px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
    <div>
      <p className="font-label text-[10px] font-bold uppercase tracking-[0.18em] text-violet-700">Manual API connection</p>
      <h2 className="mt-1 font-display text-xl font-bold text-ink">Bring your own tokens</h2>
      <p className="mt-1 max-w-2xl font-body text-xs text-ink-muted">
        Use your own Business Account ID, permanent access tokens and webhook controls.
        Telegram and Razorpay are configured here only.
      </p>
    </div>
    <div className="flex shrink-0 items-center gap-3">
      <span className="rounded-lg bg-violet-600 px-2.5 py-1 font-label text-[10px] font-bold text-white shadow-sm">Advanced</span>
      <div className="hidden w-[150px] sm:block"><ZephyrCourier variant="manual" /></div>
    </div>
  </div>
  <div className="grid grid-cols-1 gap-5 p-5 sm:p-7 md:grid-cols-2 lg:grid-cols-3">
    {CHANNELS.map(channel => { /* compute props, render ChannelCard */ })}
  </div>
</section>
```

Inside the map, compute each card's props — the metadata line keeps the current Meta Ads special case:

```tsx
const configured = channel.fields.every(f => settings.find(s => s.key === f.key)?.is_set);
const health = webhookHealth?.health?.[channel.id];
const alert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);
const source = resolveConnectionSource(channel.id, settings);
const statusSetting = settings.find(s => s.key === `${channel.id}_status`);
const isLive = !channel.hasActivation || statusSetting?.display_value === "live" || Boolean(health?.last_event);
const adsAccountName = settings.find(s => s.key === "meta_ads_account_name")?.display_value;
const adsLastSync = settings.find(s => s.key === "meta_ads_last_sync_at")?.display_value;

const metadata =
  channel.id === "meta_ads"
    ? [
        adsAccountName && adsAccountName !== "Not set" ? adsAccountName : "Ads account connected",
        adsLastSync && adsLastSync !== "Not set" ? `Synced ${timeAgo(adsLastSync)}` : null,
      ].filter(Boolean).join(" · ")
    : health?.last_event
      ? `Active event: ${timeAgo(health.last_event)}`
      : "No events received yet";
```

`CHANNELS` order gives WhatsApp, Instagram, Messenger, Meta Ads, Telegram, Razorpay — the intended grid order, so no re-sorting is needed. `STANDALONE_CHANNELS` is not used for rendering; it exists for the Task 3 grouping test and for `resolveConnectionSource` correctness.

- [ ] **Step 5: Verify it compiles**

Run: `cd frontend && npm run typecheck`
Expected: no errors from the three new files.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/settings/connect-channels/
git commit -m "feat: add embedded and manual connection sections"
```

---

### Task 8: Frontend — recompose the panel and delete the duplicate CTA

**Files:**
- Create: `frontend/app/dashboard/settings/connect-channels/Panel.tsx`
- Rewrite: `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx` (1323 lines → 1 line)

**Interfaces:**
- Consumes: everything produced by Tasks 3-7.
- Produces: `ConnectChannelsPanel({ canManage }: { canManage?: boolean })` as the default export of both `connect-channels/Panel.tsx` and the `ConnectChannelsPanel.tsx` re-export.

- [ ] **Step 1: Build `Panel.tsx`**

Move from `ConnectChannelsPanel.tsx` verbatim: the state declarations (lines 555-569 — everything except the six `metaBusiness*` / `selectedMeta*` / `unified*Ref` declarations, which now live in `useMetaSignup`), `load`, `loadHealth`, the mount `useEffect`, `settingFor`, `isChannelConfigured`, `isModalDirty`, `handleSave`, `handleActivate`, `openChannelModal`, `closeChannelModal`.

Wire the hook and compose:

```tsx
const meta = useMetaSignup({
  canManage,
  onConnected: async () => { await load(); loadHealth(); },
});

const metaConnected = META_CHANNELS.some(c => isChannelConfigured(c));

return (
  <div className="mx-auto w-full max-w-[1440px] space-y-8">
    {error && (
      <div className="flex items-center gap-2 rounded-2xl border border-red-100 bg-red-50 p-3.5 text-red-700">
        <AlertCircle size={15} />
        <span className="font-body text-sm">{error}</span>
      </div>
    )}

    {loading ? (
      <div className="space-y-6">
        <div className="h-[420px] animate-pulse rounded-[28px] bg-border-subtle" />
        <div className="h-[380px] animate-pulse rounded-[28px] bg-border-subtle" />
      </div>
    ) : (
      <div className="space-y-6">
        <EmbeddedSection
          settings={settings}
          webhookHealth={webhookHealth}
          healthLoading={healthLoading}
          canManage={canManage}
          isBusy={meta.isBusy}
          error={meta.error}
          isConnected={metaConnected}
          onConnect={meta.start}
          onRefreshHealth={loadHealth}
          onManageChannel={openChannelModal}
        />
        <ManualSection
          settings={settings}
          webhookHealth={webhookHealth}
          healthLoading={healthLoading}
          onRefreshHealth={loadHealth}
          onOpenChannel={openChannelModal}
        />
      </div>
    )}

    {meta.assets && (
      <MetaAssetPickerModal
        assets={meta.assets}
        selectedPageId={meta.selectedPageId}
        selectedAdAccountId={meta.selectedAdAccountId}
        onSelectPage={meta.setSelectedPageId}
        onSelectAdAccount={meta.setSelectedAdAccountId}
        onConfirm={meta.complete}
        onDismiss={meta.dismissAssets}
        isBusy={meta.isBusy}
        error={meta.error}
      />
    )}

    {selectedChannel && (
      <ChannelConfigModal
        channel={selectedChannel}
        settings={settings}
        drafts={drafts}
        tenantId={tenantId}
        canManage={canManage}
        isDirty={isModalDirty}
        saveState={saveState}
        activating={activating}
        activateResult={activateResult}
        connectionSource={resolveConnectionSource(selectedChannel.id, settings)}
        onDraftChange={(key, value) => setDrafts(prev => ({ ...prev, [key]: value }))}
        onSave={handleSave}
        onActivate={handleActivate}
        onClose={closeChannelModal}
      />
    )}
  </div>
);
```

The old "Business Accounts" wrapper section, the "Choose your connection method" two-card grid, the blue "ONE META CONNECTION" section, and the "Additional channels" heading are all gone — none of them are recreated.

- [ ] **Step 2: Replace `ConnectChannelsPanel.tsx` with the re-export**

The whole file becomes:

```tsx
export { default } from "./connect-channels/Panel";
```

- [ ] **Step 3: Verify there is exactly one embedded-signup CTA left**

Run: `cd frontend && grep -rn "Connect Meta Business" app/dashboard/settings/`
Expected: exactly two matches, both in `connect-channels/EmbeddedSection.tsx` — the `Connect Meta Business` / `Reconnect Meta Business` ternary on one line and nothing else. Zero matches in any other file.

- [ ] **Step 4: Typecheck, lint, and test**

Run: `cd frontend && npm run typecheck && npm run lint && npx vitest run app/dashboard/settings/connect-channels/`
Expected: typecheck clean, lint clean (no `no-unused-vars` from leftover imports), 6 tests pass.

- [ ] **Step 5: Render the page and look at it**

Start the app, sign in, open `/dashboard/settings` and select the Channels tab. Screenshot at 1440px and 768px wide. Confirm by looking at the screenshots:
- exactly one "Connect Meta Business" button on the page
- the four Meta status rows sit under the embedded CTA
- the manual grid shows six cards including Telegram and Razorpay
- the green Zephyr is in the embedded section, the violet Zephyr in the manual header band
- nothing overflows horizontally at 768px

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/settings/
git commit -m "feat: split channels settings into embedded and manual sections"
```

---

## Verification Summary

Run before reporting the work complete:

```bash
cd backend && pytest tests/test_connection_source.py tests/test_facebook_embedded_signup.py tests/test_whatsapp_embedded_signup_coexistence.py tests/test_telegram_settings.py -v
cd frontend && npm run typecheck && npm run lint && npm test
```

Plus the rendered screenshots from Task 8 Step 5. A green build is not evidence the page looks right — the screenshots are.
