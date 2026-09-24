from app.services.knowledge_sections import (
    critical_tokens,
    split_sections,
    unverified_tokens,
    verify_fact,
)


def test_blocks_are_packed_into_sections_under_the_limit():
    text = "\n\n".join(f"Paragraph {i} " + "x" * 90 for i in range(10))
    sections = split_sections(text, max_chars=300)
    assert [s.id for s in sections] == [f"s{i + 1}" for i in range(len(sections))]
    assert all(len(s.text) <= 300 for s in sections)
    assert len(sections) > 1
    assert "".join(s.text for s in sections).count("Paragraph") == 10


def test_a_block_longer_than_the_limit_is_hard_split_on_a_boundary():
    block = "\n".join(f"Line number {i} with some words." for i in range(40))
    sections = split_sections(block, max_chars=300)
    assert len(sections) > 1
    assert all(len(s.text) <= 300 for s in sections)
    assert all(s.text.endswith("words.") for s in sections)


def test_a_heading_starts_a_new_section_once_the_current_one_has_substance():
    body = "Some rule text. " * 30  # ~480 chars
    text = f"Greeting Rules\n\n{body}\n\nPricing Query Handling Rule\n\nCharges start from 29."
    sections = split_sections(text, max_chars=2500)
    assert len(sections) == 2
    assert sections[1].text.startswith("Pricing Query Handling Rule")


def test_a_heading_does_not_split_off_a_tiny_section():
    text = "Greeting Rules\n\nSay vanakkam.\n\nClosing Rules\n\nSay nandri."
    assert len(split_sections(text)) == 1


def test_default_max_chars_is_1000_so_more_sections_get_labelled_separately():
    """Lowered from 2,500 (spec measurement, 2026-09-24): a ~650-word document used to
    pack into just 2 sections, both MIXED, because 2,500 chars was room enough to merge
    a rules paragraph and a facts paragraph together. At the new 1,000-char default,
    three ~450-char paragraphs (whose combined ~1,350 chars fit a single 2,500-char
    section) get split into two sections instead of staying packed into one."""
    from app.services.knowledge_sections import MAX_SECTION_CHARS

    assert MAX_SECTION_CHARS == 1_000
    paragraphs = [f"Paragraph {i} filler text. " * 15 for i in range(3)]  # ~450 chars each
    text = "\n\n".join(paragraphs)
    assert len(split_sections(text, max_chars=2_500)) == 1
    assert len(split_sections(text)) == 2


def test_critical_tokens_cover_prices_links_phones_and_counts():
    tokens = critical_tokens(
        "Starts ₹29. See https://x.in/a/. Call 98400 12345, 1,10,000+ done. Mail Help@X.in"
    )
    assert {"29", "https://x.in/a/", "98400", "12345", "110000", "help@x.in"} <= tokens


def test_verify_fact_rejects_a_changed_price():
    assert verify_fact("Consultations start from ₹49", "Consultation charges ₹29-lendhu start") is False
    assert verify_fact("Consultations start from ₹29", "Consultation charges ₹29-lendhu start") is True


def test_verify_fact_rejects_a_changed_link():
    source = "Link: https://astrotamil.co.in/app/consultation/"
    assert verify_fact("Use https://astrotamil.co.in/app/consultation/", source) is True
    assert verify_fact("Use https://astrotamil.co.in/app/", source) is False


def test_unverified_tokens_accepts_several_sources():
    assert unverified_tokens("from 29 to 49", "was 29", "now 49") == set()
    assert unverified_tokens("from 29 to 59", "was 29", "now 49") == {"59"}


def test_text_without_numbers_always_verifies():
    assert verify_fact("Astrologers never see your phone number", "unrelated text") is True
