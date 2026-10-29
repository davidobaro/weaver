#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ "${WEAVER_MODE:-}" != demo ]; then
  echo "The hosted entry point requires WEAVER_MODE=demo." >&2
  exit 1
fi
# One process owns the ephemeral session registry and bounded background queue.
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-access-log
