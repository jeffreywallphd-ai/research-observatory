@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup-pinned-runtimes.ps1" %*
exit /b %errorlevel%
