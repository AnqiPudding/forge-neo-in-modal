from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from pathlib import PurePosixPath

import modal


APP_DIR = Path(__file__).resolve().parent
APP_NAME = os.environ.get("MODAL_APP_NAME", "forge-neo-modal-l40s")
VOLUME_NAME = os.environ.get("MODAL_VOLUME_NAME", "forge-neo-modal-data")
DATA_MOUNT_PATH = os.environ.get("MODAL_DATA_MOUNT_PATH", "/vol").rstrip("/") or "/"
GPU = os.environ.get("MODAL_GPU", "L40S")
MIN_CONTAINERS = int(os.environ.get("MODAL_MIN_CONTAINERS", "0"))
SCALEDOWN_WINDOW = int(os.environ.get("MODAL_SCALEDOWN_WINDOW", str(30 * 60)))
TIMEOUT_SECONDS = int(os.environ.get("MODAL_TIMEOUT_SECONDS", str(24 * 60 * 60)))
STARTUP_TIMEOUT_SECONDS = int(os.environ.get("MODAL_STARTUP_TIMEOUT_SECONDS", str(45 * 60)))
WEBUI_PORT = int(os.environ.get("FORGE_WEBUI_PORT", "7860"))
FILE_MANAGER_PREFIX = "/" + os.environ.get("FILE_MANAGER_PREFIX", "/files").strip("/")
FILEBROWSER_VERSION = os.environ.get("FILEBROWSER_VERSION", "v2.63.5")
FORGE_NEO_REPO = os.environ.get("FORGE_NEO_REPO", "https://github.com/Haoming02/sd-webui-forge-classic.git")
FORGE_NEO_REF = os.environ.get("FORGE_NEO_REF", "neo")
SAGEATTENTION_REF = os.environ.get("SAGEATTENTION_REF", "v2.2.0")
FORCE_BUILD = os.environ.get("MODAL_FORCE_BUILD", "").lower() in {"1", "true", "yes", "on"}
SKIP_SAGEATTENTION = os.environ.get("SKIP_SAGEATTENTION", "").lower() in {"1", "true", "yes", "on"}

if DATA_MOUNT_PATH == "/":
    raise ValueError("MODAL_DATA_MOUNT_PATH cannot be '/'.")

PYTORCH_INDEX_URL = os.environ.get("PYTORCH_INDEX_URL", "https://download.pytorch.org/whl/cu130")
PYTORCH_PACKAGES = [
    os.environ.get("TORCH_PACKAGE", "torch==2.11.0+cu130"),
    os.environ.get("TORCHVISION_PACKAGE", "torchvision==0.26.0+cu130"),
]

EXTENSIONS = {
    "Stable-Diffusion-Webui-Civitai-Helper": {
        "repo": "https://github.com/zixaphir/Stable-Diffusion-Webui-Civitai-Helper.git",
        "ref": os.environ.get("CIVITAI_HELPER_REF", "master"),
    },
    "adetailer": {
        "repo": "https://github.com/Bing-su/adetailer.git",
        "ref": os.environ.get("ADETAILER_REF", "main"),
    },
    "WAI-NSFW-illustrious-character-select": {
        "repo": "https://github.com/lanner0403/WAI-NSFW-illustrious-character-select.git",
        "ref": os.environ.get("WAI_CHARACTER_SELECT_REF", "main"),
    },
}

app = modal.App(APP_NAME)
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def extension_clone_command(name: str, repo: str, ref: str) -> str:
    return (
        f"git clone --depth=1 --branch {shlex.quote(ref)} "
        f"{shlex.quote(repo)} /opt/forge-neo/extensions/{shlex.quote(name)}"
    )


extension_clone_commands = " && ".join(
    extension_clone_command(name, config["repo"], config["ref"])
    for name, config in EXTENSIONS.items()
)

