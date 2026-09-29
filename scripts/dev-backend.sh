#!/usr/bin/env bash
# Start the backend on a laptop in SAFE mode: scheduler paused, outbound messages logged not sent.
# It still uses the LIVE Supabase DB from backend/.env — log in as the UI test tenant only
# (see .agents/context/subsystem-notes.md). Real sends only go to numbers in OUTBOUND_ALLOW_TO.
set -euo pipefail
cd "$(dirname "$0")/../backend"
export SCHEDULER_ENABLED=false
export OUTBOUND_MODE=dry_run
export OUTBOUND_ALLOW_TO="${OUTBOUND_ALLOW_TO:-}"
echo "SAFE LOCAL MODE: scheduler PAUSED, outbound DRY-RUN (allow: ${OUTBOUND_ALLOW_TO:-none}), DB = LIVE"
echo "Point the frontend here with: NEXT_PUBLIC_API_URL=http://localhost:${PORT:-8000} npm run dev"
exec .venv/bin/python -m uvicorn app.main:app --reload --port "${PORT:-8000}"
