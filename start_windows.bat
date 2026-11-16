@echo off
setlocal EnableExtensions
REM Starts TalentBridge and opens it in your browser. Keep this window open while you use the app; close it (or Ctrl+C) to stop.
REM Extra options are passed on, e.g.:  start_windows.bat --port 5051
cd /d "%~dp0"
title TalentBridge
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up TalentBridge ...
  set TB_NO_PAUSE=1
  call setup_windows.bat
  set TB_NO_PAUSE=
  if not exist ".venv\Scripts\python.exe" goto :fail
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" run.py --open %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo TalentBridge stopped with an error (see above). WINDOWS_SETUP_GUIDE.md lists common fixes.
if not defined TB_NO_PAUSE pause
exit /b 1
