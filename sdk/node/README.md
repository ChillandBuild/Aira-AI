# aira-private-send (Node)

Aira "Private Send" plug-in. Your own server sends WhatsApp messages using Aira's automation rules,
**without sending your customers' names or phone numbers to Aira**.

```
Aira ── signed rules + templates ──▶ your server (this plug-in) ── message ──▶ Meta ──▶ customer
Aira ◀── daily counts only ───────── your server
```

| Aira receives | Aira never receives |
|---|---|
| Your license key | Customer names |
| Daily counts per event and template, e.g. "purchased / loan_ready / 312 sent, 3 failed" | Customer phone numbers |
| Plug-in version (`X-Aira-Plugin: node/<version>`) | Message content you fill in |

The only hosts the plug-in talks to are the Aira API (`/api/v1/private-send/bundle` and
`/api/v1/private-send/usage`) and `graph.facebook.com`. Requires Node 18 or newer.

## What you need

1. **License key** from your Aira contact (starts with `aps_live_`). Keep it secret.
2. **Aira public key** from your Aira contact (base64 of 32 bytes). The plug-in uses it to check the rules really came from Aira.
3. **Your own Meta access token** (system user with `whatsapp_business_messaging`). Aira never sees it.
4. **Your WhatsApp phone number ID**, from WhatsApp Manager under API setup.

## Install

```bash
npm install aira-private-send
npm install pg   # only if you use a Postgres store
```

## Use

```ts
import { AiraPrivateSend } from "aira-private-send";

const aira = new AiraPrivateSend({
  licenseKey: process.env.AIRA_LICENSE_KEY!,
  airaPublicKey: process.env.AIRA_PUBLIC_KEY!,
  metaToken: process.env.META_TOKEN!,
  phoneNumberId: process.env.META_PHONE_NUMBER_ID!,
  store: "sqlite:./aira_private_send.db",
});

await aira.track("purchased", { phone: "+919876543221", name: "Ravi" });
```

Run these every minute from cron or a worker:

```ts
await aira.runDue();       // sends messages whose rule has a delay
await aira.reportUsage();  // sends today's counts to Aira (it throttles itself to every 15 min)
```

CommonJS works too: `const { AiraPrivateSend } = require("aira-private-send")`.

### Options

| Option | Default | |
|---|---|---|
| licenseKey, metaToken, phoneNumberId, airaPublicKey | required | `airaPublicKey` is one base64 key or an array of them |
| store | `"sqlite:./aira_private_send.db"` | `sqlite:<path>`, `sqlite:///<path>`, `sqlite::memory:`, a `postgresql://` URL, or your own `Store` object |
| airaBaseUrl | `https://aira-ai-5tfr.onrender.com` | https only (localhost / 127.0.0.1 may use http) |
| graphVersion | `v21.0` | |
| fetch | global `fetch` | inject your own (proxies, tests) |

### Methods

- `track(event, { phone, name?, extra?, pageUrl? })` returns `{ status, reason?, messageId? }`.
  `status` is `sent`, `failed`, `queued` or `skipped` (`reason`: `opted_out`, `no_rule`, `duplicate`).
  Throws `Error` for an unknown event or invalid phone, `LicenseError` / `QuotaExceeded` / `BundleUnavailable` as below.
- `optOut(phone)`: skip this customer from now on.
- `runDue()` returns the number sent. Rows stuck in `sending` for more than 15 minutes are marked
  `failed` / `interrupted` and never retried (Meta may already have delivered them).
- `reportUsage({ force? })` returns the number of rows reported. Sends cumulative counters for today and
  yesterday only: day, event, template id, sent, failed. Never a phone or a name.
- `close()`: close the store.

Events: `interested`, `signed_up`, `purchased` (plus aliases such as `signup`, `order`, `enquiry`).
Your team chooses the template and delay for each event on the **Auto Messages** page of the Aira
dashboard; the plug-in picks up changes within 5 minutes.

## Opt-outs and consent

You are responsible for only messaging customers who agreed to it. Call `optOut(phone)` when a
customer asks to stop. The plug-in also skips the same customer for the same event within 24 hours.

## When it stops sending

| Situation | What happens |
|---|---|
| License revoked or Private Send turned off (401/403) | `track` throws `LicenseError` (`.code`: `invalid_key`, `revoked_key`, `feature_disabled`) and the cached rules are dropped |
| Monthly cap reached | `track` throws `QuotaExceeded` |
| Aira can't be reached, or the signature is bad | Keeps using the last verified rules for the grace period (default 6 hours) after the last good fetch, then throws `BundleUnavailable` |

An unverified bundle is never used.

## Local state

Dedupe, opt-outs, the delayed queue and the daily counters live in your own store (SQLite file by
default, tables `sends`, `opt_outs`, `counters`, `meta`; same schema as the Python plug-in).

The SQLite file is created with mode 0600 (not on Windows). The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user.

## Safety checks

`airaBaseUrl` must be `https://` (`http://localhost` / `http://127.0.0.1` allowed for tests),
`phoneNumberId` digits only, `graphVersion` like `v21.0`; otherwise the constructor throws `TypeError`.
`airaPublicKey` takes one key or a list (key rotation). The first verified bundle's tenant is pinned in
the store; a later bundle for another tenant makes `track` throw `LicenseError` (`tenant_mismatch`).

## Develop

```bash
npm install && npm run build && npm test
```

Tests mock `fetch`; no real network calls. The shared vectors in `../spec/vectors` must pass.
