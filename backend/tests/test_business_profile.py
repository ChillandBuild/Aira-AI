"""Tests for business profile parsing, rendering, and conversion."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.business_profile import (
    Section, SECTIONS, HARD_WORD_LIMIT, parse, render, word_count, is_structured,
    validate, warnings, propose_conversion, _SECTION_BY_KEY, HEADING_ALIASES,
)


def test_sections_are_defined():
    """Verify the 6 sections exist in order."""
    assert len(SECTIONS) == 6
    keys = [s.key for s in SECTIONS]
    assert keys == ["about", "how_to_buy", "who", "voice", "job", "never"]
    
    # Check each section has required fields
    for section in SECTIONS:
        assert section.heading  # uppercase
        assert section.label    # display name
        assert section.hint     # user hint
        assert section.word_limit > 0


def test_parse_empty_text():
    """Parse of empty text returns empty sections and other."""
    result = parse("")
    assert result.sections == {}
    assert result.other == ""


def test_parse_single_section():
    """Parse recognizes a heading and captures text under it."""
    text = "ABOUT US\nWe sell widgets"
    result = parse(text)
    assert result.sections.get("about") == "We sell widgets"
    assert result.other == ""


def test_parse_multiple_sections():
    """Parse splits multiple sections correctly."""
    text = """ABOUT US
We sell widgets.

HOW CUSTOMERS BUY
Call or visit."""
    result = parse(text)
    assert result.sections.get("about") == "We sell widgets."
    assert result.sections.get("how_to_buy") == "Call or visit."


def test_parse_heading_with_colon():
    """Headings with trailing colon are recognized."""
    text = "ABOUT US:\nWe sell."
    result = parse(text)
    assert result.sections.get("about") == "We sell."


def test_parse_alias_heading():
    """Old heading aliases are mapped to new section keys."""
    # "WHAT WE OFFER" -> "about"
    text = "WHAT WE OFFER\nWidgets galore"
    result = parse(text)
    assert result.sections.get("about") == "Widgets galore"
    
    # "GREETINGS AND CLOSINGS" -> "voice"
    text = "GREETINGS AND CLOSINGS\nHi there!"
    result = parse(text)
    assert result.sections.get("voice") == "Hi there!"


def test_parse_pre_heading_text_goes_to_other():
    """Text before any heading goes to 'other'."""
    text = "Some intro\nABOUT US\nWe sell"
    result = parse(text)
    assert result.other == "Some intro"
    assert result.sections.get("about") == "We sell"


def test_parse_unknown_heading_goes_to_other():
    """Unknown heading lines go to 'other'."""
    text = "UNKNOWN HEADING\nSome text"
    result = parse(text)
    assert "UNKNOWN HEADING" in result.other


def test_parse_multiple_blocks_same_section():
    """Multiple blocks for one section are joined."""
    text = """ABOUT US
First line.

ABOUT US
Second part."""
    result = parse(text)
    text_val = result.sections.get("about") or ""
    assert "First line." in text_val
    assert "Second part." in text_val


def test_render_empty_sections():
    """Render of empty sections returns empty string."""
    result = render({}, "")
    assert result == ""


def test_render_single_section():
    """Render outputs section heading and text."""
    sections = {"about": "We sell widgets"}
    result = render(sections)
    assert "ABOUT US" in result
    assert "We sell widgets" in result


def test_render_in_sections_order():
    """Render outputs sections in SECTIONS order, not insertion order."""
    sections = {
        "never": "No refunds",
        "about": "We sell",
    }
    result = render(sections)
    # about comes before never in SECTIONS
    assert result.index("ABOUT US") < result.index("WHAT YOU MUST NEVER DO")


def test_render_with_other_text():
    """Render appends 'other' text at the end."""
    sections = {"about": "We sell"}
    result = render(sections, "Free shipping")
    assert "Free shipping" in result
    # Other is appended but will be part of last section when re-parsed
    assert result.endswith("Free shipping")


def test_round_trip_parse_render():
    """parse(render(parse(x))) == parse(x) for structured content."""
    original = """ABOUT US
We are a widget shop.

