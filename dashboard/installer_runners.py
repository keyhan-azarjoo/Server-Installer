import json
import os
import platform
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from constants import (
    BUILD_ID,
    LINUX_INSTALLER,
    MONGO_UNIX_FILES,
    MONGO_WINDOWS_FILES,
    MONGO_WINDOWS_INSTALLER,
    PROXY_FILES,
    PROXY_LINUX_INSTALLER,
    PROXY_SYNC_FILES,
    PROXY_WINDOWS_INSTALLER,
    ROOT,
    S3_LINUX_FILES,
    S3_LINUX_INSTALLER,
    S3_WINDOWS_FILES,
    S3_WINDOWS_INSTALLER,
    SAM3_LINUX_INSTALLER,
    SAM3_STATE_DIR,
    SAM3_STATE_FILE,
    SAM3_SYSTEMD_SERVICE,
    SAM3_UNIX_FILES,
    SAM3_WINDOWS_FILES,
    SAM3_WINDOWS_INSTALLER,
    SERVER_INSTALLER_DATA,
    WINDOWS_INSTALLER,
    WINDOWS_SETUP_MODULES,
    PROXY_NATIVE_STATE,
    PROXY_WINDOWS_STATE,
    REPO_RAW_BASE,
)
from utils import (
    _read_json_file,
    _write_json_file,
    command_exists,
    ensure_repo_files,
    find_app_dll_dir,
    prepare_source_dir,
    resolve_source_value,
    run_capture,
    run_process,
    _sudo_prefix,
    upload_root_dir,
)
from system_info import choose_service_host
from system_admin import is_windows_admin
from cert_manager import _save_installed_commit, _fetch_remote_commit_sha

def run_windows_installer(form, live_cb=None):
    if os.name != "nt":
        return 1, "Windows installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(["DotNet/windows/install-windows-dotnet-host.ps1"], live_cb=live_cb)

    source_value = (form.get("SourceValue", [""])[0] or "").strip()
    if not source_value:
        source_value = (form.get("SourceFile", [""])[0] or "").strip()
        if source_value:
            form["SourceValue"] = [source_value]
    if not source_value:
        source_value = (form.get("SourceFolder", [""])[0] or "").strip()
        if source_value:
            form["SourceValue"] = [source_value]
    if not source_value:
        return 1, "Source path/URL, uploaded file, or uploaded folder is required."

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WINDOWS_INSTALLER),
        "-NonInteractive",
    ]

    keys = [
        "DeploymentMode",
        "DotNetChannel",
        "SourceValue",
        "DomainName",
        "SiteName",
    ]
    for key in keys:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            cmd.extend([f"-{key}", value])

    deployment_mode = (form.get("DeploymentMode", ["IIS"])[0] or "IIS").strip()
    http_port = (form.get("HTTP_PORT", [""])[0] or form.get("SitePort", [""])[0] or "").strip()
    https_port = (form.get("HTTPS_PORT", [""])[0] or form.get("HttpsPort", [""])[0] or "").strip()
    if deployment_mode == "Docker":
        # Docker mode: HTTP_PORT maps to the host-side container port
        if http_port and http_port.isdigit():
            cmd.extend(["-DockerHostPort", http_port])
    else:
        # IIS mode: separate HTTP and HTTPS bindings
        if http_port and http_port.isdigit():
            cmd.extend(["-SitePort", http_port])
        if https_port and https_port.isdigit():
            cmd.extend(["-HttpsPort", https_port])

    env = os.environ.copy()
    env["SERVER_INSTALLER_NONINTERACTIVE"] = "1"
    return run_process(cmd, env=env, live_cb=live_cb)


def run_windows_setup_only(form, target, live_cb=None):
    if os.name != "nt":
        return 1, "Windows setup actions can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(WINDOWS_SETUP_MODULES, live_cb=live_cb)

    dotnet_channel = (form.get("DotNetChannel", ["8.0"])[0] or "8.0").strip()
    if not dotnet_channel:
        dotnet_channel = "8.0"

    if target == "iis":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'common.ps1'}';"
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'iis-mode.ps1'}';"
                f"Install-WindowsFeatureSet;"
                f"Install-DotNetPrerequisites -Channel '{dotnet_channel}'"
            ),
        ]
        env = os.environ.copy()
        env["SERVER_INSTALLER_NONINTERACTIVE"] = "1"
        return run_process(cmd, env=env, live_cb=live_cb)

    if target == "docker":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'common.ps1'}';"
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'docker-mode.ps1'}';"
                f"Install-DotNetPrerequisites -Channel '{dotnet_channel}' -SkipHostingBundle;"
                f"Ensure-DockerInstalled"
            ),
        ]
        env = os.environ.copy()
        env["SERVER_INSTALLER_NONINTERACTIVE"] = "1"
        return run_process(cmd, env=env, live_cb=live_cb)

    return 1, "Unknown Windows setup target."


def run_windows_docker_setup_only(live_cb=None):
    if os.name != "nt":
        return 1, "Windows Docker setup can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files([
        "DotNet/windows/modules/common.ps1",
        "DotNet/windows/modules/docker-mode.ps1",
    ], live_cb=live_cb)

    ok, ctx, err = _ensure_docker_windows_ready(live_cb=live_cb)
    if not ok:
        return 1, err
    return 0, f"Docker Engine is running (context: {ctx})."


def run_linux_installer(form, live_cb=None, require_source=True):
    if os.name == "nt":
        return 1, "Linux installer can only run on Linux hosts."
    ensure_repo_files(["DotNet/linux/install-linux-dotnet-runner.sh"], live_cb=live_cb)

    source_value = (form.get("SOURCE_VALUE", [""])[0] or "").strip()
    if not source_value:
        source_value = (form.get("SOURCE_FILE", [""])[0] or "").strip()
        if source_value:
            form["SOURCE_VALUE"] = [source_value]
    if not source_value:
        source_value = (form.get("SOURCE_FOLDER", [""])[0] or "").strip()
        if source_value:
            form["SOURCE_VALUE"] = [source_value]
    if require_source and not source_value:
        return 1, "Source path/URL, uploaded file, or uploaded folder is required."

    installer_cmd = ["bash", str(LINUX_INSTALLER)]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        installer_cmd = ["sudo"] + installer_cmd

    env = os.environ.copy()
    for key in [
        "DOTNET_CHANNEL",
        "SOURCE_VALUE",
        "DOMAIN_NAME",
        "SERVICE_NAME",
        "SERVICE_PORT",
        "HTTP_PORT",
        "HTTPS_PORT",
        "GITHUB_TOKEN",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    return run_process(installer_cmd, env=env, live_cb=live_cb)


def run_windows_sam3_installer(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Windows SAM3 installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(SAM3_WINDOWS_FILES, live_cb=live_cb, refresh=True)
    env = os.environ.copy()
    for key in [
        "SAM3_HOST_IP", "SAM3_HTTP_PORT", "SAM3_HTTPS_PORT", "SAM3_DOMAIN",
        "SAM3_USERNAME", "SAM3_PASSWORD", "SAM3_USE_OS_AUTH",
        "SAM3_GPU_DEVICE", "SAM3_DOWNLOAD_MODEL", "SAM3_DEPLOY_MODE",
    ]:
        val = (form.get(key, [""])[0] or "").strip()
        if val:
            env[key] = val
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    code, output = run_process(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SAM3_WINDOWS_INSTALLER)],
        env=env,
        live_cb=live_cb,
    )
    return code, output


def run_unix_sam3_installer(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Unix SAM3 installer can only run on Linux or macOS hosts."
    ensure_repo_files(SAM3_UNIX_FILES, live_cb=live_cb, refresh=True)
    env = os.environ.copy()
    env_keys = [
        "SAM3_HOST_IP", "SAM3_HTTP_PORT", "SAM3_HTTPS_PORT", "SAM3_DOMAIN",
        "SAM3_USERNAME", "SAM3_PASSWORD", "SAM3_USE_OS_AUTH",
        "SAM3_GPU_DEVICE", "SAM3_DOWNLOAD_MODEL", "SAM3_DEPLOY_MODE",
    ]
    for key in env_keys:
        val = (form.get(key, [""])[0] or "").strip()
        if val:
            env[key] = val
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    cmd = ["bash", str(SAM3_LINUX_INSTALLER)]
    if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
        cmd = ["sudo", "env"]
        for key in env_keys + ["SERVER_INSTALLER_DATA_DIR"]:
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(SAM3_LINUX_INSTALLER)]
    code, output = run_process(cmd, env=env, live_cb=live_cb)
    return code, output


