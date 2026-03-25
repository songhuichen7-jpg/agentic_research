#!/usr/bin/env bash
# Sprint 7d: build React assets and serve API + static UI on one port.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build
cd "$ROOT"
exec uvicorn src.api.server:app --host 127.0.0.1 --port 8000 "$@"
