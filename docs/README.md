# Forge Neo Modal Notes

## Defaults

- App: `forge-neo-modal-l40s`
- Volume: `forge-neo-modal-data`
- GPU: `L40S`
- Public endpoint label: `forge-neo`
- File Browser: `/files/`

`start-server.bat` infers the Modal URL from `modal token info`, usually:

```text
https://<workspace>--forge-neo.modal.run
```

## What Persists

The Modal Volume stores:

- `/vol/models`
- `/vol/webui/config.json`
- `/vol/webui/ui-config.json`
- `/vol/webui/output`
- `/vol/.state`
- `/vol/.cache`

Forge Neo source and the requested extensions are baked into the image. This is
intentional: the project is static and does not run a custom-node style
self-bake loop.

## Baked Extension Set

These are cloned during image build into `/opt/forge-neo/extensions`:

- `Stable-Diffusion-Webui-Civitai-Helper`
- `adetailer`
- `WAI-NSFW-illustrious-character-select`
- `modal_model_downloader`

At startup, `/vol/webui/extensions` is a symlink to the baked extension folder.
If the volume already has a real extensions directory, startup refreshes these
four extension folders from the baked copy.

## Downloader Extension

The **Modal Downloader** tab writes directly into the mounted model root. It
accepts:

- Direct `http://` or `https://` URL
- A chosen or custom folder under `models`
- Optional filename override
- Optional bearer token

The same behavior is available from:

```bat
tools\io\download-model.bat
```

## Testing Commands

```bat
python -m py_compile app\modal_app.py app\scale_down.py app\wait_for_forge.py app\scripts\webui_file_proxy.py app\scripts\volume_commit_loop.py app\extensions\modal_model_downloader\scripts\modal_model_downloader.py
modal volume create forge-neo-modal-data
modal deploy app/modal_app.py
modal run app/modal_app.py::diagnostics
modal run app/modal_app.py::startup_check
modal run app/modal_app.py::volume_status
modal run app/modal_app.py::model_health
```

`startup_check` boots Forge Neo in a temporary Modal function, checks the WebUI,
checks `/sdapi/v1/options`, and checks File Browser.
