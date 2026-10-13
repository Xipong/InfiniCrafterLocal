@echo off
setlocal
chcp 65001 >nul
if not "%~1"=="" (pushd "%~1") else (pushd "%~dp0..\..")
if errorlevel 1 exit /b 2
if not exist "LocalGenerator\server.py" (
  echo Put this BAT in the extracted Infinicraft root folder.
  pause
  exit /b 2
)
echo Starting the generator directly. Keep this window open; stop with Ctrl+C.
echo This bypasses the GUI's occupied-port and safe-restart checks.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 LocalGenerator\scripts\bootstrap.py server
) else (
  python LocalGenerator\scripts\bootstrap.py server
)
set "RESULT=%ERRORLEVEL%"
echo.
echo Server exited with code %RESULT%. The error above stays visible.
pause
popd
exit /b %RESULT%
