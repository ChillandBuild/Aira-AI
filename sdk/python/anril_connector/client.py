"""AnrilPrivateSend: track events, send via the client's own Meta token, report counts only."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Union
from urllib.parse import urlsplit

import httpx

from . import core
from ._version import __version__
from .bundle import BundleManager, Clock, anril_headers, load_public_keys, raise_if_license_rejected, utcnow
from .errors import BundleUnavailable, QuotaExceeded
from .meta import MetaOutcome, send_template, template_body
from .store import Store, iso, make_store, parse_iso

logger = logging.getLogger("anril_connector")

STUCK_AFTER = timedelta(minutes=15)
RETRY_DELAY = timedelta(minutes=1)
RETRY_WINDOW = timedelta(hours=1)
USAGE_INTERVAL = timedelta(minutes=15)
USAGE_PATH = "/api/v1/private-send/usage"
MAX_USAGE_ROWS = 500
DUE_BATCH = 50
HTTP_TIMEOUT_SECONDS = 20.0
_LAST_USAGE_KEY = "last_usage_report"
_OK, _REJECTED, _RETRY = "ok", "rejected", "retry"
_PHONE_NUMBER_ID_RE = re.compile(r"[0-9]+")
_GRAPH_VERSION_RE = re.compile(r"v[0-9]+\.[0-9]+")
_LOCAL_HTTP_HOSTS = ("localhost", "127.0.0.1")


def _check_base_url(url: str) -> str:
    """https only (the license key rides in the Authorization header); http is allowed for localhost tests."""
    try:
        parts = urlsplit(url if isinstance(url, str) else "")
        host = parts.hostname
    except ValueError:
        raise ValueError("anril_base_url is not a valid URL") from None
    if parts.scheme == "https" and host:
        return url
    if parts.scheme == "http" and host in _LOCAL_HTTP_HOSTS:
        return url
    raise ValueError("anril_base_url must be https:// (http:// is only allowed for localhost and 127.0.0.1)")


@dataclass(frozen=True)
class SendResult:
    status: str  # sent | failed | queued (waiting for a retry) | skipped
    reason: Optional[str] = None
    message_id: Optional[str] = None


class AnrilPrivateSend:
    def __init__(
        self,
        license_key: str,
        meta_token: str,
        phone_number_id: str,
        anril_public_key: Union[str, Sequence[str]],
        store: Union[str, Store] = "sqlite:///anril_connector.db",
        anril_base_url: str = "https://aira-ai-5tfr.onrender.com",
        graph_version: str = "v21.0",
        http: Optional[httpx.Client] = None,
        clock: Clock = utcnow,
    ):
        for label, value in (("license_key", license_key), ("meta_token", meta_token), ("phone_number_id", phone_number_id)):
            if not value:
                raise ValueError(f"{label} is required")
        if not isinstance(phone_number_id, str) or not _PHONE_NUMBER_ID_RE.fullmatch(phone_number_id):
            raise ValueError("phone_number_id must contain digits only")
        if not isinstance(graph_version, str) or not _GRAPH_VERSION_RE.fullmatch(graph_version):
            raise ValueError("graph_version must look like v21.0")
        self._license_key = license_key
        self._meta_token = meta_token
        self._phone_number_id = phone_number_id
        self._base_url = _check_base_url(anril_base_url).rstrip("/")
        self._graph_version = graph_version
        self._clock = clock
        self._store = make_store(store)
        self._http = http or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
        self._bundles = BundleManager(
            license_key, load_public_keys(anril_public_key), self._base_url, self._store, self._http, clock)

    def __repr__(self) -> str:  # never show the license key or Meta token
        return f"AnrilPrivateSend(phone_number_id={self._phone_number_id!r}, plugin=python/{__version__})"

    # ------------------------------------------------------------ public API

    def track(
        self, event: str, phone: str, name: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None, page_url: Optional[str] = None,
    ) -> SendResult:
        """Send the matching template now. No checks: no opt-out list, no duplicate window, no quiet hours,
        no delay. The row is written 'queued' and delivered in the same call; it stays queued (for run_due)
        only when Meta or Anril could not be reached."""
        norm_event = core.normalize_event(event)
        if not norm_event:
            raise ValueError(f"unknown event {event!r}")
        norm_phone = core.normalize_phone(phone)
        if not norm_phone:
            raise ValueError("missing or invalid phone")
        now = self._clock()
        try:
            bundle = self._bundles.current()
        except BundleUnavailable:
            return self._park_for_retry(norm_phone, norm_event, name, extra, page_url, now)
        if bundle.blocked:
            raise QuotaExceeded("monthly message cap reached")
        rule = bundle.rule_for(norm_event)
        if not rule:
            return self._skip(norm_phone, norm_event, None, "no_rule", now)
        row = self._queue_row(norm_phone, norm_event, rule["template_id"], name, extra, page_url, now, now)
        send_id = self._store.insert_send(row)
        return self._deliver({**row, "id": send_id}, bundle)

    def run_due(self) -> int:
        """The retry path: send queued rows left by an unreachable Meta or Anril. Returns how many were sent.
        A row still failing an hour after it was created is failed for good."""
        now = self._clock()
        self._store.fail_stuck(now - STUCK_AFTER)
        due = self._store.due_sends(now, DUE_BATCH)
        live = [row for row in due if not self._give_up_if_stale(row, now)]
        if not live:
            return 0
        bundle = self._bundles.current()
        if bundle.blocked:
            raise QuotaExceeded("monthly message cap reached")
        sent = 0
        for row in live:
            try:
                if self._deliver(row, bundle).status == "sent":
                    sent += 1
            except Exception as exc:  # one bad row must not stop the batch; it is failed as 'interrupted' later
                logger.error("anril run_due: unexpected error on send %s: %s", row.get("id"), type(exc).__name__)
        return sent

    def report_usage(self, force: bool = False) -> int:
        """POST cumulative counters for today and yesterday (counts only, never a phone or name).
        Throttled to once per 15 minutes unless force=True. Returns rows reported (0 if throttled,
        nothing to report, or Anril unreachable/rate-limited -- counters are cumulative, so the next call
        catches up). A 422 (e.g. unknown_template) is logged and skipped so a bad row never blocks reporting."""
        now = self._clock()
        if not force and self._usage_throttled(now):
            return 0
        rows = self._usage_rows(now)
        if not rows:
            return 0
        accepted = 0
        for start in range(0, len(rows), MAX_USAGE_ROWS):
            batch = rows[start:start + MAX_USAGE_ROWS]
            outcome = self._post_usage(batch)
            if outcome == _RETRY:
                return 0  # 429 / 5xx / network: keep the counters, no throttle, retry on the next call
            if outcome == _OK:
                accepted += len(batch)
        self._store.set_meta(_LAST_USAGE_KEY, iso(now))
        return accepted

    def close(self) -> None:
        self._store.close()

    # ------------------------------------------------------------ sending

    def _skip(self, phone: str, event: str, template_id: Optional[str], reason: str, now: datetime) -> SendResult:
        self._store.insert_send({
            "phone": phone, "event": event, "template_id": template_id, "status": "skipped",
            "reason": reason, "created_at": iso(now),
        })
        return SendResult("skipped", reason)

    @staticmethod
    def _queue_row(
        phone: str, event: str, template_id: Optional[str], name: Optional[str], extra: Optional[Dict[str, Any]],
        page_url: Optional[str], send_at: datetime, now: datetime,
    ) -> Dict[str, Any]:
        stored_extra = dict((core.build_context(name, phone, extra, page_url))["extra"])
        return {
            "phone": phone, "event": event, "template_id": template_id, "status": "queued",
            "send_at": iso(send_at), "created_at": iso(now), "name": (name or "").strip() or None, "extra": stored_extra,
        }

    def _park_for_retry(
        self, phone: str, event: str, name: Optional[str], extra: Optional[Dict[str, Any]],
        page_url: Optional[str], now: datetime,
    ) -> SendResult:
        """Anril is unreachable and no verified bundle is usable, so the rule is unknown: queue the send;
        run_due looks the rule up once a bundle is available."""
        self._store.insert_send(self._queue_row(phone, event, None, name, extra, page_url, now + RETRY_DELAY, now))
        return SendResult("queued", "anril_unreachable")

    def _is_stale(self, row: Dict[str, Any], now: datetime) -> bool:
        return now - parse_iso(row["created_at"]) >= RETRY_WINDOW

    def _give_up_if_stale(self, row: Dict[str, Any], now: datetime) -> bool:
        """Fail a queued row that has been retrying for RETRY_WINDOW. True when it was failed."""
        if not self._is_stale(row, now):
            return False
        self._count_failed(row)
        self._finish(row, "failed", "gave_up: " + (row.get("reason") or "anril_unreachable"))
        return True

    def _count_failed(self, row: Dict[str, Any]) -> None:
        if row.get("template_id"):  # a row parked before any rule was known has no template to count against
            self._store.bump_counter(self._clock().strftime("%Y-%m-%d"), row["event"], row["template_id"], 0, 1)

    def _finish(self, row: Dict[str, Any], status: str, reason: Optional[str] = None) -> SendResult:
        sent_at = self._clock() if status == "sent" else None
        self._store.finish_send(row["id"], status, reason, sent_at)
        return SendResult(status, reason)

    def _deliver(self, row: Dict[str, Any], bundle: Any) -> SendResult:
        """Claim queued -> sending (so two runs never double-send), then send once. Only a send that
        provably never reached Meta (connection failure, 429, 503) goes back to 'queued' for run_due."""
        if not self._store.claim_send(row["id"], self._clock()):
            return SendResult("skipped", "already_claimed")
        rule = bundle.rule_for(row["event"])
        if not rule:
            return self._finish(row, "skipped", "rule_removed_or_off")
        template = bundle.template(rule["template_id"])
        if not template:
            return self._finish(row, "failed", "template_not_approved")
        ctx = core.build_context(row.get("name"), row["phone"], row.get("extra"), None)
        body = template_body(
            row["phone"], template["name"], template.get("language") or "en",
            core.build_components(template, rule, ctx))
        outcome = send_template(self._http, self._graph_version, self._phone_number_id, self._meta_token, body)
        if outcome.retryable and not self._is_stale(row, self._clock()):
            return self._requeue(row, outcome)
        day = self._clock().strftime("%Y-%m-%d")
        counts = (1, 0) if outcome.ok else (0, 1)
        self._store.bump_counter(day, row["event"], rule["template_id"], *counts)
        reason = outcome.reason if outcome.ok or not outcome.retryable else "gave_up: " + (outcome.reason or "")
        result = self._finish(row, "sent" if outcome.ok else "failed", reason)
        return SendResult(result.status, result.reason, outcome.message_id)

    def _requeue(self, row: Dict[str, Any], outcome: MetaOutcome) -> SendResult:
        self._store.retry_send(row["id"], self._clock() + RETRY_DELAY, outcome.reason)
        return SendResult("queued", outcome.reason)

    # ------------------------------------------------------------ usage

    def _usage_throttled(self, now: datetime) -> bool:
        last = self._store.get_meta(_LAST_USAGE_KEY)
        if not last:
            return False
        try:
            return now - parse_iso(last) < USAGE_INTERVAL
        except ValueError:
            return False

    def _usage_rows(self, now: datetime) -> List[Dict[str, Any]]:
        days = [now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")]
        return [
            {"day": r["day"], "event": r["event"], "template_id": r["template_id"], "sent": int(r["sent"]), "failed": int(r["failed"])}
            for r in self._store.counters(days)
        ]

    def _post_usage(self, rows: List[Dict[str, Any]]) -> str:
        try:
            resp = self._http.post(self._base_url + USAGE_PATH, json={"rows": rows}, headers=anril_headers(self._license_key))
        except httpx.HTTPError as exc:
            logger.warning("anril usage report failed: %s", type(exc).__name__)
            return _RETRY
        raise_if_license_rejected(resp)
        if resp.status_code == 200:
            return _OK
        if resp.status_code == 422:
            # a bad row (e.g. unknown_template) must not wedge reporting forever: log the code only, move on
            logger.warning("anril usage report rejected: %s", _error_code(resp))
            return _REJECTED
        logger.warning("anril usage report failed: HTTP %s", resp.status_code)
        return _RETRY


def _error_code(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        code = body.get("code") if isinstance(body, dict) else None
    except ValueError:
        code = None
    return code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code) else "HTTP 422"
