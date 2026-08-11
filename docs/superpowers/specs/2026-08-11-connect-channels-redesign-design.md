# Connect Channels Settings — Redesign Around Connection Method

**Date:** 2026-08-11
**Surface:** `/dashboard/settings` → Channels tab
**Primary file today:** `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx` (1323 lines)

## Problem

Meta's Embedded Signup v4 flow was added to the page, and the page now presents one
connection in three overlapping ways:

1. **"Business Accounts → Choose your connection method"** is framed as WhatsApp Cloud API
   only, but its "Connect Meta Business" button (`ConnectChannelsPanel.tsx:938`) starts the
   unified v4 flow that provisions WhatsApp, the Facebook Page, linked Instagram, and an
   optional ad account.
2. **"One Meta connection" banner** (`ConnectChannelsPanel.tsx:1002`) calls the same
   `handleStartUnifiedMetaSignup()` with the same `META_UNIFIED_CONFIG_ID`. It is a pure
   duplicate CTA.
3. **"Additional channels" grid** still lists Instagram DM, Facebook Messenger, and Meta Ads
   as independent manual setups, even though the v4 flow fills their credentials.

A user cannot tell which button to press, or why Instagram appears both as an outcome of the
Meta flow and as a card that asks for a page access token.

## Decisions

Captured from the design conversation:

- **Segregate the page by connection method, not by channel family.** The two top-level
  sections are Embedded Onboarding and Manual API Connection.
- **Two stacked sections, both always visible.** No tabs, no accordion. Telegram and Razorpay
  have no embedded path and live only under Manual.
- **Channels connected through the embedded flow stay visible in the Manual grid**, marked
  "Connected via Meta" rather than hidden, so nothing appears to vanish.
- **Add a per-channel connection-source marker** in the backend so that badge is truthful
  instead of inferred.
- **Keep the existing Zephyr illustrations**, green for embedded and violet for manual — the
  colour already carries the meaning (guided path vs. bring-your-own-keys).

## Page Structure

```
CONNECT CHANNELS
┌─ EMBEDDED ONBOARDING ─────────────────── Recommended ─┐
│ One Meta window connects WhatsApp, Messenger,         │
│ Instagram and read-only Ads reporting.                │
│  ✓ Secure one-click connection                        │
│  ✓ Official WhatsApp Cloud API            [green zephyr]
│  ✓ Business number and webhook linked automatically   │
│  [ Connect Meta Business → ]                          │
│  Already using the WhatsApp Business app? Connect ▸   │
├───────────────────────────────────────────────────────┤
│ WhatsApp   ● Live        2m ago            Manage     │
│ Instagram  ● Live        12m ago           Manage     │
│ Messenger  ○ Not connected                 —          │
│ Meta Ads   ● Configured  Synced 1d ago     Manage     │
└───────────────────────────────────────────────────────┘

┌─ MANUAL API CONNECTION ────────────────────  Advanced ─┐
│ Bring your own Business Account ID, tokens and         │
│ webhook controls.                        [violet zephyr]
├────────────────────────────────────────────────────────┤
│ [WhatsApp]  [Instagram]  [Messenger]                   │
│ [Meta Ads]  [Telegram]   [Razorpay]                    │
└────────────────────────────────────────────────────────┘
```

### What is removed