def run_sam3_download_model(form=None, live_cb=None):
    """Download the SAM3 model file using wget/curl (no Python dependencies needed)."""
    form = form or {}
    state = _read_json_file(SAM3_STATE_FILE)
    install_dir = str(state.get("install_dir") or "").strip()
    model_dir = str(state.get("model_path") or "").strip()
    venv_python = str(state.get("python_executable") or "").strip()

    # Set defaults if missing
    if not install_dir:
        install_dir = str(SAM3_STATE_DIR / "app")
    if not model_dir:
        model_dir = str(Path(install_dir) / "models" / "sam3.pt")
    if not venv_python:
        default_base = SAM3_STATE_DIR / "app"
        if os.name == "nt":
            fallback = default_base / "venv" / "Scripts" / "python.exe"
        else:
            fallback = default_base / "venv" / "bin" / "python"
        if fallback.exists():
            venv_python = str(fallback)

    # User-provided URL or default
    model_url = (form.get("SAM3_MODEL_URL", [""])[0] or "").strip()
    if not model_url:
        model_url = "https://huggingface.co/facebook/sam3/resolve/main/sam3.pt?download=true"

    # Auth token for gated models (e.g. HuggingFace)
    dl_token = (form.get("SAM3_DL_TOKEN", [""])[0] or "").strip()

    replace_model = (form.get("SAM3_REPLACE_MODEL", ["no"])[0] or "no").strip().lower()
    target_model = Path(model_dir)
    stopped_service = False
    if target_model.exists():
        if replace_model not in ("yes", "y", "1", "true"):
            return 0, "SAM3 model is already downloaded. Select 'yes' to replace."
        # Stop SAM3 service first so the file isn't locked
        if live_cb:
            live_cb("Stopping SAM3 service before replacing model...\n")
        run_sam3_stop(live_cb=live_cb)
        stopped_service = True
        import time
        time.sleep(3)
        if live_cb:
            live_cb("Removing old model...\n")
        # Retry delete — Windows file locks take time to release after process kill
        deleted = False
        for attempt in range(8):
            try:
                target_model.unlink()
                deleted = True
                if live_cb:
                    live_cb("Old model removed.\n")
                break
            except Exception as ex:
                if attempt < 7:
                    if live_cb and attempt == 0:
                        live_cb(f"File still locked, waiting... (attempt {attempt+1}/8)\n")
                    time.sleep(3)
                else:
                    if live_cb:
                        live_cb(f"[WARN] Could not remove old model after {attempt+1} attempts: {ex}\n")
        if not deleted:
            # Download to a temp path, then swap after download
            new_path = str(target_model) + ".new"
            if live_cb:
                live_cb(f"Downloading to temporary file: {new_path}\n")
            original_model = target_model
            target_model = Path(new_path)

    # Ensure models directory exists
    target_model.parent.mkdir(parents=True, exist_ok=True)

    if live_cb:
        live_cb(f"Downloading SAM3 model from:\n  {model_url}\n  to: {target_model}\n")

    # Download with progress using Python (works on all platforms, shows progress)
    try:
        import urllib.request
        req = urllib.request.Request(model_url, headers={"User-Agent": "ServerInstaller/1.0"})
        if dl_token:
            req.add_header("Authorization", f"Bearer {dl_token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            total_mb = total / (1024 * 1024) if total else 0
            if live_cb:
                size_str = f"{total_mb:.0f} MB" if total else "unknown size"
                live_cb(f"File size: {size_str}. Downloading...\n")
            downloaded = 0
            last_pct = -1
            with open(str(target_model), "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total and live_cb:
                        pct = int(downloaded * 100 / total)
                        if pct != last_pct and pct % 5 == 0:
                            dl_mb = downloaded / (1024 * 1024)
                            remain_mb = (total - downloaded) / (1024 * 1024)
                            live_cb(f"  {pct}%  ({dl_mb:.0f} MB / {total_mb:.0f} MB)  remaining: {remain_mb:.0f} MB\n")
                            last_pct = pct
                    elif live_cb and downloaded % (50 * 1024 * 1024) < (1024 * 1024):
                        dl_mb = downloaded / (1024 * 1024)
                        live_cb(f"  Downloaded: {dl_mb:.0f} MB...\n")
        code = 0
        output = f"Download complete: {downloaded / (1024*1024):.0f} MB"
    except Exception as ex:
        code = 1
        output = f"Download failed: {ex}"
        if target_model.exists() and target_model.stat().st_size < 1000000:
            target_model.unlink(missing_ok=True)
        if live_cb:
            live_cb(f"[ERROR] {output}\n")

    if code == 0 and target_model.exists() and target_model.stat().st_size > 1000000:
        # If downloaded to .new file, swap with original
        if str(target_model).endswith(".new"):
            original = Path(str(target_model)[:-4])  # remove .new
            if live_cb:
                live_cb(f"Replacing old model with new download...\n")
            import time as _time
            # Stop service again to release file lock for swap
            run_sam3_stop(live_cb=live_cb)
            _time.sleep(3)
            try:
                if original.exists():
                    original.unlink()
                os.replace(str(target_model), str(original))
                target_model = original
                if live_cb:
                    live_cb(f"Model replaced successfully.\n")
            except Exception as swap_ex:
                if live_cb:
                    live_cb(f"[WARN] Could not swap files: {swap_ex}. Using .new file.\n")

        state["model_downloaded"] = True
        state["model_path"] = str(target_model)
        state["install_dir"] = install_dir
        if venv_python:
            state["python_executable"] = venv_python
        SAM3_STATE_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_file(SAM3_STATE_FILE, state)
        size_mb = target_model.stat().st_size / (1024 * 1024)
        output = f"{output.rstrip()}\nSAM3 model downloaded successfully ({size_mb:.0f} MB)."
        # Restart service if we stopped it
        if stopped_service:
            if live_cb:
                live_cb("Restarting SAM3 service...\n")
            run_sam3_start(live_cb=live_cb)
    elif code == 0:
        # Download succeeded but file is suspiciously small or missing
        if target_model.exists():
            target_model.unlink(missing_ok=True)
        output = f"{output.rstrip()}\n[ERROR] Download completed but file is missing or too small. Check the URL."
        code = 1
        if stopped_service:
            if live_cb:
                live_cb("Restarting SAM3 service...\n")
            run_sam3_start(live_cb=live_cb)
    else:
        # Download failed — restart service if we stopped it
        if stopped_service:
            if live_cb:
                live_cb("Restarting SAM3 service...\n")
            run_sam3_start(live_cb=live_cb)
    return code, output


def run_sam3_docker(form=None, live_cb=None):
    """Deploy SAM3 as a Docker container."""
    form = form or {}
    host_ip = (form.get("SAM3_HOST_IP", [""])[0] or "").strip()
    http_port = (form.get("SAM3_HTTP_PORT", ["5000"])[0] or "5000").strip()
    https_port = (form.get("SAM3_HTTPS_PORT", ["5443"])[0] or "5443").strip()
    gpu_device = (form.get("SAM3_GPU_DEVICE", ["auto"])[0] or "auto").strip()
    username = (form.get("SAM3_USERNAME", [""])[0] or "").strip()
    password = (form.get("SAM3_PASSWORD", [""])[0] or "").strip()

    # ── Pre-flight: check port availability ──────────────────────────────
    try:
        port_int = int(http_port)
        if is_local_tcp_port_listening(port_int):
            # Check if it's our own container
            try:
                rc, out = run_capture(["docker", "ps", "--filter", "name=serverinstaller-sam3", "--format", "{{.ID}}"], timeout=10)
                if rc == 0 and out.strip():
                    if live_cb:
                        live_cb(f"Port {http_port} is in use by existing SAM3 container — will replace it.\n")
                else:
                    return 1, f"Port {http_port} is already in use by another process. Choose a different port or stop the process using port {http_port}."
            except Exception:
                return 1, f"Port {http_port} is already in use. Choose a different port or stop the process using port {http_port}."
    except (ValueError, Exception):
        pass

    # ── Pre-flight: resolve GPU device for platform ──────────────────────
    # macOS has no NVIDIA GPU — always use CPU
    if sys.platform == "darwin" and gpu_device in ("cuda", "auto"):
        gpu_device = "cpu"
        if live_cb:
            live_cb("macOS detected — using CPU mode (no NVIDIA GPU support in Docker on Mac).\n")
    elif gpu_device == "auto":
        # Check if NVIDIA runtime is available in Docker
        try:
            rc, out = run_capture(["docker", "info", "--format", "{{.Runtimes}}"], timeout=10)
            if "nvidia" not in str(out).lower():
                gpu_device = "cpu"
                if live_cb:
                    live_cb("No NVIDIA GPU runtime detected in Docker — using CPU mode.\n")
            else:
                gpu_device = "cuda"
                if live_cb:
                    live_cb("NVIDIA GPU detected — using CUDA mode.\n")
        except Exception:
            gpu_device = "cpu"

    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        if live_cb:
            live_cb("Docker not found. Installing Docker...\n")
        _install_engine_docker(lambda m: live_cb(m + "\n") if live_cb else None)
        if sys.platform == "darwin":
            _docker_add_macos_path()
        if not command_exists("docker"):
            return 1, "Docker is not installed and could not be auto-installed. Install Docker Desktop manually from https://www.docker.com/products/docker-desktop/"

    ensure_repo_files(SAM3_WINDOWS_FILES if os.name == "nt" else SAM3_UNIX_FILES, live_cb=live_cb, refresh=True)

    common_dir = str(ROOT / "SAM3" / "common")
    sam3_data = str(SAM3_STATE_DIR / "docker-app")
    Path(sam3_data).mkdir(parents=True, exist_ok=True)

    # Create Dockerfile — use appropriate base image for platform/GPU
    use_cuda = gpu_device == "cuda"
    gpu_base = "nvidia/cuda:12.4.0-runtime-ubuntu22.04" if use_cuda else "python:3.12-slim"
    torch_index = "--index-url https://download.pytorch.org/whl/cu124" if use_cuda else "--index-url https://download.pytorch.org/whl/cpu"
    dockerfile_content = f"""FROM {gpu_base}

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv git curl libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/

RUN python3 -m venv /app/venv && \\
    /app/venv/bin/pip install --upgrade pip setuptools wheel && \\
    /app/venv/bin/pip install torch torchvision {torch_index} && \\
    /app/venv/bin/pip install -r /app/requirements.txt && \\
    /app/venv/bin/pip install "git+https://github.com/ultralytics/CLIP.git" || true

RUN mkdir -p /app/models /app/temp/videos /root/.config/Ultralytics

ENV SAM3_MODEL_PATH=/app/models/sam3.pt
ENV SAM3_DEVICE={gpu_device}
ENV SAM3_HOST=0.0.0.0
ENV SAM3_PORT={http_port}
ENV SAM3_HTTPS_PORT={https_port}
ENV SAM3_USERNAME={username}
ENV SAM3_PASSWORD={password}
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics

EXPOSE {http_port} {https_port}

CMD ["/app/venv/bin/python", "/app/app.py"]
"""
    dockerfile_path = Path(sam3_data) / "Dockerfile"
    dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    # Copy app files to docker build context
    for item in Path(common_dir).rglob("*"):
        if item.is_file() and "__pycache__" not in str(item) and "venv" not in str(item):
            rel = item.relative_to(common_dir)
            dest = Path(sam3_data) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))

    # Copy model file into build context BEFORE docker build
    # (Docker on macOS can't mount /var/root, so we bake the model into the image)
    state = _read_json_file(SAM3_STATE_FILE)
    found_model = None
    state_model_path = str(state.get("model_path") or "").strip()
    if state_model_path and Path(state_model_path).exists() and Path(state_model_path).stat().st_size > 1000000:
        found_model = Path(state_model_path)
    if not found_model:
        for d in [SAM3_STATE_DIR / "app" / "models", SAM3_STATE_DIR / "models",
                  SAM3_STATE_DIR / "docker-app" / "models",
                  Path(str(state.get("install_dir") or "")) / "models"]:
            f = d / "sam3.pt"
            if f.exists() and f.stat().st_size > 1000000:
                found_model = f
                break
    docker_model_dir = Path(sam3_data) / "models"
    docker_model_dir.mkdir(parents=True, exist_ok=True)
    if found_model:
        dest_model = docker_model_dir / "sam3.pt"
        if not dest_model.exists() or dest_model.stat().st_size != found_model.stat().st_size:
            if live_cb:
                live_cb(f"Copying model ({found_model.stat().st_size / (1024*1024):.0f} MB) into Docker build context...\n")
            shutil.copy2(str(found_model), str(dest_model))
            if live_cb:
                live_cb(f"Model copied: {found_model} -> {dest_model}\n")
        else:
            if live_cb:
                live_cb(f"Model already in build context ({dest_model.stat().st_size / (1024*1024):.0f} MB)\n")
    else:
        if live_cb:
            live_cb(f"WARNING: sam3.pt not found on host. Detection won't work until you download the model.\n")
            live_cb(f"Searched: {SAM3_STATE_DIR / 'app' / 'models' / 'sam3.pt'}\n")

    container_name = "serverinstaller-sam3"
    image_name = "serverinstaller/sam3:latest"

    # Stop and remove existing container
    run_process(["docker", "stop", container_name], live_cb=None)
    run_process(["docker", "rm", container_name], live_cb=None)

    # Build image (--no-cache ensures fresh app code is always used)
    if live_cb:
        live_cb(f"Building SAM3 Docker image ({gpu_base})...\n")
    code, output = run_process(
        ["docker", "build", "--no-cache", "-t", image_name, str(sam3_data)],
        live_cb=live_cb,
    )
    if code != 0:
        # Check common build errors
        if "no matching manifest" in output.lower() or "platform" in output.lower():
            if live_cb:
                live_cb("\nBuild failed — base image may not support this platform. Retrying with CPU image...\n")
            # Retry with python:3.12-slim base
            dockerfile_content = dockerfile_content.replace(gpu_base, "python:3.12-slim")
            dockerfile_content = dockerfile_content.replace("--index-url https://download.pytorch.org/whl/cu124", "--index-url https://download.pytorch.org/whl/cpu")
            dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
            gpu_device = "cpu"
            code, output = run_process(
                ["docker", "build", "--no-cache", "-t", image_name, str(sam3_data)],
                live_cb=live_cb,
            )
            if code != 0:
                return code, output
        else:
            return code, output

    # Run container
    docker_cmd = ["docker", "run", "-d", "--name", container_name, "--restart", "unless-stopped"]
    docker_cmd += ["-p", f"{http_port}:{http_port}"]
    if https_port:
        docker_cmd += ["-p", f"{https_port}:{https_port}"]
    if gpu_device == "cuda":
        docker_cmd += ["--gpus", "all"]
    # Model is already baked into the image (copied into build context before docker build)
    docker_cmd.append(image_name)

    if live_cb:
        live_cb("Starting SAM3 Docker container...\n")
    code2, output2 = run_process(docker_cmd, live_cb=live_cb)

    # If container start fails due to port conflict, give a clear error
    if code2 != 0 and ("port is already allocated" in output2.lower() or "bind" in output2.lower()):
        return code2, f"Failed to start container: port {http_port} is already in use. Choose a different port."

    combined = f"{output.rstrip()}\n{output2}".strip()
    if code2 == 0:
        if not host_ip:
            host_ip = choose_service_host()
        http_url = f"http://{host_ip}:{http_port}"
        https_url = f"https://{host_ip}:{https_port}" if https_port else ""
        state = _read_json_file(SAM3_STATE_FILE)
        state.update({
            "installed": True,
            "service_name": container_name,
            "deploy_mode": "docker",
            "host": host_ip,
            "http_port": http_port,
            "https_port": https_port,
            "http_url": http_url,
            "https_url": https_url,
            "device": gpu_device,
            "running": True,
        })
        _write_json_file(SAM3_STATE_FILE, state)

        # Wait for container to be healthy, then show URLs
        if live_cb:
            live_cb("\nWaiting for SAM3 container to start...\n")
        import time
        ready = False
        for i in range(20):
            time.sleep(3)
            try:
                if is_local_tcp_port_listening(int(http_port)):
                    ready = True
                    break
            except Exception:
                pass
            # Check container health — detect crash loops
            try:
                rc, out = run_capture(["docker", "inspect", "--format", "{{.RestartCount}}", container_name], timeout=10)
                if rc == 0 and out.strip().isdigit() and int(out.strip()) > 3:
                    if live_cb:
                        live_cb(f"Container is crash-looping (restarted {out.strip()} times). Checking logs...\n")
                    rc2, logs = run_capture(["docker", "logs", "--tail", "40", container_name], timeout=10)
                    if live_cb and logs:
                        live_cb(logs + "\n")
                    return 1, "SAM3 container keeps crashing. Check the logs above."
            except Exception:
                pass
            # Check container is still there
            try:
                rc, out = run_capture(["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Status}}"], timeout=10)
                if rc != 0 or not out.strip():
                    if live_cb:
                        live_cb("Container stopped unexpectedly. Checking logs...\n")
                    rc2, logs = run_capture(["docker", "logs", "--tail", "40", container_name], timeout=10)
                    if live_cb and logs:
                        live_cb(logs + "\n")
                    return 1, "SAM3 container failed to start. Check Docker logs."
            except Exception:
                pass
            if live_cb:
                live_cb(f"Waiting for SAM3... ({i+1}/20)\n")

        # Show container logs for debugging regardless of outcome
        if live_cb and not ready:
            live_cb("\nContainer logs:\n")
            try:
                rc2, logs = run_capture(["docker", "logs", "--tail", "20", container_name], timeout=10)
                if logs:
                    live_cb(logs + "\n")
            except Exception:
                pass

        if live_cb:
            live_cb("\n" + "=" * 60 + "\n")
            live_cb(" SAM3 Docker Deployment Complete!\n")
            live_cb("=" * 60 + "\n")
            live_cb(f" Web UI (HTTP):  {http_url}\n")
            if https_url:
                live_cb(f" Web UI (HTTPS): {https_url}\n")
            live_cb(f" Device: {gpu_device}\n")
            live_cb(f" Container: {container_name}\n")
            if ready:
                live_cb(f" Status: Running\n")
            else:
                live_cb(f" Status: Starting (may take a moment to load the model)\n")
            live_cb("=" * 60 + "\n")
    return code2, combined


def _kill_sam3_processes(live_cb=None):
    """Kill any running SAM3 Python processes (fallback when service stop fails)."""
    killed = False
    try:
        import subprocess
        if os.name == "nt":
            # Kill ALL python processes that have sam3 paths in their working dir or command line
            # Use multiple strategies to catch the process
            ps_script = """
$sam3Patterns = @('*sam3*', '*SAM3*', '*start-sam3*')
$killed = @()
foreach ($proc in Get-Process -Name python*, pythonw* -ErrorAction SilentlyContinue) {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
        $match = $false
        foreach ($p in $sam3Patterns) {
            if ($cmdLine -like $p) { $match = $true; break }
            if ($proc.Path -like $p) { $match = $true; break }
        }
        if ($match) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $killed += $proc.Id
        }
    } catch {}
}
if ($killed.Count -eq 0) {
    # Broader fallback: kill python processes listening on SAM3 ports
    $sam3State = $null
    $stateFile = Join-Path $env:ProgramData 'Server-Installer\\sam3\\sam3-state.json'
    if (Test-Path $stateFile) {
        $sam3State = Get-Content $stateFile -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
    }
    $ports = @()
    if ($sam3State.http_port) { $ports += $sam3State.http_port }
    if ($sam3State.https_port) { $ports += $sam3State.https_port }
    foreach ($port in $ports) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            $killed += $c.OwningProcess
        }
    }
}
Write-Output "Killed $($killed.Count) process(es)"
"""
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=15
            )
            if live_cb and result.stdout.strip():
                live_cb(f"{result.stdout.strip()}\n")
            killed = "Killed 0" not in (result.stdout or "")
        else:
            # Linux/macOS: pkill
            subprocess.run(["pkill", "-f", "start-sam3"], capture_output=True, timeout=5)
            killed = True
    except Exception as ex:
        if live_cb:
            live_cb(f"[WARN] Kill failed: {ex}\n")
    return killed


