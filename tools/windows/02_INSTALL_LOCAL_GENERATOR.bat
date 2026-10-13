@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0..\.."
if errorlevel 1 exit /b 2
echo Preparing an isolated Python environment for Infinicraft...
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 LocalGenerator\scripts\bootstrap.py setup
) else (
  python LocalGenerator\scripts\bootstrap.py setup
)
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Setup failed. Read the error above; dependencies were not marked ready.
pause
popd
exit /b %RESULT%
