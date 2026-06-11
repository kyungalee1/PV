# PV CIOMS — one-shot dev: backend auto-reload + frontend HMR + open browser
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$pip = Join-Path $root "backend\.venv\Scripts\pip.exe"

if (-not (Test-Path $python)) {
    python -m venv (Join-Path $root "backend\.venv")
    & $pip install -r (Join-Path $root "backend\requirements.txt")
}

& (Join-Path $root "scripts\stop-ports.ps1") -Ports @(8000, 5173)
Start-Sleep -Seconds 1

$uvicornArgs = @(
    "-m", "uvicorn", "app.main:app",
    "--reload",
    "--reload-dir", "app",
    "--reload-include", "*.py",
    "--reload-include", "*.html",
    "--reload-delay", "0.4",
    "--host", "127.0.0.1",
    "--port", "8000"
)

Write-Host ""
Write-Host "=== PV CIOMS Dev ===" -ForegroundColor Cyan
Write-Host "Backend : http://127.0.0.1:8000  (code save -> auto restart)" -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173  (React hot reload)" -ForegroundColor Green
Write-Host "Health  : http://127.0.0.1:8000/api/health" -ForegroundColor Yellow
Write-Host ""
Write-Host "Keep both windows open. Do NOT press Ctrl+C unless you want to stop." -ForegroundColor DarkYellow
Write-Host ""

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\backend'; Write-Host '[BACKEND] Watching app\ for changes...' -ForegroundColor Cyan; & '$python' $($uvicornArgs -join ' ')"
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"
)

Start-Sleep -Seconds 4
Start-Process "http://127.0.0.1:5173"

Write-Host "Browser opened. Edit backend\app\*.py and save — uvicorn reloads automatically." -ForegroundColor Green
