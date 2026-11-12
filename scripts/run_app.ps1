# Levanta la app dummie TiendaDemo
# Uso: powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "== TiendaDemo :: http://127.0.0.1:8000  (lab: /lab, API: /docs) ==" -ForegroundColor Cyan
Push-Location (Join-Path $root "apps\dummy")
try {
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
