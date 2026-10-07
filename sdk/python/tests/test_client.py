import json

import pytest

from aira_private_send import core
from conftest import META_TOKEN, PHONE_NUMBER_ID, SLOW_TEMPLATE_ID, TEMPLATE_ID


def _meta_body(request):
    return json.loads(request.content)


def test_immediate_send_posts_exact_meta_body(client, aira):
    result = client.track("Purchase", "98765 43210", name="Asha Rao")
    assert (result.status, result.message_id) == ("sent", "wamid.ABC")
    req = aira.meta_calls()[0]
    assert str(req.url) == f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    assert req.headers["Authorization"] == f"Bearer {META_TOKEN}"
    assert _meta_body(req) == {
        "messaging_product": "whatsapp", "to": "+919876543210", "type": "template",
        "template": {
            "name": "loan_ready", "language": {"code": "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": "Asha"}]}],
        },
    }


def test_meta_body_matches_backend_send_template_message_shape(client, aira):
    """Key order and nesting identical to backend/app/services/meta_cloud.py::send_template_message."""
    client.track("purchased", "9876543210")
    body = _meta_body(aira.meta_calls()[0])
    assert list(body) == ["messaging_product", "to", "type", "template"]
    assert list(body["template"]) == ["name", "language", "components"]


def test_meta_token_never_goes_to_aira(client, aira):
    client.track("purchased", "9876543210")
    client.report_usage(force=True)
    for req in aira.requests:
        if req.url.host != "graph.facebook.com":
            assert META_TOKEN not in str(req.headers) + req.content.decode()


def test_components_use_core_with_backend_style_ctx(client, aira):
    client.track("purchased", "9876543210", name="  Asha   Rao ", extra={"Plan": "Gold"}, page_url="https://x.com/p")
    expected_ctx = core.build_context("Asha   Rao", "+919876543210", {"plan": "Gold"}, "https://x.com/p")
    assert expected_ctx["first_name"] == "Asha"
    assert expected_ctx["page_url"] == "https://x.com/p"
    assert expected_ctx["extra"] == {"plan": "Gold", "page_url": "https://x.com/p"}
    assert _meta_body(aira.meta_calls()[0])["template"]["components"][0]["parameters"][0]["text"] == "Asha"


def test_invalid_event_and_phone_raise_value_error(client):
    with pytest.raises(ValueError):
        client.track("refund", "9876543210")
    with pytest.raises(ValueError):
        client.track("purchased", "abc")


def test_no_rule_is_skipped(client):
    result = client.track("interested", "9876543210")
    assert (result.status, result.reason) == ("skipped", "no_rule")


def test_duplicate_within_24h_skipped_then_allowed_after(client, aira, clock):
    assert client.track("purchased", "9876543210").status == "sent"
    again = client.track("purchased", "+91 98765 43210")
    assert (again.status, again.reason) == ("skipped", "duplicate")
    assert len(aira.meta_calls()) == 1
    clock.advance(hours=24, minutes=1)
    assert client.track("purchased", "9876543210").status == "sent"
    assert len(aira.meta_calls()) == 2


def test_duplicate_is_per_event_and_per_phone(client, aira):
    client.track("purchased", "9876543210")
    assert client.track("purchased", "9123456789").status == "sent"
    assert client.track("signed_up", "9876543210").status == "queued"


def test_failed_send_does_not_block_a_retry_of_the_event(client, aira):
    aira.meta_status = 400
    aira.meta_json = {"error": {"code": 131026, "message": "Message undeliverable"}}
    result = client.track("purchased", "9876543210")
    assert (result.status, result.reason) == ("failed", "meta_131026: Message undeliverable")
    aira.meta_status, aira.meta_json = 200, {"messages": [{"id": "wamid.2"}]}
    assert client.track("purchased", "9876543210").status == "sent"


def test_opt_out_skips_and_does_not_call_meta(client, aira):
    client.opt_out("98765 43210")
    result = client.track("purchased", "+919876543210")
    assert (result.status, result.reason) == ("skipped", "opted_out")
    assert aira.meta_calls() == []
    assert aira.calls("/bundle") == []


def test_opt_out_invalid_phone_raises(client):
    with pytest.raises(ValueError):
        client.opt_out("nope")


def test_delayed_rule_is_queued_and_run_due_sends_after_delay(client, aira, clock):
    result = client.track("signed_up", "9876543210", name="Ravi")
    assert result.status == "queued"
    assert aira.meta_calls() == []
    clock.advance(minutes=29)
    assert client.run_due() == 0
    clock.advance(minutes=2)
    assert client.run_due() == 1
    body = _meta_body(aira.meta_calls()[0])
    assert body["template"]["name"] == "welcome"
    assert body["template"]["language"] == {"code": "en_US"}
    assert body["template"]["components"][0]["parameters"][0]["text"] == "Ravi"
    assert client.run_due() == 0  # already sent: never twice


