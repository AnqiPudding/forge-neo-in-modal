# Forge Neo In Modal

Personal Forge Neo-on-Modal setup for an L40S GPU. It builds a static image from
Forge Neo, bakes in SageAttention plus the requested extensions, and mounts one
Modal Volume for models, outputs, config, and file browsing.

## Baked In

- Forge Neo from `Haoming02/sd-webui-forge-classic`, branch `neo`
- SageAttention, started with the `--sage` flag
- Faster default runtime flags: `--cuda-malloc`, `--cuda-stream 2`,
  `--pin-shared-memory`, `--expandable-segments`, `--fast-fp16`,
  `--fast-fp8`, `--force-non-blocking`, `--mmap-torch-files`,
  `--highvram`, and `--no-hashing`
- `zixaphir/Stable-Diffusion-Webui-Civitai-Helper`
- `Bing-su/adetailer`
- `lanner0403/WAI-NSFW-illustrious-character-select`
- `Modal Downloader`, a local extension for downloading a URL into a chosen
  folder under the mounted `models` folder, with optional bearer token support
- File Browser at `/files/`

## Requirements

- Windows with Python, Git, and the Modal CLI available in PATH
- Modal authenticated with `modal setup`
- GitHub CLI authenticated if you want to push/update the repository
- Local Python package install:

```bat
python -m pip install -r config\requirements.txt
```

## Quick Start

```bat
tools\io\create-volume.bat
tools\dev\deploy.bat
start-server.bat
```

Use `stop-server.bat` to let the GPU container sleep while keeping the deployed
URL. Use `tools\dev\stop.bat` only when you want to stop the deployed Modal app.

## Model Storage

The default Modal Volume is `forge-neo-modal-data`, mounted at `/vol`.

Common model folders:

- Checkpoints: `/vol/models/Stable-diffusion` or `/vol/models/checkpoints`
- LoRAs: `/vol/models/Lora` or `/vol/models/loras`
- VAEs: `/vol/models/VAE` or `/vol/models/vae`
- Text encoders: `/vol/models/text_encoder`, `/vol/models/text_encoders`, or `/vol/models/clip`
- ADetailer models: `/vol/models/adetailer`

Download models either from the Forge Neo **Modal Downloader** tab or locally:

```bat
tools\io\download-model.bat
```

## Configuration

Copy `.env.local.example.bat` to `.env.local.bat` if you want overrides. L40S is
already the default GPU.

Useful overrides:

```bat
set "MODAL_GPU=L40S"
set "MODAL_APP_NAME=forge-neo-modal-l40s"
set "MODAL_VOLUME_NAME=forge-neo-modal-data"
set "FORGE_EXTRA_ARGS=--autotune"
```

More detailed notes are in `docs\README.md`.
