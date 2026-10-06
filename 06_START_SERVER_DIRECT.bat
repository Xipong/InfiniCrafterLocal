@echo off
setlocal
chcp 65001 >nul
if not "%~1"=="" (cd /d "%~1") else (cd /d "%~dp0")
if not exist "LocalGenerator\server.py" (
  echo Put this BAT beside 04_OPEN_SETTINGS_GUI.bat in the InfiniCrafterLocal folder.
  pause
  exit /b 2
)
echo Starting the generator directly, without the GUI/proxy health guard.
echo Keep this window open. Stop the server with Ctrl+C.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -u -B LocalGenerator\server.py
) else (
  python -u -B LocalGenerator\server.py
)
set "RESULT=%ERRORLEVEL%"
echo.
echo Server exited with code %RESULT%. The error above stays visible.
pause
exit /b %RESULT%
