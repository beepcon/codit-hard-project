@echo off
rem Double-click to run: first time installs into .venv, then starts the app (see src\start_app.py)
chcp 65001 > nul
cd /d "%~dp0"
set "PY="
py -3.12 -c "import sys" > nul 2>&1 && set "PY=py -3.12"
if not defined PY python -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" > nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3.12 not found. Install Python 3.12 from https://www.python.org and run start.bat again.
  pause
  exit /b 1
)
%PY% src\start_app.py
if errorlevel 1 pause