def test_run_due_skips_when_opted_out_after_queueing(client, aira, clock):
    client.track("signed_up", "9876543210")
    client.opt_out("9876543210")
    clock.advance(minutes=31)
    assert client.run_due() == 0
    assert aira.meta_calls() == []


def test_run_due_skips_when_rule_removed(client, aira, clock):
    client.track("signed_up", "9876543210")
    clock.advance(minutes=31)
    aira.payload_overrides = {"rules": []}
    assert client.run_due() == 0
    assert aira.meta_calls() == []


def test_claim_prevents_double_send(client, aira, clock):
    client.track("signed_up", "9876543210")
    clock.advance(minutes=31)
    row = client._store.due_sends(clock.now, 10)[0]
    assert client._store.claim_send(row["id"], clock.now) is True
    assert client._store.claim_send(row["id"], clock.now) is False
    assert client.run_due() == 0  # claimed row is not queued any more
    assert aira.meta_calls() == []


def test_stuck_sending_is_failed_interrupted_and_never_retried(client, aira, clock):
    client.track("signed_up", "9876543210")
    clock.advance(minutes=31)
    row = client._store.due_sends(clock.now, 10)[0]
    client._store.claim_send(row["id"], clock.now)
    clock.advance(minutes=16)
    assert client.run_due() == 0
    status = client._store._exec("SELECT status, reason FROM sends WHERE id = ?", row["id"])[0][0]
    assert (status["status"], status["reason"]) == ("failed", "interrupted")
    assert aira.meta_calls() == []


def test_sending_not_yet_stuck_is_left_alone(client, clock):
    client.track("signed_up", "9876543210")
    clock.advance(minutes=31)
    row = client._store.due_sends(clock.now, 10)[0]
    client._store.claim_send(row["id"], clock.now)
    clock.advance(minutes=10)
    client.run_due()
    status = client._store._exec("SELECT status FROM sends WHERE id = ?", row["id"])[0][0]["status"]
    assert status == "sending"


def test_counters_count_sent_and_failed_per_day_event_template(client, aira, clock):
    client.track("purchased", "9876543210")
    aira.meta_status, aira.meta_json = 500, {}
    client.track("purchased", "9123456789")
    rows = client._store.counters(["2026-10-07"])
    assert rows == [{"day": "2026-10-07", "event": "purchased", "template_id": TEMPLATE_ID, "sent": 1, "failed": 1}]


def test_repr_hides_secrets(client):
    text = repr(client)
    assert META_TOKEN not in text and "aps_live_" not in text


# ---------------------------------------------------------------- constructor validation

def _make(**overrides):
    from aira_private_send import AiraPrivateSend
    args = dict(license_key="aps_live_x", meta_token="t", phone_number_id="123", aira_public_key="A" * 43 + "=",
                store="sqlite:///:memory:")
    return AiraPrivateSend(**{**args, **overrides})


@pytest.mark.parametrize("url", [
    "http://aira.example.com", "ftp://aira.example.com", "aira.example.com", "https://", "",
    "http://localhost.evil.com", "http://localhost@evil.com", "http://127.0.0.1.evil.com",
])
def test_non_https_base_url_rejected(private_key, url):
    from conftest import public_b64
    with pytest.raises(ValueError, match="https"):
        _make(aira_public_key=public_b64(private_key), aira_base_url=url)


@pytest.mark.parametrize("url", [
    "https://aira.example.com", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost",
])
def test_https_and_local_http_base_url_accepted(private_key, url):
    from conftest import public_b64
    _make(aira_public_key=public_b64(private_key), aira_base_url=url).close()


@pytest.mark.parametrize("value", ["", "12a", "../x", "123/messages", "12 3", "123\n", "١٢٣", "v21.0"])
def test_bad_phone_number_id_rejected(private_key, value):
    from conftest import public_b64
    with pytest.raises(ValueError):
        _make(aira_public_key=public_b64(private_key), phone_number_id=value)


@pytest.mark.parametrize("value", ["21.0", "v21", "v21.0.1", "v21.0/../x", "V21.0", "v21.0\n", "", "vx.y"])
def test_bad_graph_version_rejected(private_key, value):
    from conftest import public_b64
    with pytest.raises(ValueError):
        _make(aira_public_key=public_b64(private_key), graph_version=value)


def test_good_graph_version_accepted(private_key):
    from conftest import public_b64
    _make(aira_public_key=public_b64(private_key), graph_version="v22.1").close()
