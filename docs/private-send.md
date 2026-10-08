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
| Meta's own daily message count for your WhatsApp account (no numbers) | Customer replies (as long as replies are set to "Your server"; the default sends them to Anril's inbox) |

The plug-in is open source. Your security team can read it and check that the only hosts it talks
to are the Anril API (`/api/v1/private-send/bundle`, `/api/v1/private-send/usage`) and
`graph.facebook.com`.

## What you need

1. **License key** (starts with `aps_live_`): an admin of your Anril account creates it on the **Developer** page, under *Send from your server* (see "Keys and settings" below), or your Anril contact gives you one. It is shown once. Keep it secret.
2. **Anril public key**: shown on the same Developer page, or from your Anril contact. It is always required: the plug-in does not have it built in. The plug-in uses it to check that the rules really came from Anril. When Anril rotates its signing key you may be given two keys: pass a list (`anril_public_key=[old, new]` in Python, `anrilPublicKey: [old, new]` in Node). Rules are accepted if any listed key verifies them.
3. **Your own Meta access token.** In Meta Business Settings, go to Users, then System users. Add a system user, assign it your WhatsApp account with *Manage* permission, and generate a token with `whatsapp_business_messaging`. Anril never sees this token.
4. **Your WhatsApp phone number ID**, from WhatsApp Manager under API setup.

## Python

```bash
pip install anril-connector
```

```python
from anril_connector import AnrilPrivateSend

anril = AnrilPrivateSend(
    license_key=os.environ["ANRIL_LICENSE_KEY"],
    anril_public_key=os.environ["ANRIL_PUBLIC_KEY"],
    meta_token=os.environ["META_TOKEN"],
    phone_number_id=os.environ["META_PHONE_NUMBER_ID"],
    store="sqlite:///anril_connector.db",
)

anril.track("purchased", phone="+919876543221", name="Ravi")
```

Run these every minute from cron or a worker:

```python
anril.run_due()       # retries sends that could not reach Meta (see "Delivery and retries")
anril.report_usage()  # sends today's counts to Anril (it throttles itself to every 15 min)
```

## Node

```bash
npm install anril-connector
```

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

Run `await anril.runDue()` (retries only) and `await anril.reportUsage()` every minute.

## Safety checks the plug-in makes

- **HTTPS only.** `anril_base_url` / `anrilBaseUrl` must start with `https://` (plain `http://` is only allowed for `localhost` and `127.0.0.1`, for tests). Your license key travels in a header, so it is never sent over plain HTTP.
- **Input checks.** `phone_number_id` must be digits only and `graph_version` must look like `v21.0`; both go into the Meta URL.
- **Tenant pin.** The first verified rules bundle pins your Anril account (tenant) in the local database. If a later signed bundle belongs to a different tenant, it is refused and `track` raises `LicenseError` with code `tenant_mismatch`. To switch a database to another Anril account, start a new database.
- **Local database.** The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user. The plug-in creates the SQLite file with mode 0600 (not on Windows).

## Events

Built-in events: `interested`, `signed_up`, `purchased`. Their usual aliases still work (for example
`bought` and `paid` mean `purchased`). You can also add your own events on the **Auto Messages** page
(up to 20), for example "Kundli ready". The page turns the name into a code (`kundli_ready`) that never
changes after you create it; that code is what your server passes to `track`.

- **Code shape:** any slug matching `^[a-z][a-z0-9_]{1,39}$`. A custom code can't reuse a built-in name or alias.
- **Unknown codes:** a code that isn't a slug (`my-event`, `my event`) makes `track` raise `ValueError`. A slug your account has no message for is skipped with reason `no_rule`.
- **Usage reports:** Anril only checks that the event is a valid slug (anything else is a 422). It does not check it against your events, so a daily count for an event you deleted later is still accepted.
- **Deleting a custom event** also deletes its message.

Your team chooses the template for each event on the **Auto Messages** page of the Anril dashboard; the
plug-in picks up changes within 5 minutes. The signed rules carry only the event, its template and how to
fill the template's variables: there is no delay and no quiet-hours setting.

## Delivery and retries

Every message is **instant and unchecked**. `track` sends the matching template now. There are no quiet
hours, no wait before sending, no 24-hour repeat check and no opt-out list: calling `track` twice for the
same customer and event sends twice. The only skip is `no_rule` (your account has no message for that event).

- `track` writes the send as *queued* and delivers it in the same call. The result is `sent` or `failed`.
- `run_due` / `runDue` exists **only to retry** sends that provably never reached Meta: a failed connection to Meta, or Meta answering 429 or 503. Such a send stays queued, is retried after 1 minute, and `track` returns `queued`. A retry is not counted as sent or failed.
- A send that is still retrying 1 hour after it was created is marked failed (`gave_up: <reason>`) and counted as one failure. It is never sent late.
- Every other outcome is final: Meta rejecting the message (4xx), a 500, 502 or 504, or a timeout while waiting for Meta's answer (Meta may already have accepted it, so it is never re-sent).
- If Anril itself can't be reached and no saved rules are still valid, `track` does not raise. It parks the send and returns `queued` with reason `anril_unreachable`; `run_due` sends it once the rules can be fetched.

## Consent

You are responsible for only messaging customers who agreed to it. The plug-in has no opt-out list: if a
customer asks to stop, stop calling `track` for them.

## When it stops sending

| Situation | What happens |
|---|---|
| License revoked or Private Send turned off | Stops within 15 minutes; `track` raises `LicenseError` |
| Monthly cap reached (+10% grace) | `track` raises `QuotaExceeded` until the next month or a higher tier |
| Signed rules belong to a different Anril account than the pinned one | `track` raises `LicenseError` (`tenant_mismatch`) |
| Anril can't be reached | Keeps using the last rules for the grace period your Anril contact set (default 6 hours), then stops |

## Keys and settings (Developer page)

An admin of your Anril account (permission `settings.manage`) manages Private Send on the **Developer**
page; no Anril contact is needed once the feature is on for your account. The same
actions are available as API calls under `/api/v1/private-send`:

| Action | Call | Notes |
|---|---|---|
| Create a license key | `POST /keys` | The full key is returned once. 409 `key_exists` if an active key already exists |
| Revoke the key | `DELETE /keys/current` | 404 `no_active_key` if there is none. Works even if the feature was switched off |
| Pick who gets replies | `PATCH /settings` with `{"reply_mode": "client"}` or `"aira"` | `aira` = Anril's inbox (the default), `client` = your server |
| Get the public key | `GET /public-key` | Returns `{"public_keys": ["<base64>"]}`; needs only `settings.view` |

- **One key at a time.** Anril allows one active key per account: the create call refuses a second one (409), and if two creates race, the older key survives and the other creator's key is revoked.
- **Turning on "Send from your server" turns off Anril's own sending.** While an active key exists, the hosted website form and the hosted event ingest, and the Partner API's event mode, answer **409** (`private_send_on`, "This account sends from its own server"), so a customer is never messaged twice. Revoke the key to switch them back on.

## Replies

By default, customer replies come to Anril's inbox and Anril's AI can answer them. Anril will then see
the phone number of anyone who replies. If replies must stay on your side, an admin picks "Your server"
as the reply mode on the Developer page (or asks your Anril contact), and you point your own Meta app's
webhook at your server. Choosing "Your server" unsubscribes Anril's app from that WhatsApp account, so
Anril's inbox goes quiet for that number.
