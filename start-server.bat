@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%~dp0"
if exist ".env.local.bat" call ".env.local.bat"

if not defined MODAL_APP_NAME set "MODAL_APP_NAME=forge-neo-modal-l40s"
if not defined MODAL_SCALEDOWN_WINDOW set "MODAL_SCALEDOWN_WINDOW=1800"
if not defined FORGE_START_WAIT_SECONDS set "FORGE_START_WAIT_SECONDS=1200"

set "MODAL_AUTOSCALER_SCALEDOWN_WINDOW=%MODAL_SCALEDOWN_WINDOW%"
set "MODAL_AUTOSCALER_ACTION_LABEL=Prepared cold-start"
python app\scale_down.py
if errorlevel 1 (
  echo.
  echo Could not prepare the Modal autoscaler. Run tools\dev\deploy.bat first, then try again.
  pause
  exit /b 1
)

if not defined FORGE_NEO_URL (
  for /f "tokens=2" %%I in ('modal token info 2^>nul ^| findstr /B /C:"Workspace:"') do set "FORGE_NEO_URL=https://%%I--forge-neo.modal.run"
)

if not defined FORGE_NEO_URL (
  echo Could not infer the Modal workspace URL. Set FORGE_NEO_URL in .env.local.bat.
  pause
  exit /b 1
)

python app\wait_for_forge.py "%FORGE_NEO_URL%" --timeout "%FORGE_START_WAIT_SECONDS%"
if errorlevel 1 (
  echo.
  echo Forge Neo did not report ready within the wait window. Opening the URL anyway so you can see the current state.
)

echo Opening %FORGE_NEO_URL%
start "" "%FORGE_NEO_URL%"
