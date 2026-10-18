@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Bridge.ps1" -Action Uninstall %*
if errorlevel 1 pause
