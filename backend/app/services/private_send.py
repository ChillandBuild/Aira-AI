"""Private Send: license keys, signed rule bundles and usage counting.

The client's own server runs an Anril plug-in that downloads signed rules + templates from
here and sends the WhatsApp templates to Meta itself, so Anril never sees a lead's name or
number. Anril holds the license keys and counts usage for billing.
Wire contract: sdk/spec/CONTRACT.md. Tables: migration 218_private_send.sql.
"""
import base64
import binascii
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config_dynamic import get_setting, invalidate_cache
from app.services import entitlements

logger = logging.getLogger(__name__)

FEATURE_KEY = "private_send"
USAGE_METRIC = "private_send_message"
KEY_PREFIX = "aps_live_"
KEY_DISPLAY_LEN = 13
MAX_KEY_LEN = 100
MAX_VERSION_LEN = 64
SIGNING_ENV = "PRIVATE_SEND_SIGNING_KEY"
SIGNING_KEY_ID = "v1"
BUNDLE_TTL = timedelta(minutes=15)
# Blocked from 110% of the cap; integer maths because 100 * 1.1 > 110 in floating point.
BLOCK_NUMERATOR, BLOCK_DENOMINATOR = 11, 10
DEFAULT_GRACE_HOURS = 6
MIN_GRACE_HOURS, MAX_GRACE_HOURS = 1, 72
REPLY_MODES = ("client", "aira")
DASHBOARD_DAYS = 30
MISMATCH_FLOOR = 20
MISMATCH_RATIO = 0.1
# A plug-in sends a few hundred messages a day per template; anything above this in one
# (day, event, template) row is a bug or a leaked key trying to run up the bill.
MAX_DAILY_PER_TEMPLATE = 100_000
# Unknown (never valid) keys are remembered briefly so guessing can't hammer the database.
UNKNOWN_KEY_TTL_SECONDS = 60
UNKNOWN_KEY_CACHE_SIZE = 1024
USAGE_RPC = "record_private_send_usage"
GRAPH_BASE = "https://graph.facebook.com/v21.0"
META_TIMEOUT_SECONDS = 15.0
APPROVED = "APPROVED"

REPLY_MODE_KEY = "private_send_reply_mode"
GRACE_KEY = "private_send_offline_grace_hours"
CAP_KEY = "private_send_monthly_cap"

_RULE_COLUMNS = "id, event, template_id, delay_minutes, variables, button_param, enabled"
_TEMPLATE_COLUMNS = (
    "id, name, language, category, status, body_text, header_text, header_media_type, "
    "header_media_url, buttons"
)
_KEY_COLUMNS = "id, key_prefix, status, created_at, last_seen_at, plugin_version, revoked_at"


