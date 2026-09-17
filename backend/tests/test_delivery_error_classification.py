"""Tests for WhatsApp delivery error classification. No DB, no network.

webhook.py classifies a delivery-failure error code as either "the recipient's
number itself is bad" (permanently exclude that one lead) or "everything else"
(transient throttles / account-level failures — never flag the lead). Only
131026 is treated as recipient-undeliverable; the transient throttle codes
(131049/131048/131056/130472) must NOT flag the lead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes.webhook import (
    PERMANENT_UNDELIVERABLE_ERROR_CODES,
    _is_recipient_undeliverable_error,
)


def test_recipient_bad_number_code_is_undeliverable():
    assert _is_recipient_undeliverable_error(131026) is True
    assert 131026 in PERMANENT_UNDELIVERABLE_ERROR_CODES


def test_recipient_code_as_string_is_undeliverable():
    assert _is_recipient_undeliverable_error("131026") is True


def test_transient_throttle_codes_are_not_recipient_undeliverable():
    # Account-level throttles — the number is still reachable, so they must NOT
    # flag the lead as undeliverable.
    for code in (131049, 131048, 131056, 130472):
        assert _is_recipient_undeliverable_error(code) is False
        assert code not in PERMANENT_UNDELIVERABLE_ERROR_CODES


def test_none_and_garbage_are_not_undeliverable():
    assert _is_recipient_undeliverable_error(None) is False
    assert _is_recipient_undeliverable_error("not-a-code") is False


# --- fail_detail extraction from the status webhook ---------------------------
# broadcast_recipients.fail_detail used to be populated only when Meta rejected a
# send synchronously; webhook-reported delivery failures left it blank, so the
# failed CSV showed a bare "delivery_failed:131042:..." with an empty detail
# column. _delivery_fail_detail() pulls Meta's own explanation off the status
# webhook's error object so both paths fill the same column.

from app.routes.webhook import _delivery_fail_detail


def test_error_data_details_is_preferred():
    err = {
        "code": 131042,
        "title": "Business eligibility payment issue",
        "message": "Business eligibility payment issue",
        "error_data": {
            "details": "Failed to send message because there were one or more errors related to your payment method."
        },
    }
    detail = _delivery_fail_detail(err)
    assert detail == (
        "(#131042) Failed to send message because there were one or more "
        "errors related to your payment method."
    )


def test_falls_back_to_message_then_title():
    assert _delivery_fail_detail({"code": 131026, "message": "Message undeliverable"}) == (
        "(#131026) Message undeliverable"
    )
    assert _delivery_fail_detail({"code": 131026, "title": "Message undeliverable"}) == (
        "(#131026) Message undeliverable"
    )


def test_code_not_duplicated_when_already_in_text():
    err = {"code": 131058, "message": "(#131058) Hello World templates are restricted"}
    assert _delivery_fail_detail(err) == "(#131058) Hello World templates are restricted"


def test_missing_code_leaves_text_unprefixed():
    assert _delivery_fail_detail({"message": "Something broke"}) == "Something broke"


def test_empty_and_malformed_errors_yield_empty_string():
    assert _delivery_fail_detail({}) == ""
    assert _delivery_fail_detail(None) == ""
    assert _delivery_fail_detail({"code": 131042}) == ""
    assert _delivery_fail_detail({"code": 1, "error_data": "not-a-dict", "message": "ok"}) == "(#1) ok"


def test_detail_is_capped_at_300_chars():
    err = {"code": 1, "error_data": {"details": "x" * 500}}
    assert len(_delivery_fail_detail(err)) == 300