def run_sam3_stop(live_cb=None):
    """Stop the SAM3 service."""
    state = _read_json_file(SAM3_STATE_FILE)
    deploy_mode = str(state.get("deploy_mode") or "os").strip()
    service_name = str(state.get("service_name") or "").strip()
    code = 1
    output = ""

    if deploy_mode == "docker":
        code, output = run_process(["docker", "stop", service_name or "serverinstaller-sam3"], live_cb=live_cb)
    elif os.name == "nt":
        # Try NSSM first, then scheduled task, then kill processes directly
        nssm = shutil.which("nssm")
        if nssm:
            code, output = run_process([nssm, "stop", service_name or "ServerInstaller-SAM3"], live_cb=live_cb)
        if code != 0 and service_name:
            code, output = run_process(["schtasks", "/End", "/TN", service_name], live_cb=live_cb)
        if code != 0:
            # Fallback: kill SAM3 python processes directly
            if _kill_sam3_processes(live_cb=live_cb):
                code = 0
                output = "SAM3 processes killed."
    else:
        code, output = run_process(["systemctl", "stop", f"{service_name or SAM3_SYSTEMD_SERVICE}.service"], live_cb=live_cb)
        if code != 0:
            _kill_sam3_processes(live_cb=live_cb)
            code = 0

    if code == 0:
        state["running"] = False
        _write_json_file(SAM3_STATE_FILE, state)
    return code, output


def run_sam3_start(live_cb=None):
    """Start the SAM3 service."""
    state = _read_json_file(SAM3_STATE_FILE)
    deploy_mode = str(state.get("deploy_mode") or "os").strip()
    service_name = str(state.get("service_name") or "").strip()
    code = 1
    output = ""

    if deploy_mode == "docker":
        code, output = run_process(["docker", "start", service_name or "serverinstaller-sam3"], live_cb=live_cb)
    elif os.name == "nt":
        # Try NSSM, then scheduled task
        nssm = shutil.which("nssm")
        if nssm:
            code, output = run_process([nssm, "start", service_name or "ServerInstaller-SAM3"], live_cb=live_cb)
        if code != 0 and service_name:
            code, output = run_process(["schtasks", "/Run", "/TN", service_name], live_cb=live_cb)
        if code != 0:
            # Fallback: launch the SAM3 process directly in background
            install_dir = str(state.get("install_dir") or str(SAM3_STATE_DIR / "app")).strip()
            startup_script = Path(install_dir) / "start-sam3.py"
            venv_python = str(state.get("python_executable") or "").strip()
            if not venv_python:
                venv_python = str(Path(install_dir) / "venv" / "Scripts" / "python.exe")
            if Path(venv_python).exists() and startup_script.exists():
                import subprocess
                subprocess.Popen(
                    [venv_python, str(startup_script)],
                    cwd=install_dir,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                code = 0
                output = "SAM3 started as background process."
                if live_cb:
                    live_cb("SAM3 started as background process.\n")
            else:
                output = f"Could not find SAM3 files to start. Reinstall SAM3."
    else:
        code, output = run_process(["systemctl", "start", f"{service_name or SAM3_SYSTEMD_SERVICE}.service"], live_cb=live_cb)

    if code == 0:
        state["running"] = True
        _write_json_file(SAM3_STATE_FILE, state)
    return code, output


def run_sam3_delete(live_cb=None, delete_model=False):
    """Stop and completely remove SAM3 service, venv, and config."""
    state = _read_json_file(SAM3_STATE_FILE)
    deploy_mode = str(state.get("deploy_mode") or "os").strip()
    service_name = str(state.get("service_name") or "").strip()
    install_dir = str(state.get("install_dir") or "").strip()
    outputs = []

    if live_cb:
        live_cb("Stopping SAM3 service...\n")

    # Stop and disable the service
    if deploy_mode == "docker":
        run_process(["docker", "stop", service_name or "serverinstaller-sam3"], live_cb=live_cb)
        run_process(["docker", "rm", "-f", service_name or "serverinstaller-sam3"], live_cb=live_cb)
        outputs.append("Docker container removed.")
    elif os.name == "nt":
        svc = service_name or "ServerInstaller-SAM3"
        nssm = shutil.which("nssm")
        if nssm:
            run_process([nssm, "stop", svc], live_cb=live_cb)
            run_process([nssm, "remove", svc, "confirm"], live_cb=live_cb)
        else:
            run_process(["schtasks", "/End", "/TN", svc], live_cb=live_cb)
            run_process(["schtasks", "/Delete", "/TN", svc, "/F"], live_cb=live_cb)
        outputs.append("Windows service removed.")
    else:
        unit = f"{service_name or SAM3_SYSTEMD_SERVICE}.service"
        run_process(["systemctl", "stop", unit], live_cb=live_cb)
        run_process(["systemctl", "disable", unit], live_cb=live_cb)
        systemd_file = f"/etc/systemd/system/{unit}"
        if Path(systemd_file).exists():
            Path(systemd_file).unlink(missing_ok=True)
            run_process(["systemctl", "daemon-reload"], live_cb=live_cb)
        outputs.append("Systemd service removed.")

    # Remove nginx config
    nginx_conf = f"/etc/nginx/conf.d/{service_name or SAM3_SYSTEMD_SERVICE}.conf"
    if Path(nginx_conf).exists():
        if live_cb:
            live_cb("Removing Nginx config...\n")
        Path(nginx_conf).unlink(missing_ok=True)
        if command_exists("nginx"):
            run_process(["systemctl", "reload", "nginx"], live_cb=live_cb)
        outputs.append("Nginx config removed.")

    # Remove install directory (venv, app files) but preserve models dir unless delete_model
    model_path = str(state.get("model_path") or "").strip()
    model_dir = str(Path(model_path).parent) if model_path else ""
    if install_dir and Path(install_dir).exists():
        if delete_model:
            if live_cb:
                live_cb(f"Removing install directory (including model): {install_dir}\n")
            shutil.rmtree(install_dir, ignore_errors=True)
            outputs.append(f"Install directory removed: {install_dir}")
        else:
            # Remove everything except the models directory
            if live_cb:
                live_cb(f"Removing install directory (keeping model): {install_dir}\n")
            for item in Path(install_dir).iterdir():
                if item.name == "models":
                    continue
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            outputs.append(f"Install directory cleaned (model preserved): {install_dir}")

    # Remove model file if requested
    if delete_model and model_path and Path(model_path).exists():
        if live_cb:
            live_cb(f"Removing model file: {model_path}\n")
        Path(model_path).unlink(missing_ok=True)
        outputs.append("Model file removed.")

    # Remove state file
    if SAM3_STATE_FILE.exists():
        SAM3_STATE_FILE.unlink(missing_ok=True)
        outputs.append("State file removed.")

    # Remove certs
    cert_dir = SAM3_STATE_DIR / "certs"
    if cert_dir.exists():
        shutil.rmtree(str(cert_dir), ignore_errors=True)

    # Remove auth file
    auth_file = Path(f"/etc/nginx/auth/{SAM3_SYSTEMD_SERVICE}.htpasswd")
    if auth_file.exists():
        auth_file.unlink(missing_ok=True)

    if live_cb:
        live_cb("SAM3 service deleted successfully.\n")
    return 0, "\n".join(outputs) + "\nSAM3 deleted successfully."


def run_windows_s3_installer(form, live_cb=None, mode="iis"):
    if os.name != "nt":
        return 1, "Windows S3 installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(S3_WINDOWS_FILES, live_cb=live_cb, refresh=True)

    selected_mode = (form.get("S3_MODE", [mode])[0] or mode or "iis").strip().lower()
    if selected_mode not in ("iis", "docker"):
        selected_mode = "iis"
    docker_support = get_windows_s3_docker_support()
    if selected_mode == "docker" and not docker_support.get("supported", True):
        reason = str(docker_support.get("reason") or "Docker mode is not available on this Windows host.")
        if live_cb:
            live_cb(f"[WARN] {reason} Falling back to IIS mode.\n")
        selected_mode = "iis"
    mode_choice = "2\n" if selected_mode == "docker" else "1\n"
    requested_host = (form.get("LOCALS3_HOST", [""])[0] or "").strip()
    requested_mode = (form.get("LOCALS3_HOST_MODE", [""])[0] or "").strip().lower()
    requested_ip = (form.get("LOCALS3_HOST_IP", [""])[0] or "").strip()
    available_ips = [ip for ip in get_ip_addresses() if ip and not ip.startswith("127.")]
    if (requested_mode in ("", "lan")) and requested_ip:
        form["LOCALS3_HOST"] = [requested_ip]
    elif requested_mode in ("", "lan") and len(available_ips) > 1:
        return 1, "Select an IP address before starting S3 setup."
    elif requested_mode == "custom" and requested_host:
        form["LOCALS3_HOST"] = [requested_host]
    elif requested_mode == "public":
        if not requested_host or requested_host in ("localhost", "127.0.0.1"):
            resolved_host = choose_s3_host(requested_host)
            form["LOCALS3_HOST"] = [resolved_host]
    elif not requested_host or requested_host in ("localhost", "127.0.0.1"):
        if len(available_ips) > 1:
            return 1, "Select an IP address before starting S3 setup."
        resolved_host = choose_s3_host(requested_host)
        form["LOCALS3_HOST"] = [resolved_host]
    requested_ports = [
        ("LOCALS3_HTTPS_PORT", "S3 HTTPS", "_windows_locals3_iis_owns_port"),
        ("LOCALS3_API_PORT", "MinIO API", "_windows_locals3_owns_port"),
        ("LOCALS3_UI_PORT", "MinIO UI", "_windows_locals3_owns_port"),
        ("LOCALS3_CONSOLE_PORT", "MinIO Console HTTPS", "_windows_locals3_owns_port"),
    ]
    for env_name, label, owner_fn_name in requested_ports:
        requested_value = (form.get(env_name, [""])[0] or "").strip()
        if not requested_value:
            continue
        if not requested_value.isdigit():
            return 1, f"{env_name} must be numeric."
        port_ok, reason = _is_windows_tcp_port_usable(requested_value)
        if port_ok:
            continue
        owner_fn = globals().get(owner_fn_name)
        if callable(owner_fn) and owner_fn(requested_value):
            continue
        if reason == "reserved by Windows":
            return 1, f"Requested {label} port {requested_value} is reserved by Windows. Choose another port."
        return 1, f"Requested {label} port {requested_value} is already in use. Choose another port."
    # Script is interactive; only answer the mode prompt to avoid re-running the installer.
    scripted_input = mode_choice + "\n"
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(S3_WINDOWS_INSTALLER),
    ]
    env = os.environ.copy()
    for key in [
        "LOCALS3_MODE",
        "LOCALS3_HOST",
        "LOCALS3_HOST_IP",
        "LOCALS3_HOST_MODE",
        "LOCALS3_ENABLE_LAN",
        "LOCALS3_HTTP_PORT",
        "LOCALS3_HTTPS_PORT",
        "LOCALS3_API_PORT",
        "LOCALS3_UI_PORT",
        "LOCALS3_CONSOLE_PORT",
        "LOCALS3_ROOT_USER",
        "LOCALS3_ROOT_PASSWORD",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
    env["LOCALS3_MODE"] = selected_mode
    code, output = run_process(cmd, env=env, live_cb=live_cb, input_text=scripted_input)
    if code != 0:
        return code, output

    return code, output


def run_windows_mongo_installer(form, live_cb=None):
    if os.name != "nt":
        return 1, "Windows MongoDB installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(MONGO_WINDOWS_FILES, live_cb=live_cb, refresh=True)

    env = os.environ.copy()
    for key in [
        "LOCALMONGO_HOST",
        "LOCALMONGO_HOST_IP",
        "LOCALMONGO_HTTP_PORT",
        "LOCALMONGO_HTTPS_PORT",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_WEB_PORT",
        "LOCALMONGO_ADMIN_USER",
        "LOCALMONGO_ADMIN_PASSWORD",
        "LOCALMONGO_UI_USER",
        "LOCALMONGO_UI_PASSWORD",
        "LOCALMONGO_INSTANCE_NAME",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    requested_host = env.get("LOCALMONGO_HOST", "").strip()
    requested_ip = env.get("LOCALMONGO_HOST_IP", "").strip()
    available_ips = [ip for ip in get_ip_addresses() if ip and not ip.startswith("127.")]
    if (not requested_host) and requested_ip:
        env["LOCALMONGO_HOST"] = requested_ip
    elif not requested_host:
        if len(available_ips) > 1:
            return 1, "Select an IP address before starting MongoDB setup."
        env["LOCALMONGO_HOST"] = choose_service_host()

    windows_mode = (env.get("LOCALMONGO_WINDOWS_MODE", "native") or "native").strip().lower()
    port_keys = ("LOCALMONGO_MONGO_PORT",) if windows_mode != "docker" else (
        "LOCALMONGO_HTTPS_PORT",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_WEB_PORT",
    )
    for port_key in port_keys:
        port_value = env.get(port_key, "").strip()
        if port_value and (not port_value.isdigit()):
            return 1, f"{port_key} must be numeric."

    requested_mongo = env.get("LOCALMONGO_MONGO_PORT", "").strip()
    if requested_mongo and is_local_tcp_port_listening(requested_mongo):
        usage = get_port_usage(requested_mongo, "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested MongoDB port {requested_mongo} is already in use. Choose another port."

    if windows_mode == "docker":
        requested_https = env.get("LOCALMONGO_HTTPS_PORT", "").strip()
        if requested_https and is_local_tcp_port_listening(requested_https):
            usage = get_port_usage(requested_https, "tcp")
            if not usage.get("managed_owner"):
                return 1, f"Requested HTTPS port {requested_https} is already in use. Choose another port."

    return run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MONGO_WINDOWS_INSTALLER),
        ],
        env=env,
        live_cb=live_cb,
    )


