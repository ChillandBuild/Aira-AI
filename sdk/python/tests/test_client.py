import json

import httpx
import pytest

from anril_connector import BundleUnavailable, core
from conftest import META_TOKEN, PHONE_NUMBER_ID, SLOW_TEMPLATE_ID, TEMPLATE_ID


def _meta_body(request):
    return json.loads(request.content)


def test_immediate_send_posts_exact_meta_body(client, anril):
    result = client.track("Purchase", "98765 43210", name="Asha Rao")
    assert (result.status, result.message_id) == ("sent", "wamid.ABC")
    req = anril.meta_calls()[0]
    assert str(req.url) == f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    assert req.headers["Authorization"] == f"Bearer {META_TOKEN}"
    assert _meta_body(req) == {
        "messaging_product": "whatsapp", "to": "+919876543210", "type": "template",
        "template": {
            "name": "loan_ready", "language": {"code": "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": "Asha"}]}],
        },
    }


def test_meta_body_matches_backend_send_template_message_shape(client, anril):
    """Key order and nesting identical to backend/app/services/meta_cloud.py::send_template_message."""
    client.track("purchased", "9876543210")
    body = _meta_body(anril.meta_calls()[0])
    assert list(body) == ["messaging_product", "to", "type", "template"]
    assert list(body["template"]) == ["name", "language", "components"]


def test_meta_token_never_goes_to_anril(client, anril):
    client.track("purchased", "9876543210")
    client.report_usage(force=True)
    for req in anril.requests:
        if req.url.host != "graph.facebook.com":
            assert META_TOKEN not in str(req.headers) + req.content.decode()


def test_components_use_core_with_backend_style_ctx(client, anril):
    client.track("purchased", "9876543210", name="  Asha   Rao ", extra={"Plan": "Gold"}, page_url="https://x.com/p")
    expected_ctx = core.build_context("Asha   Rao", "+919876543210", {"plan": "Gold"}, "https://x.com/p")
    assert expected_ctx["first_name"] == "Asha"
    assert expected_ctx["page_url"] == "https://x.com/p"
    assert expected_ctx["extra"] == {"plan": "Gold", "page_url": "https://x.com/p"}
    assert _meta_body(anril.meta_calls()[0])["template"]["components"][0]["parameters"][0]["text"] == "Asha"


def test_invalid_event_and_phone_raise_value_error(client):
    with pytest.raises(ValueError):
        client.track("refund!", "9876543210")
    with pytest.raises(ValueError):
        client.track("purchased", "abc")


def test_no_rule_is_skipped(client):
    result = client.track("interested", "9876543210")
    assert (result.status, result.reason) == ("skipped", "no_rule")


def test_same_event_twice_sends_twice(client, anril, clock):
    first = client.track("purchased", "9876543210")
    second = client.track("purchased", "+91 98765 43210")
    assert (first.status, second.status) == ("sent", "sent")
    assert len(anril.meta_calls()) == 2
    clock.advance(hours=24, minutes=1)
    assert client.track("purchased", "9876543210").status == "sent"
    assert len(anril.meta_calls()) == 3


def test_every_event_sends_immediately_with_no_wait(client, anril):
    """signed_up used to be a 30-minute delayed rule; there is no delay any more."""
    result = client.track("signed_up", "9876543210", name="Ravi")
    assert result.status == "sent"
    body = _meta_body(anril.meta_calls()[0])
    assert body["template"]["name"] == "welcome"
    assert body["template"]["language"] == {"code": "en_US"}
    assert body["template"]["components"][0]["parameters"][0]["text"] == "Ravi"


def test_matched_event_goes_out_without_run_due(client, anril):
    assert client.track("purchased", "9876543210").status == "sent"
    assert len(anril.meta_calls()) == 1  # on the wire before any run_due call
    assert client.run_due() == 0  # nothing left to retry
    assert len(anril.meta_calls()) == 1


def test_failed_send_does_not_block_a_retry_of_the_event(client, anril):
    anril.meta_status = 400
    anril.meta_json = {"error": {"code": 131026, "message": "Message undeliverable"}}
    result = client.track("purchased", "9876543210")
    assert (result.status, result.reason) == ("failed", "meta_131026: Message undeliverable")
    anril.meta_status, anril.meta_json = 200, {"messages": [{"id": "wamid.2"}]}
    assert client.track("purchased", "9876543210").status == "sent"
    assert client.run_due() == 0  # a Meta rejection is final, never retried


