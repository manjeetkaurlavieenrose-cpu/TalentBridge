@echo off
setlocal EnableExtensions
REM Starts a demonstration copy with fictional candidates, applications and scored assessments.
REM Demo data is kept in the "demo-data" folder, separate from real data in "data".
cd /d "%~dp0"
title TalentBridge demo
if not exist ".venv\Scripts\python.exe" (
  set TB_NO_PAUSE=1
  call setup_windows.bat
  set TB_NO_PAUSE=
  if not exist ".venv\Scripts\python.exe" goto :fail
)
set "DATA_DIR=%~dp0demo-data"
set DEMO_SEED=1
set PYTHONUTF8=1
".venv\Scripts\python.exe" run.py --load-demo-candidates --open %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo The demo stopped with an error (see above). WINDOWS_SETUP_GUIDE.md lists common fixes.
if not defined TB_NO_PAUSE pause
exit /b 1