def run_unix_mongo_installer(form=None, live_cb=None):
    if os.name == "nt":
        return 1, "Linux/macOS MongoDB installer can only run on Linux or macOS hosts."
    ensure_repo_files(MONGO_UNIX_FILES, live_cb=live_cb, refresh=True)
    form = form or {}

    env = os.environ.copy()
    for key in [
        "LOCALMONGO_HOST",
        "LOCALMONGO_HOST_IP",
        "LOCALMONGO_HTTP_PORT",
        "LOCALMONGO_HTTPS_PORT",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_WEB_PORT",
        "LOCALMONGO_ADMIN_USER",
        "LOCALMONGO_ADMIN_PASSWORD",
        "LOCALMONGO_UI_USER",
        "LOCALMONGO_UI_PASSWORD",
        "LOCALMONGO_INSTANCE_NAME",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    requested_host = env.get("LOCALMONGO_HOST", "").strip()
    requested_ip = env.get("LOCALMONGO_HOST_IP", "").strip()
    available_ips = [ip for ip in get_ip_addresses() if ip and not ip.startswith("127.")]
    if (not requested_host) and requested_ip:
        env["LOCALMONGO_HOST"] = requested_ip
    elif not requested_host:
        if len(available_ips) > 1:
            return 1, "Select an IP address before starting MongoDB setup."
        env["LOCALMONGO_HOST"] = choose_service_host()

    # Native Linux installer only needs the MongoDB port — HTTPS/WEB ports are Docker-only.
    mongo_port_value = env.get("LOCALMONGO_MONGO_PORT", "").strip()
    if mongo_port_value and not mongo_port_value.isdigit():
        return 1, "LOCALMONGO_MONGO_PORT must be numeric."
    if mongo_port_value and is_local_tcp_port_listening(mongo_port_value):
        usage = get_port_usage(mongo_port_value, "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested MongoDB port {mongo_port_value} is already in use. Choose another port."

    passthrough_keys = [
        "LOCALMONGO_HOST",
        "LOCALMONGO_HOST_IP",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_ADMIN_USER",
        "LOCALMONGO_ADMIN_PASSWORD",
        "LOCALMONGO_INSTANCE_NAME",
        "LOCALMONGO_VERSION",
    ]
    cmd = ["bash", str(ROOT / "Mongo" / "linux-macos" / "setup-mongodb.sh")]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "env"]
        for key in passthrough_keys:
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(ROOT / "Mongo" / "linux-macos" / "setup-mongodb.sh")]

    return run_process(cmd, env=env, live_cb=live_cb)


def _find_docker_desktop_exe_windows():
    """Search common install paths for Docker Desktop.exe on Windows."""
    candidates = []
    for base in [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("ProgramW6432", ""),
    ]:
        if not base:
            continue
        candidates += [
            os.path.join(base, "Docker", "Docker", "Docker Desktop.exe"),
            os.path.join(base, "Programs", "Docker", "Docker", "Docker Desktop.exe"),
        ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _find_docker_bin_windows():
    """Return the first Docker CLI bin directory found on Windows."""
    for base in [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("ProgramW6432", ""),
    ]:
        if not base:
            continue
        for rel in ["Docker\\Docker\\resources\\bin", "Programs\\Docker\\Docker\\resources\\bin"]:
            d = os.path.join(base, rel)
            if os.path.isfile(os.path.join(d, "docker.exe")):
                return d
    return ""


def _docker_info_check(prefix=None, context=None):
    """
    Run `[prefix...] docker [--context ctx] info` and return True if exit code 0.
    prefix: e.g. ["sudo"] or [] or None
    context: e.g. "desktop-linux" or None
    """
    cmd = list(prefix or []) + ["docker"]
    if context:
        cmd += ["--context", context]
    cmd += ["info"]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _ensure_docker_windows_ready(live_cb=None):
    """
    Ensure Docker CLI is installed and the Docker Engine is running on Windows.
    Checks CLI, finds/installs Docker Desktop, starts it, and waits for the engine.
    Returns (ok: bool, docker_context: str, error_msg: str).
    """
    def emit(msg):
        if live_cb:
            live_cb(msg if msg.endswith("\n") else msg + "\n")

    # ── Step 1: Docker CLI ────────────────────────────────────────────────
    emit("[1/5] Checking Docker CLI...")
    docker_bin = _find_docker_bin_windows()
    if docker_bin and docker_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")

    if not shutil.which("docker") and docker_bin:
        pass  # PATH was just updated
    elif not shutil.which("docker"):
        emit("      Docker CLI not found in PATH or default locations.")
    else:
        emit(f"      Docker CLI found: {shutil.which('docker')}")

    # ── Step 2: Docker Desktop installation ──────────────────────────────
    emit("[2/5] Checking Docker Desktop installation...")
    desktop_exe = _find_docker_desktop_exe_windows()
    if desktop_exe:
        emit(f"      Docker Desktop found: {desktop_exe}")
    else:
        emit("      Docker Desktop is NOT installed.")
        emit("[3/5] Downloading and installing Docker Desktop (this may take several minutes)...")
        cache_dir = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "ServerInstaller", "downloads")
        os.makedirs(cache_dir, exist_ok=True)
        installer_path = os.path.join(cache_dir, "DockerDesktopInstaller.exe")
        download_urls = [
            "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe",
            "https://desktop.docker.com/win/stable/amd64/Docker%20Desktop%20Installer.exe",
        ]
        downloaded = False
        for url in download_urls:
            emit(f"      Downloading from: {url}")
            try:
                dl = subprocess.run(
                    ["powershell", "-Command",
                     f"$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '{url}' -OutFile '{installer_path}' -UseBasicParsing"],
                    capture_output=True, timeout=600
                )
                if dl.returncode == 0 and os.path.isfile(installer_path) and os.path.getsize(installer_path) > 100_000_000:
                    downloaded = True
                    emit("      Download complete.")
                    break
            except Exception as ex:
                emit(f"      Download attempt failed: {ex}")
        if not downloaded:
            return False, "", ("Docker Desktop download failed. "
                               "Please install manually: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe")
        emit("      Installing Docker Desktop (silent install, please wait)...")
        try:
            inst = subprocess.run(
                [installer_path, "install", "--quiet", "--accept-license"],
                capture_output=True, timeout=600
            )
            if inst.returncode not in (0, 3010):
                return False, "", f"Docker Desktop installer exited with code {inst.returncode}. Please install manually."
        except Exception as ex:
            return False, "", f"Docker Desktop installation error: {ex}"
        emit("      Docker Desktop installed.")
        # Refresh CLI path
        docker_bin = _find_docker_bin_windows()
        if docker_bin and docker_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = docker_bin + os.pathsep + os.environ.get("PATH", "")
        desktop_exe = _find_docker_desktop_exe_windows()
        if not desktop_exe:
            return False, "", "Docker Desktop installed but .exe not found. A system restart may be required."

    # ── Step 3 (skipped — was install): Start Docker Desktop ─────────────
    emit("[4/5] Checking if Docker Engine is running...")
    # Try both the default context and desktop-linux
    active_ctx = None
    for ctx in (None, "desktop-linux"):
        if _docker_info_check(context=ctx):
            active_ctx = ctx or "default"
            emit(f"      Docker Engine is already running (context: {active_ctx}).")
            break

    if active_ctx is None:
        emit("      Docker Engine is not responding. Starting Docker Desktop...")
        if desktop_exe and os.path.isfile(desktop_exe):
            subprocess.Popen([desktop_exe], close_fds=True)
        else:
            emit("      Warning: Docker Desktop executable not found; attempting 'docker context use desktop-linux' anyway.")

        emit("[5/5] Waiting for Docker Engine to start (up to 3 minutes)...")
        # Switch context to desktop-linux early
        try:
            subprocess.run(["docker", "context", "use", "desktop-linux"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass

        for tick in range(36):  # 36 × 5s = 180s
            time.sleep(5)
            elapsed = (tick + 1) * 5
            for ctx in ("desktop-linux", None):
                if _docker_info_check(context=ctx):
                    active_ctx = ctx or "default"
                    emit(f"      Docker Engine ready after {elapsed}s (context: {active_ctx}).")
                    break
            if active_ctx:
                break
            if elapsed % 20 == 0:
                emit(f"      Still waiting for Docker Engine... ({elapsed}/180s)")

        if active_ctx is None:
            return False, "", (
                "Docker Engine did not start within 3 minutes.\n"
                "Please open Docker Desktop manually, wait for 'Engine running', then retry.\n"
                "If this is a fresh install, a Windows restart may be required first."
            )

    return True, active_ctx, ""


def _ensure_docker_linux_ready(live_cb=None):
    """
    Ensure Docker CLI is installed and running on Linux/macOS.
    Returns (ok: bool, docker_prefix: list, error_msg: str).
    """
    def emit(msg):
        if live_cb:
            live_cb(msg if msg.endswith("\n") else msg + "\n")

    # Determine sudo prefix
    sudo_prefix = []
    try:
        if os.geteuid() != 0 and subprocess.run(
            ["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            sudo_prefix = ["sudo"]
    except AttributeError:
        pass

    emit("[1/3] Checking Docker CLI...")
    has_docker = bool(shutil.which("docker"))
    if has_docker:
        emit(f"      Docker CLI found: {shutil.which('docker')}")
    else:
        emit("      Docker CLI not found.")

    emit("[2/3] Checking if Docker Engine is running...")
    if has_docker and _docker_info_check(prefix=sudo_prefix):
        emit("      Docker Engine is running.")
        return True, sudo_prefix, ""

    # Need to install or start Docker
    import platform
    system = platform.system().lower()
    if not has_docker:
        emit("[3/3] Installing Docker...")
        if system == "linux":
            install_script = (
                "apt-get update -qq 2>/dev/null | tail -1 || true; "
                "if command -v apt-get >/dev/null 2>&1; then "
                "  apt-get install -y --no-install-recommends docker.io ca-certificates curl 2>&1; "
                "else "
                "  curl -fsSL https://get.docker.com | sh 2>&1; "
                "fi; "
                "systemctl enable --now docker 2>&1 || service docker start 2>&1 || true"
            )
            code, out = run_process(sudo_prefix + ["bash", "-c", install_script], live_cb=live_cb)
            if code != 0:
                return False, sudo_prefix, out or "Docker installation failed."
            emit("      Docker installed successfully.")
        elif system == "darwin":
            return False, sudo_prefix, (
                "Docker is not installed on macOS. "
                "Please install Docker Desktop from https://www.docker.com/products/docker-desktop/ and start it."
            )
    else:
        # Docker installed but not running
        emit("[3/3] Starting Docker service...")
        run_process(sudo_prefix + ["bash", "-c",
            "systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true"],
            live_cb=None)
        time.sleep(3)

    # Final check
    if _docker_info_check(prefix=sudo_prefix):
        return True, sudo_prefix, ""
    if _docker_info_check():
        return True, [], ""
    return False, sudo_prefix, "Docker is installed but engine is still not responding. Try restarting it manually."


def run_mongo_docker(form=None, live_cb=None):
    """Deploy MongoDB + mongo-express in Docker containers with optional nginx HTTPS (Linux only)."""
    form = form or {}
    is_windows = os.name == "nt"

    admin_user = (form.get("LOCALMONGO_ADMIN_USER", [""])[0] or "admin").strip()
    admin_pass = (form.get("LOCALMONGO_ADMIN_PASSWORD", [""])[0] or "StrongPassword123").strip()
    ui_user = (form.get("LOCALMONGO_UI_USER", [""])[0] or "admin").strip()
    ui_pass = (form.get("LOCALMONGO_UI_PASSWORD", [""])[0] or "StrongPassword123").strip()
    mongo_port = (form.get("LOCALMONGO_MONGO_PORT", [""])[0] or "27017").strip()
    web_port = (form.get("LOCALMONGO_WEB_PORT", [""])[0] or "8081").strip()
    https_port = (form.get("LOCALMONGO_HTTPS_PORT", [""])[0] or "").strip()
    http_port = (form.get("LOCALMONGO_HTTP_PORT", [""])[0] or "").strip()
    raw_instance = re.sub(r"[^a-zA-Z0-9_-]", "", (form.get("LOCALMONGO_INSTANCE_NAME", [""])[0] or "localmongo").strip()).lower()
    instance_name = raw_instance if re.match(r"^[a-z][a-z0-9_-]{0,29}$", raw_instance) else "localmongo"

    for name, val in [("MongoDB port", mongo_port), ("Web UI port", web_port)]:
        if val and not val.isdigit():
            return 1, f"{name} must be numeric."
    if https_port and not https_port.isdigit():
        return 1, "HTTPS port must be numeric."
    if http_port and not http_port.isdigit():
        return 1, "HTTP port must be numeric."

    # On Windows, skip nginx (no HTTPS proxy); on Linux default to HTTPS if nothing set
    if not is_windows and not https_port and not http_port:
        https_port = "9445"

    docker_prefix = []
    docker_context = None  # Windows: context name to pass as --context

    # ── Ensure Docker is installed and running ────────────────────────────
    if is_windows:
        ok, docker_context, err_msg = _ensure_docker_windows_ready(live_cb=live_cb)
        if not ok:
            return 1, err_msg
        # Build Windows docker prefix with context
        if docker_context and docker_context != "default":
            docker_prefix = ["docker", "--context", docker_context]
        else:
            docker_prefix = ["docker"]
        # docker_prefix replaces the base "docker" command
        docker_cmd_base = docker_prefix
    else:
        ok, docker_prefix_sudo, err_msg = _ensure_docker_linux_ready(live_cb=live_cb)
        if not ok:
            return 1, err_msg
        docker_prefix = docker_prefix_sudo
        docker_cmd_base = docker_prefix + ["docker"]

    # Remove old containers if they exist
    for cname in [f"{instance_name}-db", f"{instance_name}-web"]:
        run_process(docker_cmd_base + ["rm", "-f", cname], live_cb=None)

    # Start MongoDB container
    if live_cb:
        live_cb(f"Starting MongoDB container '{instance_name}-db' on port {mongo_port}...\n")
    mongo_run = docker_cmd_base + [
        "run", "-d",
        "--name", f"{instance_name}-db",
        "--restart", "unless-stopped",
        "-p", f"127.0.0.1:{mongo_port}:27017",
        "-e", f"MONGO_INITDB_ROOT_USERNAME={admin_user}",
        "-e", f"MONGO_INITDB_ROOT_PASSWORD={admin_pass}",
        "mongo:latest",
    ]
    code, out = run_process(mongo_run, live_cb=live_cb)
    if code != 0:
        return code, out or "Failed to start MongoDB container."

    # Start mongo-express container (web UI on localhost only)
    internal_web_port = str(int(web_port))
    if live_cb:
        live_cb(f"Starting mongo-express web UI '{instance_name}-web' on port {internal_web_port}...\n")
    mongoexpress_run = docker_cmd_base + [
        "run", "-d",
        "--name", f"{instance_name}-web",
        "--restart", "unless-stopped",
        "--link", f"{instance_name}-db:mongo",
        "-p", f"127.0.0.1:{internal_web_port}:8081",
        "-e", f"ME_CONFIG_MONGODB_ADMINUSERNAME={admin_user}",
        "-e", f"ME_CONFIG_MONGODB_ADMINPASSWORD={admin_pass}",
        "-e", f"ME_CONFIG_BASICAUTH_USERNAME={ui_user}",
        "-e", f"ME_CONFIG_BASICAUTH_PASSWORD={ui_pass}",
        "-e", "ME_CONFIG_MONGODB_URL=mongodb://$(ME_CONFIG_MONGODB_ADMINUSERNAME):$(ME_CONFIG_MONGODB_ADMINPASSWORD)@mongo:27017/",
        "mongo-express:latest",
    ]
    code, out = run_process(mongoexpress_run, live_cb=live_cb)
    if code != 0 and live_cb:
        live_cb(f"[WARN] mongo-express failed to start: {out}\n")

    resolved_ip = choose_service_host()
    extra = f"\nMongoDB Docker deploy complete.\nMongoDB port: {mongo_port}\nWeb UI: http://127.0.0.1:{internal_web_port}\n"
    if is_windows:
        extra += f"Web UI accessible at: http://localhost:{internal_web_port}\nNote: HTTPS/nginx proxy is not configured on Windows. Access directly via the port above.\n"

    # Set up nginx HTTPS for the web UI if requested (Linux/macOS only)
    if https_port and not is_windows:
        service_name = instance_name
        cert_dir = f"/etc/nginx/ssl/{service_name}"
        nginx_script = f"""
set -euo pipefail
command -v nginx >/dev/null 2>&1 || {{ echo "nginx not found; skipping nginx setup."; exit 0; }}
mkdir -p "{cert_dir}"
if [[ ! -f "{cert_dir}/server.crt" || ! -f "{cert_dir}/server.key" ]]; then
  HOST=$(hostname -I | awk '{{{{print $1}}}}')
  SAN="IP:$HOST"
  openssl req -x509 -nodes -newkey rsa:2048 \\
    -keyout "{cert_dir}/server.key" -out "{cert_dir}/server.crt" \\
    -days 825 -subj "/CN=$HOST" -addext "subjectAltName=$SAN" 2>/dev/null
  chmod 600 "{cert_dir}/server.key"
fi
cat > "/etc/nginx/conf.d/{service_name}.conf" <<'NGINX'
server {{{{
    listen {https_port} ssl;
    server_name _;
    ssl_certificate {cert_dir}/server.crt;
    ssl_certificate_key {cert_dir}/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    location / {{{{
        proxy_pass http://127.0.0.1:{internal_web_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }}}}
}}}}
NGINX
nginx -t && (systemctl is-active --quiet nginx && systemctl reload nginx || systemctl restart nginx)
echo "nginx configured: HTTPS={https_port} -> web UI port {internal_web_port}"
"""
        sudo_prefix = []
        if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            sudo_prefix = ["sudo"]
        nginx_code, nginx_out = run_process(sudo_prefix + ["bash", "-c", nginx_script], live_cb=live_cb)
        if nginx_code == 0:
            extra += f"MongoDB Web UI HTTPS: https://{resolved_ip}:{https_port}\n"
            if http_port:
                manage_firewall_port("open", http_port, "tcp", host=resolved_ip)
                _setup_nginx_http_redirect(service_name, http_port, https_port, live_cb=live_cb)
                extra += f"HTTP URL: http://{resolved_ip}:{http_port} (redirects to HTTPS)\n"
        else:
            if live_cb:
                live_cb(f"[WARN] nginx setup failed. Web UI available only at http://127.0.0.1:{internal_web_port}\n")
        manage_firewall_port("open", https_port, "tcp", host=resolved_ip)

    if live_cb:
        live_cb(extra)
    return 0, extra


def run_linux_proxy_installer(form=None, live_cb=None):
    if os.name == "nt":
        return 1, "Linux proxy installer can only run on Linux/macOS hosts."
    if live_cb:
        live_cb("[INFO] Checking and updating Proxy installer files...\n")
    ensure_repo_files(PROXY_SYNC_FILES, live_cb=live_cb, refresh=True)
    form = form or {}
    env = os.environ.copy()
    for key in ("PROXY_LAYER", "PROXY_DOMAIN", "PROXY_EMAIL", "PROXY_DUCKDNS_TOKEN", "PROXY_PANEL_PORT", "PROXY_HOST_IP", "SERVER_INSTALLER_DASHBOARD_PORT"):
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    panel_port = env.get("PROXY_PANEL_PORT", "").strip()
    if panel_port:
        if not panel_port.isdigit():
            return 1, "PROXY_PANEL_PORT must be numeric."
        if is_local_tcp_port_listening(panel_port):
            usage = get_port_usage(panel_port, "tcp")
            if not usage.get("managed_owner"):
                return 1, f"Requested proxy dashboard port {panel_port} is already in use. Choose another port."
    env["PROXY_REPO_ROOT"] = str(PROXY_ROOT)
    if not PROXY_LINUX_INSTALLER.exists():
        return 1, f"Proxy installer is missing: {PROXY_LINUX_INSTALLER}"
    cmd = ["bash", str(PROXY_LINUX_INSTALLER)]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "env"]
        for key in ("PROXY_LAYER", "PROXY_DOMAIN", "PROXY_EMAIL", "PROXY_DUCKDNS_TOKEN", "PROXY_PANEL_PORT", "PROXY_HOST_IP", "PROXY_REPO_ROOT", "SERVER_INSTALLER_DATA_DIR", "SERVER_INSTALLER_DASHBOARD_PORT"):
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(PROXY_LINUX_INSTALLER)]
    return run_process(cmd, env=env, live_cb=live_cb)


def run_windows_proxy_installer(form=None, live_cb=None):
    if os.name != "nt":
        return 1, "Windows proxy installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    if live_cb:
        live_cb("[INFO] Checking and updating Proxy installer files...\n")
    ensure_repo_files(PROXY_SYNC_FILES, live_cb=live_cb, refresh=True)
    form = form or {}
    env = os.environ.copy()
    for key in ("PROXY_LAYER", "PROXY_DOMAIN", "PROXY_EMAIL", "PROXY_DUCKDNS_TOKEN", "PROXY_WSL_DISTRO", "PROXY_PANEL_PORT", "PROXY_HOST_IP", "SERVER_INSTALLER_DASHBOARD_PORT"):
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    panel_port = env.get("PROXY_PANEL_PORT", "").strip()
    if panel_port:
        if not panel_port.isdigit():
            return 1, "PROXY_PANEL_PORT must be numeric."
        if is_local_tcp_port_listening(panel_port):
            usage = get_port_usage(panel_port, "tcp")
            if not usage.get("managed_owner"):
                return 1, f"Requested proxy dashboard port {panel_port} is already in use. Choose another port."
    if is_windows_local_system():
        env["PROXY_SKIP_INTERACTIVE_RELAUNCH"] = "1"
        return run_windows_interactive_powershell_file(
            PROXY_WINDOWS_INSTALLER,
            env=env,
            live_cb=live_cb,
            timeout=3600,
        )
    return run_process(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROXY_WINDOWS_INSTALLER)],
        env=env,
        live_cb=live_cb,
    )


