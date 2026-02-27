@echo off
setlocal

cd /d "%~dp0"

:: Check for Python
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Check for venv and create if needed
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
    echo Setup complete.
)

:: Validate core deps; install/repair if missing
.venv\Scripts\python.exe -c "import sv_ttk" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies detected. Installing requirements...
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: Launch app
.venv\Scripts\python.exe main.py %*