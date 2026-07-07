@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Installing Python requirements for InfiniCrafterLocal...
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m pip install -r LocalGenerator\requirements.txt
) else (
  python -m pip install -r LocalGenerator\requirements.txt
)
echo.
echo Done. If there were errors, install Python 3.11+ and tick "Add Python to PATH".
pause