base_image = (
    modal.Image.from_registry(
        os.environ.get("CUDA_BASE_IMAGE", "nvidia/cuda:13.0.2-cudnn-devel-ubuntu24.04"),
        add_python="3.13",
        force_build=FORCE_BUILD,
    )
    .apt_install(
        "aria2",
        "build-essential",
        "ca-certificates",
        "cmake",
        "curl",
        "ffmpeg",
        "git",
        "git-lfs",
        "libgl1",
        "libglib2.0-0",
        "libgomp1",
        "libopengl0",
        "libsm6",
        "libxext6",
        "libxrender1",
        "ninja-build",
        "rsync",
        "wget",
    )
    .env(
        {
            "PYTHONUNBUFFERED": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_EXTRA_INDEX_URL": PYTORCH_INDEX_URL,
            "TORCH_INDEX_URL": PYTORCH_INDEX_URL,
            "CUDA_MODULE_LOADING": "LAZY",
            "TORCH_CUDA_ARCH_LIST": "8.9",
            "CC": "/usr/bin/gcc",
            "CXX": "/usr/bin/g++",
            "CUDAHOSTCXX": "/usr/bin/g++",
            "GRADIO_ANALYTICS_ENABLED": "False",
        }
    )
    .pip_install(
        *PYTORCH_PACKAGES,
        index_url=PYTORCH_INDEX_URL,
        force_build=FORCE_BUILD,
    )
    .pip_install(
        "modal>=1.4.2",
        "packaging>=24,<27",
        "setuptools>=75,<82",
        "wheel>=0.45,<1",
        "ninja>=1.11,<2",
        "requests>=2.32,<3",
        "aria2p>=0.12,<1",
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "python - <<'PY'\n"
        "import pathlib, sys, sysconfig, torch\n"
        "include = pathlib.Path(sysconfig.get_paths()['include']) / 'Python.h'\n"
        "print('Python', sys.version)\n"
        "print('Python.h', include, include.exists())\n"
        "print('Torch', torch.__version__, 'CUDA', torch.version.cuda)\n"
        "raise SystemExit(0 if include.exists() else 1)\n"
        "PY",
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "set -eux; "
        "curl -fsSL -o /tmp/filebrowser.tar.gz "
        "\"https://github.com/filebrowser/filebrowser/releases/download/${FILEBROWSER_VERSION}/linux-amd64-filebrowser.tar.gz\"; "
        "tar -xzf /tmp/filebrowser.tar.gz -C /tmp filebrowser; "
        "install -m 0755 /tmp/filebrowser /usr/local/bin/filebrowser; "
        "rm -f /tmp/filebrowser /tmp/filebrowser.tar.gz; "
        "filebrowser version",
        env={"FILEBROWSER_VERSION": FILEBROWSER_VERSION},
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "git clone --depth=1 --branch \"$FORGE_NEO_REF\" \"$FORGE_NEO_REPO\" /opt/forge-neo",
        env={"FORGE_NEO_REPO": FORGE_NEO_REPO, "FORGE_NEO_REF": FORGE_NEO_REF},
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "mkdir -p /opt/forge-neo/extensions && " + extension_clone_commands,
        force_build=FORCE_BUILD,
    )
    .add_local_dir(
        str(APP_DIR / "extensions"),
        "/opt/forge-neo-local-extensions",
        copy=True,
        ignore=["**/__pycache__/**", "**/*.pyc"],
    )
    .run_commands(
        "cp -a /opt/forge-neo-local-extensions/modal_model_downloader /opt/forge-neo/extensions/",
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "cd /opt/forge-neo && "
        "python -m pip install --upgrade pip setuptools wheel && "
        "python launch.py --skip-python-version-check --skip-torch-cuda-test --skip-version-check "
        "--sage --exit",
        gpu=GPU,
        force_build=FORCE_BUILD,
    )
    .run_commands(
        "if [ \"$SKIP_SAGEATTENTION\" = \"1\" ]; then "
        "  echo 'Skipping explicit SageAttention source build by request.'; "
        "else "
        "  python -c \"import sageattention; print('SageAttention already importable:', getattr(sageattention, '__version__', 'unknown'))\" "
        "  || ("
        "    git clone --depth=1 --branch \"$SAGEATTENTION_REF\" https://github.com/thu-ml/SageAttention.git /tmp/SageAttention "
        "      || git clone --depth=1 https://github.com/thu-ml/SageAttention.git /tmp/SageAttention; "
        "    cd /tmp/SageAttention; "
        "    export CC=${CC:-/usr/bin/gcc}; "
        "    export CXX=${CXX:-/usr/bin/g++}; "
        "    export CUDAHOSTCXX=${CUDAHOSTCXX:-/usr/bin/g++}; "
        "    export EXT_PARALLEL=${SAGEATTENTION_EXT_PARALLEL:-${EXT_PARALLEL:-1}}; "
        "    export MAX_JOBS=${SAGEATTENTION_MAX_JOBS:-${MAX_JOBS:-1}}; "
        "    unset NVCC_APPEND_FLAGS; "
        "    python -m pip install --no-build-isolation --no-warn-conflicts ."
        "  ); "
        "  python -c \"import sageattention; print('SageAttention import OK:', getattr(sageattention, '__version__', 'unknown'))\"; "
        "fi",
        env={
            "SAGEATTENTION_REF": SAGEATTENTION_REF,
            "SKIP_SAGEATTENTION": "1" if SKIP_SAGEATTENTION else "0",
            "TORCH_CUDA_ARCH_LIST": "8.9",
            "CC": "/usr/bin/gcc",
            "CXX": "/usr/bin/g++",
            "CUDAHOSTCXX": "/usr/bin/g++",
        },
        gpu=GPU,
        force_build=FORCE_BUILD,
    )
)

