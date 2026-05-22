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
modal run app/modal_app.py::startup_check
pause
