---
name: wiki
description: Rebuild the architecture module wiki (graphify-out/wiki/). Default re-extracts code; "fast" reuses graph.json; "docs" does full LLM re-extraction.
---

The user wants to refresh the architecture wiki. Argument: `$ARGUMENTS`

Run from the repo root (`/Users/prem/Documents/Aira AI`) via Bash. Pick by argument:

- **empty or `refresh`** → `make wiki-refresh`
  (re-extract code with `graphify update . --force` (AST, no LLM) → rebuild wiki). This is the default and the right choice after code changes. `--force` prunes nodes for DELETED files — without it, removed modules linger as ghosts in the graph forever.

- **`fast` or `labels`** → `make wiki`
  (rebuild wiki from the existing `graph.json` only — use when only labels in `scripts/build_wiki.py` changed, or nothing changed). Fast, no extraction.

- **`docs`** → the wiki needs changed markdown specs picked up, which needs LLM re-extraction. Run the graphify update + wiki:
  1. `/graphify . --update` (LLM re-extracts changed docs)
  2. then `make wiki`

After running, report the article count line from the output and link `graphify-out/wiki/index.md`. Do not edit the generated `.md` files by hand — they are regenerated wholesale; label changes go in `scripts/build_wiki.py` (`FILE_OVERRIDE`).
