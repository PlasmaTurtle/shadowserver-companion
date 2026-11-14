@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    set "ATTRIBUTION_PYTHON=python"
) else (
    set "ATTRIBUTION_PYTHON=py -3"
)
%ATTRIBUTION_PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo Python 3.11 or newer is required. Install Python and run Setup.cmd again.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    %ATTRIBUTION_PYTHON% -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse --require-hashes -r requirements-windows.txt
if errorlevel 1 (
    echo Setup failed. Keep the wheelhouse directory beside this script.
    pause
    exit /b 1
)
echo.
echo Setup complete. Double-click Attribution.cmd for an interactive lookup.
echo Command line: Attribution.cmd check google.com 8.8.8.8 --export exports\google
pause

