# anril-connector (Python)

Send WhatsApp auto-messages from **your own server** with **your own Meta token**. Anril supplies the
rules and templates and a license; the lead's name and phone number never leave your server.

## Install

```bash
pip install anril-connector                 # SQLite store (stdlib), httpx, cryptography
pip install "anril-connector[postgres]"     # optional: keep state in Postgres
```

Python 3.9+.

## Quick start

```python
from anril_connector import AnrilPrivateSend

ps = AnrilPrivateSend(
    license_key="aps_live_...",           # from your Anril operator
    meta_token="EAAG...",                 # your own WhatsApp Cloud API token
    phone_number_id="123456789012345",
    anril_public_key="<base64 public key Anril gave you>",
    # store="sqlite:///anril_connector.db"  (default)  or  "postgresql://user:pw@host/db"
)

result = ps.track("purchased", "98765 43210", name="Asha Rao", extra={"order_id": "A42"})
print(result.status, result.reason)       # sent | failed | queued | skipped
```

**Every message is instant and there are no checks.** `track()` sends the matching template right away,
inside the call. There is no opt-out list, no 24-hour duplicate skip, no quiet hours and no per-rule delay:
the same event for the same number twice sends twice. Only message people who agreed to it; that is on you.

`status` is `sent` or `failed` (`reason` holds Meta's error), `skipped` (`reason` is `no_rule`, the only skip),
or `queued` when Meta or Anril could not be reached and the send is waiting for a retry (see Cron).

`track()` raises `ValueError` for an unknown event or invalid phone, `LicenseError` (code
`invalid_key` / `revoked_key` / `feature_disabled`) when Anril rejects the key, and `QuotaExceeded` when
the monthly cap is reached. If Anril is unreachable and the cached rules are past their offline grace,
`track()` does not raise: it parks the send and returns `queued / anril_unreachable`; `run_due()` sends it
once a verified bundle is back (and raises `BundleUnavailable` while it is still down).

## Events

Events: `interested`, `signed_up`, `purchased` (plus aliases such as `signup`, `order`, `enquiry`), or any
custom event name of 2-40 characters: a lowercase letter, then lowercase letters, digits or `_`
(e.g. `refund`, `cart_abandoned`). Case and surrounding spaces are ignored. If your Anril rules have no
template for an event, `track()` returns `skipped / no_rule`; anything that is not a valid name raises
`ValueError`.

## Cron

Run this every minute. `run_due()` is only the **retry path**: it re-sends messages that did not reach Meta
because Meta or Anril was unreachable. Nothing waits in it on purpose. `report_usage()` pushes your daily
counts to Anril.

```cron
* * * * * cd /srv/app && python -c "from myapp import ps; ps.run_due(); ps.report_usage()"
```

A send is retried (every minute, for up to one hour after the event) only when it provably never reached
Meta: the connection failed, or Meta answered 429 or 503. After an hour it is marked `failed / gave_up` and
never sent late. Everything else is final and never retried: a Meta rejection, a read timeout (Meta may
already have delivered), and a send that crashed mid-flight (`failed / interrupted` after 15 minutes).
`run_due()` returns how many it sent.

`report_usage()` throttles itself to once per 15 minutes (the time is kept in the store, so it works
across cron processes). `report_usage(force=True)` sends now.

## What Anril sees, and what it does not

| Anril sees | Anril never sees |
|---|---|
| Per day, per event, per template: how many were sent and how many failed | Phone numbers |
| Your plug-in version and the last time it checked in | Customer names or any `extra` field |
| | Your Meta token or message content |

The usage report body is exactly `{"rows": [{"day", "event", "template_id", "sent", "failed"}]}`; Anril's
server rejects any other field.

Rules and templates arrive as an Ed25519-signed bundle verified with `anril_public_key`; an unverified
bundle is never used. Older bundles may still carry `quiet_hours` or a per-rule `delay_minutes`; both are
ignored. If Anril is unreachable the last verified bundle keeps working for the offline
grace period (default 6 hours).

## Local data

The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user. The SQLite file is created with mode 0600 (POSIX). It keeps the send log, the retry queue, the daily counters and the cached bundle. A store file from an earlier build (with an `opt_outs` table) still opens; the opt-out list is ignored. A custom `Store` object needs `retry_send(send_id, send_at, reason)`.

## Safety checks

`anril_base_url` must be `https://` (`http://localhost` / `http://127.0.0.1` allowed for tests),
`phone_number_id` digits only, `graph_version` like `v21.0`; otherwise the constructor raises `ValueError`.
`anril_public_key` is required: one key or a list (key rotation). The first verified bundle's tenant is pinned
in the store; a later bundle for another tenant makes `track()` raise `LicenseError` (`tenant_mismatch`).

## Tests

```bash
pip install -e ".[test]" && python -m pytest tests -q
```

The tests reuse the shared vectors in `sdk/spec/vectors/` that the backend and the Node plug-in also pass.
