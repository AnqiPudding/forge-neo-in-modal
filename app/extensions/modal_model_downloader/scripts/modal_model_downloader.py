from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import gradio as gr

from modules import script_callbacks
from modules.paths_internal import models_path


DEFAULT_FOLDERS = [
    "Stable-diffusion",
    "checkpoints",
    "diffusion_models",
    "unet",
    "Lora",
    "loras",
    "VAE",
    "vae",
    "embeddings",
    "text_encoder",
    "text_encoders",
    "clip",
    "ControlNet",
    "ControlNetPreprocessor",
    "ESRGAN",
    "GFPGAN",
    "Codeformer",
    "upscale_models",
    "adetailer",
]


def model_root() -> Path:
    return Path(os.environ.get("MODEL_DIR") or models_path).resolve()


def available_folders() -> list[str]:
    root = model_root()
    folders = set(DEFAULT_FOLDERS)
    if root.exists():
        for child in root.iterdir():
            if child.is_dir() or child.is_symlink():
                folders.add(child.name)
    return sorted(folders, key=str.lower)


def clean_subdir(raw_subdir: str) -> str:
    subdir = (raw_subdir or "").strip().strip("/").replace("\\", "/") or "Stable-diffusion"
    parts = [part for part in subdir.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("Model folder cannot contain '..'.")
    return "/".join(parts) or "Stable-diffusion"


def clean_filename(raw_filename: str) -> str | None:
    filename = (raw_filename or "").strip()
    if not filename:
        return None
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError("Filename override must be a plain file name.")
    return filename


def infer_filename(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = posixpath.basename(parsed.path)
    return urllib.parse.unquote(name) if name else "downloaded-model"


def commit_volume() -> str:
    volume_name = os.environ.get("MODAL_VOLUME_NAME")
    if not volume_name:
        return "Volume commit skipped because MODAL_VOLUME_NAME is not set."
    try:
        import modal

        modal.Volume.from_name(volume_name).commit()
    except Exception as exc:
        return f"Volume commit failed, but the file is present in this running container: {exc}"
    return f"Committed Modal Volume {volume_name}."


def download_with_aria2(url: str, target_dir: Path, filename: str | None, token: str | None) -> None:
    command = [
        "aria2c",
        "--continue=true",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--summary-interval=10",
        "--content-disposition=true",
        "--dir",
        str(target_dir),
    ]
    if token:
        command.append(f"--header=Authorization: Bearer {token}")
    if filename:
        command.extend(["--out", filename])
    command.append(url)
    subprocess.run(command, check=True)


def download_with_python(url: str, target_dir: Path, filename: str | None, token: str | None) -> Path:
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        output_name = filename
        if not output_name:
            content_disposition = response.headers.get("Content-Disposition", "")
            match = None
            for part in content_disposition.split(";"):
                part = part.strip()
                if part.lower().startswith("filename="):
                    match = part.split("=", 1)[1].strip('"')
            output_name = match or infer_filename(url)
        output = target_dir / clean_filename(output_name)
        with output.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
    return output


def download_model(url: str, folder: str, custom_folder: str, filename: str, token: str) -> str:
    url = (url or "").strip()
    if not url.startswith(("https://", "http://")):
        return "Enter a direct http:// or https:// download URL."

    try:
        subdir = clean_subdir(custom_folder or folder)
        output_name = clean_filename(filename)
    except ValueError as exc:
        return str(exc)

    root = model_root()
    target_dir = (root / subdir).resolve()
    try:
        target_dir.relative_to(root)
    except ValueError:
        return "Target folder must stay inside the models folder."

    target_dir.mkdir(parents=True, exist_ok=True)
    token = (token or "").strip() or None

    try:
        if shutil.which("aria2c"):
            download_with_aria2(url, target_dir, output_name, token)
        else:
            download_with_python(url, target_dir, output_name, token)
    except subprocess.CalledProcessError as exc:
        return f"Download failed with exit code {exc.returncode}."
    except Exception as exc:
        return f"Download failed: {exc}"

    commit_message = commit_volume()
    saved_name = output_name or infer_filename(url)
    return f"Downloaded {saved_name} into models/{subdir}.\n{commit_message}"


def on_folder_choice(folder: str) -> str:
    return folder or "Stable-diffusion"


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as tab:
        gr.Markdown("Download a model file directly into the mounted Modal models volume.")
        with gr.Row():
            folder = gr.Dropdown(
                label="Quick model folder",
                choices=available_folders(),
                value="Stable-diffusion",
                allow_custom_value=True,
            )
            custom_folder = gr.Textbox(
                label="Folder under models",
                value="Stable-diffusion",
                placeholder="Stable-diffusion, Lora, VAE, text_encoder, custom/subfolder",
            )
        url = gr.Textbox(label="Download URL", placeholder="https://...")
        filename = gr.Textbox(label="Optional filename override", placeholder="model.safetensors")
        token = gr.Textbox(label="Optional bearer token", type="password")
        download = gr.Button("Download to models volume", variant="primary")
        status = gr.Textbox(label="Status", lines=5)

        folder.change(on_folder_choice, inputs=folder, outputs=custom_folder, show_progress=False)
        download.click(
            download_model,
            inputs=[url, folder, custom_folder, filename, token],
            outputs=status,
            show_progress=True,
        )

    return [(tab, "Modal Downloader", "modal_model_downloader")]


script_callbacks.on_ui_tabs(on_ui_tabs)
