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
