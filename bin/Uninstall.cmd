@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Plugins.ps1" -Action Uninstall %*
pause
