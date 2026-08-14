@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 codex_hud.py --debug
  exit /b %errorlevel%
)
python codex_hud.py --debug
