# Private Send — wire contract (v1)

The client's server runs the Anril plug-in (Python or Node). Anril supplies rules, templates and the
license; the plug-in sends to Meta itself. **No lead name or phone number is ever sent to Anril.**

Production base URL: `https://aira-ai-5tfr.onrender.com`

## Auth

Every plug-in call carries `Authorization: Bearer <license key>` and `X-Anril-Plugin: <lang>/<version>`
(e.g. `python/1.0.0`). Keys look like `aps_live_` + 32 url-safe chars. Anril stores only the sha256 hex
of the full key plus a display prefix (first 13 chars, e.g. `aps_live_7Hq2`).

## GET /api/v1/private-send/bundle

| Status | Body | Plug-in action |
|---|---|---|
| 200 | `{"payload": "<base64 of UTF-8 JSON bytes>", "sig": "<base64 Ed25519 signature over the raw payload bytes>", "key_id": "v1"}` | verify sig, then parse payload |
| 401 | `{"error": "...", "code": "invalid_key" \| "revoked_key"}` | stop at once, drop cached bundle |
| 403 | `{"error": "...", "code": "feature_disabled"}` | stop at once, drop cached bundle |
| 429 | rate limited (60/min per key) | keep last bundle, retry later |
| 503 | `{"code": "signing_not_configured"}` or any 5xx / network error | "Anril unreachable" (see grace) |

Signature: Ed25519 over the exact payload bytes (base64-decoded). No JSON canonicalisation needed.
Server private key: env `PRIVATE_SEND_SIGNING_KEY` = base64 of the 32-byte raw seed. Plug-ins take
the public key (base64 of 32 raw bytes) as a constructor option `anril_public_key` / `anrilPublicKey`.
The option takes one key or a list of keys (see "Plug-in bundle rules"). `key_id` is informational only.

Payload JSON:
```json
{
  "version": 1,
  "tenant_id": "uuid",
  "issued_at": "2026-10-07T10:00:00Z",
  "expires_at": "2026-10-07T10:15:00Z",
  "offline_grace_hours": 6,
  "limits": {"monthly_cap": 50000, "used": 41200, "blocked": false},
  "rules": [
    {"id": "uuid", "event": "purchased", "template_id": "uuid", "delay_minutes": 0,
     "variables": [{"source": "first_name", "fallback": "there"}],
     "button_param": null, "enabled": true}
  ],
  "templates": [
    {"id": "uuid", "name": "loan_ready", "language": "en", "category": "UTILITY",
     "body_text": "Hi {{1}}, your loan is approved.", "header_text": null,
     "header_media_type": null, "header_media_url": null, "buttons": []}
  ]
}
```
Only enabled rules and APPROVED templates used by them are included. `rules[].variables` and
`button_param` have exactly the shape stored in `auto_message_rules` (migration 215/216):
`source` is one of `first_name`, `full_name`, `page_url`, `phone`, `text` (uses `value`) or
`extra` (uses `key`); `fallback` is used when the value is empty or a customer field holds a link.

### Plug-in bundle rules
- Refresh every 5 minutes (and on first `track`).
- A bundle may be used until `expires_at`.
- If refresh fails with 429/5xx/network error, the last verified bundle stays usable until
  (time of last successful fetch + `offline_grace_hours`). After that: refuse to send.
- 401/403 → refuse to send immediately (raise `LicenseError` with the code).
- `limits.blocked == true` → refuse to send (`QuotaExceeded`).
- Bad signature → treat as a failed refresh (never use an unverified bundle).
- **Signing-key rotation.** `anril_public_key` / `anrilPublicKey` accepts one base64 key or a list of
  them. A bundle is valid if **any** listed key verifies its signature. The response's `key_id` is
  informational: never use it to choose a key (an attacker controls that field). To rotate, ship the
  new public key alongside the old one, switch the server's signing key, then drop the old key.
- **Tenant pin.** The `tenant_id` of the first verified bundle is stored in the plug-in's local store
  (meta key `pinned_tenant_id`). A later verified bundle with a different `tenant_id` (or none) is a
  failed refresh: it is not cached or used, and `track` raises `LicenseError` with code
  `tenant_mismatch`. The error message never contains either tenant id. To move a store to another
  tenant, use a new store.
- **Transport and inputs.** The constructor rejects an `anril_base_url` / `anrilBaseUrl` that is not
  `https://` (`http://localhost` and `http://127.0.0.1` are allowed for tests): `ValueError` in
  Python, `TypeError` in Node. `phone_number_id` must match `^\d+$` and `graph_version` must match
  `^v\d+\.\d+$`, because both go into the Graph URL path.
- **Local database.** When the SQLite store creates its file it sets mode `0600` (POSIX only, skipped on
  Windows). The local database holds customer phone numbers; keep it on an encrypted disk, readable
  only by the app user.

## POST /api/v1/private-send/usage

