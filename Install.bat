@echo off
setlocal
cd /d "%~dp0"
title Quotex Vision AI - Installation

echo.
echo ============================================
echo       QUOTEX VISION AI INSTALLER
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher was not found.
    echo.
    echo Please install Python 3.12 from:
    echo https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

echo Creating virtual environment...
py -3.12 -m venv .venv
if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Installation completed.
echo.
echo You can now start the app with:
echo run_app.bat
echo.
pause
endlocal

echo.
echo Source installation completed.