class PrivateSendError(Exception):
    """A failure with the HTTP status and machine code the contract specifies."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------- keys

def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """(full key, display prefix, sha256 hex). token_urlsafe(24) is exactly 32 chars."""
    full = KEY_PREFIX + secrets.token_urlsafe(24)
    return full, full[:KEY_DISPLAY_LEN], hash_key(full)


def create_key(db, tenant_id: str) -> dict:
    """Stores only the hash. The full key is returned here once and never again."""
    full, prefix, key_hash = generate_key()
    inserted = (
        db.table("private_send_keys")
        .insert({"tenant_id": tenant_id, "key_prefix": prefix, "key_hash": key_hash})
        .execute()
    ).data or []
    if not inserted:
        raise PrivateSendError(500, "key_not_saved", "Could not save the key")
    return {"id": inserted[0]["id"], "key": full, "key_prefix": prefix}


def revoke_key(db, tenant_id: str, key_id: str) -> None:
    updated = (
        db.table("private_send_keys")
        .update({"status": "revoked", "revoked_at": _iso(datetime.now(timezone.utc))})
        .eq("id", key_id).eq("tenant_id", tenant_id)
        .execute()
    ).data or []
    if not updated:
        raise PrivateSendError(404, "key_not_found", "Key not found")


class _UnknownKeyCache:
    """Hashes that were looked up and not found, for a short time, bounded in size.
    Only misses are cached: a found key (active or revoked) is always re-read, so a
    revoke takes effect at once. A key created within the TTL of its first (failed)
    use can take up to that long to start working."""

    def __init__(self, ttl_seconds: float, max_size: int):
        self._ttl, self._max = ttl_seconds, max_size
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def contains(self, key_hash: str) -> bool:
        now = time.monotonic()
        with self._lock:
            added = self._seen.get(key_hash)
            if added is None:
                return False
            if now - added >= self._ttl:
                del self._seen[key_hash]
                return False
            return True

    def add(self, key_hash: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._seen[key_hash] = now
            self._seen.move_to_end(key_hash)
            while len(self._seen) > self._max:
                self._seen.popitem(last=False)  # oldest first

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


_unknown_keys = _UnknownKeyCache(UNKNOWN_KEY_TTL_SECONDS, UNKNOWN_KEY_CACHE_SIZE)


def reset_unknown_key_cache() -> None:
    _unknown_keys.clear()


def unknown_key_cache_len() -> int:
    return len(_unknown_keys)


def find_key(db, raw_key: str | None) -> dict:
    """Looks the key up by hash. 401 invalid_key / revoked_key."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX) or len(raw_key) > MAX_KEY_LEN:
        raise PrivateSendError(401, "invalid_key", "Invalid license key")
    key_hash = hash_key(raw_key)
    if _unknown_keys.contains(key_hash):
        raise PrivateSendError(401, "invalid_key", "Invalid license key")
    rows = (
        db.table("private_send_keys").select("id, tenant_id, key_prefix, status")
        .eq("key_hash", key_hash).limit(1).execute()
    ).data or []
    if not rows:
        _unknown_keys.add(key_hash)
        raise PrivateSendError(401, "invalid_key", "Invalid license key")
    if rows[0].get("status") != "active":
        raise PrivateSendError(401, "revoked_key", "This license key was revoked")
    return rows[0]


def authorize_key(db, key: dict, plugin_version: str | None = None) -> dict:
    """Records the plug-in's heartbeat, then 403 feature_disabled if the tenant lost the feature."""
    patch = {"last_seen_at": _iso(datetime.now(timezone.utc))}
    if plugin_version:
        patch["plugin_version"] = plugin_version.strip()[:MAX_VERSION_LEN]
    try:
        db.table("private_send_keys").update(patch).eq("id", key["id"]).execute()
    except Exception as e:
        logger.warning("private-send heartbeat failed key_id=%s err=%s", key["id"], e)
    if not is_enabled(db, key["tenant_id"]):
        raise PrivateSendError(403, "feature_disabled", "Private Send is not enabled for this account")
    return key


def verify_key(db, raw_key: str | None, plugin_version: str | None = None) -> dict:
    return authorize_key(db, find_key(db, raw_key), plugin_version)


def is_enabled(db, tenant_id: str) -> bool:
    """On when the operator switched the feature on for the tenant (tenants.enabled_features,
    the existing features endpoint) or the tenant bought it (subscription items)."""
    rows = db.table("tenants").select("enabled_features").eq("id", tenant_id).limit(1).execute().data or []
    if FEATURE_KEY in ((rows[0].get("enabled_features") if rows else None) or []):
        return True
    return entitlements.check_feature_enabled(db, tenant_id, FEATURE_KEY)


# ---------------------------------------------------------------- settings

def get_reply_mode(tenant_id: str) -> str:
    value = get_setting(REPLY_MODE_KEY, tenant_id=tenant_id)
    return value if value in REPLY_MODES else "client"


def get_grace_hours(tenant_id: str) -> int:
    try:
        hours = int(get_setting(GRACE_KEY, tenant_id=tenant_id) or DEFAULT_GRACE_HOURS)
    except ValueError:
        return DEFAULT_GRACE_HOURS
    return max(MIN_GRACE_HOURS, min(MAX_GRACE_HOURS, hours))


def get_monthly_cap(tenant_id: str) -> int | None:
    raw = get_setting(CAP_KEY, tenant_id=tenant_id)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------- usage totals

def _month_start(today: date) -> date:
    return today.replace(day=1)


def _usage_rows(db, tenant_id: str, since: date) -> list[dict]:
    return (
        db.table("private_send_usage")
        .select("day, event, template_id, reported_sent, reported_failed")
        .eq("tenant_id", tenant_id).gte("day", since.isoformat()).execute()
    ).data or []


def _meta_rows(db, tenant_id: str, since: date) -> list[dict]:
    return (
        db.table("private_send_meta_daily").select("day, volume, aira_sent")
        .eq("tenant_id", tenant_id).gte("day", since.isoformat()).execute()
    ).data or []


