@echo off
rem Paper-trade the strategies in kalshi15m\live.json on live Kalshi markets.
rem Windows: double-click this file, or run  scripts\run_live.bat  (stop by closing the window)
cd /d "%~dp0\.."
if not exist .venv (
  echo First run: creating .venv and installing packages ...
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3.10+ is required & pause & exit /b 1)
  .venv\Scripts\pip install -q -r kalshi15m\requirements.txt
)
if not exist data\kalshi15m mkdir data\kalshi15m
start "kalshi15m live-report" /min cmd /c "for /l %%i in () do (timeout /t 900 /nobreak >nul & .venv\Scripts\python -m kalshi15m live-report >nul 2>&1)"
echo Paper trading started %date% %time%. Log: data\kalshi15m\bot_log.jsonl
:loop
.venv\Scripts\python -u -m kalshi15m bot --config kalshi15m\live.json
echo bot exited, restarting in 10 s ...
timeout /t 10 /nobreak >nul
goto loop
