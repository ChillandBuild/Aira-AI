# Aira AI — convenience targets
# graphify python is resolved from the env graphify wrote; falls back to python3.
PY := $(shell cat graphify-out/.graphify_python 2>/dev/null || echo python3)

.PHONY: wiki wiki-refresh second-brain-close doctor

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

# Session-end second-brain health check (dead links, credential scan, generated-artifact
# git churn, hook liveness, stale .agents/ claims). Read-only. Same script every project
# scaffolded with bootstrapping-second-brain uses — see scripts/second_brain_close.py.
second-brain-close:
	python3 scripts/second_brain_close.py

# Check for a partially-destroyed dev environment (antivirus quarantine has
# deleted individual files out of the stdlib, site-packages, and node_modules
# on this project before). Run when imports fail in ways that make no sense.
# Uses the CURRENT interpreter on purpose — run it from the venv you suspect.
doctor:
	python scripts/check_env_integrity.py
