@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if exist "%PROJECT_ROOT%\.env.local.bat" call "%PROJECT_ROOT%\.env.local.bat"
if not defined MODAL_VOLUME_NAME set "MODAL_VOLUME_NAME=forge-neo-modal-data"
modal volume create "%MODAL_VOLUME_NAME%"
pause