def manage_proxy_service(action, name):
    action = (action or "").strip().lower()
    svc_name = _safe_service_name(name)
    if action not in ("start", "stop", "restart", "delete"):
        return False, "Supported actions: start, stop, restart, delete."
    if not svc_name:
        return False, "Invalid proxy service name."
    if os.name == "nt":
        state = _read_json_file(PROXY_WINDOWS_STATE)
        distro = str(state.get("distro") or os.environ.get("PROXY_WSL_DISTRO", "Ubuntu")).strip()
        if svc_name.lower() == "serverinstaller-proxywsl":
            if action == "delete":
                rc, out = run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-ProxyWSL", "/F"], timeout=30)
                try:
                    PROXY_WINDOWS_STATE.unlink(missing_ok=True)
                except Exception:
                    pass
                return rc == 0, (out or "ServerInstaller-ProxyWSL task deleted.")
            task_action = {"start": "/Run", "stop": "/End", "restart": "/Run"}[action]
            if action == "restart":
                run_capture(["schtasks", "/End", "/TN", "ServerInstaller-ProxyWSL"], timeout=15)
            rc, out = run_capture(["schtasks", task_action, "/TN", "ServerInstaller-ProxyWSL"], timeout=30)
            return rc == 0, (out or f"Action '{action}' requested for ServerInstaller-ProxyWSL.")
        if action == "delete":
            if svc_name.lower() != "proxy-panel":
                return False, "Delete is only supported for the managed Proxy stack entry."
            cleanup_script = """
set -e
if [ -f /opt/proxy-panel/repo/common/uninstall.sh ]; then
  bash /opt/proxy-panel/repo/common/uninstall.sh || true
fi
systemctl stop proxy-panel >/dev/null 2>&1 || true
systemctl disable proxy-panel >/dev/null 2>&1 || true
rm -f /etc/systemd/system/proxy-panel.service || true
systemctl daemon-reload >/dev/null 2>&1 || true
rm -rf /opt/proxy-panel || true
"""
            rc, out = run_capture(["wsl.exe", "-d", distro, "--user", "root", "--", "bash", "-lc", cleanup_script], timeout=120)
            run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-ProxyWSL", "/F"], timeout=30)
            try:
                PROXY_WINDOWS_STATE.unlink(missing_ok=True)
            except Exception:
                pass
            return rc == 0, (out or "Proxy stack removed from WSL.")
        linux_action = f"systemctl {action} {shlex.quote(svc_name)}"
        rc, out = run_capture(["wsl.exe", "-d", distro, "--user", "root", "--", "bash", "-lc", linux_action], timeout=60)
        return rc == 0, (out or f"Action '{action}' requested for WSL service '{svc_name}'.")
    prefix = _sudo_prefix()
    if action == "delete":
        if svc_name != "proxy-panel":
            return False, "Delete is only supported for the managed Proxy stack entry."
        cleanup_script = (
            "set -e; "
            "if [ -f /opt/proxy-panel/repo/common/uninstall.sh ]; then bash /opt/proxy-panel/repo/common/uninstall.sh || true; fi; "
            "systemctl stop proxy-panel >/dev/null 2>&1 || true; "
            "systemctl disable proxy-panel >/dev/null 2>&1 || true; "
            "rm -f /etc/systemd/system/proxy-panel.service || true; "
            "systemctl daemon-reload >/dev/null 2>&1 || true; "
            "rm -rf /opt/proxy-panel || true"
        )
        rc, out = run_capture(prefix + ["bash", "-lc", cleanup_script], timeout=120)
        return rc == 0, (out or "Proxy stack removed.")
    rc, out = run_capture(prefix + ["systemctl", action, svc_name], timeout=60)
    if rc == 0:
        return True, (out or f"Action '{action}' requested for {svc_name}.")
    if not svc_name.endswith(".service"):
        rc, out = run_capture(prefix + ["systemctl", action, f"{svc_name}.service"], timeout=60)
        if rc == 0:
            return True, (out or f"Action '{action}' requested for {svc_name}.service.")
    return False, (out or f"Failed to {action} {svc_name}.")