Body (unknown fields at either level → 422, so a phone can never be smuggled in):
```json
{"rows": [{"day": "2026-10-07", "event": "purchased", "template_id": "uuid", "sent": 312, "failed": 3}]}
```
- 1–500 rows. `day` within the last 7 days (UTC), not in the future. `sent`, `failed` ≥ 0.
  `sent` and `failed` are each ≤ 100000 per (day, event, template) row.
- Values are **cumulative totals for that day**, not increments. The server keeps the **highest** value
  it has seen per (day, event, template_id) and bills only the growth, so resending is safe, and a lower
  value (e.g. after the plug-in's local store was reset) never lowers the stored total or bills twice.
  Duplicate rows in one request are merged to the highest values. The plug-in reports today and
  yesterday every 15 minutes.
- Nothing in a request is stored if any row is rejected (422).
- Rate limits: 30 requests per minute per license key, plus 120 per minute per client IP on both
  `/bundle` and `/usage` (checked before the key is looked up). Over the limit: 429
  `{"code": "rate_limited"}` with `Retry-After: 60`.
- `limits.used` in the bundle: for a day Anril has reconciled with Meta's own count, Meta's number is
  used; the plug-in's report only counts for days not yet reconciled.
- 200 `{"ok": true, "accepted": <n>}`. Same 401/403 codes as `/bundle`.
- 422 with `{"code": "unknown_template"}`: a `template_id` that is not the tenant's. The plug-in logs a
  warning with the error code only (no ids, no body), does not raise, and carries on, so one bad row
  never blocks reporting. It does start the 15-minute throttle.
- 429 (rate limited) or any 5xx / network error: the plug-in keeps its counters, does **not** start the
  throttle, and retries on the next `report_usage` / `reportUsage` call.

## Sending (inside the plug-in)

Events: `interested`, `signed_up`, `purchased` plus the aliases in `normalize_event`
(backend/app/services/auto_messages.py). One enabled rule per event.

`track(event, phone, name=None, extra=None, page_url=None)`:
1. Normalise event and phone (same rules as the backend). Invalid → raise `ValueError`.
2. Opted out locally → skip (`status="skipped", reason="opted_out"`).
3. No rule → skip `no_rule`. Same phone + event queued/sending/sent in the last 24 h → skip `duplicate`.
4. `delay_minutes == 0` → send now; else store in the local queue for `run_due()`.
5. Build the Meta components with the same logic as `build_components`; context =
   `{first_name, full_name, page_url, phone, extra}` as in the backend's `send_one`.
6. POST `https://graph.facebook.com/<graph_version>/<phone_number_id>/messages` with the client's own
   Meta token. Count `sent` / `failed` per (day, event, template_id) in the local store.

All state (dedupe, opt-outs, queue, counters) lives in the client's local store. Default SQLite file.

The test cases in `sdk/spec/vectors/*.json` are the source of truth for component building; the
backend, the Python plug-in and the Node plug-in must all pass them.

## Operator API (operator auth, same as other /api/v1/operator routes)

- `GET  /api/v1/operator/clients/{tenant_id}/private-send` →
  ```json
  {"enabled": true, "monthly_cap": 50000, "reply_mode": "client", "offline_grace_hours": 6,
   "keys": [{"id": "uuid", "key_prefix": "aps_live_7Hq2", "status": "active", "created_at": "...",
             "last_seen_at": "...", "plugin_version": "python/1.0.0", "revoked_at": null}],
   "usage": {"period": "2026-10", "reported_sent": 41200, "meta_volume": 41350, "mismatch": false,
             "days": [{"day": "2026-10-07", "reported_sent": 312, "meta_volume": 315}]}}
  ```
- `POST   …/private-send/keys` → `{"id": "uuid", "key": "aps_live_…(full, shown once)", "key_prefix": "aps_live_7Hq2"}`
- `DELETE …/private-send/keys/{key_id}` → `{"ok": true}` (status → revoked, revoked_at set)
- `PATCH  …/private-send/settings` body any of `{"reply_mode": "client"|"aira", "offline_grace_hours": 1..72, "monthly_cap": int|null}` → same body as GET.
  Changing `reply_mode` calls Meta `subscribed_apps` (DELETE for `client`, POST for `aira`) on the
  tenant's `meta_waba_id`; if Meta fails → 502 and nothing is saved.
- Turning the feature on/off uses the existing features endpoint with feature key `private_send`.
- Every change writes `record_audit_event`.

## Client dashboard API (tenant auth, `settings.view`)

- `GET /api/v1/auto-messages/private-send` →
  ```json
  {"enabled": true, "key_prefix": "aps_live_7Hq2", "reply_mode": "client",
   "days": [{"day": "2026-10-07", "event": "purchased", "template_id": "uuid", "template_name": "loan_ready", "sent": 312, "failed": 3}]}
  ```
  Last 30 days. `enabled: false` → the other fields are null/empty.

## Settings keys (app_settings, per tenant)
`private_send_reply_mode` (default `client`), `private_send_offline_grace_hours` (default `6`),
`private_send_monthly_cap` (default null = no cap).
