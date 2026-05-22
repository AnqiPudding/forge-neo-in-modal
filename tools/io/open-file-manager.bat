@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if exist "%PROJECT_ROOT%\.env.local.bat" call "%PROJECT_ROOT%\.env.local.bat"
if not defined FORGE_NEO_URL (
  for /f "tokens=2" %%I in ('modal token info 2^>nul ^| findstr /B /C:"Workspace:"') do set "FORGE_NEO_URL=https://%%I--forge-neo.modal.run"
)
if not defined FORGE_NEO_URL (
  echo Could not infer the Modal workspace URL. Set FORGE_NEO_URL in .env.local.bat.
  pause
  exit /b 1
)
start "" "%FORGE_NEO_URL%/files/"
