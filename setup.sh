#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "CyberSLM requires uv. Install it from https://docs.astral.sh/uv/ and rerun this script."
  exit 1
fi

RUNTIME_EXTRA="transformers"
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
  RUNTIME_EXTRA="mlx"
fi

echo "Setting up CyberSLM with Python 3.12 and the ${RUNTIME_EXTRA} runtime..."
uv sync --python 3.12 --extra "$RUNTIME_EXTRA" --extra dev

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p data/uploads

echo
echo "Setup complete. Start CyberSLM with:"
echo "  uv run cyberslm-knowledge sync"
echo "  uv run cyberslm-knowledge verify"
echo "  ./start.sh"
echo
echo "The selected Gemma model downloads lazily on the first prompt."
echo "For a quick smoke test without a model, set CYBERSLM_MODEL_BACKEND=mock in .env."
