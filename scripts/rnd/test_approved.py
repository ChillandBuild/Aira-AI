"""Which ticked report items the builder picks up.

    python3 -m pytest scripts/rnd/test_approved.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("approved.py")

REPORT = """# Aira night report — 2026-09-28
## Read this first

### 1. Pooja's WhatsApp is dead
details
- [ ] Approve

### 2. Three API routes turn **Supabase** hiccups into 500s
details about `execute_with_retry`
- [x] Approve

### 3. Verify tooling is broken
- [X] Approve

## Production errors
- [x] Approve  (outside any ### item: ignored)
"""


def run(tmp_path: Path, done: list[str] | None = None, limit: int = 5) -> tuple[int, Path]:
    reports, out = tmp_path / "reports", tmp_path / "out"
    reports.mkdir()
    (reports / "2026-09-28-night.md").write_text(REPORT)
    (reports / "LATEST-night.md").write_text(REPORT)  # a copy: must not double-count
    built = tmp_path / "built.json"
    if done is not None:
        built.write_text(json.dumps(done))
    res = subprocess.run([sys.executable, str(SCRIPT), str(reports), str(built), str(limit), str(out)],
                         capture_output=True, text=True, check=True)
    return int(res.stdout.strip()), out


def env(path: Path) -> dict:
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def test_only_ticked_items_inside_sections(tmp_path):
    count, out = run(tmp_path)
    assert count == 2
    first = env(out / "item-0.env")
    assert first["ITEM_ID"] == "'2026-09-28-night#2'"
    assert first["ITEM_BRANCH"] == "rnd/2026-09-28-night-2-three-api-routes-turn-supabase-hiccups"
    assert "execute_with_retry" in (out / "item-0.md").read_text()
    assert env(out / "item-1.env")["ITEM_ID"] == "'2026-09-28-night#3'"


def test_already_built_items_are_skipped(tmp_path):
    count, _ = run(tmp_path, done=["2026-09-28-night#2"])
    assert count == 1


def test_limit(tmp_path):
    count, out = run(tmp_path, limit=1)
    assert count == 1 and not (out / "item-1.env").exists()
