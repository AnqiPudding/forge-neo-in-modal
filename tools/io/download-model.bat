@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if exist "%PROJECT_ROOT%\.env.local.bat" call "%PROJECT_ROOT%\.env.local.bat"
if not defined MODAL_APP_NAME set "MODAL_APP_NAME=forge-neo-modal-l40s"
if not defined MODAL_VOLUME_NAME set "MODAL_VOLUME_NAME=forge-neo-modal-data"
set /p MODEL_URL=Model URL: 
if "%MODEL_URL%"=="" (
  echo No URL entered.
  pause
  exit /b 1
)
set /p MODEL_SUBDIR=Model folder under models [Stable-diffusion]: 
if "%MODEL_SUBDIR%"=="" set "MODEL_SUBDIR=Stable-diffusion"
set /p MODEL_FILENAME=Optional filename override [blank]: 
set /p MODEL_TOKEN=Optional bearer token [blank]: 
if "%MODEL_FILENAME%"=="" (
  if "%MODEL_TOKEN%"=="" (
    modal run app/modal_app.py::download_model --url "%MODEL_URL%" --subdir "%MODEL_SUBDIR%"
  ) else (
    modal run app/modal_app.py::download_model --url "%MODEL_URL%" --subdir "%MODEL_SUBDIR%" --token "%MODEL_TOKEN%"
  )
) else (
  if "%MODEL_TOKEN%"=="" (
    modal run app/modal_app.py::download_model --url "%MODEL_URL%" --subdir "%MODEL_SUBDIR%" --filename "%MODEL_FILENAME%"
  ) else (
    modal run app/modal_app.py::download_model --url "%MODEL_URL%" --subdir "%MODEL_SUBDIR%" --filename "%MODEL_FILENAME%" --token "%MODEL_TOKEN%"
  )
)
pause
