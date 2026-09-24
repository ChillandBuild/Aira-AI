"""Dry-run eval: do filled Business Kit files sort where the Kit table says?
Spec: docs/superpowers/specs/2026-09-24-aira-business-kit-design.md

For each of the 12 invented industry examples, builds the file a client would upload
(template text with the example filled in, plus an [OWNER TO CHECK] line and the
template's own example block left at the end), then runs the same steps as run_sort:
strip_example + scrub_placeholders -> label_document (Kit headings, else LLM) -> bucket -> compile (LLM)
-> section limits -> verified_handover -> readiness.

Checks per file:
- every price line (PRODUCTS, SERVICES, PRICES) and Q/A line is in the facts, verbatim;
- the handover phone number is in the handover line and NOT in the Description;
- the Description has ABOUT US and HOW CUSTOMERS BUY;
- no placeholder or example-block text reaches facts or the Description;
- readiness says all 4 must-haves are present.

NEVER writes to the database. Uses the tenant model of KEY_TENANT, like run_eval.py.

    cd backend && .venv/bin/python -m evals.knowledge_sort.run_kit_eval
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services import business_profile, knowledge_sort  # noqa: E402
from app.services.knowledge_kit import readiness, scrub_placeholders, strip_example  # noqa: E402
from evals.knowledge_sort.run_eval import KEY_TENANT  # noqa: E402
from scripts.kit.build_kit import EXAMPLE_MARKER, EXAMPLES, HEADINGS  # noqa: E402

_PHONE_RE = re.compile(r"9\d{4} \d{5}")
_LEAK_MARKERS = ("OWNER TO CHECK", "Parking near", "EXAMPLE BELOW", "Decoy Academy")


def kit_file(example: dict) -> str:
    parts = ["Aira Business Kit", f"Template for: {example['industry']}"]
    for (heading, _hints), body in zip(HEADINGS, example["sections"], strict=True):
        parts.append(f"{heading}\n{body}")
    parts[-1] += "\nQ: Is there parking?\nA: [OWNER TO CHECK]\nParking near the entrance: [OWNER TO CHECK]"
    parts.append(f"{EXAMPLE_MARKER}\nExample: Decoy Academy. Fee Rs 99,999. Call 91111 11111.")
    return "\n\n".join(parts)


async def run_one(example: dict) -> list[str]:
    text, blanks = scrub_placeholders(strip_example(kit_file(example)))
    sections, labels = await knowledge_sort.label_document(KEY_TENANT, text)
    b = knowledge_sort.bucket_sections(sections, labels)
    description, _conflicts, handover = await knowledge_sort.compile_description(KEY_TENANT, "", b.rules)
    description = await knowledge_sort.enforce_section_limits(KEY_TENANT, description)
    handover = knowledge_sort.verified_handover(handover, text)
    facts = "\n\n".join(b.facts)

    problems: list[str] = []
    fact_lines = example["sections"][6].split("\n") + example["sections"][7].split("\n")
    lost = [line for line in fact_lines if line not in facts]
    if lost:
        problems.append(f"{len(lost)}/{len(fact_lines)} price/Q&A lines not in facts, e.g. {lost[0]!r}")
    phone = _PHONE_RE.search(example["sections"][5]).group(0)
    if phone not in handover:
        problems.append(f"handover missing {phone}: {handover!r}")
    if phone in description:
        problems.append("phone number leaked into the Description")
    parsed = business_profile.parse(description).sections
    for key in ("about", "how_to_buy"):
        if not parsed.get(key):
            problems.append(f"Description has no {key} section")
    for marker in _LEAK_MARKERS:
        if marker.lower() in (facts + description).lower():
            problems.append(f"leak: {marker!r}")
    if blanks != ["Is there parking?", "Parking near the entrance:"]:
        problems.append(f"blanks were {blanks}")
    must = [i for i in readiness(description=description, handover_line=handover, facts=b.facts) if i["level"] == "must"]
    if not all(i["ok"] for i in must):
        problems.append("readiness: " + ", ".join(i["key"] for i in must if not i["ok"]) + " missing")
    return problems


async def main() -> None:
    failed = 0
    for example in EXAMPLES:
        problems = await run_one(example)
        failed += bool(problems)
        print(f"{'PASS' if not problems else 'FAIL'}  {example['slug']}")
        for p in problems:
            print(f"      - {p}")
    print(f"\n{len(EXAMPLES) - failed}/{len(EXAMPLES)} Kit files sorted cleanly")


if __name__ == "__main__":
    asyncio.run(main())
