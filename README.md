# Forge Neo In Modal

Personal Forge Neo-on-Modal setup for an L40S GPU. It builds a static image from
Forge Neo, lets Forge install SageAttention through `--sage`, bakes in the
requested extensions, and mounts one Modal Volume for models, outputs, config,
and file browsing.

## Baked In

- Forge Neo from `Haoming02/sd-webui-forge-classic`, branch `neo`
- Pinned Forge Neo head: `61d327da65b0483cafb74d641f030737db2d6bf1`
- Python 3.13.11 from `python-build-standalone`
- PyTorch `2.10.0+cu130` and torchvision `0.25.0+cu130`
- SageAttention installed by Forge during image build through the `--sage` flag,
  with `SAGE_PACKAGE` pointing at the official `v2.2.0` source tag because the
  Linux PyPI package currently does not expose `2.2.0`
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

On startup, the wrapper checks Forge Neo's own config version marker. If a
persisted `config.json` is stale after an upstream UI-breaking update, it backs
up `config.json` and `ui-config.json` and lets Forge regenerate clean UI config;
models and outputs stay in the volume.

Useful overrides:

```bat
set "MODAL_GPU=L40S"
set "MODAL_APP_NAME=forge-neo-modal-l40s"
set "MODAL_VOLUME_NAME=forge-neo-modal-data"
set "MODAL_FORCE_BUILD=1"
set "FORGE_EXTRA_ARGS=--autotune"
```

More detailed notes are in `docs\README.md`.
