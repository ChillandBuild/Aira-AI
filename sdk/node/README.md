# anril-connector (Node)

Anril "Private Send" plug-in. Your own server sends WhatsApp messages using Anril's automation rules,
**without sending your customers' names or phone numbers to Anril**.

```
Anril ── signed rules + templates ──▶ your server (this plug-in) ── message ──▶ Meta ──▶ customer
Anril ◀── daily counts only ───────── your server
```

| Anril receives | Anril never receives |
|---|---|
| Your license key | Customer names |
| Daily counts per event and template, e.g. "purchased / loan_ready / 312 sent, 3 failed" | Customer phone numbers |
| Plug-in version (`X-Anril-Plugin: node/<version>`) | Message content you fill in |

The only hosts the plug-in talks to are the Anril API (`/api/v1/private-send/bundle` and
`/api/v1/private-send/usage`) and `graph.facebook.com`. Requires Node 18 or newer.

## What you need

1. **License key** from your Anril contact (starts with `aps_live_`). Keep it secret.
2. **Anril public key** from your Anril contact (base64 of 32 bytes). The plug-in uses it to check the rules really came from Anril.
3. **Your own Meta access token** (system user with `whatsapp_business_messaging`). Anril never sees it.
4. **Your WhatsApp phone number ID**, from WhatsApp Manager under API setup.

## Install

```bash
npm install anril-connector
npm install pg   # only if you use a Postgres store
```

## Use

```ts
import { AnrilPrivateSend } from "anril-connector";

const anril = new AnrilPrivateSend({
  licenseKey: process.env.ANRIL_LICENSE_KEY!,
  anrilPublicKey: process.env.ANRIL_PUBLIC_KEY!,
  metaToken: process.env.META_TOKEN!,
  phoneNumberId: process.env.META_PHONE_NUMBER_ID!,
  store: "sqlite:./anril_connector.db",
});

await anril.track("purchased", { phone: "+919876543221", name: "Ravi" });
```

**Every message is instant and there are no checks.** `track` sends the matching template right away, inside
the call. There is no opt-out list, no 24-hour duplicate skip, no quiet hours and no per-rule delay: the same
event for the same number twice sends twice. Only message people who agreed to it; that is on you.

Run these every minute from cron or a worker:

```ts
await anril.runDue();       // the retry path: re-sends messages that could not reach Meta or Anril
await anril.reportUsage();  // sends today's counts to Anril (it throttles itself to every 15 min)
```

CommonJS works too: `const { AnrilPrivateSend } = require("anril-connector")`.

### Options

| Option | Default | |
|---|---|---|
| licenseKey, metaToken, phoneNumberId, anrilPublicKey | required | `anrilPublicKey` is one base64 key or an array of them |
| store | `"sqlite:./anril_connector.db"` | `sqlite:<path>`, `sqlite:///<path>`, `sqlite::memory:`, a `postgresql://` URL, or your own `Store` object |
| anrilBaseUrl | `https://aira-ai-5tfr.onrender.com` | https only (localhost / 127.0.0.1 may use http) |
| graphVersion | `v21.0` | |
| fetch | global `fetch` | inject your own (proxies, tests) |

### Methods

- `track(event, { phone, name?, extra?, pageUrl? })` returns `{ status, reason?, messageId? }`.
  `status` is `sent`, `failed` (`reason` holds Meta's error), `skipped` (`reason: "no_rule"`, the only skip) or
  `queued` (Meta or Anril could not be reached; `runDue` retries it).
  Throws `Error` for an unknown event or invalid phone, and `LicenseError` / `QuotaExceeded` as below.
  If Anril is unreachable and the cached rules are past their offline grace, `track` does not throw: it parks the
  send and returns `{ status: "queued", reason: "anril_unreachable" }`.
- `runDue()` returns the number sent. It is only the retry path. A send is retried (every minute, for up to one
  hour after the event) only when it provably never reached Meta: the connection failed, or Meta answered 429
  or 503. After an hour it is marked `failed` / `gave_up` and never sent late. Everything else is final and never
  retried: a Meta rejection, a read timeout (Meta may already have delivered), and a send that crashed mid-flight
  (`failed` / `interrupted` after 15 minutes). While Anril is still unreachable `runDue` throws `BundleUnavailable`
  and the queued rows wait.
- `reportUsage({ force? })` returns the number of rows reported. Sends cumulative counters for today and
  yesterday only: day, event, template id, sent, failed. Never a phone or a name.
- `close()`: close the store.

Events: `interested`, `signed_up`, `purchased` (plus aliases such as `signup`, `order`, `enquiry`), or any
custom event name of 2-40 characters: a lowercase letter, then lowercase letters, digits or `_`
(e.g. `refund`, `cart_abandoned`). Case and surrounding spaces are ignored. If your Anril rules have no
template for an event, `track` returns `skipped / no_rule`; anything that is not a valid name throws `Error`.
Your team chooses the template for each event on the **Auto Messages** page of the Anril
dashboard; the plug-in picks up changes within 5 minutes. Older bundles may still carry `quiet_hours` or a
per-rule `delay_minutes`; both are ignored.

## Consent

You are responsible for only messaging customers who agreed to it. The plug-in keeps no opt-out list and
does not skip repeats: stop calling `track` for a customer who asks to stop.

## When it stops sending

| Situation | What happens |
|---|---|
| License revoked or Private Send turned off (401/403) | `track` throws `LicenseError` (`.code`: `invalid_key`, `revoked_key`, `feature_disabled`) and the cached rules are dropped |
| Monthly cap reached | `track` throws `QuotaExceeded` |
| Anril can't be reached, or the signature is bad | Keeps using the last verified rules for the grace period (default 6 hours) after the last good fetch, then `track` queues the send (`queued` / `anril_unreachable`) for `runDue` instead of sending |

An unverified bundle is never used.

## Local state

The send log, the retry queue and the daily counters live in your own store (SQLite file by
default, tables `sends`, `counters`, `meta`; same schema as the Python plug-in). A store file from an earlier
build (with an `opt_outs` table) still opens; the opt-out list is ignored. A custom `Store` object needs
`retrySend(id, sendAt, reason)`.

The SQLite file is created with mode 0600 (not on Windows). The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user.

## Safety checks

`anrilBaseUrl` must be `https://` (`http://localhost` / `http://127.0.0.1` allowed for tests),
`phoneNumberId` digits only, `graphVersion` like `v21.0`; otherwise the constructor throws `TypeError`.
`anrilPublicKey` is required: one key or a list (key rotation). The first verified bundle's tenant is pinned in
the store; a later bundle for another tenant makes `track` throw `LicenseError` (`tenant_mismatch`).

## Develop

```bash
npm install && npm run build && npm test
```

Tests mock `fetch`; no real network calls. The shared vectors in `../spec/vectors` must pass.
