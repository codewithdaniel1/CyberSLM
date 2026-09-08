#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -d .venv ]]; then
  echo "CyberSLM is not set up yet. Run ./setup.sh first."
  exit 1
fi

ENV_FILE="${CYBERSLM_ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

API_HOST="${CYBERSLM_API_HOST:-127.0.0.1}"
API_PORT="${CYBERSLM_API_PORT:-8000}"
UI_PORT="${CYBERSLM_UI_PORT:-8501}"
API_LOG="${TMPDIR:-/tmp}/cyberslm-api.log"

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "CyberSLM starting..."
echo "Model: ${CYBERSLM_MODEL_ID:-backend default}"
echo "Backend: ${CYBERSLM_MODEL_BACKEND:-auto}"
echo "Mode: Local"

uv run uvicorn cyberslm.api:app --host "$API_HOST" --port "$API_PORT" >"$API_LOG" 2>&1 &
API_PID=$!

for _ in {1..40}; do
  if curl --silent --fail "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "The API failed to start. Log output:"
    tail -n 80 "$API_LOG"
    exit 1
  fi
  sleep 0.25
done

if ! curl --silent --fail "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
  echo "The API did not become ready. See $API_LOG"
  exit 1
fi

echo "UI: http://localhost:${UI_PORT}"
echo "API docs: http://${API_HOST}:${API_PORT}/docs"
echo

uv run streamlit run ui/app.py \
  --server.address 127.0.0.1 \
  --server.port "$UI_PORT" \
  --server.headless true \
  --browser.gatherUsageStats false
