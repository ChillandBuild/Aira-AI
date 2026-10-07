# aira-private-send (Python)

Send WhatsApp auto-messages from **your own server** with **your own Meta token**. Aira supplies the
rules and templates and a license; the lead's name and phone number never leave your server.

## Install

```bash
pip install aira-private-send                 # SQLite store (stdlib), httpx, cryptography
pip install "aira-private-send[postgres]"     # optional: keep state in Postgres
```

Python 3.9+.

## Quick start

```python
from aira_private_send import AiraPrivateSend

ps = AiraPrivateSend(
    license_key="aps_live_...",           # from your Aira operator
    meta_token="EAAG...",                 # your own WhatsApp Cloud API token
    phone_number_id="123456789012345",
    aira_public_key="<base64 public key Aira gave you>",
    # store="sqlite:///aira_private_send.db"  (default)  or  "postgresql://user:pw@host/db"
)

result = ps.track("purchased", "98765 43210", name="Asha Rao", extra={"order_id": "A42"})
print(result.status, result.reason)       # sent | queued | skipped | failed
```

Also: `ps.opt_out("98765 43210")` stops all future sends to that number.

`track()` raises `ValueError` for an unknown event or invalid phone, `LicenseError` (code
`invalid_key` / `revoked_key` / `feature_disabled`) when Aira rejects the key, `QuotaExceeded` when
the monthly cap is reached, and `BundleUnavailable` when Aira is unreachable and the cached rules are
past their offline grace.

## Cron

Delayed rules wait in your local queue; usage counts are pushed to Aira. Run both every minute:

```cron
* * * * * cd /srv/app && python -c "from myapp import ps; ps.run_due(); ps.report_usage()"
```

`report_usage()` throttles itself to once per 15 minutes (the time is kept in the store, so it works
across cron processes). `report_usage(force=True)` sends now. `run_due()` returns how many were sent;
a send that crashes mid-flight is marked `failed / interrupted` after 15 minutes and is never retried,
because Meta may already have delivered it.

## What Aira sees, and what it does not

| Aira sees | Aira never sees |
|---|---|
| Per day, per event, per template: how many were sent and how many failed | Phone numbers |
| Your plug-in version and the last time it checked in | Customer names or any `extra` field |
| | Your Meta token or message content |

The usage report body is exactly `{"rows": [{"day", "event", "template_id", "sent", "failed"}]}`; Aira's
server rejects any other field.

Rules and templates arrive as an Ed25519-signed bundle verified with `aira_public_key`; an unverified
bundle is never used. If Aira is unreachable the last verified bundle keeps working for the offline
grace period (default 6 hours).

## Local data

The local database holds customer phone numbers; keep it on an encrypted disk, readable only by the app user. The SQLite file is created with mode 0600 (POSIX).

## Safety checks

`aira_base_url` must be `https://` (`http://localhost` / `http://127.0.0.1` allowed for tests),
`phone_number_id` digits only, `graph_version` like `v21.0`; otherwise the constructor raises `ValueError`.
`aira_public_key` takes one key or a list (key rotation). The first verified bundle's tenant is pinned
in the store; a later bundle for another tenant makes `track()` raise `LicenseError` (`tenant_mismatch`).

## Tests

```bash
pip install -e ".[test]" && python -m pytest tests -q
```

The tests reuse the shared vectors in `sdk/spec/vectors/` that the backend and the Node plug-in also pass.
