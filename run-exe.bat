@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0CodexTokenOverlay.exe" (
  "%~dp0CodexTokenOverlay.exe"
  exit /b %errorlevel%
)
echo CodexTokenOverlay.exe not found. Download the GitHub Release asset or run build.ps1.
pause
exit /b 1