def test_opt_out_api_is_gone(client):
    assert not hasattr(client, "opt_out")


# ---------------------------------------------------------------- retry path (Meta / Anril unreachable)

def _row_status(client, send_id=None):
    rows = client._store._exec("SELECT id, status, reason, template_id FROM sends ORDER BY created_at")[0]
    return rows[-1] if send_id is None else next(r for r in rows if r["id"] == send_id)


def test_meta_unreachable_queues_for_retry_and_run_due_sends(client, anril, clock):
    anril.meta_network_error = httpx.ConnectError
    result = client.track("purchased", "9876543210", name="Asha")
    assert (result.status, result.reason) == ("queued", "network_error: ConnectError")
    assert client.report_usage(force=True) == 0  # a queued retry counts as neither sent nor failed
    anril.meta_network_error = None
    assert client.run_due() == 0  # retry is not due for a minute
    clock.advance(minutes=1)
    assert client.run_due() == 1
    assert _row_status(client)["status"] == "sent"
    assert client.run_due() == 0  # never twice
    sent_bodies = [_meta_body(r) for r in anril.meta_calls()]
    assert sent_bodies[-1]["template"]["components"][0]["parameters"][0]["text"] == "Asha"


@pytest.mark.parametrize("status", [429, 503])
def test_meta_429_and_503_are_retried(client, anril, clock, status):
    anril.meta_status, anril.meta_json = status, {}
    assert client.track("purchased", "9876543210").status == "queued"
    anril.meta_status, anril.meta_json = 200, {"messages": [{"id": "wamid.R"}]}
    clock.advance(minutes=1)
    assert client.run_due() == 1


@pytest.mark.parametrize("status", [400, 500, 502, 504])
def test_other_meta_errors_are_final(client, anril, clock, status):
    anril.meta_status, anril.meta_json = status, {}
    assert client.track("purchased", "9876543210").status == "failed"
    clock.advance(minutes=5)
    assert client.run_due() == 0
    assert len(anril.meta_calls()) == 1


def test_read_timeout_is_not_retried_because_meta_may_have_delivered(client, anril, clock):
    anril.meta_network_error = httpx.ReadTimeout
    assert client.track("purchased", "9876543210").status == "failed"
    clock.advance(minutes=5)
    anril.meta_network_error = None
    assert client.run_due() == 0
    assert len(anril.meta_calls()) == 1


def test_retry_gives_up_after_an_hour_and_counts_one_failure(client, anril, clock):
    anril.meta_network_error = httpx.ConnectError
    assert client.track("purchased", "9876543210").status == "queued"
    for _ in range(59):
        clock.advance(minutes=1)
        assert client.run_due() == 0
        assert _row_status(client)["status"] == "queued"
    clock.advance(minutes=1)
    assert client.run_due() == 0
    row = _row_status(client)
    assert (row["status"], row["reason"]) == ("failed", "gave_up: network_error: ConnectError")
    assert client._store.counters(["2026-10-07"]) == [
        {"day": "2026-10-07", "event": "purchased", "template_id": TEMPLATE_ID, "sent": 0, "failed": 1}]
    clock.advance(minutes=5)
    anril.meta_network_error = None
    assert client.run_due() == 0  # a given-up row is not sent late


def test_anril_unreachable_queues_and_run_due_sends_once_a_bundle_is_back(client, anril, clock):
    anril.bundle_network_error = True
    result = client.track("purchased", "9876543210", name="Asha")
    assert (result.status, result.reason) == ("queued", "anril_unreachable")
    assert anril.meta_calls() == []
    clock.advance(minutes=1)
    with pytest.raises(BundleUnavailable):
        client.run_due()  # still down: the row stays queued
    assert _row_status(client)["status"] == "queued"
    anril.bundle_network_error = False
    assert client.run_due() == 1
    body = _meta_body(anril.meta_calls()[0])
    assert body["template"]["name"] == "loan_ready"
    assert body["template"]["components"][0]["parameters"][0]["text"] == "Asha"


def test_parked_send_gives_up_after_an_hour_even_while_anril_is_down(client, anril, clock):
    anril.bundle_network_error = True
    client.track("purchased", "9876543210")
    clock.advance(hours=1, minutes=1)
    assert client.run_due() == 0  # no bundle needed to give up
    row = _row_status(client)
    assert (row["status"], row["reason"]) == ("failed", "gave_up: anril_unreachable")
    assert anril.meta_calls() == []