- The blue "ONE META CONNECTION" section (`ConnectChannelsPanel.tsx:985-1013`). Its copy
  ("One secure Meta window connects WhatsApp, your Facebook Page and Messenger, linked
  Instagram, and optional read-only ad reporting") moves into the Embedded section header,
  where it accurately describes the button beneath it.
- The two-card "Choose your connection method" grid (`ConnectChannelsPanel.tsx:907-983`).
  Those two cards become the two page-level sections.
- The "Additional channels / Keep every conversation connected" heading. The Manual section
  header replaces it.

### Illustration placement

`ZephyrCourier` (`ConnectChannelsPanel.tsx:293`) keeps both variants and both image assets.
The green variant sits beside the embedded value-props, as it does today. Because the Manual
section is now a six-card grid rather than a single card, the violet variant moves into that
section's header band, to the right of the "bring your own tokens" copy.

### Status rows in the Embedded section

Each of the four Meta channels renders as a row: icon, name, status pill, health metadata,
and a Manage action that opens the same channel config modal used by the Manual cards. The
status rule is unchanged from today:

```
isLive = !channel.hasActivation
      || settings[`${channel.id}_status`] === "live"
      || Boolean(health[channel.id]?.last_event)
```

The section-level status pill and Refresh health button stay in the Embedded section header.

## Connection-Source Marker

### Keys

New `app_settings` rows, one per Meta channel, value `"embedded"` or `"manual"`:

- `whatsapp_connection_source`
- `instagram_connection_source`
- `facebook_connection_source`
- `meta_ads_connection_source`

No database migration is required. `app_settings` is a free-form tenant/key/value table and
`PATCH /api/v1/settings/` has no key allowlist — it upserts whatever keys it is given
(`backend/app/routes/app_settings.py:266-280`). `GET /api/v1/settings/` returns every row for
the tenant, so the new keys reach the frontend with no route change.

None of these keys are secret, so none are added to `_SECRET_KEYS`.

### Write sites

Stamp `"embedded"` alongside the existing credential writes in every route that provisions
credentials on the user's behalf:

| Route | Line | Stamps |
|---|---|---|
| `POST /meta/unified-signup/complete` | `app_settings.py:1131-1152` | whatsapp, facebook; instagram when an IG account is linked; meta_ads when an ad account is chosen |
| `POST /whatsapp/embedded-signup` | `app_settings.py:737` | whatsapp |
| `POST /facebook/business-login/complete` | `app_settings.py:997-999` | facebook; instagram when linked; meta_ads when an ad account is chosen |
| `POST /facebook/embedded-signup` | `app_settings.py:1196` | facebook |

Stamp `"manual"` in `PATCH /api/v1/settings/` whenever the payload contains any credential key
belonging to a channel. The channel-to-credential-key mapping lives in one module-level dict
in `app_settings.py` so the three legacy routes and the PATCH handler share one source of
truth.

### Back-compat

Existing tenants have no `*_connection_source` row. The frontend resolves a missing key as:

```
source(channel) = settings[`${channel}_connection_source`]
               ?? (settings.meta_business_access_token?.is_set ? "embedded" : "manual")
```

`meta_business_access_token` is written only by Meta-guided flows — the unified v4 flow
(`app_settings.py:1137`) and the older Facebook Business Login flow (`app_settings.py:979`).
Never by the manual token form. Its presence is therefore a sound one-time inference. No
backfill script; the value self-corrects the next time either path writes.

### Frontend effect

A Manual card whose channel resolves to `"embedded"`:

- status pill reads **Connected via Meta**
- card body is muted (reduced emphasis, no hover lift)
- primary button reads **Override manually** instead of Manage
- the config modal opens with a warning strip: saving replaces the credentials the embedded
  flow provisioned, and reconnecting through Embedded Onboarding restores them

Telegram and Razorpay never carry a source marker; their cards are unchanged.

## File Decomposition

`ConnectChannelsPanel.tsx` is 1323 lines and mixes SDK loading, data fetching, six presentation
concerns, and two modals. The redesign splits it into
`frontend/app/dashboard/settings/connect-channels/`, keeping
`frontend/app/dashboard/settings/ConnectChannelsPanel.tsx` as a one-line re-export so
`frontend/app/dashboard/settings/page.tsx:10` is untouched.

| File | Responsibility |
|---|---|
| `ConnectChannelsPanel.tsx` | State, data fetching, composition of the two sections |
| `EmbeddedSection.tsx` | Meta CTA, coexistence link, four channel status rows |
| `ManualSection.tsx` | Six-card grid and its header band |
| `ChannelCard.tsx` | A single channel card, including the source badge |
| `ChannelConfigModal.tsx` | Token form, Activate, webhook guide, override warning |
| `MetaAssetPickerModal.tsx` | Facebook Page and ad account selection after signup |
| `useMetaSignup.ts` | FB SDK load, `postMessage` listener, start/finish/complete |
| `channels.ts` | `CHANNELS` config, `FieldDef`/`ChannelConfig` types, source resolution |
| `ui.tsx` | Status badge, refresh button, outlined/secret fields, copy button, `timeAgo` |

Each file stays well under the 800-line ceiling; the largest is expected to be
`ChannelConfigModal.tsx` at roughly 250 lines.

## States and Error Handling

The embedded flow keeps its existing state machine:
`idle → connecting → selecting → finishing → success | error`.

Today, embedded errors render in two places (the embedded card and the duplicate banner).
After the redesign there is one render site, in the Embedded section body. The success message
("Your selected Meta channels are connected. Ads access is read-only and used only for
reporting.") renders in the same place.

Existing failure behaviour is preserved: an expired signup session returns 400 with "This Meta
signup session has expired. Start the connection again."; a WhatsApp number already claimed by
another workspace returns 409. Both surface as the inline error strip.

## Verification

- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint` — the build ignores lint, so lint must be run explicitly;
  unused imports left behind by the split will fail it
- `cd backend && pytest` — covering the new source-marker writes on the unified-signup
  complete path and the PATCH manual path
- Render `/dashboard/settings` → Channels tab and screenshot at 1440 and 768 before reporting
  the work complete

Backend writes reach the live Supabase project only when the user runs a real Meta signup;
the implementation will not trigger a live Meta OAuth flow.

## Known Risk

"Override manually" on an embedded-connected channel overwrites the `meta_access_token` or
`facebook_access_token` that the v4 flow provisioned. This is recoverable — reconnecting
through Embedded Onboarding rewrites them — so it is not destructive, but the modal states it
explicitly rather than leaving the user to discover it.