def run_linux_s3_installer(form=None, live_cb=None):
    if os.name == "nt":
        return 1, "Linux S3 installer can only run on Linux/macOS hosts."
    if live_cb:
        live_cb("[INFO] Checking and updating S3 installer files...\n")
    ensure_repo_files(S3_LINUX_FILES, live_cb=live_cb, refresh=True)
    form = form or {}
    if live_cb:
        live_cb(f"[DEBUG] Dashboard build: {BUILD_ID}\n")
        live_cb(f"[DEBUG] Linux S3 core path: {(ROOT / 'S3' / 'linux-macos' / 'modules' / 'core.sh')}\n")
    if not ((form.get("LOCALS3_CONSOLE_PORT", [""])[0] or "").strip()):
        form["LOCALS3_CONSOLE_PORT"] = ["9443"]

    requested_https = (form.get("LOCALS3_HTTPS_PORT", [""])[0] or "").strip()
    if requested_https and (not requested_https.isdigit()):
        return 1, "LOCALS3_HTTPS_PORT must be numeric."
    if requested_https and is_local_tcp_port_listening(requested_https):
        if _linux_locals3_owns_port(requested_https):
            if live_cb:
                live_cb(f"Requested HTTPS port {requested_https} is currently owned by LocalS3. Reclaiming it...\n")
            stop_code, stop_out = run_linux_s3_stop(live_cb=live_cb)
            if stop_code != 0 and live_cb and stop_out:
                live_cb(stop_out + "\n")
            # Selected HTTPS port is strict: never auto-switch to another port.
            # Give the OS a short moment to release sockets after stop/reload.
            still_busy = False
            for attempt in range(10):
                if is_local_tcp_port_listening(requested_https):
                    still_busy = True
                    if live_cb and attempt in (0, 4, 8):
                        live_cb(f"[WARN] Port {requested_https} still busy after reclaim attempt {attempt + 1}/10.\n")
                    time.sleep(1)
                    continue
                still_busy = False
                break
            if still_busy:
                if live_cb:
                    listeners = get_port_usage(requested_https, "tcp")
                    live_cb(f"[ERROR] Port {requested_https} remains in use after reclaim. Listeners: {listeners.get('listeners')}\n")
                return 1, (
                    f"Requested HTTPS port {requested_https} is still busy after LocalS3 reclaim attempt. "
                    "Please stop the process using this port or choose another port."
                )
        else:
            return 1, f"Requested HTTPS port {requested_https} is already in use by another app. Choose another port."

    requested_host = (form.get("LOCALS3_HOST", [""])[0] or "").strip()
    if not requested_host:
        # Use the IP the user selected in the frontend dropdown
        requested_host_ip = (form.get("LOCALS3_HOST_IP", [""])[0] or "").strip()
        if requested_host_ip:
            requested_host = requested_host_ip
            form["LOCALS3_HOST"] = [requested_host_ip]
        else:
            resolved_host = choose_s3_host("")
            form["LOCALS3_HOST"] = [resolved_host]
            requested_host = resolved_host
    # If host is still empty after all fallbacks, auto-resolve
    if not requested_host:
        resolved_host = choose_s3_host("")
        form["LOCALS3_HOST"] = [resolved_host]
        requested_host = resolved_host
    requested_lan = (form.get("LOCALS3_ENABLE_LAN", [""])[0] or "").strip().lower()
    host_line = requested_host if requested_host else ""
    lan_line = "y" if requested_lan in ("1", "true", "yes", "y", "on") else "n"

    # Keep compatibility with older interactive scripts:
    # 1) host prompt
    # 2) (only when host=localhost) "Use public IP instead?" prompt -> answer No
    # 3) LAN prompt
    # 4) use 443 prompt -> default to No
    # 5) choose HTTPS option / custom port
    if requested_https:
        if requested_https == "443":
            https_flow = "y"
        else:
            https_flow = f"n\n2\n{requested_https}"
    else:
        https_flow = "n\n1"

    # When host is localhost, core.sh may ask "Use public IP instead?" - answer No
    if requested_host in ("localhost", "127.0.0.1"):
        scripted_input = f"{host_line}\nn\n{lan_line}\n{https_flow}\n" + ("\n" * 200)
    else:
        scripted_input = f"{host_line}\n{lan_line}\n{https_flow}\n" + ("\n" * 200)
    env = os.environ.copy()
    forwarded_env = {}
    instance_name = re.sub(r"[^a-z0-9-]", "-", (form.get("LOCALS3_INSTANCE_NAME", ["locals3"])[0] or "locals3").strip().lower()) or "locals3"
    forwarded_env["INSTANCE"] = instance_name
    env["INSTANCE"] = instance_name

    for key in [
        "LOCALS3_HOST",
        "LOCALS3_ENABLE_LAN",
        "LOCALS3_HTTP_PORT",
        "LOCALS3_HTTPS_PORT",
        "LOCALS3_API_PORT",
        "LOCALS3_UI_PORT",
        "LOCALS3_CONSOLE_PORT",
        "LOCALS3_ROOT_USER",
        "LOCALS3_ROOT_PASSWORD",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
            forwarded_env[key] = value

    local_core = ROOT / "S3" / "linux-macos" / "modules" / "core.sh"
    local_cleanup = ROOT / "S3" / "linux-macos" / "modules" / "cleanup.sh"
    local_platform = ROOT / "S3" / "linux-macos" / "modules" / "platform.sh"
    env_exports = "".join([f"export {k}={shlex.quote(v)}; " for k, v in forwarded_env.items()])
    # Defensive override: stale module variants may print prompt text to stdout.
    force_port_fn = (
        'resolve_https_port_unix(){ '
        'local p="${LOCALS3_HTTPS_PORT:-}"; '
        'if [ -n "$p" ]; then echo "$p"; return; fi; '
        'echo "8443"; '
        '}; '
    )
    safe_cleanup_fn = (
        'cleanup_previous_locals3(){ '
        'local inst="${INSTANCE:-locals3}"; '
        'local root="/opt/$inst"; '
        '[ "$(detect_os)" = "macos" ] && root="/usr/local/$inst"; '
        'if has_cmd systemctl; then '
        '  systemctl stop "${inst}-minio" >/dev/null 2>&1 || true; '
        '  systemctl stop "${inst}-nginx" >/dev/null 2>&1 || true; '
        'fi; '
        'if [ -f "/opt/$inst/nginx/nginx.pid" ]; then '
        '  kill "$(cat "/opt/$inst/nginx/nginx.pid")" >/dev/null 2>&1 || true; '
        '  rm -f "/opt/$inst/nginx/nginx.pid" || true; '
        'fi; '
        'if [ -d "$root" ]; then '
        '  rm -rf "${root}/data/.minio.sys" >/dev/null 2>&1 || true; '
        '  rm -rf "${root}/config" >/dev/null 2>&1 || true; '
        '  rm -rf "${root}/tmp" >/dev/null 2>&1 || true; '
        'fi; '
        '}; '
    )
    safe_minio_fn = r'''
pick_distinct_port() {
  local used="$1"
  shift
  local p
  for p in "$@"; do
    if [ "$p" = "$used" ]; then
      continue
    fi
    if port_free "$p"; then
      echo "$p"
      return
    fi
  done
  echo ""
}

configure_minio_linux() {
  local root="$1" api_port="$2" ui_port="$3" public_url="$4" console_browser_url="$5"
  local inst="${INSTANCE:-locals3}"
  local bin="/usr/local/bin/minio"
  local data="${root}/data"
  local envf="/etc/default/${inst}-minio"
  mkdir -p "$root" "$data"

  install_minio_binary "$bin"

  cat > "$envf" <<EOF
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=StrongPassword123
MINIO_SERVER_URL=${public_url}
MINIO_BROWSER_REDIRECT_URL=${console_browser_url}
EOF

  cat > "/etc/systemd/system/${inst}-minio.service" <<EOF
[Unit]
Description=Local S3 MinIO (${inst})
After=network.target

[Service]
EnvironmentFile=$envf
ExecStart=$bin server $data --address :$api_port --console-address :$ui_port
Restart=always
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "${inst}-minio"
}

configure_minio_macos() {
  local root="$1" api_port="$2" ui_port="$3" public_url="$4" console_browser_url="$5"
  local inst="${INSTANCE:-locals3}"
  local bin="/usr/local/bin/minio"
  [ -d /opt/homebrew/bin ] && bin="/opt/homebrew/bin/minio"
  local data="${root}/data"
  local plist="/Library/LaunchDaemons/com.${inst}.minio.plist"
  mkdir -p "$root" "$data"
  install_minio_binary "$bin"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.${inst}.minio</string>
  <key>ProgramArguments</key><array>
    <string>$bin</string><string>server</string><string>$data</string>
    <string>--address</string><string>:$api_port</string>
    <string>--console-address</string><string>:$ui_port</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>MINIO_ROOT_USER</key><string>admin</string>
    <key>MINIO_ROOT_PASSWORD</key><string>StrongPassword123</string>
    <key>MINIO_SERVER_URL</key><string>$public_url</string>
    <key>MINIO_BROWSER_REDIRECT_URL</key><string>$console_browser_url</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
EOF

  launchctl bootout system "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap system "$plist"
  launchctl enable "system/com.${inst}.minio"
  launchctl kickstart -k "system/com.${inst}.minio"
}

open_public_tcp_ports_linux() {
  local ports=("$@")
  local port

  [ "${#ports[@]}" -eq 0 ] && return 0

  if has_cmd ufw; then
    for port in "${ports[@]}"; do
      ufw allow "${port}/tcp" >/dev/null 2>&1 || true
    done
  fi

  if has_cmd firewall-cmd; then
    for port in "${ports[@]}"; do
      firewall-cmd --quiet --add-port="${port}/tcp" >/dev/null 2>&1 || true
      firewall-cmd --quiet --permanent --add-port="${port}/tcp" >/dev/null 2>&1 || true
    done
    firewall-cmd --quiet --reload >/dev/null 2>&1 || true
  fi

  if has_cmd iptables; then
    for port in "${ports[@]}"; do
      iptables -C INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || \
        iptables -I INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || true
    done
  fi

  if has_cmd ip6tables; then
    for port in "${ports[@]}"; do
      ip6tables -C INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || \
        ip6tables -I INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || true
    done
  fi
}

main() {
  relaunch_elevated "$@"
  local os root cert_dir https_port console_https_port api_port ui_port domain lan_ans enable_lan expose_remote lan_ip public_ip use_public_ip proxy_host api_url console_url
  os="$(detect_os)"
  [ "$os" = "unknown" ] && { err "Unsupported OS."; exit 1; }
  info "===== Local S3 Storage Installer (${os}) - Native Mode ====="

  read -r -p "Enter local domain/URL for HTTPS (default: localhost): " domain
  domain="$(normalize_host_input "${domain:-}")"
  if [ "$domain" = "localhost" ]; then
    public_ip="$(get_public_ipv4)"
    if [ -n "$public_ip" ]; then
      read -r -p "Detected public/static IP ${public_ip}. Use it instead of localhost? (Y/n): " use_public_ip
      use_public_ip="$(echo "${use_public_ip:-y}" | tr '[:upper:]' '[:lower:]')"
      if [ "$use_public_ip" = "y" ] || [ "$use_public_ip" = "yes" ]; then
        domain="$public_ip"
      fi
    fi
  fi
  read -r -p "Allow LAN access from other computers? (y/N): " lan_ans
  lan_ans="$(echo "${lan_ans:-n}" | tr '[:upper:]' '[:lower:]')"
  enable_lan=false
  expose_remote=false
  lan_ip=""
  if [ "$lan_ans" = "y" ] || [ "$lan_ans" = "yes" ]; then
    enable_lan=true
    expose_remote=true
    lan_ip="$(get_lan_ipv4)"
  fi

  https_port="$(resolve_https_port_unix)"
  if [ "$https_port" != "443" ]; then
    warn "Using HTTPS port: $https_port"
  fi
  if [ -n "${LOCALS3_API_PORT:-}" ]; then
    api_port="${LOCALS3_API_PORT}"
  else
    api_port="$(pick_port 9000 19000 29000)"
  fi
  if [ -n "${LOCALS3_UI_PORT:-}" ]; then
    ui_port="${LOCALS3_UI_PORT}"
  else
    ui_port="$(pick_port 9001 19001 29001)"
  fi
  [ -z "$api_port" ] && { err "No free API port."; exit 1; }
  [ -z "$ui_port" ] && { err "No free UI port."; exit 1; }
  if [ -n "${LOCALS3_CONSOLE_PORT:-}" ]; then
    console_https_port="${LOCALS3_CONSOLE_PORT}"
  else
    console_https_port="$(pick_distinct_port "$https_port" 9443 10443 18443 8444)"
  fi
  [ -z "$console_https_port" ] && { err "No free Console HTTPS port."; exit 1; }

  proxy_host="$domain"
  if [ "$proxy_host" = "localhost" ] && [ -n "$lan_ip" ]; then
    proxy_host="$lan_ip"
  fi
  if [ "$domain" != "localhost" ]; then
    expose_remote=true
  fi
  if [ "$https_port" -eq 443 ]; then
    api_url="https://${proxy_host}"
  else
    api_url="https://${proxy_host}:${https_port}"
  fi
  if [ "$console_https_port" -eq 443 ]; then
    console_url="https://${proxy_host}"
  else
    console_url="https://${proxy_host}:${console_https_port}"
  fi

  root="/opt/${INSTANCE:-locals3}"
  [ "$os" = "macos" ] && root="/usr/local/${INSTANCE:-locals3}"
  cert_dir="${root}/certs"
  mkdir -p "$root" "$cert_dir"

  if [ "$os" = "linux" ]; then
    ensure_prereqs_linux
    configure_minio_linux "$root" "$api_port" "$ui_port" "$api_url" "$console_url"
  else
    ensure_prereqs_macos
    configure_minio_macos "$root" "$api_port" "$ui_port" "$api_url" "$console_url"
  fi

  ensure_hosts_entry "$domain" "127.0.0.1"
  generate_cert "$cert_dir" "$domain" "$lan_ip"
  trust_cert "${cert_dir}/localhost.crt"

  if [ "$os" = "linux" ]; then
    configure_nginx_linux "$domain" "$https_port" "$api_port" "$console_https_port" "$ui_port" "$cert_dir"
    if [ "$expose_remote" = true ]; then
      open_public_tcp_ports_linux "$https_port" "$console_https_port"
    fi
  else
    configure_nginx_macos "$domain" "$https_port" "$api_port" "$console_https_port" "$ui_port" "$cert_dir"
  fi

  echo ""
  echo "===== INSTALLATION COMPLETE ====="
  echo "MinIO Console (direct): http://localhost:${ui_port}"
  echo "MinIO API (direct):     http://localhost:${api_port}"
  echo "API URL:                ${api_url}"
  echo "Console URL:            ${console_url}"
  if [ "$enable_lan" = true ] && [ -n "$lan_ip" ]; then
    if [ "$https_port" -eq 443 ]; then
      echo "LAN API URL:            https://${lan_ip}"
    else
      echo "LAN API URL:            https://${lan_ip}:${https_port}"
    fi
    echo "LAN Console Port:       ${console_https_port}"
    echo "DNS mapping needed:     ${domain} -> ${lan_ip}"
  fi
  echo ""
  echo "Login:"
  echo "  Username: admin"
  echo "  Password: StrongPassword123"
}
'''
    safe_nginx_fn = r'''
configure_nginx_linux() {
  local domain="$1" api_https_port="$2" api_target_port="$3" console_https_port="$4" console_target_port="$5" cert_dir="$6"
  local inst="${INSTANCE:-locals3}"
  local http_port="${LOCALS3_HTTP_PORT:-}"
  cat > "/etc/nginx/conf.d/${inst}.conf" <<EOF
server {
    listen ${api_https_port} ssl;
    server_name ${domain} localhost;
    ssl_certificate ${cert_dir}/localhost.crt;
    ssl_certificate_key ${cert_dir}/localhost.key;
    location / {
        proxy_pass http://127.0.0.1:${api_target_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Ssl on;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen ${console_https_port} ssl;
    server_name ${domain} localhost;
    ssl_certificate ${cert_dir}/localhost.crt;
    ssl_certificate_key ${cert_dir}/localhost.key;
    location / {
        proxy_pass http://127.0.0.1:${console_target_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Ssl on;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

  if [ -n "$http_port" ]; then
    cat >> "/etc/nginx/conf.d/${inst}.conf" <<EOF

server {
    listen ${http_port};
    server_name ${domain} localhost;
    location / {
        proxy_pass http://127.0.0.1:${console_target_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
  fi

  nginx -t || { err "Nginx config test failed."; exit 1; }

  if has_cmd systemctl; then
    systemctl unmask nginx >/dev/null 2>&1 || true
    if systemctl is-active --quiet nginx 2>/dev/null; then
      systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx >/dev/null 2>&1 || true
    else
      systemctl start nginx >/dev/null 2>&1 || true
    fi
    if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
      [ -n "$http_port" ] && open_public_tcp_ports_linux "$http_port"
      return
    fi
  elif has_cmd service; then
    service nginx reload >/dev/null 2>&1 || service nginx restart >/dev/null 2>&1 || true
    if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
      [ -n "$http_port" ] && open_public_tcp_ports_linux "$http_port"
      return
    fi
  fi

  warn "System nginx could not bind HTTPS ports ${api_https_port}/${console_https_port}. Trying isolated LocalS3 nginx..."
  local standalone_dir="/opt/${inst}/nginx"
  local standalone_conf="${standalone_dir}/nginx-standalone.conf"
  local standalone_pid="${standalone_dir}/nginx.pid"
  mkdir -p "$standalone_dir"
  if [ -f "$standalone_pid" ]; then
    kill "$(cat "$standalone_pid")" >/dev/null 2>&1 || true
    rm -f "$standalone_pid" || true
  fi

  local http_block=""
  if [ -n "$http_port" ]; then
    http_block="
    server {
        listen ${http_port};
        server_name ${domain} localhost;
        location / {
            proxy_pass http://127.0.0.1:${console_target_port};
            proxy_http_version 1.1;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Host \$http_host;
            proxy_set_header X-Forwarded-Port \$server_port;
            proxy_set_header X-Forwarded-Proto http;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \"upgrade\";
        }
    }"
  fi

  cat > "$standalone_conf" <<EOF
pid ${standalone_pid};
events {}
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile on;
    access_log    ${standalone_dir}/access.log;
    error_log     ${standalone_dir}/error.log;
    server {
        listen ${api_https_port} ssl;
        server_name ${domain} localhost;
        ssl_certificate ${cert_dir}/localhost.crt;
        ssl_certificate_key ${cert_dir}/localhost.key;
        location / {
            proxy_pass http://127.0.0.1:${api_target_port};
            proxy_http_version 1.1;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Host \$http_host;
            proxy_set_header X-Forwarded-Port \$server_port;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-Ssl on;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
    server {
        listen ${console_https_port} ssl;
        server_name ${domain} localhost;
        ssl_certificate ${cert_dir}/localhost.crt;
        ssl_certificate_key ${cert_dir}/localhost.key;
        location / {
            proxy_pass http://127.0.0.1:${console_target_port};
            proxy_http_version 1.1;
            proxy_set_header Host \$http_host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Host \$http_host;
            proxy_set_header X-Forwarded-Port \$server_port;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-Ssl on;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }${http_block}
}
EOF
  nginx -t -c "$standalone_conf" || { err "Isolated nginx config test failed."; exit 1; }
  nginx -c "$standalone_conf" >/dev/null 2>&1 || true
  if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
    [ -n "$http_port" ] && open_public_tcp_ports_linux "$http_port"
    return
  fi

  err "Nginx did not start correctly on ports ${api_https_port}/${console_https_port}."
  if has_cmd systemctl; then
    warn "nginx.service status:"
    systemctl status nginx --no-pager -l 2>/dev/null || true
  fi
  if [ -f "${standalone_dir}/error.log" ]; then
    warn "Isolated nginx error log:"
    tail -n 80 "${standalone_dir}/error.log" 2>/dev/null || true
  fi
  exit 1
}
'''
    launcher = (
        f"{env_exports}"
        f"source '{local_core}'; "
        f"source '{local_cleanup}'; "
        f"source '{local_platform}'; "
        f"{safe_cleanup_fn}"
        f"{safe_minio_fn}"
        f"{safe_nginx_fn}"
        f"{force_port_fn}"
        "run_linux_macos_install"
    )
    cmd = ["bash", "-c", launcher]
    if live_cb:
        live_cb(f"[DEBUG] Effective LOCALS3_HTTPS_PORT: {(forwarded_env.get('LOCALS3_HTTPS_PORT', ''))}\n")

    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "env"]
        for k, v in forwarded_env.items():
            cmd.append(f"{k}={v}")
        cmd += ["bash", "-c", launcher]

    return run_process(cmd, env=env, live_cb=live_cb, input_text=scripted_input)


