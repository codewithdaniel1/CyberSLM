$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "CyberSLM requires uv. Install it from https://docs.astral.sh/uv/ and rerun this script."
}

Write-Host "Setting up the format-neutral CyberSLM model toolkit with Python 3.12..."
uv sync --python 3.12 --extra dev

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

New-Item -ItemType Directory -Force -Path "data/training" | Out-Null
New-Item -ItemType Directory -Force -Path "data/adapters" | Out-Null
New-Item -ItemType Directory -Force -Path "data/knowledge" | Out-Null

Write-Host ""
Write-Host "Setup complete. Useful next commands:"
Write-Host "  uv run cyberslm-knowledge sync"
Write-Host "  uv run cyberslm-knowledge verify"
Write-Host "  uv run cyberslm-train --help"
Write-Host "  uv run cyberslm-eval --help"
Write-Host ""
Write-Host "Install only the runtime needed for a task: --extra mlx or --extra transformers."
