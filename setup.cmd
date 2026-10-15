@echo off
setlocal
call "%~dp0setup-pinned-runtimes.cmd" -RepoRoot "%~dp0." -RunBootstrap %*
set "SETUP_EXIT_CODE=%errorlevel%"
if not "%SETUP_EXIT_CODE%"=="0" exit /b %SETUP_EXIT_CODE%
rem Add later setup steps here, retaining the failure handling above.
exit /b 0
