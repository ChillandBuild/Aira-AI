"""Dry-run eval of the "upload a document to the knowledge base" pipeline.

For each fixture document: split -> label (LLM) -> bucket -> compile_description (LLM),
starting from an empty Description (and, for the dental doc, a second run merging into a
small pre-existing Description). Checks where content lands: the always-read business
PROFILE (6 fixed sections), looked-up FACTS (retrieval), or dropped as JUNK/left_out --
and whether that placement matches each fixture's expectations file.

NEVER writes to the database: only pure/LLM pipeline functions are called
(split_sections, label_sections, bucket_sections, compile_description, business_profile
parse/word_count/validate). run_sort/sort_document/apply_review/index_facts are never
imported.

    cd backend && source .venv/bin/activate && python -m evals.knowledge_sort.run_eval
"""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))

from app.services import business_profile  # noqa: E402
from app.services import knowledge_sections  # noqa: E402
from app.services import knowledge_sort  # noqa: E402

KEY_TENANT = "eba3ed94-277c-430f-a992-19bbe855e2f4"
DOCS_DIR = HERE / "docs"
SCRATCH_DIR = Path(
    "/private/tmp/claude-501/-Users-prem-Documents-Aira-AI/"
    "14047afc-557a-4881-b6a4-4853cdfe7b64/scratchpad"
)
RESULTS_PATH = SCRATCH_DIR / "knowledge_sort_eval_results.json"
V9_DOC_PATH = SCRATCH_DIR / "v9_doc.txt"
V9_TENANT_ID = "9dfe3f53-a4f8-4c0e-99b5-853b42556ee8"

# A small existing profile (business_profile.render()-shaped) to test the dental doc
# merging new rules into a Description that already has content under two of the six
# headings.
DENTAL_EXISTING_PROFILE = """ABOUT US
Smile Care Dental Clinic is a family-run dental clinic in RS Puram, Coimbatore, open since 2014, with two dentists on staff and an in-house digital X-ray machine.

WHAT YOU MUST NEVER DO
Never discuss surgery risks or treatment complications in detail over chat -- always tell the patient to book an in-person consultation for anything beyond a routine question."""

SECTION_LIMITS = {s.key: s.word_limit for s in business_profile.SECTIONS}


def _normalize_line(line: str) -> str:
    return " ".join(line.strip().lower().split())


def duplicate_lines(text: str) -> list[str]:
    """Non-empty lines (normalized) that appear more than once in the compiled profile."""
    seen: dict[str, int] = {}
    for raw in text.split("\n"):
        norm = _normalize_line(raw)
        if not norm:
            continue
        seen[norm] = seen.get(norm, 0) + 1
    return [line for line, count in seen.items() if count > 1]


def check_must_be_facts(items: list[str], facts_text: str, unverified_text: str, profile_text: str) -> dict[str, str]:
    out = {}
    facts_l = facts_text.lower()
    unverified_l = unverified_text.lower()
    profile_l = profile_text.lower()
    for item in items:
        il = item.lower()
        if il in facts_l:
            out[item] = "facts"
        elif il in unverified_l:
            out[item] = "unverified"
        elif il in profile_l:
            out[item] = "in profile only"
        else:
            out[item] = "LOST"
    return out


def check_must_be_profile(items: list[str], profile_text: str) -> dict[str, bool]:
    profile_l = profile_text.lower()
    return {item: (item.lower() in profile_l) for item in items}


def check_must_not_leak(items: list[str], profile_text: str) -> dict[str, bool]:
    """True means it LEAKED (bad)."""
    profile_l = profile_text.lower()
    return {item: (item.lower() in profile_l) for item in items}


async def run_pipeline(text: str, existing_description: str = "") -> dict:
    sections = knowledge_sections.split_sections(text)
    labels = await knowledge_sort.label_sections(KEY_TENANT, sections)
    buckets = knowledge_sort.bucket_sections(sections, labels)
    # Same order as knowledge_sort.run_sort: compile (strips handover lines), then
    # enforce the per-section word limits.
    compiled, conflicts, handover = await knowledge_sort.compile_description(
        KEY_TENANT, existing_description, buckets.rules
    )
    compiled = await knowledge_sort.enforce_section_limits(KEY_TENANT, compiled)
    facts_text = "\n\n".join(buckets.facts)
    unverified_text = "\n\n".join(buckets.unverified)
    parsed = business_profile.parse(compiled)

    label_counts = {"RULE": 0, "FACT": 0, "MIXED": 0, "JUNK": 0}
    for lab in labels.values():
        label_counts[lab.label] = label_counts.get(lab.label, 0) + 1
    unlabelled = len(sections) - len(labels)

    per_section_words = {}
    over_limit_sections = []
    for key, text_ in parsed.sections.items():
        words = business_profile.word_count(text_)
        limit = SECTION_LIMITS.get(key)
        per_section_words[key] = {"words": words, "limit": limit}
        if limit is not None and words > limit:
            over_limit_sections.append({"key": key, "words": words, "limit": limit})

    total_words = business_profile.word_count(compiled)
    validate_errors = business_profile.validate(parsed.sections, parsed.other)

    return {
        "sections_count": len(sections),
        "label_counts": label_counts,
        "unlabelled": unlabelled,
        "labels": {sid: {"label": lab.label, "facts": lab.facts, "note": lab.note} for sid, lab in labels.items()},
        "left_out": buckets.left_out,
        "rules_count": len(buckets.rules),
        "facts_count": len(buckets.facts),
        "unverified_count": len(buckets.unverified),
        "facts_text": facts_text,
        "unverified_text": unverified_text,
        "compiled_profile": compiled,
        "suggested_handover": handover,
        "conflicts": conflicts,
        "other_text": parsed.other,
        "per_section_words": per_section_words,
        "over_limit_sections": over_limit_sections,
        "total_words": total_words,
        "over_hard_limit": total_words > business_profile.HARD_WORD_LIMIT,
        "validate_errors": validate_errors,
        "duplicate_lines": duplicate_lines(compiled),
    }


