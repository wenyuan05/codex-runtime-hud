@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 codex_hud.py
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python codex_hud.py
  exit /b %errorlevel%
)
echo [Codex HUD] Python 3 not found.
echo Install Python 3.10+ from python.org, then run this file again.
pause
exit /b 1
