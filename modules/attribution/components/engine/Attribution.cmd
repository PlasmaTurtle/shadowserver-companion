@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run Setup.cmd first.
    pause
    exit /b 1
)
if "%~1"=="" (
    ".venv\Scripts\python.exe" -m attribution interactive
    pause
    exit /b
)
".venv\Scripts\python.exe" -m attribution %*
exit /b %errorlevel%

