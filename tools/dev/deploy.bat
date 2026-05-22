@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if exist "%PROJECT_ROOT%\.env.local.bat" call "%PROJECT_ROOT%\.env.local.bat"
if not defined MODAL_GPU set "MODAL_GPU=L40S"
if not defined MODAL_APP_NAME set "MODAL_APP_NAME=forge-neo-modal-l40s"
if not defined MODAL_VOLUME_NAME set "MODAL_VOLUME_NAME=forge-neo-modal-data"
modal deploy app/modal_app.py
if errorlevel 1 (
  echo.
  echo Deploy failed.
  pause
  exit /b 1
)
echo.
echo Deploy complete.
echo Use start-server.bat from the project root to open Forge Neo.
echo Use stop-server.bat from the project root to let the GPU container sleep while keeping the URL.
echo Use tools\dev\stop.bat only when you want to stop the deployed app itself.
pause