def run_linux_s3_docker_installer(form=None, live_cb=None):
    if os.name == "nt":
        return 1, "Linux S3 Docker installer can only run on Linux/macOS hosts."
    form = form or {}

    api_port  = (form.get("LOCALS3_HTTPS_PORT",   ["9443"])[0] or "9443").strip()
    cons_port = (form.get("LOCALS3_CONSOLE_PORT", ["18443"])[0] or "18443").strip()
    minio_api = (form.get("LOCALS3_API_PORT",     ["9000"])[0] or "9000").strip()
    minio_ui  = (form.get("LOCALS3_UI_PORT",      ["9001"])[0] or "9001").strip()
    root_user = (form.get("LOCALS3_ROOT_USER",    ["admin"])[0] or "admin").strip()
    root_pass = (form.get("LOCALS3_ROOT_PASSWORD",["StrongPassword123"])[0] or "StrongPassword123").strip()
    instance_name = re.sub(r"[^a-z0-9-]", "-", (form.get("LOCALS3_INSTANCE_NAME", ["locals3"])[0] or "locals3").strip().lower()) or "locals3"

    requested_host = (form.get("LOCALS3_HOST", [""])[0] or "").strip()
    if not requested_host:
        requested_host = (form.get("LOCALS3_HOST_IP", [""])[0] or "").strip()
    if not requested_host or requested_host in ("localhost", "127.0.0.1"):
        requested_host = choose_s3_host(requested_host)

    for label, val in [("API HTTPS", api_port), ("Console HTTPS", cons_port),
                       ("MinIO API", minio_api), ("MinIO UI", minio_ui)]:
        if not val.isdigit():
            return 1, f"{label} port must be numeric."

    # Port conflict check: reject ports already used by other services/instances
    for label, val in [("API HTTPS", api_port), ("Console HTTPS", cons_port),
                       ("MinIO API", minio_api), ("MinIO UI (Console)", minio_ui)]:
        if is_local_tcp_port_listening(val):
            if _docker_instance_owns_port(val, instance_name):
                # This instance's own containers will be stopped by compose down - OK
                if live_cb:
                    live_cb(f"Port {val} ({label}) is owned by this instance ({instance_name}); will be reclaimed.\n")
            else:
                return 1, (
                    f"{label} port {val} is already in use by another service. "
                    f"Choose a different port for instance '{instance_name}'. "
                    "Each S3 instance needs unique ports."
                )

    sudo_prefix = []
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() != 0:
        if subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            sudo_prefix = ["sudo"]

    host = shlex.quote(requested_host)
    inst = shlex.quote(instance_name)
    script = rf"""
set -euo pipefail

HOST={host}
API_PORT={shlex.quote(api_port)}
CONS_PORT={shlex.quote(cons_port)}
MINIO_API={shlex.quote(minio_api)}
MINIO_UI={shlex.quote(minio_ui)}
ROOT_USER={shlex.quote(root_user)}
ROOT_PASS={shlex.quote(root_pass)}
INSTANCE={inst}

PROJECT=/opt/${{INSTANCE}}/docker
CERT_DIR="$PROJECT/certs"
NGINX_DIR="$PROJECT/nginx"
VOLUME="${{INSTANCE}}-docker-minio-data"
MINIO_IMAGE=minio/minio:latest
LABEL=com.locals3.installer=true

echo "[1/7] Ensuring Docker is installed and running..."
if ! command -v docker >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-plugin 2>/dev/null || apt-get install -y -qq docker.io
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q docker docker-compose-plugin 2>/dev/null || dnf install -y -q docker
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q docker
  elif command -v brew >/dev/null 2>&1; then
    brew install --quiet docker docker-compose
  else
    echo "[ERROR] Cannot install Docker: no known package manager found."
    exit 1
  fi
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now docker >/dev/null 2>&1 || true
fi
if ! docker info >/dev/null 2>&1; then
  echo "[ERROR] Docker daemon is not responding. Start Docker and retry."
  exit 1
fi
# Ensure docker compose (V2 plugin or V1 standalone) is available
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y -qq docker-compose 2>/dev/null || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q docker-compose 2>/dev/null || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y -q docker-compose 2>/dev/null || true
  elif command -v brew >/dev/null 2>&1; then
    brew install --quiet docker-compose 2>/dev/null || true
  fi
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    echo "[ERROR] docker compose is not available. Install docker-compose or docker-compose-plugin and retry."
    exit 1
  fi
fi
echo "      Docker is ready (compose: $COMPOSE_CMD)."

echo "[2/7] Stopping previous instance containers (if any)..."
docker rm -f "${{INSTANCE}}-minio" "${{INSTANCE}}-nginx" >/dev/null 2>&1 || true
if [ -f "$PROJECT/docker-compose.yml" ]; then
  $COMPOSE_CMD -p "${{INSTANCE}}" -f "$PROJECT/docker-compose.yml" down >/dev/null 2>&1 || true
fi

echo "[3/7] Creating project directories..."
mkdir -p "$CERT_DIR" "$NGINX_DIR"

echo "[4/7] Generating self-signed TLS certificate..."
SAN="DNS:localhost,IP:127.0.0.1"
if echo "$HOST" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  SAN="$SAN,IP:$HOST"
elif [ "$HOST" != "localhost" ]; then
  SAN="$SAN,DNS:$HOST"
fi
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$CERT_DIR/localhost.key" \
  -out "$CERT_DIR/localhost.crt" \
  -subj "/CN=$HOST" \
  -addext "subjectAltName=$SAN" \
  2>/dev/null
echo "      Certificate generated."

if [ "$HOST" = "localhost" ] || echo "$HOST" | grep -qE '^127\.'; then
  DISPLAY_HOST="127.0.0.1"
else
  DISPLAY_HOST="$HOST"
fi
CONSOLE_REDIRECT_URL="https://${{DISPLAY_HOST}}:${{CONS_PORT}}"

echo "[5/7] Writing nginx config..."
cat > "$NGINX_DIR/default.conf" <<NGINXEOF
server {{
    listen 443 ssl;
    server_name $HOST localhost;
    ssl_certificate     /etc/nginx/certs/localhost.crt;
    ssl_certificate_key /etc/nginx/certs/localhost.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    client_max_body_size 5g;
    location / {{
        proxy_pass         http://${{INSTANCE}}-minio:9000;
        proxy_http_version 1.1;
        proxy_set_header   Host \$http_host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 3600;
        proxy_buffering    off;
        client_max_body_size 5g;
    }}
}}
server {{
    listen 4443 ssl;
    server_name $HOST localhost;
    ssl_certificate     /etc/nginx/certs/localhost.crt;
    ssl_certificate_key /etc/nginx/certs/localhost.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    client_max_body_size 5g;
    location / {{
        proxy_pass         http://${{INSTANCE}}-minio:9001;
        proxy_http_version 1.1;
        proxy_set_header   Host \$http_host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600;
        proxy_buffering    off;
    }}
}}
NGINXEOF

echo "[6/7] Writing docker-compose.yml and starting containers..."
cat > "$PROJECT/docker-compose.yml" <<COMPOSEEOF
services:
  ${{INSTANCE}}-minio:
    image: $MINIO_IMAGE
    container_name: ${{INSTANCE}}-minio
    labels:
      - "$LABEL"
      - "com.locals3.role=minio"
      - "com.locals3.instance=${{INSTANCE}}"
    environment:
      MINIO_ROOT_USER: "$ROOT_USER"
      MINIO_ROOT_PASSWORD: "$ROOT_PASS"
      MINIO_BROWSER_REDIRECT_URL: "$CONSOLE_REDIRECT_URL"
    command: server /data --address ":9000" --console-address ":9001"
    volumes:
      - $VOLUME:/data
    ports:
      - "${{MINIO_API}}:9000"
      - "${{MINIO_UI}}:9001"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 15s
      timeout: 5s
      retries: 6
      start_period: 20s

  ${{INSTANCE}}-nginx:
    image: nginx:alpine
    container_name: ${{INSTANCE}}-nginx
    labels:
      - "$LABEL"
      - "com.locals3.role=nginx"
      - "com.locals3.instance=${{INSTANCE}}"
      - "com.serverinstaller.https_port=${{API_PORT}}"
      - "com.serverinstaller.https_console_port=${{CONS_PORT}}"
    ports:
      - "${{API_PORT}}:443"
      - "${{CONS_PORT}}:4443"
    volumes:
      - $NGINX_DIR:/etc/nginx/conf.d:ro
      - $CERT_DIR:/etc/nginx/certs:ro
    depends_on:
      - ${{INSTANCE}}-minio
    restart: unless-stopped

volumes:
  $VOLUME:
COMPOSEEOF

$COMPOSE_CMD -p "${{INSTANCE}}" -f "$PROJECT/docker-compose.yml" up -d

echo "[7/7] Waiting for MinIO to become healthy..."
ELAPSED=0
until docker inspect "${{INSTANCE}}-minio" --format='{{{{.State.Health.Status}}}}' 2>/dev/null | grep -q healthy; do
  sleep 3; ELAPSED=$((ELAPSED+3))
  if [ "$ELAPSED" -ge 90 ]; then
    echo "[WARN] MinIO health check timed out. Container may still be starting."
    break
  fi
done

# Open firewall ports
for port in "$API_PORT" "$CONS_PORT"; do
  if command -v ufw >/dev/null 2>&1; then ufw allow "${{port}}/tcp" >/dev/null 2>&1 || true; fi
  if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --quiet --add-port="${{port}}/tcp" >/dev/null 2>&1 || true
    firewall-cmd --quiet --permanent --add-port="${{port}}/tcp" >/dev/null 2>&1 || true
  fi
done

echo ""
echo "===== INSTALLATION COMPLETE ====="
echo "API URL:      https://${{DISPLAY_HOST}}:${{API_PORT}}"
echo "Console URL:  https://${{DISPLAY_HOST}}:${{CONS_PORT}}"
echo "Username:     $ROOT_USER"
echo "Password:     $ROOT_PASS"
echo ""
echo "Project dir:  $PROJECT"
"""
    cmd = ["bash", "-c", script]
    if sudo_prefix:
        cmd = sudo_prefix + cmd
    return run_process(cmd, live_cb=live_cb)


def run_linux_s3_stop(live_cb=None):
    if os.name == "nt":
        return 1, "Linux S3 stop can only run on Linux/macOS hosts."

    script = rf"""
set -euo pipefail
echo "[DEBUG] Dashboard build: {BUILD_ID}"
echo "[INFO] Stopping LocalS3 services..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl stop locals3-minio >/dev/null 2>&1 || true
  systemctl disable locals3-minio >/dev/null 2>&1 || true
fi
pkill -f "minio server .*locals3" >/dev/null 2>&1 || true
pkill -f "/usr/local/bin/minio server" >/dev/null 2>&1 || true
if command -v docker >/dev/null 2>&1; then
  docker rm -f minio nginx console >/dev/null 2>&1 || true
fi
if [ -f /etc/nginx/conf.d/locals3.conf ]; then
  rm -f /etc/nginx/conf.d/locals3.conf || true
  nginx -t >/dev/null 2>&1 || true
  if command -v systemctl >/dev/null 2>&1; then
    systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx >/dev/null 2>&1 || true
  elif command -v service >/dev/null 2>&1; then
    service nginx reload >/dev/null 2>&1 || service nginx restart >/dev/null 2>&1 || true
  fi
fi
if [ -f /opt/locals3/nginx/nginx.pid ]; then
  kill "$(cat /opt/locals3/nginx/nginx.pid)" >/dev/null 2>&1 || true
  rm -f /opt/locals3/nginx/nginx.pid >/dev/null 2>&1 || true
fi
pkill -f "nginx -c /opt/locals3/nginx/nginx-standalone.conf" >/dev/null 2>&1 || true
if [ -f /Library/LaunchDaemons/com.locals3.minio.plist ]; then
  launchctl bootout system /Library/LaunchDaemons/com.locals3.minio.plist >/dev/null 2>&1 || true
fi
if command -v brew >/dev/null 2>&1; then
  brew services stop nginx >/dev/null 2>&1 || true
fi
echo "[INFO] LocalS3 API/Console services stopped."
"""
    cmd = ["bash", "-c", script]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "bash", "-c", script]
    return run_process(cmd, env=os.environ.copy(), live_cb=live_cb)


