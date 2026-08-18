@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Installing first-run environment...
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python 3.12 was not found.
        echo Please install Python 3.12 and run Install.bat.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

".venv\Scripts\python.exe" main.py
endlocal
