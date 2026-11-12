# Levanta el servidor de desarrollo de Temporal (persistencia local en artifacts\)
# Uso: powershell -ExecutionPolicy Bypass -File scripts\temporal_dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cli = Join-Path $root "tools\temporal\temporal.exe"

if (-not (Test-Path $cli)) {
    Write-Error "No se encontro $cli - ejecuta scripts\setup.ps1 o descarga el CLI de Temporal."
}

Write-Host "== Temporal dev server ==" -ForegroundColor Cyan
Write-Host "   Frontend : http://localhost:7233"
Write-Host "   Web UI   : http://localhost:8233"
Write-Host "   Ctrl+C para detener`n"

& $cli server start-dev --port 7233 --ui-port 8233 `
    --db-filename (Join-Path $root "artifacts\temporal-dev.db") `
    --log-level error
