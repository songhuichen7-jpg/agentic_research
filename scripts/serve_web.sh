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

PORT=8000
if PIDS=$(lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -t 2>/dev/null); then
  echo "Port ${PORT} in use; stopping PID(s): ${PIDS}" >&2
  kill ${PIDS} 2>/dev/null || true
  sleep 0.5
fi

VENV_PY="${ROOT}/.venv/bin/python"
if [[ -x "${VENV_PY}" ]]; then
  exec "${VENV_PY}" -m uvicorn src.api.server:app --host 127.0.0.1 --port "${PORT}" "$@"
else
  exec python3 -m uvicorn src.api.server:app --host 127.0.0.1 --port "${PORT}" "$@"
fi
