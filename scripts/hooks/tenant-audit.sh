#!/bin/sh
# Advisory only: flags staged route files that never mention tenant_id.
# Kept in a file because lefthook on Windows mangles multi-line inline scripts.
for f in "$@"; do
  if ! grep -q "tenant_id" "$f"; then
    echo "TENANT AUDIT: $f has no tenant_id - verify isolation"
  fi
done
