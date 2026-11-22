@echo off
setlocal
cd /d "%~dp0..\..\.."
call tools\ensure_environment.cmd
if errorlevel 1 goto failed
if "%~1"=="" goto interactive
".venv\Scripts\python.exe" -m attribution %*
exit /b %errorlevel%
:interactive
".venv\Scripts\python.exe" -m attribution interactive
pause
exit /b 0
:failed
pause
exit /b 1
