@echo off
setlocal

set "LOCAL_TOOLCHAINS=%~dp0.local\toolchains"
set "LOCAL_NODE=%LOCAL_TOOLCHAINS%\node-v24.19.0-win-x64"
set "LOCAL_CARGO=%LOCAL_TOOLCHAINS%\cargo"
set "LOCAL_RUSTUP=%LOCAL_TOOLCHAINS%\rustup"

if exist "%LOCAL_NODE%\node.exe" (
  set "PATH=%LOCAL_NODE%;%PATH%"
  set "COREPACK_HOME=%LOCAL_TOOLCHAINS%\corepack"
)
if exist "%LOCAL_CARGO%\bin\cargo.exe" (
  set "PATH=%LOCAL_CARGO%\bin;%PATH%"
  set "CARGO_HOME=%LOCAL_CARGO%"
  set "RUSTUP_HOME=%LOCAL_RUSTUP%"
)
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PATH=%~dp0.venv\Scripts;%PATH%"
)

where python.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is unavailable. Install the version pinned in .python-version, ensure python is on PATH, and rerun bootstrap.cmd. 1>&2
  exit /b 2
)

python.exe "%~dp0tools\bootstrap.py" --repo "%~dp0."
exit /b %errorlevel%
