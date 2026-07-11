@echo off
setlocal
set ROOT=%~dp0
powershell -ExecutionPolicy Bypass -File "%ROOT%tools\validate_release_windows.ps1" -RequireBuild %*
exit /b %ERRORLEVEL%
