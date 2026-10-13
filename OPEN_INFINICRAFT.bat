@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 2
set "ACTION=gui"
if not "%~1"=="" set "ACTION=%~1"
echo Infinicraft: %ACTION%
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 LocalGenerator\scripts\bootstrap.py "%ACTION%"
) else (
  python LocalGenerator\scripts\bootstrap.py "%ACTION%"
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo Could not open Infinicraft. Read the error above.
  echo Python 3.11+ with Tcl/Tk is required. Download: https://www.python.org/downloads/
  pause
)
popd
exit /b %RESULT%
