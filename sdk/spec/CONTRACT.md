# Private Send — wire contract (v1)

The client's server runs the Anril plug-in (Python or Node). Anril supplies rules, templates and the
license; the plug-in sends to Meta itself. **No lead name or phone number is ever sent to Anril.**

Production base URL: `https://aira-ai-5tfr.onrender.com`

Packages: `anril-connector` on PyPI (import `anril_connector`) and on npm. The class is still
`AnrilPrivateSend`. Internal names are unchanged: the `private_send` table, routes and feature key, and the
`aps_live_` key prefix.

## Auth

Every plug-in call carries `Authorization: Bearer <license key>` and `X-Anril-Plugin: <lang>/<version>`
(e.g. `python/1.1.0`). Keys look like `aps_live_` + 32 url-safe chars. Anril stores only the sha256 hex
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
Today the option is **required**: the production public key is not yet baked into the packages. Once it is,
the option becomes optional and an explicitly passed key still overrides the default.

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
    {"id": "uuid", "event": "purchased", "template_id": "uuid",
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
Only enabled rules and APPROVED templates used by them are included. Bundle `version` stays `1`.
**There are no quiet hours and no per-rule delay:** the backend no longer sends `quiet_hours` or
`rules[].delay_minutes`, and a plug-in must not require either. An older backend may still send them; a
plug-in **ignores both if present** (whatever their value, even a malformed `quiet_hours`: it never rejects
the bundle). A rule's `event` is a
built-in key or one of the tenant's own event slugs (`^[a-z][a-z0-9_]{1,39}$`). `rules[].variables` and
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
- **Fields the plug-in does not use.** `quiet_hours`, `rules[].delay_minutes` and any other unknown field
  are ignored. They never change when or whether a message is sent.
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
- 1–500 rows. `event` is a slug matching `^[a-z][a-z0-9_]{1,39}$` (anything else → 422). `day` within the last 7 days (UTC), not in the future. `sent`, `failed` ≥ 0.
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
- Any `event` that matches the slug pattern is accepted. The event is a label only: it is not checked
  against the tenant's built-in or custom events, because an owner can delete a custom event after the
  plug-in already sent messages for it, and rejecting those rows would drop the whole batch (lost billing).
  Only the slug shape (422 if it does not match) and template ownership (`unknown_template`) are checked.
- 429 (rate limited) or any 5xx / network error: the plug-in keeps its counters, does **not** start the
  throttle, and retries on the next `report_usage` / `reportUsage` call.

## Sending (inside the plug-in)

**Every message is instant and there are no checks.** No opt-out list, no duplicate window, no quiet hours
and no per-rule delay. A call to `track` for an event that has a rule sends that template now. Whether a
customer agreed to be messaged is the client's responsibility, not the plug-in's.

Events: `interested`, `signed_up`, `purchased` plus the aliases in `normalize_event`
(backend/app/services/auto_messages.py), or a **custom event slug**. One enabled rule per event.

Event normalisation in the plug-ins (`normalize_event` / `normalizeEvent`): empty or missing means
`interested`; trim, lowercase, collapse runs of non-alphanumerics to `_`; if that is a built-in alias, return
its event. Otherwise the trimmed, lowercased text itself is accepted if it matches
`^[a-z][a-z0-9_]{1,39}$` (no mapping is invented for slugs, so `my-event` and `my event` are rejected).
Anything else is rejected: `track` raises `ValueError` ("unknown event"; `Error` in Node). Whether a
custom event does anything is the bundle's decision: no rule for it means skip `no_rule`.

`track(event, phone, name=None, extra=None, page_url=None)`:
1. Normalise event and phone (same rules as the backend). Invalid → raise `ValueError`.
2. Get a verified bundle (`LicenseError` / `QuotaExceeded` still raise). No usable bundle because Anril is
   unreachable (`BundleUnavailable` inside the plug-in) → park the send for the retry path, return
   `queued / anril_unreachable`.
3. No rule for the event → skip `no_rule` (the only skip). The template must be one of the bundle's APPROVED
   templates; otherwise the row is failed `template_not_approved`.
4. Insert the send as `queued` (due now) and **deliver it in the same call**: claim `queued → sending`, build the
   Meta components with the same logic as `build_components`; context =
   `{first_name, full_name, page_url, phone, extra}` as in the backend's `send_one`, and POST
   `https://graph.facebook.com/<graph_version>/<phone_number_id>/messages` with the client's own Meta token.
   Count `sent` / `failed` per (day, event, template_id) in the local store. The result is `sent` or `failed`, or `queued` on the retry path below.

The same event for the same phone twice sends twice.

### Retry path (`run_due` / `runDue`)

The queue and the every-minute `run_due` job exist **only** to retry sends that did not reach Meta because
Meta or Anril could not be reached. Nothing waits in the queue on purpose.
- A send goes back to `queued` (due in 1 minute, reason kept) only when it provably never reached Meta: a failed
  TCP connect (Python `ConnectError` / `ConnectTimeout`; Node `ECONNREFUSED`, `ENOTFOUND`, `EAI_AGAIN`,
  `ENETUNREACH`, `EHOSTUNREACH`, `UND_ERR_CONNECT_TIMEOUT`), or Meta HTTP `429` / `503`. `track` returns
  `queued` with that reason. A retry is not counted as sent or failed.
- Every other outcome is final: a Meta rejection (4xx), `500` / `502` / `504`, a read timeout or reset (Meta may
  already have accepted the message, so it is never re-sent), and a crash mid-send (a row stuck in `sending` for
  15 minutes becomes `failed / interrupted`).
- Anril unreachable at `track` time: the row is parked with no template; `run_due` looks the rule up once a bundle
  is available. While Anril is still down `run_due` raises `BundleUnavailable` and the rows stay queued.
- A row still retrying one hour after it was created is failed `gave_up: <reason>` and counted as one `failed`
  (if its template is known). It is never sent late.
- `run_due` returns how many it sent. Old queued rows from a store written before this version are still sent
  by `run_due` when their stored `send_at` passes.

All state (send log, retry queue, counters, bundle cache) lives in the client's local store. Default SQLite
file. An older store file with `opt_outs` or dedupe history opens fine; both are ignored. A custom store must
implement `retry_send(send_id, send_at, reason)` / `retrySend(id, sendAt, reason)`, which moves a row from
`sending` back to `queued`, clears its claim and sets `send_at`; it replaces the old `reschedule_send`, and
`is_opted_out`, `add_opt_out` and `has_recent_send` are gone.

The test cases in `sdk/spec/vectors/*.json` are the source of truth for component building; the
backend, the Python plug-in and the Node plug-in must all pass them.

## Operator API (operator auth, same as other /api/v1/operator routes)

- `GET  /api/v1/operator/clients/{tenant_id}/private-send` →
  ```json
  {"enabled": true, "monthly_cap": 50000, "reply_mode": "aira", "offline_grace_hours": 6,
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

## Client dashboard API (tenant auth, `auto_messages.view`)

- `GET /api/v1/auto-messages/private-send` →
  ```json
  {"enabled": true, "key_prefix": "aps_live_7Hq2", "reply_mode": "aira",
   "days": [{"day": "2026-10-07", "event": "purchased", "template_id": "uuid", "template_name": "loan_ready", "sent": 312, "failed": 3}]}
  ```
  Last 30 days. `enabled: false` → the other fields are null/empty.

## Settings keys (app_settings, per tenant)
`private_send_reply_mode` (default `aira`, was `client`), `private_send_offline_grace_hours` (default `6`),
`private_send_monthly_cap` (default null = no cap).
