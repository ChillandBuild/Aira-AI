from app.services.description_diff import (
    apply_hunks,
    client_lines,
    closest_line,
    diff_hunks,
    insert_under_heading,
    is_heading_line,
    lines_of,
    normalize,
    remove_lines,
    replace_exact_line,
)

CURRENT = "ABOUT US\nWe are AstroTamil.\n\nWHAT YOU MUST NEVER DO\n- Never predict.\n- Never ask for DOB."
PROPOSED = "ABOUT US\nWe are AstroTamil, since 2025.\n\nWHAT YOU MUST NEVER DO\n- Never predict.\n- Never promise security."


def test_lines_of_ignores_one_trailing_newline_and_normalises_endings():
    assert lines_of("a\r\nb\n") == ["a", "b"]
    assert lines_of("a\n\n") == ["a", ""]
    assert lines_of("") == []


def test_applying_all_hunks_gives_the_proposal_and_none_gives_the_current_text():
    hunks = diff_hunks(CURRENT, PROPOSED, machine_lines=set())
    assert hunks
    assert apply_hunks(CURRENT, hunks, {h.id for h in hunks}) == PROPOSED
    assert apply_hunks(CURRENT, hunks, set()) == CURRENT


def test_hunks_can_be_accepted_one_at_a_time():
    hunks = diff_hunks(CURRENT, PROPOSED, machine_lines=set())
    first = hunks[0]
    result = apply_hunks(CURRENT, hunks, {first.id})
    assert "We are AstroTamil, since 2025." in result
    assert "- Never ask for DOB." in result


def test_whitespace_only_differences_are_not_changes():
    assert diff_hunks("Never  predict.", "Never predict.  ", machine_lines=set()) == []


def test_a_hunk_touching_a_line_no_document_claims_is_flagged():
    machine = {normalize("We are AstroTamil.")}
    hunks = diff_hunks(CURRENT, PROPOSED, machine_lines=machine)
    by_old = {tuple(h.old_lines): h for h in hunks}
    assert by_old[("We are AstroTamil.",)].touches_client_lines is False
    assert by_old[("- Never ask for DOB.",)].touches_client_lines is True


def test_pure_additions_never_touch_client_lines():
    hunks = diff_hunks("A line.", "A line.\nNew rule.", machine_lines=set())
    assert [h.kind for h in hunks] == ["add"]
    assert hunks[0].touches_client_lines is False


def test_client_lines_excludes_machine_lines_and_blanks():
    assert client_lines("Mine.\n\nFrom file.", {normalize("From file.")}) == {"Mine."}


def test_heading_detection():
    assert is_heading_line("WHAT YOU MUST NEVER DO")
    assert not is_heading_line("- Never predict.")
    assert not is_heading_line("வணக்கம்")  # no case: not a heading
    assert not is_heading_line("")


def test_insert_under_heading_goes_to_the_end_of_that_section():
    result = insert_under_heading(CURRENT, "about us", "Since December 2025.")
    assert lines_of(result)[:3] == ["ABOUT US", "We are AstroTamil.", "Since December 2025."]


def test_insert_under_the_last_heading_appends_inside_it():
    result = insert_under_heading(CURRENT, "WHAT YOU MUST NEVER DO", "- Never guarantee.")
    assert lines_of(result)[-1] == "- Never guarantee."


def test_insert_under_a_missing_heading_appends_at_the_end():
    assert lines_of(insert_under_heading(CURRENT, "GREETINGS", "Say vanakkam."))[-1] == "Say vanakkam."
    assert insert_under_heading("", "GREETINGS", "Say vanakkam.") == "Say vanakkam."


def test_replace_exact_line_swaps_one_line_or_reports_it_gone():
    text = "Price starts at 29.\nOther."
    assert replace_exact_line(text, "Price  starts at 29.", "Price starts at 49.") == "Price starts at 49.\nOther."
    assert replace_exact_line(text, "Missing line.", "x") is None


def test_remove_lines_collapses_doubled_blank_lines():
    text = "A\n\nB\n\nC"
    assert remove_lines(text, {"B"}) == "A\n\nC"


def test_closest_line_finds_an_edited_version():
    candidates = ["- Never ask for date of birth in chat.", "Something else entirely."]
    assert closest_line("- Never ask for DOB in chat.", candidates) == candidates[0]
    assert closest_line("Totally unrelated words here", candidates) is None
