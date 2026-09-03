#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "CyberSLM requires uv. Install it from https://docs.astral.sh/uv/ and rerun this script."
  exit 1
fi

echo "Setting up CyberSLM with Python 3.12..."
uv sync --python 3.12 --extra mlx --extra dev

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p data/uploads

echo
echo "Setup complete. Start CyberSLM with:"
echo "  ./start.sh"
echo
echo "The 4-bit Gemma model downloads lazily on the first prompt."
echo "For a quick smoke test without the model, set CYBERSLM_MODEL_BACKEND=mock in .env."
