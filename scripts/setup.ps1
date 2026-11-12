# Setup del Laboratorio QA (M0-M1: app dummie)
# Uso: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== Laboratorio QA :: setup ==" -ForegroundColor Cyan

# 1. Entorno virtual
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[1/4] Creando venv..."
    python -m venv (Join-Path $root ".venv")
} else {
    Write-Host "[1/4] venv ya existe (ok)"
}

# 2. Dependencias de la app dummie + del agente QA
Write-Host "[2/4] Instalando dependencias..."
& $venvPython -m pip install --disable-pip-version-check -q -r (Join-Path $root "apps\dummy\requirements.txt")
& $venvPython -m pip install --disable-pip-version-check -q -r (Join-Path $root "qa_agent\requirements.txt")

# 3. .env si no existe
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Write-Host "[3/4] .env creado desde .env.example"
} else {
    Write-Host "[3/4] .env ya existe (ok)"
}

# 4. Verificacion: correr la suite de la app
Write-Host "[4/4] Corriendo tests de la app dummie..."
Push-Location (Join-Path $root "apps\dummy")
& $venvPython -m pytest tests
$code = $LASTEXITCODE
Pop-Location

if ($code -eq 0) {
    Write-Host "`nSetup completo. Para levantar la app: powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1" -ForegroundColor Green
} else {
    Write-Host "`nSetup termino con errores en los tests." -ForegroundColor Red
    exit $code
}