def test_run_due_skips_when_rule_removed(client, anril, clock):
    anril.meta_network_error = httpx.ConnectError
    client.track("purchased", "9876543210")
    anril.meta_network_error = None
    clock.advance(minutes=6)  # bundle cache (5 min) expired, so run_due re-fetches
    anril.payload_overrides = {"rules": []}
    assert client.run_due() == 0
    assert anril.meta_calls()[-1].url.path.endswith("/messages") and len(anril.meta_calls()) == 1
    assert _row_status(client)["reason"] == "rule_removed_or_off"


def _parked_row(client, anril, clock):
    anril.meta_network_error = httpx.ConnectError
    client.track("signed_up", "9876543210")
    anril.meta_network_error = None
    clock.advance(minutes=1)
    return client._store.due_sends(clock.now, 10)[0]


def test_claim_prevents_double_send(client, anril, clock):
    row = _parked_row(client, anril, clock)
    sent_before = len(anril.meta_calls())
    assert client._store.claim_send(row["id"], clock.now) is True
    assert client._store.claim_send(row["id"], clock.now) is False
    assert client.run_due() == 0  # claimed row is not queued any more
    assert len(anril.meta_calls()) == sent_before


def test_stuck_sending_is_failed_interrupted_and_never_retried(client, anril, clock):
    row = _parked_row(client, anril, clock)
    sent_before = len(anril.meta_calls())
    client._store.claim_send(row["id"], clock.now)
    clock.advance(minutes=16)
    assert client.run_due() == 0
    status = client._store._exec("SELECT status, reason FROM sends WHERE id = ?", row["id"])[0][0]
    assert (status["status"], status["reason"]) == ("failed", "interrupted")
    assert len(anril.meta_calls()) == sent_before


def test_sending_not_yet_stuck_is_left_alone(client, anril, clock):
    row = _parked_row(client, anril, clock)
    client._store.claim_send(row["id"], clock.now)
    clock.advance(minutes=10)
    client.run_due()
    status = client._store._exec("SELECT status FROM sends WHERE id = ?", row["id"])[0][0]["status"]
    assert status == "sending"


def test_counters_count_sent_and_failed_per_day_event_template(client, anril, clock):
    client.track("purchased", "9876543210")
    anril.meta_status, anril.meta_json = 500, {}
    client.track("purchased", "9123456789")
    rows = client._store.counters(["2026-10-07"])
    assert rows == [{"day": "2026-10-07", "event": "purchased", "template_id": TEMPLATE_ID, "sent": 1, "failed": 1}]


def test_repr_hides_secrets(client):
    text = repr(client)
    assert META_TOKEN not in text and "aps_live_" not in text


# ---------------------------------------------------------------- constructor validation

def _make(**overrides):
    from anril_connector import AnrilPrivateSend
    args = dict(license_key="aps_live_x", meta_token="t", phone_number_id="123", anril_public_key="A" * 43 + "=",
                store="sqlite:///:memory:")
    return AnrilPrivateSend(**{**args, **overrides})


@pytest.mark.parametrize("url", [
    "http://anril.example.com", "ftp://anril.example.com", "anril.example.com", "https://", "",
    "http://localhost.evil.com", "http://localhost@evil.com", "http://127.0.0.1.evil.com",
])
def test_non_https_base_url_rejected(private_key, url):
    from conftest import public_b64
    with pytest.raises(ValueError, match="https"):
        _make(anril_public_key=public_b64(private_key), anril_base_url=url)


@pytest.mark.parametrize("url", [
    "https://anril.example.com", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost",
])
def test_https_and_local_http_base_url_accepted(private_key, url):
    from conftest import public_b64
    _make(anril_public_key=public_b64(private_key), anril_base_url=url).close()


@pytest.mark.parametrize("value", ["", "12a", "../x", "123/messages", "12 3", "123\n", "١٢٣", "v21.0"])
def test_bad_phone_number_id_rejected(private_key, value):
    from conftest import public_b64
    with pytest.raises(ValueError):
        _make(anril_public_key=public_b64(private_key), phone_number_id=value)


@pytest.mark.parametrize("value", ["21.0", "v21", "v21.0.1", "v21.0/../x", "V21.0", "v21.0\n", "", "vx.y"])
def test_bad_graph_version_rejected(private_key, value):
    from conftest import public_b64
    with pytest.raises(ValueError):
        _make(anril_public_key=public_b64(private_key), graph_version=value)


def test_good_graph_version_accepted(private_key):
    from conftest import public_b64
    _make(anril_public_key=public_b64(private_key), graph_version="v22.1").close()
