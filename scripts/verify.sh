#!/usr/bin/env bash
# `make verify` — one answer to "is it really done?". Runs every check that exists and
# prints PASS / FAIL / SKIPPED per stage; exits non-zero if anything FAILED.
#
#   backend      pytest (python -m pytest, from backend/ — see CLAUDE.md)
#   frontend     typecheck + lint
#   fence        the unattended-run safety fence (scripts/rnd/test_fence.py)
#   ui-live      read-only Playwright checks on the LIVE site as the UI test account
#                (skipped without backend/evals/ui/.test-account.json)
#   evals        AI reply evals — only with AIRA_EVAL_KEY_TENANT set to a TEST tenant
#                with its own API key (never a client's key: see run_aira.py)
#
# VERIFY_SKIP="ui-live evals" skips stages by name.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$(mktemp -d "${TMPDIR:-/tmp}/aira-verify.XXXXXX")"
PY="$ROOT/backend/.venv/bin/python"
declare -a NAMES=() RESULTS=()
FAILED=0

skipped() {  # "ui-live" in VERIFY_SKIP also skips every "ui-live:<check>" stage
  local name="$1" entry
  for entry in ${VERIFY_SKIP:-}; do
    [[ "$name" == "$entry" || "$name" == "$entry:"* ]] && return 0
  done
  return 1
}

stage() {
  local name="$1"; shift
  if skipped "$name"; then
    NAMES+=("$name"); RESULTS+=("SKIPPED (VERIFY_SKIP)"); return
  fi
  echo "▶ $name"
  if (cd "$ROOT" && "$@") >"$LOGS/$name.log" 2>&1; then
    NAMES+=("$name"); RESULTS+=("PASS")
  else
    NAMES+=("$name"); RESULTS+=("FAIL (log: $LOGS/$name.log)"); FAILED=1
    tail -15 "$LOGS/$name.log" | sed 's/^/    /'
  fi
}

skip() { NAMES+=("$1"); RESULTS+=("SKIPPED — $2"); }

# Same placeholders as CI: the suite never talks to a real database, and a clean worktree
# (the R&D runs) has no backend/.env.
stage backend bash -c "cd backend && SUPABASE_URL=\${SUPABASE_URL:-https://dummy.supabase.co} SUPABASE_SERVICE_KEY=\${SUPABASE_SERVICE_KEY:-dummy} '$PY' -m pytest -q -p no:cacheprovider"
stage frontend-types bash -c "cd frontend && npm run -s typecheck"
stage frontend-lint bash -c "cd frontend && npm run -s lint"
stage fence "$PY" -m pytest -q -p no:cacheprovider scripts/rnd/test_fence.py

if [ -f "$ROOT/backend/evals/ui/.test-account.json" ]; then
  for check in "$ROOT"/backend/evals/ui/check_*.js; do
    stage "ui-live:$(basename "$check" .js)" node "$check"
  done
else
  skip ui-live "no backend/evals/ui/.test-account.json on this machine"
fi

if [ -n "${AIRA_EVAL_KEY_TENANT:-}" ]; then
  stage evals bash -c "cd backend && '$PY' -m evals.conversations.run_aira --key-tenant '$AIRA_EVAL_KEY_TENANT' --test-key-tenant --no-judge"
else
  skip evals "set AIRA_EVAL_KEY_TENANT to a TEST tenant with its own API key"
fi

echo
echo "── verify summary ──────────────────────────────"
for i in "${!NAMES[@]}"; do printf '  %-32s %s\n' "${NAMES[$i]}" "${RESULTS[$i]}"; done
echo "────────────────────────────────────────────────"
[ "$FAILED" -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit "$FAILED"
