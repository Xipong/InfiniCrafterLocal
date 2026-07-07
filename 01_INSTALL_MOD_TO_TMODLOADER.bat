@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 tools\install_to_tmodloader_modsources.py
) else (
  python tools\install_to_tmodloader_modsources.py
)
