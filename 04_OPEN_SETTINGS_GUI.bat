@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Starting InfiniCrafterLocal settings GUI...
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 LocalGenerator\settings_gui.py
) else (
  python LocalGenerator\settings_gui.py
)
if %ERRORLEVEL% NEQ 0 pause
