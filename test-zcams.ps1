$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "cfa-dash"
$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
$TmpDir = Join-Path $AppDir "pytest-tmp"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment missing. Run .\run-zcams.ps1 first."
    exit 1
}

Push-Location $AppDir
& $VenvPython -m pytest -p no:cacheprovider --basetemp=$TmpDir
Pop-Location
