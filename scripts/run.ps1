# One-command local demo (Windows PowerShell).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
pip install -q -r backend/requirements.txt
python -m playwright install chromium | Out-Null

if (-not (Test-Path "frontend\dist\index.html")) {
    Push-Location frontend
    npm install --no-audit --no-fund
    npm run build
    Pop-Location
}

Write-Host "Dashboard: http://127.0.0.1:8000/app/" -ForegroundColor Cyan
python -m uvicorn backend.app.main:app --port 8000
