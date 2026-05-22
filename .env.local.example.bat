@echo off
set "MODAL_APP_NAME=forge-neo-modal-l40s"
set "MODAL_VOLUME_NAME=forge-neo-modal-data"
set "MODAL_GPU=L40S"
set "MODAL_SCALEDOWN_WINDOW=1800"

rem Force a fresh image rebuild when refreshing upstream Forge Neo or Python/PyTorch layers.
rem set "MODAL_FORCE_BUILD=1"

rem Current pinned Forge Neo head from the neo branch. Clear or replace to test another commit.
rem set "FORGE_NEO_COMMIT=61d327da65b0483cafb74d641f030737db2d6bf1"

rem Forge uses this when --sage installs SageAttention on Linux.
rem set "SAGE_PACKAGE=--no-build-isolation git+https://github.com/thu-ml/SageAttention.git@v2.2.0"

rem Optional extra Forge Neo flags appended after the fast defaults.
rem set "FORGE_EXTRA_ARGS=--autotune"
