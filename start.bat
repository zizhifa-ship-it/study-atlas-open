@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" server.py --open %*
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 server.py --open %*
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python server.py --open %*
  goto done
)
echo Python 3.9 or newer is required. Install it from https://www.python.org/downloads/
:done
pause
