@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is unavailable. Install the version pinned in .python-version, ensure python is on PATH, and rerun bootstrap.cmd. 1>&2
  exit /b 2
)

python "%~dp0tools\bootstrap.py" --repo "%~dp0."
exit /b %errorlevel%
