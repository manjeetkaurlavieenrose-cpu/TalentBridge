@echo off
setlocal EnableExtensions
REM Checks that TalentBridge works on this Windows computer:
REM   1. the automated test suite (about 160 tests, 1-3 minutes)
REM   2. an end-to-end check that starts the real app on a spare port with a temporary data folder
REM Your own data is not touched. Results are also saved to test-results-windows.txt.
cd /d "%~dp0"
title TalentBridge tests
if not exist ".venv\Scripts\python.exe" (
  set TB_NO_PAUSE=1
  call setup_windows.bat dev
  set TB_NO_PAUSE=
  if not exist ".venv\Scripts\python.exe" goto :fail
)
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -c "import reportlab" >nul 2>nul || "%VPY%" -m pip install -r requirements-dev.txt || goto :fail
set PYTHONUTF8=1
set "LOG=%~dp0test-results-windows.txt"
echo TalentBridge Windows test run, %DATE% %TIME% > "%LOG%"
ver >> "%LOG%"
"%VPY%" --version >> "%LOG%" 2>&1

echo.
echo [1/2] Automated tests ...
pushd backend
"%VPY%" -m unittest discover -s tests -t . >> "%LOG%" 2>&1
set "UNIT=%ERRORLEVEL%"
popd
if "%UNIT%"=="0" (echo       passed) else (echo       FAILED - details in test-results-windows.txt)

echo [2/2] End-to-end check of the running app ...
"%VPY%" scripts\smoke_test.py >> "%LOG%" 2>&1
set "SMOKE=%ERRORLEVEL%"
if "%SMOKE%"=="0" (echo       passed) else (echo       FAILED - details in test-results-windows.txt)

echo.
if "%UNIT%%SMOKE%"=="00" (
  echo ALL CHECKS PASSED on this computer.
  echo ALL CHECKS PASSED >> "%LOG%"
  if not defined TB_NO_PAUSE pause
  exit /b 0
)
echo SOME CHECKS FAILED. Open test-results-windows.txt to see which.
echo SOME CHECKS FAILED >> "%LOG%"
:fail
if not defined TB_NO_PAUSE pause
exit /b 1
