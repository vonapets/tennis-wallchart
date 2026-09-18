#!/bin/bash
# Sync, rank and rebuild, with logging. Safe to run from cron.
#   ./run.sh              always runs
#   ./run.sh --scheduled  no-ops if the data is already fresher than four hours
set -uo pipefail
cd "$(dirname "$0")" || exit 1
mkdir -p logs
LOG="logs/$(date +%Y-%m-%d).log"

if [ "${1:-}" = "--scheduled" ] && [ -f data/fixtures.json ]; then
  age=$(( $(date +%s) - $(stat -f %m data/fixtures.json 2>/dev/null || echo 0) ))
  if [ "$age" -lt 14400 ]; then
    echo "$(date -u +%FT%TZ) fresh ($((age/60))m) - skipping" >> "$LOG"
    exit 0
  fi
fi

{
  echo "=== $(date -u +%FT%TZ) ==="
  python3 sync.py  || { echo "sync failed - keeping previous page"; exit 1; }
  python3 picks.py || echo "picks failed - page will use the previous ranking"
  python3 build.py || { echo "build failed"; exit 1; }
} >> "$LOG" 2>&1
