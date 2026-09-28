#!/usr/bin/env python3
"""Items the founder approved in a night report (`- [x] Approve`) that have not been built yet.

    approved.py <reports_dir> <built.json> <limit> <out_dir>

A report item is a `### <n>. <title>` section (see .agents/rnd/night.md). For each new
approved item, writes <out_dir>/item-<k>.md (the section text) and <out_dir>/item-<k>.env
(ITEM_ID, ITEM_TITLE, ITEM_BRANCH, ITEM_SAFE) for scripts/rnd/run.sh; prints the count.
Only dated reports are read (never LATEST-*.md, which is a copy).
"""
import json
import re
import shlex
import sys
from pathlib import Path

HEADING = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
TICKED = re.compile(r"^\s*-\s*\[[xX]\]\s*Approve\b", re.M)


def sections(text: str) -> list[dict]:
    found, current = [], None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading or line.startswith("## ") or line.startswith("# "):
            if current:
                found.append(current)
            current = {"n": heading.group(1), "title": heading.group(2), "lines": [line]} if heading else None
            continue
        if current:
            current["lines"].append(line)
    if current:
        found.append(current)
    return found


def slug(title: str, limit: int = 40) -> str:
    """Branch-safe words of the title, cut at a whole word."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"[*_`]", "", title).lower())
    out = ""
    for word in words:
        if out and len(out) + 1 + len(word) > limit:
            break
        out = f"{out}-{word}" if out else word[:limit]
    return out or "item"


def approved(reports_dir: Path, done: set[str]) -> list[dict]:
    items = []
    for report in sorted(reports_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-night*.md")):
        for s in sections(report.read_text(encoding="utf-8")):
            body = "\n".join(s["lines"])
            item_id = f"{report.stem}#{s['n']}"
            if TICKED.search(body) and item_id not in done:
                safe = f"{report.stem}-{s['n']}-{slug(s['title'])}"
                items.append({"id": item_id, "title": re.sub(r"[*_`]", "", s["title"]),
                              "safe": safe, "branch": f"rnd/{safe}", "text": body})
    return items


def main() -> None:
    reports_dir, built_file, limit, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
    done = set(json.loads(built_file.read_text())) if built_file.exists() else set()
    items = approved(reports_dir, done)[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)
    for k, item in enumerate(items):
        (out_dir / f"item-{k}.md").write_text(item["text"] + "\n", encoding="utf-8")
        (out_dir / f"item-{k}.env").write_text(
            "".join(f"{key}={shlex.quote(item[field])}\n" for key, field in
                    [("ITEM_ID", "id"), ("ITEM_TITLE", "title"), ("ITEM_BRANCH", "branch"), ("ITEM_SAFE", "safe")]),
            encoding="utf-8",
        )
    print(len(items))


if __name__ == "__main__":
    main()
