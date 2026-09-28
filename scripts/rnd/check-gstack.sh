#!/usr/bin/env bash
# SessionStart: say something only when gstack is missing or not the pinned version, so the
# agent (and whoever is at the keyboard) knows the CLAUDE.md sprint commands may not work.
# Silent when everything matches. Pinned version: CLAUDE.md "gstack setup" section.
PINNED="1.91.2.0"
GS="$HOME/.claude/skills/gstack"
if [ ! -f "$GS/VERSION" ]; then
  echo "gstack is NOT installed on this machine: the /gstack-* commands in CLAUDE.md will not work. Tell the user and point them to the 'gstack setup' section of CLAUDE.md."
elif [ "$(cat "$GS/VERSION")" != "$PINNED" ]; then
  echo "gstack here is $(cat "$GS/VERSION"), but Aira is pinned to $PINNED (CLAUDE.md 'gstack setup'). Tell the user once; do not upgrade or downgrade it yourself."
fi
exit 0
