#!/usr/bin/env bash
set -Eeuo pipefail

FORGE_DIR="${FORGE_DIR:-/opt/forge-neo}"
DATA_DIR="${DATA_DIR:-/vol}"
WEBUI_DATA_DIR="${WEBUI_DATA_DIR:-${DATA_DIR}/webui}"
MODEL_DIR="${MODEL_DIR:-${DATA_DIR}/models}"
STATE_DIR="${DATA_DIR}/.state"
CACHE_DIR="${DATA_DIR}/.cache"
PORT="${FORGE_WEBUI_PORT:-7860}"
BACKEND_PORT="${FORGE_BACKEND_PORT:-7861}"
FILEBROWSER_PORT="${FILEBROWSER_PORT:-7862}"
ENABLE_FILE_MANAGER="${ENABLE_FILE_MANAGER:-1}"
FILE_MANAGER_PREFIX="${FILE_MANAGER_PREFIX:-/files}"
ENABLE_VOLUME_COMMIT_LOOP="${ENABLE_VOLUME_COMMIT_LOOP:-1}"
VOLUME_COMMIT_INTERVAL_SECONDS="${VOLUME_COMMIT_INTERVAL_SECONDS:-120}"

log() {
  printf '[%s] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

mkdir -p "${DATA_DIR}" "${WEBUI_DATA_DIR}" "${MODEL_DIR}" "${STATE_DIR}" "${CACHE_DIR}/pip" "${CACHE_DIR}/huggingface"

ensure_model_dirs() {
  local dirs=(
    Stable-diffusion checkpoints diffusion_models unet
    Lora loras LyCORIS
    VAE vae
    embeddings
    ESRGAN GFPGAN Codeformer
    ControlNet ControlNetPreprocessor
    text_encoder text_encoders clip
    hypernetworks
    upscale_models
    adetailer
  )

  for dir in "${dirs[@]}"; do
    mkdir -p "${MODEL_DIR}/${dir}"
  done
}

ensure_static_extensions() {
  local baked="${FORGE_DIR}/extensions"
  local runtime="${WEBUI_DATA_DIR}/extensions"

  mkdir -p "${WEBUI_DATA_DIR}"
  if [ -L "${runtime}" ]; then
    return 0
  fi

  if [ ! -e "${runtime}" ]; then
    ln -s "${baked}" "${runtime}"
    log "Using baked static extensions from ${baked}."
    return 0
  fi

  if [ -d "${runtime}" ]; then
    log "Refreshing baked extensions inside existing runtime extension directory."
    for extension in \
      Stable-Diffusion-Webui-Civitai-Helper \
      adetailer \
      WAI-NSFW-illustrious-character-select \
      modal_model_downloader
    do
      if [ -d "${baked}/${extension}" ]; then
        mkdir -p "${runtime}/${extension}"
        rsync -a --delete "${baked}/${extension}/" "${runtime}/${extension}/"
      fi
    done
  fi
}

write_default_config() {
  WEBUI_DATA_DIR="${WEBUI_DATA_DIR}" MODEL_DIR="${MODEL_DIR}" python - <<'PY'
import json
import os
from pathlib import Path

webui = Path(os.environ["WEBUI_DATA_DIR"])
model_dir = Path(os.environ["MODEL_DIR"])
config_path = webui / "config.json"
config_path.parent.mkdir(parents=True, exist_ok=True)

try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        config = {}
except FileNotFoundError:
    config = {}
except Exception:
    backup = config_path.with_suffix(".json.broken")
    config_path.replace(backup)
    print(f"Moved unreadable config to {backup}")
    config = {}

defaults = {
    "VERSION_UID": "PY313",
    "outdir_txt2img_samples": str(webui / "output" / "txt2img-images"),
    "outdir_img2img_samples": str(webui / "output" / "img2img-images"),
    "outdir_extras_samples": str(webui / "output" / "extras-images"),
    "outdir_txt2img_grids": str(webui / "output" / "txt2img-grids"),
    "outdir_img2img_grids": str(webui / "output" / "img2img-grids"),
    "outdir_grids": "",
    "outdir_samples": "",
    "samples_save": True,
    "grid_save": True,
    "ad_extra_models_dir": str(model_dir / "adetailer"),
}

changed = False
for key, value in defaults.items():
    if key == "VERSION_UID" or key not in config:
        if config.get(key) != value:
            config[key] = value
            changed = True

if changed or not config_path.exists():
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote default Forge Neo config to {config_path}")
else:
    print(f"Forge Neo config already exists at {config_path}")

for path in [
    webui / "output" / "txt2img-images",
    webui / "output" / "img2img-images",
    webui / "output" / "extras-images",
    webui / "output" / "txt2img-grids",
    webui / "output" / "img2img-grids",
]:
    path.mkdir(parents=True, exist_ok=True)
PY
}

start_volume_commit_loop() {
  if [ "${ENABLE_VOLUME_COMMIT_LOOP}" != "1" ]; then
    return 0
  fi

  if [ -z "${MODAL_VOLUME_NAME:-}" ]; then
    log "Volume commit loop disabled because MODAL_VOLUME_NAME is not set."
    return 0
  fi

  log "Starting background Modal Volume commit loop every ${VOLUME_COMMIT_INTERVAL_SECONDS}s."
  python /opt/forge-neo-modal/volume_commit_loop.py \
    --volume-name "${MODAL_VOLUME_NAME}" \
    --interval "${VOLUME_COMMIT_INTERVAL_SECONDS}" &
}

ensure_model_dirs
ensure_static_extensions
write_default_config

export GRADIO_ANALYTICS_ENABLED="${GRADIO_ANALYTICS_ENABLED:-False}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${CACHE_DIR}/pip}"
export HF_HOME="${HF_HOME:-${CACHE_DIR}/huggingface}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${CACHE_DIR}}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

if [ "${FORGE_PREPARE_ONLY:-0}" = "1" ]; then
  log "Preparation-only mode completed."
  exit 0
fi

start_volume_commit_loop

extra_args=()
if [ -n "${FORGE_EXTRA_ARGS:-}" ]; then
  # Intentional shell-style splitting for simple Modal env overrides.
  extra_args=(${FORGE_EXTRA_ARGS})
fi

server_args=(
  python launch.py
  --listen
  --port "${PORT}"
  --api
  --enable-insecure-extension-access
  --data-dir "${WEBUI_DATA_DIR}"
  --model-ref "${MODEL_DIR}"
  --ckpt-dirs "${MODEL_DIR}/checkpoints"
  --ckpt-dirs "${MODEL_DIR}/diffusion_models"
  --ckpt-dirs "${MODEL_DIR}/unet"
  --lora-dirs "${MODEL_DIR}/Lora"
  --lora-dirs "${MODEL_DIR}/loras"
  --vae-dirs "${MODEL_DIR}/VAE"
  --vae-dirs "${MODEL_DIR}/vae"
  --text-encoder-dirs "${MODEL_DIR}/text_encoder"
  --text-encoder-dirs "${MODEL_DIR}/text_encoders"
  --text-encoder-dirs "${MODEL_DIR}/clip"
  --embeddings-dir "${MODEL_DIR}/embeddings"
  --esrgan-models-path "${MODEL_DIR}/ESRGAN"
  --gfpgan-models-path "${MODEL_DIR}/GFPGAN"
  --codeformer-models-path "${MODEL_DIR}/Codeformer"
  --sage
  --cuda-malloc
  --cuda-stream "${FORGE_CUDA_STREAMS:-2}"
  --pin-shared-memory
  --expandable-segments
  --fast-fp16
  --fast-fp8
  --force-non-blocking
  --mmap-torch-files
  --highvram
  --no-hashing
  --skip-python-version-check
  --skip-version-check
  --skip-install
  "${extra_args[@]}"
)

cd "${FORGE_DIR}"

if [ "${ENABLE_FILE_MANAGER}" = "1" ]; then
  FILEBROWSER_DB="${FILEBROWSER_DB:-${STATE_DIR}/filebrowser.db}"
  FILEBROWSER_AUTH_HEADER="${FILEBROWSER_AUTH_HEADER:-X-Modal-Filebrowser-User}"
  FILEBROWSER_AUTH_USER="${FILEBROWSER_AUTH_USER:-admin}"

  if ! filebrowser config cat --database "${FILEBROWSER_DB}" >/dev/null 2>&1; then
    filebrowser config init \
      --database "${FILEBROWSER_DB}" \
      --address 127.0.0.1 \
      --port "${FILEBROWSER_PORT}" \
      --root "${DATA_DIR}" \
      --baseURL "${FILE_MANAGER_PREFIX}" \
      --auth.method=proxy \
      --auth.header="${FILEBROWSER_AUTH_HEADER}" \
      --disableExec >/dev/null
  fi
  filebrowser config set \
    --database "${FILEBROWSER_DB}" \
    --address 127.0.0.1 \
    --port "${FILEBROWSER_PORT}" \
    --root "${DATA_DIR}" \
    --baseURL "${FILE_MANAGER_PREFIX}" \
    --auth.method=proxy \
    --auth.header="${FILEBROWSER_AUTH_HEADER}" \
    --disableExec >/dev/null

  filebrowser_command=(
    filebrowser
    --address 127.0.0.1
    --port "${FILEBROWSER_PORT}"
    --root "${DATA_DIR}"
    --database "${FILEBROWSER_DB}"
    --baseURL "${FILE_MANAGER_PREFIX}"
    --disableExec
  )

  log "Starting Forge Neo on 127.0.0.1:${BACKEND_PORT} and File Browser at ${FILE_MANAGER_PREFIX}/ via 0.0.0.0:${PORT}."
  server_args=(
    python launch.py
    --listen
    --port "${BACKEND_PORT}"
    --api
    --enable-insecure-extension-access
    --data-dir "${WEBUI_DATA_DIR}"
    --model-ref "${MODEL_DIR}"
    --ckpt-dirs "${MODEL_DIR}/checkpoints"
    --ckpt-dirs "${MODEL_DIR}/diffusion_models"
    --ckpt-dirs "${MODEL_DIR}/unet"
    --lora-dirs "${MODEL_DIR}/Lora"
    --lora-dirs "${MODEL_DIR}/loras"
    --vae-dirs "${MODEL_DIR}/VAE"
    --vae-dirs "${MODEL_DIR}/vae"
    --text-encoder-dirs "${MODEL_DIR}/text_encoder"
    --text-encoder-dirs "${MODEL_DIR}/text_encoders"
    --text-encoder-dirs "${MODEL_DIR}/clip"
    --embeddings-dir "${MODEL_DIR}/embeddings"
    --esrgan-models-path "${MODEL_DIR}/ESRGAN"
    --gfpgan-models-path "${MODEL_DIR}/GFPGAN"
    --codeformer-models-path "${MODEL_DIR}/Codeformer"
    --sage
    --cuda-malloc
    --cuda-stream "${FORGE_CUDA_STREAMS:-2}"
    --pin-shared-memory
    --expandable-segments
    --fast-fp16
    --fast-fp8
    --force-non-blocking
    --mmap-torch-files
    --highvram
    --no-hashing
    --skip-python-version-check
    --skip-version-check
    --skip-install
    "${extra_args[@]}"
  )

  exec python /opt/forge-neo-modal/webui_file_proxy.py \
    --listen 0.0.0.0 \
    --port "${PORT}" \
    --webui-url "http://127.0.0.1:${BACKEND_PORT}" \
    --filebrowser-url "http://127.0.0.1:${FILEBROWSER_PORT}" \
    --filebrowser-prefix "${FILE_MANAGER_PREFIX}" \
    --filebrowser-command "$(printf '%q ' "${filebrowser_command[@]}")" \
    --filebrowser-auth-header "${FILEBROWSER_AUTH_HEADER}" \
    --filebrowser-auth-user "${FILEBROWSER_AUTH_USER}" \
    -- \
    "${server_args[@]}"
fi

log "Starting Forge Neo on 0.0.0.0:${PORT} with GPU target ${MODAL_GPU:-L40S}."
exec "${server_args[@]}"
