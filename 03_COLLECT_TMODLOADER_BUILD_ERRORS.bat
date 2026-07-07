@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%tools\collect_tml_build_errors_windows.ps1" %*
exit /b %ERRORLEVEL%
