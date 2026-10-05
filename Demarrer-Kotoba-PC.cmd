@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-pc.ps1" -ShowPairing
if errorlevel 1 pause
