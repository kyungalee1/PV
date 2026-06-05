# PV CIOMS backend — port 8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    python -m venv .venv
    & (Join-Path $PSScriptRoot ".venv\Scripts\pip.exe") install -r requirements.txt
}

Write-Host "Starting backend at http://127.0.0.1:8000"
& $python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
