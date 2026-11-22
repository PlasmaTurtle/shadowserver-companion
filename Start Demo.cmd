@echo off
setlocal
cd /d "%~dp0"
call tools\ensure_environment.cmd
if errorlevel 1 goto failed
".venv\Scripts\python.exe" run.py --demo
if errorlevel 1 goto failed
exit /b 0
:failed
pause
exit /b 1
