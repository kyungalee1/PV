# PV CIOMS - start backend and frontend (Windows)
$root = $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$pip = Join-Path $root "backend\.venv\Scripts\pip.exe"

if (-not (Test-Path $python)) {
  python -m venv (Join-Path $root "backend\.venv")
  & $pip install -r (Join-Path $root "backend\requirements.txt")
}

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd '$root\backend'; & '$python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd '$root\frontend'; npm install; npm run dev"
)

Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://localhost:5173"
