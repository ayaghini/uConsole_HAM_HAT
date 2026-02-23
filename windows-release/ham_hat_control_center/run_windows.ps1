param(
  [switch]$Build
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (!(Test-Path '.venv')) {
  py -3 -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if ($Build) {
  python -m pip install pyinstaller
  pyinstaller --noconfirm --onefile --name ham-hat-control app\main.py
  Write-Host 'Build output: dist\ham-hat-control.exe'
} else {
  python app\main.py
}
