@echo off
setlocal
if "%~1"=="" (
  echo Drag a saved request JSON onto this file.
  pause
  exit /b 2
)
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0prompt_audit.py" "%~1"
) else (
  py -3 "%~dp0prompt_audit.py" "%~1"
)
if errorlevel 1 (
  pause
  exit /b 2
)
echo Open the .audit.html file next to your JSON.
pause
