#!/usr/bin/env bash
# Start an unattended, report-only R&D run.
#
#   scripts/rnd/run.sh night      quality scouts (errors, conversations, live UI, code health)
#   scripts/rnd/run.sh strategy   the weekly strategy run (.agents/rnd/charter.md)
#   scripts/rnd/run.sh auto       what launchd calls: night every day, strategy on Sundays
#
# Safety: AIRA_AUTONOMOUS=1 switches on scripts/rnd/fence.py (loaded via fence-settings.json,
# regardless of what the worktree contains). The run happens in a dedicated worktree reset
# to the committed local main; reports go to rnd/reports/ (gitignored: they can hold
# aggregated customer patterns). Caps: RND_NIGHT_BUDGET / RND_STRATEGY_BUDGET (USD estimate).
set -euo pipefail

MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="$HOME/.aira-rnd"
WT="$MAIN/.worktrees/rnd"
OUT="$MAIN/rnd/reports"
KIND="${1:-auto}"
NIGHT_BUDGET="${RND_NIGHT_BUDGET:-8}"
STRATEGY_BUDGET="${RND_STRATEGY_BUDGET:-20}"
MAX_SECONDS="${RND_MAX_SECONDS:-5400}"

export PATH="$HOME/.local/bin:$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$STATE/logs" "$OUT"
# The Supabase MCP token lives here (chmod 600, never in git); launchd does not load a shell profile.
[ -f "$STATE/env" ] && source "$STATE/env"

notify() { osascript -e "display notification \"$2\" with title \"Aira R&D\" subtitle \"$1\"" >/dev/null 2>&1 || true; }

prepare_worktree() {
  # Local `main` (committed work, pushed or not — never the half-edited working tree).
  # Production itself is checked directly by the scouts (logs, DB, live site).
  git -C "$MAIN" fetch -q origin main || true
  if [ ! -d "$WT/.git" ] && [ ! -f "$WT/.git" ]; then
    git -C "$MAIN" worktree add -q --detach "$WT" main
  else
    git -C "$WT" checkout -q -f --detach main
    git -C "$WT" clean -q -fd -e backend/.venv -e frontend/node_modules
  fi
  # Heavy or secret files a clean checkout lacks; linked, never copied into git.
  ln -sfn "$MAIN/backend/.venv" "$WT/backend/.venv"
  ln -sfn "$MAIN/frontend/node_modules" "$WT/frontend/node_modules"
  [ -f "$MAIN/backend/evals/ui/.test-account.json" ] && \
    ln -sfn "$MAIN/backend/evals/ui/.test-account.json" "$WT/backend/evals/ui/.test-account.json"
  return 0
}

run_one() {
  local kind="$1" model="$2" budget="$3"
  local log prompt started rc=0
  log="$STATE/logs/$kind-$(date +%Y-%m-%d-%H%M).log"
  prompt="$(cat "$MAIN/.agents/rnd/$kind.md")"
  started="$(mktemp "$STATE/.started.XXXXXX")"
  echo "[$(date)] $kind run starting (model=$model budget=\$$budget)" >>"$log"
  (
    cd "$WT"
    export AIRA_AUTONOMOUS=1 AIRA_RND_ROOT="$WT" AIRA_RND_OUT="$OUT"
    caffeinate -dimsu timeout "$MAX_SECONDS" claude -p "$prompt" \
      --model "$model" \
      --max-budget-usd "$budget" \
      --permission-mode bypassPermissions \
      --settings "$MAIN/scripts/rnd/fence-settings.json" \
      --add-dir "$OUT" \
      --no-session-persistence
  ) >>"$log" 2>&1 || rc=$?
  echo "[$(date)] $kind run finished (exit $rc)" >>"$log"
  # Success means a fresh report exists, not just a clean exit.
  if [ "$rc" -eq 0 ] && [ "$OUT/LATEST-$kind.md" -nt "$started" ]; then
    notify "$kind report ready" "Open rnd/reports/LATEST-$kind.md"
  else
    notify "$kind run needs a look" "Exit $rc, no fresh report. Log: ~/.aira-rnd/logs/$(basename "$log")"
  fi
  rm -f "$started"
}

main() {
  # One run at a time (mkdir is atomic; macOS has no flock).
  if ! mkdir "$STATE/run.lock" 2>/dev/null; then
    echo "another R&D run is in progress (remove $STATE/run.lock if stale)" >&2; exit 0
  fi
  trap 'rmdir "$STATE/run.lock" 2>/dev/null' EXIT
  command -v timeout >/dev/null || timeout() { shift; "$@"; }
  prepare_worktree
  case "$KIND" in
    night)    run_one night sonnet "$NIGHT_BUDGET" ;;
    strategy) run_one strategy opus "$STRATEGY_BUDGET" ;;
    auto)
      run_one night sonnet "$NIGHT_BUDGET"
      if [ "$(date +%u)" = "7" ]; then run_one strategy opus "$STRATEGY_BUDGET"; fi ;;
    *) echo "usage: $0 night|strategy|auto" >&2; exit 2 ;;
  esac
}

main