def _plugin_volume(meta_row: dict) -> int:
    """Meta's volume for the day minus what Anril itself sent = what the plug-in sent."""
    return max(0, (meta_row.get("volume") or 0) - (meta_row.get("aira_sent") or 0))


def month_totals(db, tenant_id: str, today: date | None = None) -> dict:
    """`used` is what the cap is checked against. Once Meta's own count exists for a day it
    is the truth for that day (a leaked key can't inflate it); the plug-in's report only
    counts for days Meta hasn't reconciled yet."""
    since = _month_start(today or _utc_today())
    reported_by_day: dict[str, int] = {}
    for r in _usage_rows(db, tenant_id, since):
        reported_by_day[r["day"]] = reported_by_day.get(r["day"], 0) + (r.get("reported_sent") or 0)
    meta_by_day = {m["day"]: _plugin_volume(m) for m in _meta_rows(db, tenant_id, since)}
    used = sum(
        meta_by_day[day] if day in meta_by_day else reported_by_day.get(day, 0)
        for day in set(reported_by_day) | set(meta_by_day)
    )
    return {
        "reported_sent": sum(reported_by_day.values()),
        "meta_volume": sum(meta_by_day.values()),
        "used": used,
    }


# ---------------------------------------------------------------- bundle

def _enabled_rules(db, tenant_id: str) -> list[dict]:
    return (
        db.table("auto_message_rules").select(_RULE_COLUMNS)
        .eq("tenant_id", tenant_id).eq("enabled", True).execute()
    ).data or []


def _approved_templates(db, tenant_id: str, template_ids: list[str]) -> dict[str, dict]:
    if not template_ids:
        return {}
    rows = (
        db.table("message_templates").select(_TEMPLATE_COLUMNS)
        .eq("tenant_id", tenant_id).in_("id", template_ids).execute()
    ).data or []
    return {t["id"]: t for t in rows if (t.get("status") or "").upper() == APPROVED}


def _public_template(t: dict) -> dict:
    return {
        "id": t["id"], "name": t.get("name"), "language": t.get("language"),
        "category": t.get("category"), "body_text": t.get("body_text") or "",
        "header_text": t.get("header_text"), "header_media_type": t.get("header_media_type"),
        "header_media_url": t.get("header_media_url"), "buttons": t.get("buttons") or [],
    }


def _public_rule(r: dict) -> dict:
    return {
        "id": r["id"], "event": r["event"], "template_id": r["template_id"],
        "delay_minutes": r.get("delay_minutes") or 0, "variables": r.get("variables") or [],
        "button_param": r.get("button_param"), "enabled": True,
    }


def build_bundle(db, tenant_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rules = _enabled_rules(db, tenant_id)
    templates = _approved_templates(db, tenant_id, sorted({r["template_id"] for r in rules}))
    usable = sorted((r for r in rules if r["template_id"] in templates), key=lambda r: r["event"])
    used_ids = {r["template_id"] for r in usable}
    cap = get_monthly_cap(tenant_id)
    used = month_totals(db, tenant_id, now.date())["used"]
    return {
        "version": 1,
        "tenant_id": tenant_id,
        "issued_at": _iso(now),
        "expires_at": _iso(now + BUNDLE_TTL),
        "offline_grace_hours": get_grace_hours(tenant_id),
        "limits": {"monthly_cap": cap, "used": used, "blocked": cap is not None and used * BLOCK_DENOMINATOR >= cap * BLOCK_NUMERATOR},
        "rules": [_public_rule(r) for r in usable],
        "templates": sorted((_public_template(templates[i]) for i in used_ids), key=lambda t: t["name"] or ""),
    }


def _signing_key() -> Ed25519PrivateKey:
    raw = (os.environ.get(SIGNING_ENV) or "").strip()
    try:
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw, validate=True))
    except (ValueError, binascii.Error):
        raise PrivateSendError(503, "signing_not_configured", "Bundle signing is not configured")


def sign_payload(payload: bytes) -> str:
    """base64 Ed25519 signature over the exact payload bytes."""
    return base64.b64encode(_signing_key().sign(payload)).decode("ascii")


