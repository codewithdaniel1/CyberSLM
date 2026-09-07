$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Error "CyberSLM is not set up yet. Run ./setup.ps1 first."
}

if (Test-Path ".env") {
    foreach ($line in Get-Content ".env") {
        if ($line -match '^\s*([^#=][^=]*)=(.*)$') {
            $name = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$apiHost = if ($env:CYBERSLM_API_HOST) { $env:CYBERSLM_API_HOST } else { "127.0.0.1" }
$apiPort = if ($env:CYBERSLM_API_PORT) { $env:CYBERSLM_API_PORT } else { "8000" }
$uiPort = if ($env:CYBERSLM_UI_PORT) { $env:CYBERSLM_UI_PORT } else { "8501" }
$apiLog = Join-Path ([System.IO.Path]::GetTempPath()) "cyberslm-api.log"
$apiErrorLog = Join-Path ([System.IO.Path]::GetTempPath()) "cyberslm-api-error.log"
$uv = (Get-Command uv).Source

Write-Host "CyberSLM starting..."
Write-Host "Backend: $(if ($env:CYBERSLM_MODEL_BACKEND) { $env:CYBERSLM_MODEL_BACKEND } else { 'auto' })"
Write-Host "Mode: Local"

$apiProcess = Start-Process -FilePath $uv `
    -ArgumentList @("run", "uvicorn", "cyberslm.api:app", "--host", $apiHost, "--port", $apiPort) `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErrorLog `
    -NoNewWindow `
    -PassThru

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($apiProcess.HasExited) {
            Write-Host "The API failed to start. Log output:"
            if (Test-Path $apiLog) { Get-Content $apiLog -Tail 80 }
            if (Test-Path $apiErrorLog) { Get-Content $apiErrorLog -Tail 80 }
            exit 1
        }
        try {
            Invoke-WebRequest "http://${apiHost}:${apiPort}/api/health" -UseBasicParsing | Out-Null
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }

    if (-not $ready) {
        Write-Error "The API did not become ready. See $apiLog and $apiErrorLog"
    }

    Write-Host "UI: http://localhost:${uiPort}"
    Write-Host "API docs: http://${apiHost}:${apiPort}/docs"
    Write-Host ""

    uv run streamlit run ui/app.py `
        --server.address 127.0.0.1 `
        --server.port $uiPort `
        --server.headless true `
        --browser.gatherUsageStats false
}
finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
        $apiProcess.WaitForExit()
    }
}
