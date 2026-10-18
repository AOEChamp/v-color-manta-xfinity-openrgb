@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Bridge.ps1" -Action Install %*
if errorlevel 1 pause
