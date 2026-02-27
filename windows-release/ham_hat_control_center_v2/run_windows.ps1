#Requires -Version 5.1
<#
.SYNOPSIS
    Launch HAM HAT Control Center v2 on Windows.
.DESCRIPTION
    Creates a Python virtual environment on first run, installs requirements,
    then launches the application. Subsequent runs reuse the existing venv.
.EXAMPLE
    .\run_windows.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    # Check Python
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Error "Python 3.10+ not found. Download from https://python.org"
        exit 1
    }

    # Create venv if missing
    $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Host "Creating virtual environment..." -ForegroundColor Cyan
        python -m venv .venv
        Write-Host "Installing dependencies..." -ForegroundColor Cyan
        & $venvPy -m pip install --upgrade pip -q
        & $venvPy -m pip install -r requirements.txt -q
        Write-Host "Setup complete." -ForegroundColor Green
    }

    # Launch
    & $venvPy main.py @args
}
finally {
    Pop-Location
}
