# Private Send — setup guide for client IT teams

Private Send lets your own server send WhatsApp messages with Anril's automation rules, **without
sending your customers' names or phone numbers to Anril**.

```
Anril ── signed rules + templates ──▶ your server (Anril plug-in) ── message ──▶ Meta ──▶ customer
Anril ◀── daily counts only ───────── your server
```

## What Anril sees, and what it doesn't

| Anril receives | Anril never receives |
|---|---|
| Your license key | Customer names |
| Daily counts per event and template, e.g. "purchased / loan_ready / 312 sent, 3 failed" | Customer phone numbers |
| Plug-in version | Message content you fill in |
| Meta's own daily message count for your WhatsApp account (no numbers) | Customer replies (unless your Anril contact switches replies to "Anril AI") |

The plug-in is open source. Your security team can read it and check that the only hosts it talks
to are the Anril API (`/api/v1/private-send/bundle`, `/api/v1/private-send/usage`) and
`graph.facebook.com`.

## What you need

1. **License key**: from your Anril contact (starts with `aps_live_`). Keep it secret.
2. **Anril public key**: from your Anril contact. The plug-in uses it to check that the rules really came from Anril. When Anril rotates its signing key you may be given two keys: pass a list (`anril_public_key=[old, new]` in Python, `anrilPublicKey: [old, new]` in Node). Rules are accepted if any listed key verifies them.
3. **Your own Meta access token.** In Meta Business Settings, go to Users, then System users. Add a system user, assign it your WhatsApp account with *Manage* permission, and generate a token with `whatsapp_business_messaging`. Anril never sees this token.
4. **Your WhatsApp phone number ID**, from WhatsApp Manager under API setup.

## Python

```bash
pip install anril-private-send
```

```python
from anril_private_send import AnrilPrivateSend

anril = AnrilPrivateSend(
    license_key=os.environ["ANRIL_LICENSE_KEY"],
    anril_public_key=os.environ["ANRIL_PUBLIC_KEY"],
    meta_token=os.environ["META_TOKEN"],
    phone_number_id=os.environ["META_PHONE_NUMBER_ID"],
    store="sqlite:///anril_private_send.db",
)

anril.track("purchased", phone="+919876543221", name="Ravi")
```

Run these every minute from cron or a worker:

```python
anril.run_due()       # sends messages whose rule has a delay
anril.report_usage()  # sends today's counts to Anril (it throttles itself to every 15 min)
```

## Node

```bash
npm install anril-private-send
```

```ts
import { AnrilPrivateSend } from "anril-private-send";

const anril = new AnrilPrivateSend({
  licenseKey: process.env.ANRIL_LICENSE_KEY!,
  anrilPublicKey: process.env.ANRIL_PUBLIC_KEY!,
  metaToken: process.env.META_TOKEN!,
  phoneNumberId: process.env.META_PHONE_NUMBER_ID!,
  store: "sqlite:./anril_private_send.db",
});

await anril.track("purchased", { phone: "+919876543221", name: "Ravi" });
```

Run `await anril.runDue()` and `await anril.reportUsage()` every minute.

## Safety checks the plug-in makes

- **HTTPS only.** `anril_base_url` / `anrilBaseUrl` must start with `https://` (plain `http://` is only allowed for `localhost` and `127.0.0.1`, for tests). Your license key travels in a header, so it is never sent over plain HTTP.
- **Input checks.** `phone_number_id` must be digits only and `graph_version` must look like `v21.0`; both go into the Meta URL.
- **Tenant pin.** The first verified rules bundle pins your Anril account (tenant) in the local database. If a later signed bundle belongs to a different tenant, it is refused and `track` raises `LicenseError` with code `tenant_mismatch`. To switch a database to another Anril account, start a new database.
- **Local database.** The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user. The plug-in creates the SQLite file with mode 0600 (not on Windows).

## Events

`interested`, `signed_up`, `purchased`. Your team chooses the template and delay for each event on
the **Auto Messages** page of the Anril dashboard; the plug-in picks up changes within 5 minutes.

## Opt-outs and consent

You are responsible for only messaging customers who agreed to it. Call `opt_out(phone)` /
`optOut(phone)` when a customer asks to stop; the plug-in will skip them from then on. The plug-in
also skips the same customer for the same event within 24 hours.

## When it stops sending

| Situation | What happens |
|---|---|
| License revoked or Private Send turned off | Stops within 15 minutes; `track` raises `LicenseError` |
| Monthly cap reached (+10% grace) | `track` raises `QuotaExceeded` until the next month or a higher tier |
| Signed rules belong to a different Anril account than the pinned one | `track` raises `LicenseError` (`tenant_mismatch`) |
| Anril can't be reached | Keeps using the last rules for the grace period your Anril contact set (default 6 hours), then stops |

## Replies

By default, customer replies go to **your** system: point your own Meta app's webhook at your server.
If you want Anril's AI to answer replies, ask your Anril contact to switch replies to "Anril AI". Anril
will then see the phone number of anyone who replies.