runtime_image = (
    base_image.run_commands(
        f"rm -rf {shlex.quote(DATA_MOUNT_PATH)}",
        force_build=FORCE_BUILD,
    )
    .add_local_dir(
        str(APP_DIR / "scripts"),
        "/opt/forge-neo-modal",
        copy=True,
        ignore=["**/__pycache__/**", "**/*.pyc"],
    )
    .env(
        {
            "FORGE_DIR": "/opt/forge-neo",
            "DATA_DIR": DATA_MOUNT_PATH,
            "WEBUI_DATA_DIR": f"{DATA_MOUNT_PATH}/webui",
            "MODEL_DIR": f"{DATA_MOUNT_PATH}/models",
            "FORGE_WEBUI_PORT": str(WEBUI_PORT),
            "PERSISTENT_OUTPUT_DIR": f"{DATA_MOUNT_PATH}/webui/output",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "GRADIO_ANALYTICS_ENABLED": "False",
            "MODAL_VOLUME_NAME": VOLUME_NAME,
            "MODAL_DATA_MOUNT_PATH": DATA_MOUNT_PATH,
        }
    )
)


@app.function(
    image=runtime_image,
    gpu=GPU,
    volumes={DATA_MOUNT_PATH: data_volume},
    timeout=TIMEOUT_SECONDS,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=MIN_CONTAINERS,
    max_containers=1,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(WEBUI_PORT, startup_timeout=STARTUP_TIMEOUT_SECONDS, label="forge-neo")
def forge_neo():
    subprocess.Popen(["bash", "/opt/forge-neo-modal/start.sh"])


def run_git_status_command(args: list[str], timeout: int = 30) -> str:
    command = ["git", "-C", "/opt/forge-neo", *args]
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except Exception as exc:
        return f"ERROR: {exc}"
    output = completed.stdout.strip()
    if completed.returncode != 0:
        return f"ERROR({completed.returncode}): {output}"
    return output


def collect_forge_git_status() -> dict:
    forge_path = Path("/opt/forge-neo")
    if not (forge_path / ".git").exists():
        return {"exists": forge_path.exists(), "git": False}

    return {
        "exists": True,
        "git": True,
        "head": run_git_status_command(["rev-parse", "--short", "HEAD"]),
        "branch": run_git_status_command(["branch", "--show-current"]),
        "remote": run_git_status_command(["remote", "get-url", "origin"]),
        "status_short": run_git_status_command(["status", "--short"], timeout=60),
    }


@app.function(
    image=runtime_image,
    gpu=GPU,
    volumes={DATA_MOUNT_PATH: data_volume},
    timeout=30 * 60,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
)
def diagnostics() -> dict:
    env = os.environ.copy()
    env["FORGE_PREPARE_ONLY"] = "1"
    prepare = subprocess.run(
        ["bash", "/opt/forge-neo-modal/start.sh"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20 * 60,
    )

    probe = subprocess.run(
        [
            "python",
            "-c",
            (
                "import importlib.metadata, json, sys, torch; "
                "import sageattention; "
                "print(json.dumps({"
                "'python': sys.version, "
                "'torch': torch.__version__, "
                "'torch_cuda': torch.version.cuda, "
                "'cuda_available': torch.cuda.is_available(), "
                "'device_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "
                "'sageattention': getattr(sageattention, '__version__', 'unknown'), "
                "'gradio': importlib.metadata.version('gradio')"
                "}, sort_keys=True))"
            ),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )

    nvidia_smi = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    result = {
        "forge_git": collect_forge_git_status(),
        "prepare_exit_code": prepare.returncode,
        "prepare_log_tail": "\n".join(prepare.stdout.splitlines()[-80:]),
        "probe_exit_code": probe.returncode,
        "probe": probe.stdout.strip(),
        "nvidia_smi": nvidia_smi.stdout.strip(),
    }
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return result


@app.function(
    image=runtime_image,
    gpu=GPU,
    volumes={DATA_MOUNT_PATH: data_volume},
    timeout=30 * 60,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
)
def startup_check() -> dict:
    env = os.environ.copy()
    timeout_seconds = int(os.environ.get("FORGE_STARTUP_CHECK_TIMEOUT_SECONDS", str(STARTUP_TIMEOUT_SECONDS)))
    url = f"http://127.0.0.1:{WEBUI_PORT}/"
    file_manager_url = f"http://127.0.0.1:{WEBUI_PORT}{FILE_MANAGER_PREFIX}/"
    check_host = os.environ.get("FORGE_STARTUP_CHECK_HOST", "startup-check.modal.run")
    headers = {"Host": check_host, "Origin": f"https://{check_host}"}
    log_lines: list[str] = []

    process = subprocess.Popen(
        ["bash", "/opt/forge-neo-modal/start.sh"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        start_new_session=True,
    )

    def read_logs() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log_lines.append(line.rstrip())

    reader = threading.Thread(target=read_logs, daemon=True)
    reader.start()

    status_code: int | None = None
    file_manager_status_code: int | None = None
    api_status_code: int | None = None
    extensions_status_code: int | None = None
    extension_names: list[str] = []
    last_error = ""
    deadline = time.monotonic() + timeout_seconds

    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=10) as response:
                    status_code = response.status
                    response.read(1_000_000)
                    if 200 <= status_code < 400:
                        last_error = ""
                        break
            except urllib.error.HTTPError as exc:
                status_code = exc.code
                last_error = str(exc)
            except Exception as exc:
                last_error = str(exc)
            time.sleep(5)

        if status_code is not None and 200 <= status_code < 400:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{WEBUI_PORT}/sdapi/v1/options",
                        headers=headers,
                    )
                    with urllib.request.urlopen(request, timeout=20) as response:
                        api_status_code = response.status
                        response.read(1_000_000)
                        if 200 <= api_status_code < 400:
                            last_error = ""
                            break
                except urllib.error.HTTPError as exc:
                    api_status_code = exc.code
                    last_error = str(exc)
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(5)

            if api_status_code is not None and 200 <= api_status_code < 400:
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{WEBUI_PORT}/sdapi/v1/extensions",
                        headers=headers,
                    )
                    with urllib.request.urlopen(request, timeout=20) as response:
                        extensions_status_code = response.status
                        payload = json.loads(response.read(2_000_000).decode("utf-8", errors="ignore"))
                        if isinstance(payload, list):
                            extension_names = [
                                str(item.get("name"))
                                for item in payload
                                if isinstance(item, dict) and item.get("name")
                            ]
                except urllib.error.HTTPError as exc:
                    extensions_status_code = exc.code
                    last_error = str(exc)
                except Exception as exc:
                    last_error = str(exc)

            try:
                request = urllib.request.Request(file_manager_url, headers={"Host": check_host})
                with urllib.request.urlopen(request, timeout=10) as response:
                    file_manager_status_code = response.status
            except urllib.error.HTTPError as exc:
                file_manager_status_code = exc.code
                last_error = str(exc)
            except Exception as exc:
                last_error = str(exc)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=30)
        reader.join(timeout=5)

    result = {
        "status_code": status_code,
        "api_status_code": api_status_code,
        "extensions_status_code": extensions_status_code,
        "extension_names": extension_names,
        "file_manager_status_code": file_manager_status_code,
        "process_exit_code": process.returncode,
        "last_error": last_error,
        "log_tail": "\n".join(log_lines[-120:]),
    }
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)

    if status_code is None or not (200 <= status_code < 400):
        raise RuntimeError(f"Forge Neo startup check failed: status={status_code}, last_error={last_error}")
    if api_status_code is None or not (200 <= api_status_code < 400):
        raise RuntimeError(f"Forge Neo API check failed: status={api_status_code}, last_error={last_error}")
    if extensions_status_code is None or not (200 <= extensions_status_code < 400):
        raise RuntimeError(
            f"Forge Neo extensions API check failed: status={extensions_status_code}, last_error={last_error}"
        )
    expected_extensions = {
        "Stable-Diffusion-Webui-Civitai-Helper",
        "adetailer",
        "WAI-NSFW-illustrious-character-select",
    }
    missing_extensions = sorted(expected_extensions.difference(extension_names))
    if missing_extensions:
        raise RuntimeError(f"Baked extensions missing from Forge API listing: {missing_extensions}")
    if file_manager_status_code is None or not (200 <= file_manager_status_code < 400):
        raise RuntimeError(
            f"File-manager startup check failed: status={file_manager_status_code}, last_error={last_error}"
        )
    return result


