@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%~dp0"
if exist ".env.local.bat" call ".env.local.bat"
if not defined MODAL_APP_NAME set "MODAL_APP_NAME=forge-neo-modal-l40s"

python app\scale_down.py
if errorlevel 1 (
  echo.
  echo Scale-down request failed.
  pause
  exit /b 1
)

echo.
echo Scale-down requested. The app URL stays deployed; the next visit will cold-start a container.
pause
