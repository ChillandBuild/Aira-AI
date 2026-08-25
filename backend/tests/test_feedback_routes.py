import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException

from app.routes.feedback import MESSAGE_MAX, validate_feedback_message


def test_validate_accepts_a_good_message():
    assert validate_feedback_message("  Love the new packages UI  ") == "Love the new packages UI"


def test_validate_rejects_blank_message():
    with pytest.raises(HTTPException) as e:
        validate_feedback_message("   ")
    assert e.value.status_code == 400


def test_validate_rejects_message_over_max():
    with pytest.raises(HTTPException, match=str(MESSAGE_MAX)):
        validate_feedback_message("x" * (MESSAGE_MAX + 1))


def test_validate_accepts_message_at_max():
    message = "x" * MESSAGE_MAX
    assert validate_feedback_message(message) == message
