#!/usr/bin/env bash
# Dev: run chat backend + frontend in parallel. Ctrl+C kills both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cleanup() { kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

export TUTOR_DEEP_VISION_EXPLAIN="${TUTOR_DEEP_VISION_EXPLAIN:-1}"

PORT_BACKEND="${STATRAG_BACKEND_PORT:-8766}"
echo "[dev] starting backend on :$PORT_BACKEND"
.venv/bin/python -m uvicorn src.services.chat.api:app --reload --port "$PORT_BACKEND" --host 0.0.0.0 &

echo "[dev] starting frontend on :5175"
(cd web && npm run dev) &

wait
