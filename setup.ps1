$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "CyberSLM requires uv. Install it from https://docs.astral.sh/uv/ and rerun this script."
}

Write-Host "Setting up CyberSLM with Python 3.12 and the portable Transformers runtime..."
uv sync --python 3.12 --extra transformers --extra dev

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

New-Item -ItemType Directory -Force -Path "data/uploads" | Out-Null

Write-Host ""
Write-Host "Setup complete. Start CyberSLM with:"
Write-Host "  uv run cyberslm-knowledge sync"
Write-Host "  uv run cyberslm-knowledge verify"
Write-Host "  ./start.ps1"
Write-Host ""
Write-Host "The Gemma model downloads lazily on the first prompt."
Write-Host "For a smoke test without the model, set CYBERSLM_MODEL_BACKEND=mock in .env."