async def run_fixture(name: str, existing_description: str = "") -> dict:
    txt_path = DOCS_DIR / f"{name}.txt"
    exp_path = DOCS_DIR / f"{name}.expected.json"
    text = txt_path.read_text()
    expectations = json.loads(exp_path.read_text())

    result = await run_pipeline(text, existing_description)

    result["must_be_facts_result"] = check_must_be_facts(
        expectations["must_be_facts"], result["facts_text"], result["unverified_text"], result["compiled_profile"]
    )
    result["must_be_profile_result"] = check_must_be_profile(
        expectations["must_be_profile"], result["compiled_profile"]
    )
    result["must_not_be_profile_result"] = check_must_not_leak(
        expectations["must_not_be_profile"], result["compiled_profile"]
    )
    junk_marker = expectations["junk_marker"]
    result["junk_marker"] = junk_marker
    result["junk_leaked_profile"] = junk_marker.lower() in result["compiled_profile"].lower()
    result["junk_leaked_facts"] = junk_marker.lower() in result["facts_text"].lower()
    return result


async def run_real_v9() -> dict:
    text = V9_DOC_PATH.read_text()
    result = await run_pipeline(text, existing_description="")
    result["source"] = "real v9 document (not committed)"
    result["word_count_source"] = business_profile.word_count(text)
    result["char_count_source"] = len(text)
    return result


def print_summary_row(name: str, r: dict) -> None:
    lc = r["label_counts"]
    lost = [k for k, v in r.get("must_be_facts_result", {}).items() if v == "LOST"]
    missing_profile = [k for k, v in r.get("must_be_profile_result", {}).items() if not v]
    leaked = [k for k, v in r.get("must_not_be_profile_result", {}).items() if v]
    print(
        f"{name:32s} sec={r['sections_count']:3d} "
        f"R/F/M/J/unl={lc['RULE']}/{lc['FACT']}/{lc['MIXED']}/{lc['JUNK']}/{r['unlabelled']} "
        f"facts_chars={len(r['facts_text']):5d} words={r['total_words']:4d} "
        f"lost={len(lost)} missing_profile={len(missing_profile)} leaked={len(leaked)} "
        f"dup={len(r['duplicate_lines'])} over_limit={len(r['over_limit_sections'])} "
        f"other={'Y' if r['other_text'] else 'N'} junk_leak={'Y' if (r.get('junk_leaked_profile') or r.get('junk_leaked_facts')) else 'N'}"
    )


async def _with_retry(label: str, make_coro, attempts: int = 3) -> dict | None:
    """A dropped connection mid-run must not throw away the other documents' results."""
    for attempt in range(1, attempts + 1):
        try:
            return await make_coro()
        except Exception as e:  # network blips (httpx.ReadError etc.)
            print(f"  {label}: attempt {attempt} failed: {type(e).__name__}: {e}", flush=True)
    print(f"  {label}: GAVE UP after {attempts} attempts", flush=True)
    return None


def _record(all_results: dict, key: str, result: dict | None) -> None:
    if result is None:
        return
    all_results[key] = result
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(all_results, ensure_ascii=False, indent=1))
    print_summary_row(key, result)
    print(f"  suggested handover: {result.get('suggested_handover')!r}", flush=True)


async def main() -> None:
    fixtures = [
        "dental_coimbatore",
        "realestate_chennai",
        "neet_madurai",
        "saree_shop_online",
        "salon",
    ]
    all_results: dict[str, dict] = {}

    for name in fixtures:
        print(f"\n=== {name} (empty description) ===", flush=True)
        _record(all_results, f"{name}__empty",
                await _with_retry(name, lambda n=name: run_fixture(n, existing_description="")))

    print("\n=== dental_coimbatore (merge into existing profile) ===", flush=True)
    _record(all_results, "dental_coimbatore__merge", await _with_retry(
        "dental merge", lambda: run_fixture("dental_coimbatore", existing_description=DENTAL_EXISTING_PROFILE)))

    if V9_DOC_PATH.exists():
        print("\n=== real v9 document (no expectations) ===", flush=True)
        _record(all_results, "real_v9", await _with_retry("real v9", run_real_v9))
    else:
        print(f"\n(skipping real v9 doc -- {V9_DOC_PATH} not found)")

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(all_results, ensure_ascii=False, indent=1))

    print("\n\n===== SUMMARY =====")
    for name, r in all_results.items():
        print_summary_row(name, r)
    print(f"\nFull artefacts written to: {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
