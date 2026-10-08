"""Custom event slugs: any ^[a-z][a-z0-9_]{1,39}$ is accepted; the bundle decides whether a rule exists."""
import pytest

from anril_connector import core
from conftest import TEMPLATE_ID, default_payload


@pytest.mark.parametrize("raw,expected", [
    ("refund", "refund"),
    ("Refund", "refund"),
    ("  KYC_done  ", "kyc_done"),
    ("cart_abandoned_2", "cart_abandoned_2"),
    ("ab", "ab"),
    ("a" + "b" * 39, "a" + "b" * 39),
])
def test_custom_slugs_are_accepted_after_trim_and_lowercase(raw, expected):
    assert core.normalize_event(raw) == expected


@pytest.mark.parametrize("raw", [
    "a", "1abc", "_abc", "abc-def", "abc def", "refund!", "a" + "b" * 40, "é", "ab\ncd", "  ", "-", "__",
])
def test_junk_is_rejected(raw):
    assert core.normalize_event(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("order", "purchased"), ("Sign Up", "signed_up"), ("ORDER-PLACED", "purchased"), ("lead", "interested"),
    (None, "interested"), ("", "interested"),
])
def test_aliases_still_win_and_normalize_as_before(raw, expected):
    assert core.normalize_event(raw) == expected


def test_track_custom_event_without_rule_is_skipped_no_rule(client):
    result = client.track("refund", "9876543210")
    assert (result.status, result.reason) == ("skipped", "no_rule")


def test_track_custom_event_with_rule_sends(client, anril):
    rules = default_payload()["rules"] + [
        {"id": "r9", "event": "refund", "template_id": TEMPLATE_ID,
         "variables": [], "button_param": None, "enabled": True}]
    anril.payload_overrides = {"rules": rules}
    assert client.track("Refund", "9876543210").status == "sent"


def test_track_junk_event_still_raises(client):
    with pytest.raises(ValueError, match="unknown event"):
        client.track("not a slug!", "9876543210")
