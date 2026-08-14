@echo off
setlocal
cd /d "%~dp0.."
if exist "%~dp0..\dist\CodexRuntimeHUD.exe" (
  "%~dp0..\dist\CodexRuntimeHUD.exe"
  exit /b %errorlevel%
)
echo CodexRuntimeHUD.exe not found. Download the GitHub Release asset or run scripts\build.ps1.
pause
exit /b 1
