# PV CIOMS backend — port 8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$stopScript = Join-Path (Split-Path $PSScriptRoot -Parent) "scripts\stop-ports.ps1"
if (Test-Path $stopScript) {
    & $stopScript -Ports @(8000)
    Start-Sleep -Seconds 1
}
if (-not (Test-Path $python)) {
    python -m venv .venv
    & (Join-Path $PSScriptRoot ".venv\Scripts\pip.exe") install -r requirements-dev.txt
}

Write-Host "Starting backend at http://127.0.0.1:8000"
Write-Host "Auto-reload ON — save any file under app\ to restart (keep this window open)."
& $python -m uvicorn app.main:app `
    --reload `
    --reload-dir app `
    --reload-include "*.py" `
    --reload-include "*.html" `
    --reload-delay 0.4 `
    --host 127.0.0.1 `
    --port 8000