HOW CUSTOMERS BUY
Call us."""
    
    parsed1 = parse(original)
    rendered = render(parsed1.sections, parsed1.other)
    parsed2 = parse(rendered)
    
    assert parsed1.sections == parsed2.sections
    assert parsed1.other == parsed2.other


def test_word_count():
    """word_count splits on whitespace."""
    assert word_count("") == 0
    assert word_count("one") == 1
    assert word_count("one two three") == 3
    assert word_count("  spaced  out  ") == 2


def test_is_structured_with_sections_no_other():
    """is_structured is True when sections exist and no pre-section other text."""
    sections = {"about": "We sell"}
    text = render(sections)
    assert is_structured(text) is True


def test_is_structured_with_pre_section_text():
    """is_structured is False when pre-section text exists."""
    # Create text with content before any heading
    text = "Some intro\nABOUT US\nWe sell"
    assert is_structured(text) is False


def test_is_structured_empty():
    """is_structured is False for empty text."""
    assert is_structured("") is False


def test_validate_empty():
    """validate of empty sections and other returns no errors."""
    errors = validate({}, "")
    assert errors == []


def test_validate_unknown_key():
    """validate rejects unknown section keys."""
    errors = validate({"unknown_key": "text"}, "")
    assert any("Unknown section" in e for e in errors)


def test_validate_total_word_count_under_limit():
    """validate passes when total words <= HARD_WORD_LIMIT."""
    # 3 words total, limit is 700
    sections = {"about": "one two three"}
    errors = validate(sections)
    assert errors == []


def test_validate_total_word_count_exceeds_limit():
    """validate rejects when total words > HARD_WORD_LIMIT."""
    # Create a section with more than 700 words
    text = " ".join(["word"] * (HARD_WORD_LIMIT + 10))
    sections = {"about": text}
    errors = validate(sections)
    assert any("Total is" in e and "words" in e and str(HARD_WORD_LIMIT) in e for e in errors)


def test_warnings_empty():
    """warnings of empty sections returns empty list."""
    warns = warnings({})
    assert warns == []


def test_warnings_per_section_over_limit():
    """warnings lists sections exceeding their word limit."""
    # "about" has limit 80; add 90 words
    text = " ".join(["word"] * 90)
    sections = {"about": text}
    warns = warnings(sections)
    
    assert len(warns) == 1
    assert warns[0]["key"] == "about"
    assert warns[0]["words"] == 90
    assert warns[0]["limit"] == 80


def test_warnings_multiple_sections():
    """warnings lists multiple sections over their limits."""
    sections = {
        "about": " ".join(["word"] * 100),  # 100 words, limit 80
        "how_to_buy": " ".join(["word"] * 70),  # 70 words, limit 60
    }
    warns = warnings(sections)
    
    assert len(warns) == 2
    keys = {w["key"] for w in warns}
    assert keys == {"about", "how_to_buy"}


@pytest.mark.asyncio
async def test_propose_conversion_empty_description():
    """propose_conversion of empty description returns error."""
    result = await propose_conversion("tenant-1", "")
    assert result["errors"] == ["Description is empty."]
    assert result["sections"] == {}
    assert result["total_words"] == 0


@pytest.mark.asyncio
async def test_propose_conversion_llm_error_handled():
    """propose_conversion gracefully handles LLM failures."""
    with patch("app.services.business_profile._llm_json") as mock_llm:
        mock_llm.side_effect = RuntimeError("Model not configured")
        result = await propose_conversion("tenant-1", "We sell widgets")
        assert len(result["errors"]) > 0
        assert "Model not configured" in str(result["errors"])


@pytest.mark.asyncio
async def test_propose_conversion_success():
    """propose_conversion calls LLM and processes response."""
    with patch("app.services.business_profile._llm_json") as mock_llm:
        mock_llm.return_value = {
            "sections": {
                "about": "A widget shop.",
                "how_to_buy": "Call us.",
                "who": "Businesses",
            },
            "removed": [
                {"text": "Reply in English", "why": "already in the platform rules"},
            ],
            "facts_to_move": ["Price: $10"],
            "suggested_handover": "Ask for our support team",
        }
        
        result = await propose_conversion("tenant-1", "We sell widgets to businesses. Call us for quotes. Price: $10. Reply in English.")
        
        assert result["sections"]["about"] == "A widget shop."
        assert result["sections"]["how_to_buy"] == "Call us."
        assert result["sections"]["who"] == "Businesses"
        assert len(result["removed"]) == 1
        assert result["removed"][0]["why"] == "already in the platform rules"
        assert result["facts_to_move"] == ["Price: $10"]
        assert result["suggested_handover"] == "Ask for our support team"
        assert result["total_words"] > 0


@pytest.mark.asyncio
async def test_propose_conversion_filters_unknown_keys():
    """propose_conversion only keeps known section keys in response."""
    with patch("app.services.business_profile._llm_json") as mock_llm:
        mock_llm.return_value = {
            "sections": {
                "about": "We sell.",
                "unknown_key": "This should be dropped.",
            },
            "removed": [],
            "facts_to_move": [],
            "suggested_handover": "",
        }
        
        result = await propose_conversion("tenant-1", "We sell widgets.")
        
        assert "unknown_key" not in result["sections"]
        assert "about" in result["sections"]


def test_heading_aliases_mapped():
    """All heading aliases map to known section keys."""
    for alias, key in HEADING_ALIASES.items():
        assert key in _SECTION_BY_KEY, f"Alias '{alias}' maps to unknown key '{key}'"


def test_unknown_heading_after_a_section_goes_to_other_not_the_section():
    # Real Astro Tamil shape: handover rules under a heading that is not a section.
    from app.services.business_profile import parse
    text = "WHAT YOU MUST NEVER DO\n- Never guess.\n\nHAND OVER TO A PERSON WHEN\n- They ask for a human."
    parsed = parse(text)
    assert parsed.sections["never"] == "- Never guess."
    assert "HAND OVER TO A PERSON WHEN" in parsed.other
    assert "- They ask for a human." in parsed.other


def test_bullet_in_capitals_is_not_treated_as_a_heading():
    from app.services.business_profile import parse
    parsed = parse("ABOUT US\n- WE SELL SAREES ONLINE\nMore text")
    assert parsed.sections["about"] == "- WE SELL SAREES ONLINE\nMore text"
    assert parsed.other == ""