def signed_bundle(db, tenant_id: str, now: datetime | None = None) -> dict:
    _signing_key()  # fail fast with 503 before reading the database
    raw = json.dumps(build_bundle(db, tenant_id, now), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "payload": base64.b64encode(raw).decode("ascii"),
        "sig": sign_payload(raw),
        "key_id": SIGNING_KEY_ID,
    }


# ---------------------------------------------------------------- usage reports

def _check_templates_belong_to_tenant(db, tenant_id: str, rows: list[dict]) -> None:
    """422 unknown_template unless every template_id is one of this tenant's templates.
    One IN query for the whole request."""
    wanted = sorted({r["template_id"] for r in rows})
    known = (
        db.table("message_templates").select("id")
        .eq("tenant_id", tenant_id).in_("id", wanted).execute()
    ).data or []
    if {t["id"] for t in known} != set(wanted):
        raise PrivateSendError(422, "unknown_template", "template_id is not one of this account's templates")


def _merge_duplicate_rows(rows: list[dict]) -> list[dict]:
    """One row per (day, event, template): the highest totals, since totals only grow."""
    merged: dict[tuple, dict] = {}
    for r in rows:
        key = (r["day"], r["event"], r["template_id"])
        seen = merged.get(key)
        merged[key] = r if seen is None else {**r, "sent": max(seen["sent"], r["sent"]), "failed": max(seen["failed"], r["failed"])}
    return list(merged.values())


def record_usage(db, tenant_id: str, rows: list[dict]) -> int:
    """Stores the plug-in's cumulative per-day totals and meters only their growth.

    The upsert and the growth maths happen in one Postgres function
    (record_private_send_usage, migration 218): stored totals only ever rise, so a plug-in
    reinstall (counters back to 0) or two concurrent calls can't meter the same messages
    twice. We bill exactly what the function says grew."""
    _check_templates_belong_to_tenant(db, tenant_id, rows)
    payload = _merge_duplicate_rows(rows)
    try:
        delta = db.rpc(USAGE_RPC, {"p_tenant": tenant_id, "p_rows": payload}).execute().data
    except Exception as e:
        logger.error("private-send usage upsert failed tenant=%s err=%s", tenant_id, e)
        raise PrivateSendError(500, "usage_not_saved", "Could not save the usage report")
    delta = int(delta or 0)
    if delta > 0:
        entitlements.meter(db, tenant_id, USAGE_METRIC, delta)
    return len(rows)


# ---------------------------------------------------------------- Meta reconcile

def _meta_error_message(body: dict) -> str:
    error = body.get("error") if isinstance(body, dict) else None
    return (error or {}).get("message") or "Meta rejected the request"


def _json_or_empty(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _sum_volume(body: dict) -> int:
    total = 0
    for block in (body.get("pricing_analytics") or {}).get("data") or []:
        for point in block.get("data_points") or []:
            total += int(point.get("volume") or 0)
    return total


async def fetch_meta_volume(waba_id: str, token: str, day: date) -> int:
    """Meta's own message count for one UTC day on the tenant's WABA. The token goes in a
    header, never in the URL, so it can't reach a request log."""
    start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    fields = (
        f"pricing_analytics.start({start}).end({start + 86400})"
        '.granularity(DAILY).metric_types(["VOLUME"])'
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GRAPH_BASE}/{waba_id}", params={"fields": fields},
            headers={"Authorization": f"Bearer {token}"}, timeout=META_TIMEOUT_SECONDS,
        )
    body = _json_or_empty(r)
    if r.status_code >= 400 or "error" in body:
        raise RuntimeError(f"Meta pricing_analytics failed: {_meta_error_message(body)}")
    return _sum_volume(body)


def count_aira_outbound(db, tenant_id: str, day: date) -> int:
    """Outbound WhatsApp messages Anril itself sent that UTC day."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    res = (
        db.table("messages").select("id", count="exact")
        .eq("tenant_id", tenant_id).eq("direction", "outbound").eq("channel", "whatsapp")
        .gte("created_at", _iso(start)).lt("created_at", _iso(start + timedelta(days=1)))
        .limit(1).execute()
    )
    return res.count or 0


async def reconcile_meta_volume(db, tenant_id: str, day: date) -> dict | None:
    """Stores Meta's count and Anril's own sends for `day`. None when Meta isn't connected."""
    token = get_setting("meta_access_token", tenant_id=tenant_id)
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not token or not waba_id:
        return None
    row = {
        "tenant_id": tenant_id, "day": day.isoformat(),
        "volume": await fetch_meta_volume(waba_id, token, day),
        "aira_sent": count_aira_outbound(db, tenant_id, day),
        "updated_at": _iso(datetime.now(timezone.utc)),
    }
    db.table("private_send_meta_daily").upsert(row, on_conflict="tenant_id,day").execute()
    return row


