from app.services import ai_reply


def test_intake_in_progress_prompt_block_forbids_the_app_link():
    block = ai_reply._intake_in_progress_prompt_block("consultation")
    assert "consultation" in block.lower()
    assert "app" in block.lower()
    assert "do not" in block.lower() or "do NOT" in block


def test_intake_in_progress_prompt_block_does_not_resell():
    block = ai_reply._intake_in_progress_prompt_block("reading")
    assert "re-offer" in block.lower() or "re-describe" in block.lower()
