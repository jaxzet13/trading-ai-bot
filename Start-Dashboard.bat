@echo off
REM TradeLab one-click launcher for Windows.
REM Double-click this file to set everything up and open the dashboard.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
    pause
    exit /b 1
)

if not exist .venv (
    echo Creating Python environment ^(first run only^)...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing/updating dependencies ^(may take a few minutes on first run^)...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency install failed. Scroll up for the error, or run this file again.
    pause
    exit /b 1
)

echo.
echo Starting TradeLab dashboard - your browser will open automatically.
echo Close this window or press Ctrl+C to stop.
echo.
python -m tradelab.main web

pause