def enabled_tenant_ids(db) -> list[str]:
    flagged = db.table("tenants").select("id").contains("enabled_features", [FEATURE_KEY]).execute().data or []
    bought = (
        db.table("tenant_subscription_items").select("tenant_id").eq("feature_key", FEATURE_KEY).execute()
    ).data or []
    return sorted({r["id"] for r in flagged} | {r["tenant_id"] for r in bought})


async def process_meta_reconcile(db=None) -> int:
    """Daily job: reconcile yesterday (UTC) for every tenant with Private Send."""
    if db is None:
        from app.db.supabase import get_supabase
        db = get_supabase()
    yesterday = _utc_today() - timedelta(days=1)
    done = 0
    for tenant_id in enabled_tenant_ids(db):
        try:
            if await reconcile_meta_volume(db, tenant_id, yesterday):
                done += 1
        except Exception as e:
            logger.error("private-send meta reconcile failed tenant=%s err=%s", tenant_id, e)
    return done


# ---------------------------------------------------------------- reply mode

async def _call_subscribed_apps(method: str, waba_id: str, token: str) -> None:
    """POST subscribes Anril to the WABA's webhooks, DELETE unsubscribes it. 502 on any Meta failure."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.request(
                method, f"{GRAPH_BASE}/{waba_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {token}"}, timeout=META_TIMEOUT_SECONDS,
            )
    except httpx.HTTPError:
        raise PrivateSendError(502, "meta_unreachable", "Could not reach Meta")
    body = _json_or_empty(r)
    if r.status_code >= 400 or "error" in body or body.get("success") is False:
        raise PrivateSendError(502, "meta_error", _meta_error_message(body))


def _write_setting(db, key: str, value: str, tenant_id: str) -> None:
    """Same upsert as config_dynamic.save_setting, but a failure raises instead of being
    swallowed, so the operator never sees "saved" for a setting that wasn't."""
    try:
        db.table("app_settings").upsert(
            {"key": key, "value": value, "tenant_id": tenant_id, "is_secret": False},
            on_conflict="key,tenant_id",
        ).execute()
    except Exception as e:
        logger.error("private-send setting write failed key=%s tenant=%s err=%s", key, tenant_id, e)
        raise PrivateSendError(500, "setting_not_saved", "Could not save the setting. Nothing was changed; try again.")
    invalidate_cache(key)


async def set_reply_mode(db, tenant_id: str, mode: str) -> None:
    """client = the plug-in's owner handles replies (Anril leaves the WABA's webhooks);
    aira = Anril subscribes and keeps handling replies. Saved only after Meta says yes; if
    the save then fails, the Meta change is rolled back so Meta and Anril agree."""
    token = get_setting("meta_access_token", tenant_id=tenant_id)
    waba_id = get_setting("meta_waba_id", tenant_id=tenant_id)
    if not token or not waba_id:
        raise PrivateSendError(400, "meta_not_configured", "Save the Meta access token and WABA id first")
    previous = get_reply_mode(tenant_id)
    await _call_subscribed_apps("DELETE" if mode == "client" else "POST", waba_id, token)
    try:
        _write_setting(db, REPLY_MODE_KEY, mode, tenant_id)
    except PrivateSendError:
        await _revert_subscription(tenant_id, waba_id, token, previous, mode)
        raise PrivateSendError(
            500, "setting_not_saved",
            "Could not save the reply mode. Meta was switched back; check the setting and try again.",
        )


async def _revert_subscription(tenant_id: str, waba_id: str, token: str, previous: str, attempted: str) -> None:
    if previous == attempted:
        return  # Meta already matches what we have stored
    try:
        await _call_subscribed_apps("DELETE" if previous == "client" else "POST", waba_id, token)
    except PrivateSendError as e:
        logger.error(
            "private-send reply_mode revert FAILED tenant=%s: Meta is now '%s' but the stored mode is '%s' (%s)",
            tenant_id, attempted, previous, e.message,
        )
        return
    logger.error("private-send reply_mode save failed; reverted Meta to '%s' tenant=%s", previous, tenant_id)


