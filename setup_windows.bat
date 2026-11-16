@echo off
setlocal EnableExtensions
REM One-time setup on Windows 10/11: creates .venv and installs TalentBridge's packages.
REM Needs Python 3.10 or newer from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH").
REM Usage: double-click, or in Command Prompt / PowerShell:  setup_windows.bat [dev] [postgres] [anthropic]
cd /d "%~dp0"
title TalentBridge setup

set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo Python was not found.
  echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
  echo During installation tick "Add python.exe to PATH", then run this file again.
  echo If typing "python" opens the Microsoft Store, turn off the "App execution aliases" for python in Windows Settings.
  goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" || (
  echo Python 3.10 or newer is required. This computer has:
  %PY% --version
  goto :fail
)
echo Using:
%PY% --version

if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment in .venv ...
  %PY% -m venv .venv || goto :fail
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install -r requirements.txt || goto :fail
for %%A in (%*) do (
  if /I "%%~A"=="dev" "%VPY%" -m pip install -r requirements-dev.txt || goto :fail
  if /I "%%~A"=="postgres" "%VPY%" -m pip install -r requirements-postgres.txt || goto :fail
  if /I "%%~A"=="anthropic" "%VPY%" -m pip install -r requirements-anthropic.txt || goto :fail
)
if not exist .env copy .env.example .env >nul

echo.
where tesseract >nul 2>nul || if not exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
  echo Optional: to read scanned CVs, install Tesseract OCR - see WINDOWS_SETUP_GUIDE.md, step 5.
)
REM Free AI (optional, no account, runs on this PC). The app works without it, using the built-in rule-based engine.
set "HAVE_OLLAMA="
where ollama >nul 2>nul && set "HAVE_OLLAMA=1"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "HAVE_OLLAMA=1"
if not defined HAVE_OLLAMA (
  where winget >nul 2>nul && (
    echo Installing the free AI engine ^(Ollama^) ... this can take a few minutes. Close this window to skip.
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
  )
)
where ollama >nul 2>nul || if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
  echo Optional: for the free AI features, install Ollama from https://ollama.com/download and start TalentBridge again.
  echo           TalentBridge finds it by itself and downloads its model the first time. No account or payment is needed.
)
echo.
echo Setup finished.
echo   Start the app:        double-click start_windows.bat  (it opens http://localhost:5050)
echo   Demo with sample data: double-click start_demo_windows.bat
echo   Check everything:      double-click test_windows.bat
if not defined TB_NO_PAUSE pause
exit /b 0

:fail
echo.
echo Setup did not finish. See the messages above and WINDOWS_SETUP_GUIDE.md ("If something goes wrong").
if not defined TB_NO_PAUSE pause
exit /b 1