def collect_volume_status() -> dict:
    roots = [
        "models",
        "webui",
        "webui/output",
        "webui/extensions",
        "webui/config.json",
        "webui/ui-config.json",
        ".state",
        ".cache",
    ]
    status: dict[str, object] = {}
    for root in roots:
        path = PurePosixPath(DATA_MOUNT_PATH) / root
        if not os.path.exists(path):
            status[root] = {"exists": False}
            continue
        path_string = str(path)
        if os.path.isfile(path_string) or os.path.islink(path_string):
            try:
                stat = os.stat(path_string)
                status[root] = {"exists": True, "type": "file", "bytes": stat.st_size}
            except OSError as exc:
                status[root] = {"exists": True, "type": "file", "error": str(exc)}
            continue
        du = subprocess.run(
            ["du", "-sh", path_string],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        count = 0
        for _, _, files in os.walk(path_string):
            count += len(files)
        status[root] = {
            "exists": True,
            "type": "dir",
            "size": du.stdout.split()[0] if du.stdout.split() else "unknown",
            "files": count,
        }
    return status


def collect_model_health() -> dict:
    model_root = Path(DATA_MOUNT_PATH) / "models"
    if not model_root.exists():
        return {"exists": False, "root": str(model_root), "folders": {}}

    folders: dict[str, object] = {}
    for child in sorted(model_root.iterdir(), key=lambda item: item.name.lower()):
        entry: dict[str, object] = {
            "type": "symlink" if child.is_symlink() else ("dir" if child.is_dir() else "file"),
        }
        if child.is_symlink():
            try:
                entry["target"] = os.readlink(child)
                entry["resolved_target"] = str(child.resolve(strict=False))
            except OSError as exc:
                entry["target_error"] = str(exc)
            folders[child.name] = entry
            continue

        if child.is_dir():
            file_count = 0
            byte_count = 0
            large_files: list[dict[str, object]] = []
            for current_root, _, files in os.walk(child):
                for filename in files:
                    file_path = Path(current_root) / filename
                    try:
                        size = file_path.stat().st_size
                    except OSError:
                        continue
                    file_count += 1
                    byte_count += size
                    if size >= 1024 * 1024 and len(large_files) < 12:
                        try:
                            rel_path = file_path.relative_to(child).as_posix()
                        except ValueError:
                            rel_path = file_path.name
                        large_files.append({"name": rel_path, "bytes": size})
            entry["files"] = file_count
            entry["bytes"] = byte_count
            entry["large_files"] = large_files
        elif child.is_file():
            try:
                entry["bytes"] = child.stat().st_size
            except OSError:
                entry["bytes"] = None
        folders[child.name] = entry

    return {"exists": True, "root": str(model_root), "folders": folders}


@app.function(image=runtime_image, volumes={DATA_MOUNT_PATH: data_volume}, timeout=5 * 60)
def volume_status() -> dict:
    status = collect_volume_status()
    print(json.dumps(status, indent=2, sort_keys=True), flush=True)
    return status


@app.function(image=runtime_image, volumes={DATA_MOUNT_PATH: data_volume}, timeout=5 * 60)
def model_health() -> dict:
    try:
        data_volume.reload()
    except Exception as exc:
        print(f"Volume reload skipped or failed before model health scan: {exc}", flush=True)
    status = collect_model_health()
    print(json.dumps(status, indent=2, sort_keys=True), flush=True)
    return status


def clean_model_subdir(subdir: str) -> str:
    clean_subdir = subdir.strip().strip("/").replace("\\", "/") or "Stable-diffusion"
    parts = [part for part in clean_subdir.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("Model subdir cannot contain '..'.")
    return "/".join(parts) or "Stable-diffusion"


def infer_filename_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    name = posixpath.basename(parsed.path)
    if not name or name in {".", ".."}:
        return None
    return urllib.parse.unquote(name)


@app.function(image=runtime_image, volumes={DATA_MOUNT_PATH: data_volume}, timeout=24 * 60 * 60)
def download_model(
    url: str,
    subdir: str = "Stable-diffusion",
    filename: str | None = None,
    token: str | None = None,
) -> str:
    if not url.startswith(("https://", "http://")):
        raise ValueError("Only http:// and https:// model URLs are supported.")

    clean_subdir = clean_model_subdir(subdir)
    target_dir = posixpath.join(DATA_MOUNT_PATH, "models", clean_subdir)
    os.makedirs(target_dir, exist_ok=True)

    command = [
        "aria2c",
        "--continue=true",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--summary-interval=30",
        "--dir",
        target_dir,
    ]
    if token:
        command.append(f"--header=Authorization: Bearer {token}")
    if filename:
        if "/" in filename or "\\" in filename or filename in {".", ".."}:
            raise ValueError("Filename must be a plain file name.")
        command.extend(["--out", filename])
    command.append(url)
    subprocess.check_call(command)
    data_volume.commit()

    saved_name = filename or infer_filename_from_url(url) or "(remote filename)"
    result = f"Downloaded {saved_name} into {target_dir}"
    print(result, flush=True)
    return result


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "app": APP_NAME,
                "volume": VOLUME_NAME,
                "data_mount_path": DATA_MOUNT_PATH,
                "gpu": GPU,
                "forge_neo_repo": FORGE_NEO_REPO,
                "forge_neo_ref": FORGE_NEO_REF,
                "extensions": EXTENSIONS,
                "filebrowser_version": FILEBROWSER_VERSION,
                "force_build": FORCE_BUILD,
            },
            indent=2,
        )
    )
