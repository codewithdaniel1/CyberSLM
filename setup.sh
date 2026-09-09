#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "CyberSLM requires uv. Install it from https://docs.astral.sh/uv/ and rerun this script."
  exit 1
fi

echo "Setting up the format-neutral CyberSLM model toolkit with Python 3.12..."
uv sync --python 3.12 --extra dev

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p data/training data/adapters data/knowledge

echo
echo "Setup complete. Useful next commands:"
echo "  uv run cyberslm-knowledge sync"
echo "  uv run cyberslm-knowledge verify"
echo "  uv run cyberslm-train --help"
echo "  uv run cyberslm-eval --help"
echo
echo "Install only the runtime needed for a task: --extra mlx or --extra transformers."