# ---------------------------------------------------------------- operator + tenant views

def _day_summaries(usage: list[dict], meta: list[dict]) -> list[dict]:
    reported: dict[str, int] = {}
    for r in usage:
        reported[r["day"]] = reported.get(r["day"], 0) + (r.get("reported_sent") or 0)
    meta_by_day = {m["day"]: _plugin_volume(m) for m in meta}
    return [
        {"day": day, "reported_sent": reported.get(day, 0), "meta_volume": meta_by_day.get(day)}
        for day in sorted(set(reported) | set(meta_by_day), reverse=True)
    ]


def _is_mismatch(days: list[dict]) -> bool:
    """Meta saw clearly more than the plug-in reported, over the days Meta has reported."""
    checked = [d for d in days if d["meta_volume"] is not None]
    reported = sum(d["reported_sent"] for d in checked)
    meta = sum(d["meta_volume"] for d in checked)
    return meta - reported > max(MISMATCH_FLOOR, reported * MISMATCH_RATIO)


def operator_overview(db, tenant_id: str, today: date | None = None) -> dict:
    today = today or _utc_today()
    since = _month_start(today)
    keys = (
        db.table("private_send_keys").select(_KEY_COLUMNS)
        .eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
    ).data or []
    usage, meta = _usage_rows(db, tenant_id, since), _meta_rows(db, tenant_id, since)
    days = _day_summaries(usage, meta)
    return {
        "enabled": is_enabled(db, tenant_id),
        "monthly_cap": get_monthly_cap(tenant_id),
        "reply_mode": get_reply_mode(tenant_id),
        "offline_grace_hours": get_grace_hours(tenant_id),
        "keys": keys,
        "usage": {
            "period": since.strftime("%Y-%m"),
            "reported_sent": sum(d["reported_sent"] for d in days),
            "meta_volume": sum(d["meta_volume"] or 0 for d in days),
            "mismatch": _is_mismatch(days),
            "days": days,
        },
    }


async def update_settings(db, tenant_id: str, changes: dict) -> None:
    """Applies reply_mode / offline_grace_hours / monthly_cap. The Meta call runs first, so
    a Meta failure raises before anything is saved."""
    if "reply_mode" in changes:
        await set_reply_mode(db, tenant_id, changes["reply_mode"])
    if "offline_grace_hours" in changes:
        _write_setting(db, GRACE_KEY, str(changes["offline_grace_hours"]), tenant_id)
    if "monthly_cap" in changes:
        cap = changes["monthly_cap"]
        _write_setting(db, CAP_KEY, "" if cap is None else str(cap), tenant_id)


def _template_names(db, tenant_id: str, template_ids: list[str]) -> dict[str, str]:
    if not template_ids:
        return {}
    rows = (
        db.table("message_templates").select("id, name")
        .eq("tenant_id", tenant_id).in_("id", template_ids).execute()
    ).data or []
    return {t["id"]: t["name"] for t in rows}


def tenant_overview(db, tenant_id: str, today: date | None = None) -> dict:
    """The client dashboard's last 30 days. Counts only: there is no lead data to show."""
    if not is_enabled(db, tenant_id):
        return {"enabled": False, "key_prefix": None, "reply_mode": None, "days": []}
    since = (today or _utc_today()) - timedelta(days=DASHBOARD_DAYS - 1)
    key = (
        db.table("private_send_keys").select("key_prefix")
        .eq("tenant_id", tenant_id).eq("status", "active").order("created_at", desc=True).limit(1).execute()
    ).data or []
    usage = sorted(_usage_rows(db, tenant_id, since), key=lambda r: (r["day"], r["event"]), reverse=True)
    names = _template_names(db, tenant_id, sorted({r["template_id"] for r in usage}))
    return {
        "enabled": True,
        "key_prefix": key[0]["key_prefix"] if key else None,
        "reply_mode": get_reply_mode(tenant_id),
        "days": [
            {
                "day": r["day"], "event": r["event"], "template_id": r["template_id"],
                "template_name": names.get(r["template_id"]),
                "sent": r.get("reported_sent") or 0, "failed": r.get("reported_failed") or 0,
            }
            for r in usage
        ],
    }
