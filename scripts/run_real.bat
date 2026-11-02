@echo off
rem REAL-MONEY runner for KXNEAR15M fair_value (see REAL_MONEY.md). Windows version of run_real.sh.
rem   scripts\run_real.bat              DEMO exchange (fake money)  <- default
rem   scripts\run_real.bat --dry-run    signals only, no key, no orders
rem   scripts\run_real.bat --live       REAL MONEY: asks you to type a phrase
rem Stop: Ctrl+C, or create a file named STOP in the repo folder.
cd /d "%~dp0\.."
if not exist .venv (
  echo First run: creating .venv and installing packages ...
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3.10+ is required & pause & exit /b 1)
  .venv\Scripts\pip install -q -r kalshi15m\requirements.txt
)
if not exist data\kalshi15m mkdir data\kalshi15m
set ARGS=%*
echo %ARGS% | findstr /c:"--live" /c:"--demo" >nul || set ARGS=%ARGS% --demo
:loop
if exist STOP (echo STOP file present: not starting. Delete it to run again. & exit /b 0)
.venv\Scripts\python -u -m kalshi15m real %ARGS%
set CODE=%ERRORLEVEL%
if "%CODE%"=="0" (echo runner stopped cleanly; not restarting. & exit /b 0)
if "%CODE%"=="2" (echo configuration / key / confirmation problem; not restarting. & exit /b 2)
echo runner crashed (exit %CODE%); restarting in 15 s ...
timeout /t 15 /nobreak >nul
goto loop
