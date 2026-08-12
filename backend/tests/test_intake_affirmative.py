import pytest

from app.services import intake as ik


@pytest.mark.parametrize("message", [
    "seri", "Seri pannunga", "sari", "aama", "aamaa", "ama", "okay",
    "ok", "sure", "seri boss", "சரி", "ஆம்", "yes please",
])
def test_affirmative_variants_are_accepted(message):
    assert ik._is_affirmative(message) is True


@pytest.mark.parametrize("message", [
    "vendaam", "no", "illa", "later", "evlo aagum?", "costly",
])
def test_negative_and_question_replies_are_not_affirmative(message):
    assert ik._is_affirmative(message) is False