def run_dashboard_update(live_cb=None):
    repo_base = REPO_RAW_BASE

    manifest_path = ROOT / "dashboard" / "download-manifest.txt"
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
        files = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    except Exception:
        files = [
            "dashboard/download-manifest.txt",
            "dashboard/start-server-dashboard.py",
            "dashboard/server_installer_dashboard.py",
            "dashboard/windows_dashboard_service.py",
            "dashboard/file_manager.py",
            "dashboard/ui_assets.py",
            "dashboard/ui/core.js",
            "dashboard/ui/utils.js",
            "dashboard/ui/actions.js",
            "dashboard/ui/components.js",
            "dashboard/ui/file-manager.js",
            "dashboard/ui/pages/home/home.js",
            "dashboard/ui/pages/api/api.js",
            "dashboard/ui/pages/sysinfo/sysinfo.js",
            "dashboard/ui/pages/ports/ports.js",
            "dashboard/ui/pages/services/services.js",
            "dashboard/ui/pages/s3/s3.js",
            "dashboard/ui/pages/mongo/mongo.js",
            "dashboard/ui/pages/mongo/mongo-native.js",
            "dashboard/ui/pages/mongo/mongo-docker.js",
            "dashboard/ui/pages/docker/docker.js",
            "dashboard/ui/pages/proxy/proxy.js",
            "dashboard/ui/pages/dotnet/dotnet.js",
            "dashboard/ui/pages/dotnet/dotnet-iis.js",
            "dashboard/ui/pages/dotnet/dotnet-docker.js",
            "dashboard/ui/pages/dotnet/dotnet-linux.js",
            "dashboard/ui/pages/python/python.js",
            "dashboard/ui/pages/python/python-api.js",
            "dashboard/ui/pages/python/python-system.js",
            "dashboard/ui/pages/python/python-docker.js",
            "dashboard/ui/pages/python/python-iis.js",
            "dashboard/ui/pages/website/website.js",
            "dashboard/ui/pages/ai/ai.js",
            "dashboard/ui/pages/ai/sam3.js",
            "dashboard/ui/pages/ai/ollama.js",
            "dashboard/ui/pages/ai/tgwui.js",
            "dashboard/ui/pages/ai/comfyui.js",
            "dashboard/ui/pages/ai/whisper.js",
            "dashboard/ui/pages/ai/piper.js",
            "dashboard/ui/pages/ai/ai-all.js",
            "dashboard/ui/pages/api/api-docs.js",
            "dashboard/ui/pages/files/files.js",
            "dashboard/ui/app.js",
            "dashboard/api_gateway.py",
            "Ollama/windows/setup-ollama.ps1",
            "Ollama/linux-macos/setup-ollama.sh",
            "Ollama/common/ollama_web.py",
            "Ollama/common/requirements.txt",
            "Ollama/common/web/templates/index.html",
        ]

    total = len(files)
    if live_cb:
        live_cb(f"[INFO] Downloading {total} files from repository...\n")

    failed = []
    for i, rel in enumerate(files, 1):
        url = f"{repo_base}/{rel}"
        target = ROOT / rel.replace("/", os.sep)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(target) + ".download")
        if live_cb:
            live_cb(f"[{i}/{total}] {rel}\n")
        try:
            urllib.request.urlretrieve(url, str(tmp))
            os.replace(str(tmp), str(target))
        except Exception as ex:
            try:
                tmp.unlink()
            except Exception:
                pass
            if live_cb:
                live_cb(f"  WARNING: failed to download {rel}: {ex}\n")
            failed.append(rel)

    if failed:
        if live_cb:
            live_cb(f"[WARN] {len(failed)} file(s) could not be downloaded; using cached versions.\n")

    # Clear bytecode caches so restarted process loads the new .py files.
    for cache_dir in (ROOT / "dashboard").rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir, ignore_errors=True)
        except Exception:
            pass

    # Record the remote commit SHA so the next version-check knows what was installed.
    remote_sha = _fetch_remote_commit_sha(timeout=8)
    if remote_sha:
        _save_installed_commit(remote_sha)
        if live_cb:
            live_cb(f"[INFO] Recorded installed commit: {remote_sha[:12]}\n")

    if live_cb:
        live_cb("[INFO] All files synced. Restarting dashboard service...\n")

    def _restart():
        time.sleep(1)
        if os.name == "nt":
            # Windows: spawn a detached cmd.exe that waits, then uses
            # sc.exe to stop and start the service. sc.exe is more
            # reliable than Stop-Service/Start-Service from a child
            # process because it talks directly to the SCM.
            state_file = ROOT / "dashboard" / "service-state.json"
            service_name = "ServerInstallerDashboard"
            try:
                sdata = json.loads(state_file.read_text(encoding="utf-8"))
                service_name = str(sdata.get("service") or service_name).strip()
            except Exception:
                pass
            try:
                # Use cmd /c with timeout+sc for maximum compatibility.
                # The 5-second wait gives the HTTP response time to reach
                # the client before this process is killed.
                cmd = (
                    f'cmd /c "timeout /t 5 /nobreak >nul '
                    f'& net stop {service_name} '
                    f'& timeout /t 3 /nobreak >nul '
                    f'& net start {service_name}"'
                )
                subprocess.Popen(
                    cmd,
                    shell=True,
                    creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            except Exception:
                pass
        else:
            # Linux: exit this process cleanly so the parent (start-server-dashboard.py)
            # also exits, and systemd's Restart=always restarts the whole service with
            # the new downloaded files. Calling systemctl restart from inside the service
            # causes a race where the orphaned process still holds the port.
            os._exit(0)

    threading.Thread(target=_restart, daemon=False).start()
    return 0, ""

def run_windows_s3_stop(live_cb=None):
    if os.name != "nt":
        return 1, "Windows S3 stop can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."

    ps = r"""
$ErrorActionPreference = 'Continue'
Write-Host '[INFO] Stopping LocalS3 services...'
schtasks /End /TN 'LocalS3-MinIO' 1>$null 2>$null | Out-Null
Import-Module WebAdministration -ErrorAction SilentlyContinue
if (Test-Path 'IIS:\Sites\LocalS3') {
  Stop-Website -Name 'LocalS3' -ErrorAction SilentlyContinue | Out-Null
}
if (Get-Command docker -ErrorAction SilentlyContinue) {
  docker rm -f minio nginx console 1>$null 2>$null | Out-Null
}
Write-Host '[INFO] LocalS3 API/Console services stopped.'
"""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        ps,
    ]
    return run_process(cmd, env=os.environ.copy(), live_cb=live_cb)


def run_linux_docker_setup(live_cb=None):
    if os.name == "nt":
        return 1, "Linux Docker setup can only run on Linux hosts."

    script = r"""
set -euo pipefail

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

run_with_timeout() {
  local sec="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$sec" "$@"
  else
    "$@"
  fi
}

retry_cmd() {
  local tries="$1"; shift
  local n=1
  while [ "$n" -le "$tries" ]; do
    if "$@"; then
      return 0
    fi
    if [ "$n" -lt "$tries" ]; then
      log "Command failed (attempt ${n}/${tries}). Retrying in 8s..."
      sleep 8
    fi
    n=$((n+1))
  done
  return 1
}

wait_apt_locks() {
  local max_wait=900
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      log "apt/dpkg locks did not clear after ${max_wait}s."
      return 1
    fi
    log "apt is busy, waiting... (${waited}s elapsed)"
    sleep 5
    waited=$((waited+5))
  done
  return 0
}

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Unsupported Linux distribution for automatic Docker install. apt-get is required."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

if command -v docker >/dev/null 2>&1; then
  if systemctl is-active --quiet docker 2>/dev/null; then
    log "Docker is already installed and running."
    docker --version || true
    exit 0
  fi
  log "Docker binary exists, but daemon is not active. Attempting to start service."
fi

log "Checking apt locks..."
wait_apt_locks || exit 1

log "Updating apt package index..."
retry_cmd 3 run_with_timeout 1800 apt-get -o Dpkg::Use-Pty=0 -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine package..."
  wait_apt_locks || exit 1
  retry_cmd 2 run_with_timeout 2400 apt-get -o Dpkg::Use-Pty=0 install -y --no-install-recommends docker.io
else
  log "Docker package is already installed."
fi

log "Enabling Docker service..."
systemctl enable --now docker || true
sleep 1

if command -v docker >/dev/null 2>&1 && systemctl is-active --quiet docker 2>/dev/null; then
  log "Docker version:"
  docker --version
  log "Docker installed and ready."
  docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 || true
else
  log "Docker installation did not complete successfully."
  systemctl status docker --no-pager || true
  exit 1
fi
"""

    cmd = ["bash", "-lc", script]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo"] + cmd
    return run_process(cmd, env=os.environ.copy(), live_cb=live_cb)


def run_linux_docker_deploy(form, live_cb=None):
    if os.name == "nt":
        return 1, "Linux Docker deploy can only run on Linux hosts."

    source_value = resolve_source_value(form, "SOURCE_VALUE", "SOURCE_FILE", "SOURCE_FOLDER")
    if not source_value:
        return 1, "Source path/URL, uploaded file, or uploaded folder is required."

    http_port = (form.get("HTTP_PORT", [""])[0] or "").strip()
    https_port = (form.get("HTTPS_PORT", [""])[0] or "").strip()
    if not http_port and not https_port:
        return 1, "At least one of HTTP Port or HTTPS Port must be specified."
    if http_port and not http_port.isdigit():
        return 1, "HTTP Port must be numeric."
    if https_port and not https_port.isdigit():
        return 1, "HTTPS Port must be numeric."

    # Determine the Docker host-to-container port binding.
    # HTTP_PORT → expose container directly on that host port.
    # HTTPS-only → bind container to localhost-only internal port; nginx terminates TLS.
    if http_port:
        docker_host_port = http_port
        docker_bind = f"{http_port}:8080"
    else:
        internal_port = str(min(int(https_port) + 10000, 60000))
        docker_host_port = internal_port
        docker_bind = f"127.0.0.1:{internal_port}:8080"

    source_dir = prepare_source_dir(source_value, live_cb=live_cb)
    app_dir, dll_name = find_app_dll_dir(source_dir)
    if not app_dir or not dll_name:
        return 1, "No published .NET dll found in the provided source."

    base = upload_root_dir()
    context_dir = base / f"docker-context-{int(time.time())}-{secrets.token_hex(4)}"
    app_target = context_dir / "app"
    context_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, app_target, dirs_exist_ok=True)

    dockerfile = context_dir / "Dockerfile"
    dockerfile.write_text(
        "\n".join([
            "FROM mcr.microsoft.com/dotnet/aspnet:8.0",
            "WORKDIR /app",
            "COPY app/ .",
            "ENV ASPNETCORE_URLS=http://+:8080",
            "EXPOSE 8080",
            f'ENTRYPOINT ["dotnet", "{dll_name}"]',
            "",
        ]),
        encoding="utf-8",
    )

    docker_prefix = []
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        docker_prefix = ["sudo"]

    raw_name = (form.get("CONTAINER_NAME", [""])[0] or "dotnetapp").strip()
    container_name = re.sub(r"[^a-z0-9\-]", "-", raw_name.lower()).strip("-") or "dotnetapp"
    image_name = container_name

    if live_cb:
        live_cb(f"Building Docker image from: {context_dir}\n")
    code, output = run_process(docker_prefix + ["docker", "build", "-t", image_name, str(context_dir)], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."

    run_process(docker_prefix + ["docker", "rm", "-f", container_name], live_cb=live_cb)

    if live_cb:
        live_cb(f"Starting container '{container_name}' mapped to host port {docker_host_port}\n")
    run_labels = []
    if https_port:
        run_labels += ["--label", f"com.serverinstaller.https_port={https_port}"]
    code, output = run_process(
        docker_prefix + ["docker", "run", "-d", "--restart", "unless-stopped", "--name", container_name, "-p", docker_bind] + run_labels + [image_name],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."

    extra = f"\nDocker deploy complete.\nContainer: {container_name}\n"
    if http_port:
        extra += f"HTTP port: {http_port}\n"
    if https_port:
        extra += f"HTTPS port: {https_port}\n"

    if https_port:
        service_name = container_name
        cert_dir = f"/etc/nginx/ssl/{service_name}"
        # HTTP is served directly by Docker's port binding — no nginx HTTP block needed,
        # which also avoids a port conflict between Docker and nginx on the same port.
        nginx_script = f"""
set -euo pipefail
command -v nginx >/dev/null 2>&1 || {{ echo "nginx not found; skipping nginx setup."; exit 0; }}
mkdir -p "{cert_dir}"
if [[ ! -f "{cert_dir}/server.crt" || ! -f "{cert_dir}/server.key" ]]; then
  HOST=$(hostname -I | awk '{{print $1}}')
  SAN="IP:$HOST"
  openssl req -x509 -nodes -newkey rsa:2048 \\
    -keyout "{cert_dir}/server.key" -out "{cert_dir}/server.crt" \\
    -days 825 -subj "/CN=$HOST" -addext "subjectAltName=$SAN" 2>/dev/null
  chmod 600 "{cert_dir}/server.key"
fi
cat > "/etc/nginx/conf.d/{service_name}.conf" <<'NGINX'
server {{
    listen {https_port} ssl;
    server_name _;
    ssl_certificate {cert_dir}/server.crt;
    ssl_certificate_key {cert_dir}/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    location / {{
        proxy_pass http://127.0.0.1:{docker_host_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
NGINX
nginx -t && (systemctl is-active --quiet nginx && systemctl reload nginx || systemctl restart nginx)
echo "Nginx configured: HTTPS={https_port} -> container port {docker_host_port}"
"""
        sudo_prefix = []
        if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            sudo_prefix = ["sudo"]
        nginx_code, nginx_out = run_process(sudo_prefix + ["bash", "-c", nginx_script], live_cb=live_cb)
        if nginx_code != 0 and live_cb:
            live_cb(f"[WARN] nginx setup returned non-zero; container is still running on port {docker_host_port}.\n")
        if nginx_code == 0:
            resolved_ip = choose_service_host()
            extra += f"HTTPS URL: https://{resolved_ip}:{https_port}\n"
            if http_port:
                extra += f"HTTP URL:  http://{resolved_ip}:{http_port}\n"

    return 0, (output or "") + extra

