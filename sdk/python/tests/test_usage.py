import json

import pytest

from anril_connector import LicenseError
from conftest import LICENSE_KEY, TEMPLATE_ID

ALLOWED_ROW_KEYS = {"day", "event", "template_id", "sent", "failed"}


def _usage_requests(anril):
    return anril.calls("/usage")


def test_usage_body_is_exact_and_has_no_phone_or_name(client, anril, clock):
    client.track("purchased", "9876543210", name="Asha Rao", extra={"city": "Pune"}, page_url="https://x.com/p")
    assert client.report_usage() == 1
    req = _usage_requests(anril)[0]
    assert json.loads(req.content) == {"rows": [
        {"day": "2026-10-07", "event": "purchased", "template_id": TEMPLATE_ID, "sent": 1, "failed": 0},
    ]}
    raw = req.content.decode()
    for secret in ("9876543210", "919876543210", "Asha", "Rao", "Pune", "x.com"):
        assert secret not in raw
    assert req.headers["Authorization"] == f"Bearer {LICENSE_KEY}"
    assert req.headers["X-Anril-Plugin"].startswith("python/")


def test_usage_rows_contain_only_contract_fields(client, anril):
    client.track("purchased", "9876543210", name="Asha")
    client.track("signed_up", "9123456789", name="Ravi")
    client.report_usage()
    body = json.loads(_usage_requests(anril)[0].content)
    assert set(body) == {"rows"}
    assert all(set(r) == ALLOWED_ROW_KEYS for r in body["rows"])


def test_usage_reports_today_and_yesterday_cumulative(client, anril, clock):
    client.track("purchased", "9876543210")
    clock.advance(days=1)
    client.track("purchased", "9123456789")
    client.report_usage()
    rows = json.loads(_usage_requests(anril)[0].content)["rows"]
    assert [(r["day"], r["sent"]) for r in rows] == [("2026-10-07", 1), ("2026-10-08", 1)]
    clock.advance(days=1)
    client.report_usage()
    days = [r["day"] for r in json.loads(_usage_requests(anril)[1].content)["rows"]]
    assert days == ["2026-10-08"]


def test_usage_with_nothing_to_report_makes_no_call(client, anril):
    assert client.report_usage() == 0
    assert _usage_requests(anril) == []


def test_usage_throttled_to_once_per_15_minutes(client, anril, clock):
    client.track("purchased", "9876543210")
    assert client.report_usage() == 1
    clock.advance(minutes=1)
    assert client.report_usage() == 0
    clock.advance(minutes=13)
    assert client.report_usage() == 0
    assert len(_usage_requests(anril)) == 1
    clock.advance(minutes=1, seconds=1)
    assert client.report_usage() == 1
    assert len(_usage_requests(anril)) == 2


def test_usage_force_bypasses_throttle(client, anril, clock):
    client.track("purchased", "9876543210")
    client.report_usage()
    assert client.report_usage(force=True) == 1
    assert len(_usage_requests(anril)) == 2


def test_throttle_survives_a_new_process(private_key, clock, anril, tmp_path):
    """Cron runs a fresh process each minute, so the throttle lives in the store, not in memory."""
    import httpx
    from anril_connector import AnrilPrivateSend
    from conftest import META_TOKEN, PHONE_NUMBER_ID, public_b64

    def make():
        return AnrilPrivateSend(LICENSE_KEY, META_TOKEN, PHONE_NUMBER_ID, public_b64(private_key),
                               store=f"sqlite:///{tmp_path / 'ps.db'}", clock=clock,
                               http=httpx.Client(transport=httpx.MockTransport(anril)))

    first = make()
    first.track("purchased", "9876543210")
    assert first.report_usage() == 1
    first.close()
    clock.advance(minutes=1)
    second = make()
    assert second.report_usage() == 0
    second.close()
    assert len(_usage_requests(anril)) == 1


def test_failed_report_does_not_start_the_throttle(client, anril, clock):
    client.track("purchased", "9876543210")
    anril.usage_status = 500
    assert client.report_usage() == 0
    anril.usage_status = 200
    clock.advance(minutes=1)
    assert client.report_usage() == 1


@pytest.mark.parametrize("status", [401, 403])
def test_usage_license_rejection_raises(client, anril, status):
    client.track("purchased", "9876543210")
    anril.usage_status = status
    with pytest.raises(LicenseError):
        client.report_usage()


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_429_and_5xx_keep_counters_and_do_not_start_throttle(client, anril, clock, status):
    client.track("purchased", "9876543210")
    anril.usage_status = status
    assert client.report_usage() == 0
    anril.usage_status = 200
    assert client.report_usage() == 1  # same instant: no throttle was started
    assert [json.loads(r.content)["rows"][0]["sent"] for r in _usage_requests(anril)] == [1, 1]


def test_422_is_logged_with_code_only_and_does_not_raise(client, anril, clock, caplog):
    import logging
    client.track("purchased", "9876543210", name="Asha Rao")
    anril.usage_status = 422
    anril.usage_json = {"error": "template 'tpl-1' not yours", "code": "unknown_template"}
    with caplog.at_level(logging.WARNING, logger="anril_connector"):
        assert client.report_usage() == 0
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "unknown_template" in messages
    assert TEMPLATE_ID not in messages and "9876543210" not in messages and "not yours" not in messages


def test_422_does_not_wedge_reporting(client, anril, clock):
    """After a 422 the throttle runs (no hammering) and the next window reports normally."""
    client.track("purchased", "9876543210")
    anril.usage_status = 422
    assert client.report_usage() == 0
    clock.advance(minutes=1)
    assert client.report_usage() == 0  # throttled, not stuck in an error loop
    anril.usage_status = 200
    clock.advance(minutes=15)
    assert client.report_usage() == 1


def test_422_on_one_batch_still_sends_the_others(client, anril, monkeypatch):
    import anril_connector.client as mod
    monkeypatch.setattr(mod, "MAX_USAGE_ROWS", 1)
    client.track("purchased", "9876543210")
    client._store.bump_counter("2026-10-07", "signed_up", "tpl-2", 1, 0)
    statuses = iter([422, 200])
    original = anril.__call__

    def route(request):
        if request.url.path.endswith("/usage"):
            anril.usage_status = next(statuses)
        return original(request)

    import httpx
    client._http = httpx.Client(transport=httpx.MockTransport(route))
    assert client.report_usage() == 1
    assert len(_usage_requests(anril)) == 2
