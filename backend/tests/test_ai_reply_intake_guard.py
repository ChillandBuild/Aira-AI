from app.services import ai_reply


def test_intake_in_progress_prompt_block_forbids_the_app_link():
    block = ai_reply._intake_in_progress_prompt_block("consultation")
    assert "consultation" in block.lower()
    assert "app" in block.lower()
    assert "do not" in block.lower() or "do NOT" in block


def test_intake_in_progress_prompt_block_does_not_resell():
    block = ai_reply._intake_in_progress_prompt_block("reading")
    assert "re-offer" in block.lower() or "re-describe" in block.lower()


def test_paid_prompt_block_promises_whatsapp_only_when_there_is_no_app():
    """Default (no app configured) keeps the pre-2026-08-18 behaviour: the expert
    reaches them here."""
    block = ai_reply._intake_paid_prompt_block("consultation")
    assert "here on WhatsApp" in block


def test_paid_prompt_block_points_at_the_app_when_the_answer_lands_there():
    """With an app_download_link set, the answer arrives in the app — telling a
    paying customer to watch WhatsApp for it is a promise Aira cannot keep."""
    block = ai_reply._intake_paid_prompt_block("reading", answer_in_app=True)
    assert "here on WhatsApp" not in block
    assert "app" in block.lower()
    assert "ready" in block.lower()


def test_paid_prompt_block_forbids_the_ai_writing_the_app_link():
    """A hallucinated download URL sends a paying customer nowhere — the same
    failure commit 24494b3d fixed on the offer message."""
    block = ai_reply._intake_paid_prompt_block("reading", answer_in_app=True)
    assert "link" in block.lower()
    assert "do not write a link" in block.lower()


def test_paid_prompt_block_never_answers_the_paid_question_either_way():
    for block in (
        ai_reply._intake_paid_prompt_block("reading"),
        ai_reply._intake_paid_prompt_block("reading", answer_in_app=True),
    ):
        assert "Do NOT attempt to answer their original question" in block
        assert "Do NOT offer or re-sell" in block
