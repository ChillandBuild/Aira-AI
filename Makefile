# Aira AI — convenience targets
# graphify python is resolved from the env graphify wrote; falls back to python3.
PY := $(shell cat graphify-out/.graphify_python 2>/dev/null || echo python3)

.PHONY: wiki wiki-refresh

# Rebuild the curated module wiki from the EXISTING graph.json (fast, no extraction).
# Use after running `make wiki-refresh`, or when you only tweaked labels in scripts/build_wiki.py.
wiki:
	$(PY) scripts/build_wiki.py

# Re-extract code (AST only, no LLM) → rebuild graph.json → regenerate the wiki.
# Catches code changes. --force prunes nodes for DELETED files (AST is deterministic,
# so a smaller graph means real deletions, not a bad run). Without it, deleted modules
# linger as ghosts forever. NOTE: changed docs/specs (markdown) need LLM re-extraction —
# for those run `/graphify . --update` in Claude instead, then `make wiki`.
wiki-refresh:
	graphify update . --force
	$(PY) scripts/build_wiki.py
