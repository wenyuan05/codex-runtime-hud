@echo off
setlocal
cd /d "%~dp0.."
if exist "%~dp0..\dist\CodexTokenOverlay.exe" (
  "%~dp0..\dist\CodexTokenOverlay.exe"
  exit /b %errorlevel%
)
echo CodexTokenOverlay.exe not found. Download the GitHub Release asset or run scripts\build.ps1.
pause
exit /b 1
