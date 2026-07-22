"""Opt-out keyword matching for inbound WhatsApp replies."""
import pytest

from app.routes.webhook import _is_opt_out


@pytest.mark.parametrize("body", ["stop", "unsubscribe", "ஆர்வம் இல்லை"])
def test_stop_words_opt_out(body):
    assert _is_opt_out(body)


@pytest.mark.parametrize("body", ["STOP", "Stop", "  stop  ", "Unsubscribe"])
def test_matching_is_case_and_whitespace_insensitive(body):
    assert _is_opt_out(body)


@pytest.mark.parametrize("body", ["hi", "vanakkam", "how much", "", "stopped"])
def test_normal_replies_do_not_opt_out(body):
    assert not _is_opt_out(body)


@pytest.mark.parametrize("body", ["stop.", "stop please", "please stop"])
def test_known_gap_exact_match_only(body):
    """Matching is exact, so decorated forms of 'stop' fall through to scoring
    rather than triggering a hard opt-out. Documents current behaviour."""
    assert not _is_opt_out(body)
