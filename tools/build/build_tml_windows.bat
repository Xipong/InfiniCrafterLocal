@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_tml_windows.ps1" %*
exit /b %ERRORLEVEL%
