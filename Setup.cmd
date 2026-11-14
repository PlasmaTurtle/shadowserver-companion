@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto pythonfallback
py -3 tools\setup_environment.py
exit /b %errorlevel%
:pythonfallback
python tools\setup_environment.py
exit /b %errorlevel%
