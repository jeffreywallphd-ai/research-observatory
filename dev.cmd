@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "LOCAL_TOOLCHAINS=%REPO_ROOT%.local\toolchains"
set "LOCAL_NODE=%LOCAL_TOOLCHAINS%\node-v24.19.0-win-x64"
set "LOCAL_CARGO=%LOCAL_TOOLCHAINS%\cargo"
set "LOCAL_RUSTUP=%LOCAL_TOOLCHAINS%\rustup"
set "LOCAL_PYTHON=%REPO_ROOT%.venv\Scripts"

if not exist "%LOCAL_NODE%\node.exe" (
  echo ERROR: The repository-pinned Node.js runtime is unavailable. Run bootstrap.cmd first. 1>&2
  exit /b 2
)
if not exist "%LOCAL_NODE%\corepack.cmd" (
  echo ERROR: Corepack is unavailable in the repository-pinned Node.js runtime. Run bootstrap.cmd first. 1>&2
  exit /b 2
)
if not exist "%LOCAL_CARGO%\bin\cargo.exe" (
  echo ERROR: The repository-pinned Rust toolchain is unavailable. Run bootstrap.cmd first. 1>&2
  exit /b 2
)
if not exist "%LOCAL_PYTHON%\python.exe" (
  echo ERROR: The repository-pinned Python environment is unavailable. Run bootstrap.cmd first. 1>&2
  exit /b 2
)

set "PATH=%LOCAL_NODE%;%LOCAL_CARGO%\bin;%LOCAL_PYTHON%;%PATH%"
set "COREPACK_HOME=%LOCAL_TOOLCHAINS%\corepack"
set "CARGO_HOME=%LOCAL_CARGO%"
set "RUSTUP_HOME=%LOCAL_RUSTUP%"

pushd "%REPO_ROOT%" >nul
call "%LOCAL_NODE%\corepack.cmd" pnpm dev %*
set "DEV_EXIT_CODE=%errorlevel%"
popd >nul

exit /b %DEV_EXIT_CODE%
