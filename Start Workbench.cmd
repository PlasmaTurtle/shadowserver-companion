@echo off
setlocal
cd /d "%~dp0"
set /p WORKBENCH_VERSION=<VERSION
if not exist ".venv\Scripts\python.exe" goto setup
if not exist ".venv\workbench-version.txt" goto setup
findstr /x /c:"%WORKBENCH_VERSION%" ".venv\workbench-version.txt" >nul
if not errorlevel 1 goto run
:setup
call Setup.cmd
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
exit /b 0
:failed
pause
exit /b 1
