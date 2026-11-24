@echo off
setlocal
chcp 65001 >nul
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%~dp0generator\scripts\bootstrap.py" %*
) else (
  python "%~dp0generator\scripts\bootstrap.py" %*
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo Could not open Infinicraft. Read the error above.
  echo Python 3.11+ is required. Download: https://www.python.org/downloads/
  pause
)
exit /b %RESULT%
