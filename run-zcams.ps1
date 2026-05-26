$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "cfa-dash"
$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
$Requirements = Join-Path $AppDir "requirements.txt"
$EnvExample = Join-Path $AppDir ".env.example"
$EnvFile = Join-Path $AppDir ".env"

if (-not (Test-Path $AppDir)) {
    throw "Cannot find app directory: $AppDir"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is required. Install Python 3.11+ and try again."
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating Python virtual environment..."
    Push-Location $AppDir
    python -m venv .venv
    Pop-Location
}

if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created .env from .env.example"
}

Write-Host "Installing dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r $Requirements

$Port = 8050
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "Starting ZCAMS Dash for ZAFFA Clearing & Forwarding..."
Write-Host "Open http://127.0.0.1:8050/login (hard refresh if the page was blank before)"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

Push-Location $AppDir
& $VenvPython app.py
Pop-Location
