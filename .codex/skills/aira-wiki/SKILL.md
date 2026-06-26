---
name: aira-wiki
description: Refresh or rebuild the Aira architecture wiki in graphify-out/wiki. Use when the user says "wiki", "/wiki", "aira-wiki", "refresh wiki", "rebuild architecture wiki", or asks to update graphify/module documentation.
---

# Aira Wiki

Run from the repo root. This is the Codex version of `.claude/commands/wiki.md`, adapted for the current Windows workspace.

## Modes

- Empty, `refresh`, or no argument: run `make wiki-refresh`.
- `fast` or `labels`: run `make wiki`.
- `docs`: run the LLM-backed graphify update for changed docs, then run `make wiki`.

## Procedure

1. Check `Makefile` before running commands if the repo has changed.
2. Use the requested mode. Default to `refresh` after code changes.
3. Do not manually edit generated files under `graphify-out/wiki/`.
4. If label or grouping changes are needed, edit `scripts/build_wiki.py`, then rerun `make wiki`.
5. Report the article count line from output and link `graphify-out/wiki/index.md`.

## Windows Notes

If `make` is unavailable in PowerShell, inspect `Makefile` and run the equivalent commands directly. Keep generated wiki files local-only if `.gitignore` excludes them.
