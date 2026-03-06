#!/usr/bin/env python3
import argparse
import ctypes
import html
import ipaddress
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import warnings
import zipfile
import tarfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

warnings.filterwarnings("ignore", category=DeprecationWarning)


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INSTALLER = ROOT / "DotNet" / "windows" / "install-windows-dotnet-host.ps1"
LINUX_INSTALLER = ROOT / "DotNet" / "linux" / "install-linux-dotnet-runner.sh"
REPO_RAW_BASE = os.environ.get(
    "SERVER_INSTALLER_REPO_BASE",
    "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main",
)

WINDOWS_SETUP_MODULES = [
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
]

SESSIONS = set()
JOBS = {}
JOBS_LOCK = threading.Lock()


def is_windows_admin():
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def validate_os_credentials(username, password):
    username = (username or "").strip()
    if not username or not password:
        return False, "Username and password are required."

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        logon_user = ctypes.windll.advapi32.LogonUserW
        close_handle = ctypes.windll.kernel32.CloseHandle
        token = wintypes.HANDLE()

        domain = "."
        user = username
        if "\\" in username:
            domain, user = username.split("\\", 1)
        elif "@" in username:
            domain = None

        ok = logon_user(
            user,
            domain,
            password,
            3,  # LOGON32_LOGON_NETWORK
            0,  # LOGON32_PROVIDER_DEFAULT
            ctypes.byref(token),
        )
        if ok:
            close_handle(token)
            return True, ""
        return False, "Invalid Windows username/password."

    try:
        import crypt
        import spwd

        hashed = spwd.getspnam(username).sp_pwdp
        if not hashed or hashed in ("x", "*", "!", "!!"):
            return False, "This Linux account cannot be validated by password."
        return (crypt.crypt(password, hashed) == hashed, "Invalid Linux username/password.")
    except PermissionError:
        return False, "Run dashboard as root to validate Linux system credentials for remote login."
    except Exception:
        return False, "Invalid Linux username/password."


def run_process(cmd, env=None, live_cb=None):
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    chunks = []
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                chunks.append(line)
                if live_cb:
                    live_cb(line)
        proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.returncode, "".join(chunks)


def upload_root_dir():
    if os.name == "nt":
        d_drive = Path("D:/")
        if d_drive.exists():
            return d_drive / "Server-Installer" / "uploads"
        return Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "uploads"
    return Path("/var/tmp/server-installer/uploads")


def save_uploaded_stream(filename, stream):
    safe_name = Path(filename or "upload.bin").name
    base = upload_root_dir()
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{int(time.time())}-{secrets.token_hex(4)}-{safe_name}"
    with target.open("wb") as f:
        shutil.copyfileobj(stream, f)
    return str(target)


def _safe_rel_path(name: str):
    rel = (name or "file.bin").replace("\\", "/")
    if ":" in rel:
        rel = rel.split(":", 1)[1]
    rel = rel.lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts:
        return "file.bin"
    return "/".join(parts)


def save_uploaded_folder(items):
    base = upload_root_dir()
    base.mkdir(parents=True, exist_ok=True)
    folder_name = f"folder-{int(time.time())}-{secrets.token_hex(4)}"
    source_dir = base / folder_name
    source_dir.mkdir(parents=True, exist_ok=True)

    for it in items:
        rel = _safe_rel_path(getattr(it, "filename", "") or "file.bin")
        target = source_dir / Path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as f:
            shutil.copyfileobj(it.file, f)

    zip_path = base / f"{folder_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in source_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(source_dir))

    extract_dir = base / f"{folder_name}-extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    return str(extract_dir)


def resolve_source_value(form, path_key, file_key, folder_key):
    value = (form.get(path_key, [""])[0] or "").strip()
    if value:
        return value
    value = (form.get(file_key, [""])[0] or "").strip()
    if value:
        form[path_key] = [value]
        return value
    value = (form.get(folder_key, [""])[0] or "").strip()
    if value:
        form[path_key] = [value]
        return value
    return ""


def prepare_source_dir(source_value, live_cb=None):
    src = (source_value or "").strip()
    if not src:
        raise RuntimeError("Empty source value.")

    path_obj = Path(src)
    if src.lower().startswith(("http://", "https://")):
        base = upload_root_dir()
        base.mkdir(parents=True, exist_ok=True)
        download_target = base / f"download-{int(time.time())}-{secrets.token_hex(4)}"
        if live_cb:
            live_cb(f"Downloading source artifact: {src}\n")
        urllib.request.urlretrieve(src, str(download_target))
        path_obj = download_target

    if path_obj.is_dir():
        return path_obj

    if path_obj.is_file():
        extract_dir = upload_root_dir() / f"extract-{int(time.time())}-{secrets.token_hex(4)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        lower = path_obj.name.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(path_obj, "r") as zf:
                zf.extractall(extract_dir)
            return extract_dir
        if lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar"):
            mode = "r:gz" if (lower.endswith(".tar.gz") or lower.endswith(".tgz")) else "r:"
            with tarfile.open(path_obj, mode) as tf:
                tf.extractall(extract_dir)
            return extract_dir
        raise RuntimeError("File source must be a .zip, .tar.gz, .tgz, or .tar archive.")

    raise RuntimeError(f"Source does not exist: {src}")


def find_app_dll_dir(root_dir: Path):
    root_dir = root_dir.resolve()

    runtime_configs = list(root_dir.rglob("*.runtimeconfig.json"))
    for rc in runtime_configs:
        dll = rc.with_suffix("").with_suffix(".dll")
        if dll.exists():
            return dll.parent, dll.name

    dlls = [p for p in root_dir.rglob("*.dll") if p.is_file()]
    if not dlls:
        return None, None
    dlls.sort(key=lambda p: len(str(p)))
    return dlls[0].parent, dlls[0].name


def ensure_repo_files(relative_paths, live_cb=None):
    for rel in relative_paths:
        rel_path = Path(rel)
        target = ROOT / rel_path
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = target.with_suffix(target.suffix + ".download")
        url = f"{REPO_RAW_BASE}/{rel_path.as_posix()}"
        message = f"Downloading required file on demand: {rel_path.as_posix()}"
        if live_cb:
            live_cb(message + "\n")
        else:
            print(message)
        try:
            urllib.request.urlretrieve(url, tmp_target)
            os.replace(tmp_target, target)
        except Exception as ex:
            if tmp_target.exists():
                tmp_target.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download required file '{rel_path.as_posix()}': {ex}") from ex


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
        "SitePort",
        "HttpsPort",
        "DockerHostPort",
    ]
    for key in keys:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            cmd.extend([f"-{key}", value])

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


def run_linux_docker_setup(live_cb=None):
    if os.name == "nt":
        return 1, "Linux Docker setup can only run on Linux hosts."

    script = r"""
set -e
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Unsupported Linux distribution for automatic Docker install. apt-get is required."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
echo "Checking apt locks..."
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
  echo "apt is busy, waiting 5s..."
  sleep 5
done

echo "Updating apt package index..."
apt-get -o Dpkg::Use-Pty=0 -o Acquire::Progress=false update

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker Engine..."
  apt-get -o Dpkg::Use-Pty=0 install -y docker.io
else
  echo "Docker is already installed."
fi

echo "Enabling Docker service..."
systemctl enable --now docker || true

if command -v docker >/dev/null 2>&1; then
  echo "Docker version:"
  docker --version
  echo "Docker installed and ready."
else
  echo "Docker installation did not complete successfully."
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

    host_port = (form.get("DOCKER_HOST_PORT", ["8080"])[0] or "8080").strip()
    if not host_port.isdigit():
        return 1, "Docker host port must be numeric."

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

    image_name = "dotnetapp"
    container_name = "dotnetapp"

    if live_cb:
        live_cb(f"Building Docker image from: {context_dir}\n")
    code, output = run_process(docker_prefix + ["docker", "build", "-t", image_name, str(context_dir)], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."

    run_process(docker_prefix + ["docker", "rm", "-f", container_name], live_cb=live_cb)

    if live_cb:
        live_cb(f"Starting container '{container_name}' on host port {host_port}\n")
    code, output = run_process(
        docker_prefix + ["docker", "run", "-d", "--restart", "unless-stopped", "--name", container_name, "-p", f"{host_port}:8080", image_name],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."

    extra = f"\nDocker deploy complete.\nContainer: {container_name}\nHost port: {host_port}\n"
    return 0, (output or "") + extra


def start_live_job(title, runner):
    job_id = secrets.token_hex(12)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "title": title,
            "output": "",
            "done": False,
            "exit_code": None,
            "created": time.time(),
        }

    def append_out(text):
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["output"] += text

    def worker():
        try:
            code, output = runner(append_out)
            with JOBS_LOCK:
                if job_id in JOBS:
                    if output and not JOBS[job_id]["output"]:
                        JOBS[job_id]["output"] = output
                    JOBS[job_id]["exit_code"] = code
                    JOBS[job_id]["done"] = True
        except Exception as ex:
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["output"] += f"\nUnhandled error: {ex}\n"
                    JOBS[job_id]["exit_code"] = 1
                    JOBS[job_id]["done"] = True

    threading.Thread(target=worker, daemon=True).start()
    return job_id


def page_login(message=""):
    msg = f"<p style='color:#b42318'>{html.escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Login</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;margin:0;padding:40px}}
.card{{max-width:420px;margin:auto;background:#fff;border-radius:12px;padding:20px;box-shadow:0 8px 30px rgba(2,32,71,.08)}}
input{{width:100%;padding:10px;margin:6px 0 12px;border:1px solid #d0d7e2;border-radius:8px}}
button{{background:#0f766e;color:#fff;border:0;padding:10px 14px;border-radius:8px}}
</style></head>
<body><div class="card"><h2>Server Installer</h2>{msg}
<p>Remote access requires this computer's OS username/password.</p>
<form method="post" action="/login">
<label>Server Username</label><input name="username" required>
<label>Server Password</label><input type="password" name="password" required>
<button type="submit">Open Dashboard</button>
</form></div></body></html>"""


def page_dashboard_mui(message="", system_name=""):
    config = {
        "os": (system_name or platform.system()).lower(),
        "os_label": platform.system(),
        "message": message or "",
    }
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Server Installer Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    html, body, #root { height: 100%; margin: 0; }
    body { font-family: "Manrope", "Segoe UI", sans-serif; background: #eef3fb; }
    .terminal-log { white-space: pre-wrap; word-break: break-word; font-family: Consolas, monospace; font-size: 12px; }
  </style>
  <script>window.__APP_CONFIG__ = __CONFIG__;</script>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/@mui/material@5.16.14/umd/material-ui.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" src="/static/ui/components.js"></script>
  <script type="text/babel" src="/static/ui/app.js"></script>
</body>
</html>""".replace("__CONFIG__", json.dumps(config))


def page_dashboard(message=""):
    system_name = platform.system().lower()
    return page_dashboard_mui(message, system_name)
    is_windows = system_name == "windows"
    is_linux = system_name == "linux"
    is_macos = system_name == "darwin"

    if is_windows:
        nav_items_html = """
      <div class="navitem active" data-view="view-home"><a class="navlink" href="#">Dashboard</a></div>
      <div class="navitem" data-view="view-win-setup"><a class="navlink" href="#">Windows Setup</a></div>
      <div class="navitem" data-view="view-win-deploy"><a class="navlink" href="#">Windows Deploy</a></div>
"""
    elif is_linux:
        nav_items_html = """
      <div class="navitem active" data-view="view-home"><a class="navlink" href="#">Dashboard</a></div>
      <div class="navitem" data-view="view-linux"><a class="navlink" href="#">Linux Deploy</a></div>
"""
    else:
        nav_items_html = """
      <div class="navitem active" data-view="view-home"><a class="navlink" href="#">Dashboard</a></div>
      <div class="navitem" data-view="view-macos"><a class="navlink" href="#">macOS</a></div>
"""

    msg = f"<div class='flash'>{html.escape(message)}</div>" if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Dashboard</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:"Segoe UI",Arial,sans-serif;background:#f4f7fb;margin:0;color:#0f172a;overflow-x:hidden}}
.layout{{display:grid;grid-template-columns:280px 1fr;min-height:100vh}}
.sidebar{{background:linear-gradient(180deg,#0b1f3a,#112c4a);color:#e8eef9;padding:22px 18px;border-right:1px solid rgba(255,255,255,.08);position:sticky;top:0;height:100vh;overflow:auto;z-index:30;transition:transform .24s ease}}
.sidebar.open{{transform:translateX(0)}}
.brand{{font-size:22px;font-weight:700;margin-bottom:18px;letter-spacing:.2px}}
.navgroup{{margin-bottom:14px}}
.navtitle{{font-size:12px;text-transform:uppercase;opacity:.75;margin-bottom:8px}}
.navitem{{padding:11px 12px;margin:7px 0;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);border-radius:10px;font-size:14px;cursor:pointer;transition:all .18s ease}}
.navitem:hover{{background:rgba(255,255,255,.12)}}
.navitem.active{{background:#1d4ed8;border-color:#60a5fa}}
.navlink{{display:block;text-decoration:none;color:#e8eef9}}
.main{{padding:28px 30px 24px}}
.header{{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px}}
.title{{font-size:28px;font-weight:700;letter-spacing:.2px}}
.subtitle{{font-size:14px;color:#475569}}
.flash{{padding:12px 14px;background:#ecfdf3;border:1px solid #86efac;border-radius:10px;margin-bottom:16px;color:#14532d}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#fff;border-radius:14px;padding:18px 18px 14px;box-shadow:0 10px 28px rgba(2,32,71,.06);border:1px solid #e5eaf4}}
.card h3{{margin:0 0 6px 0;font-size:18px}}
.card p{{margin:0 0 12px 0;font-size:13px;color:#475569}}
.divider{{height:1px;background:#e2e8f0;margin:12px 0}}
label{{display:block;font-size:12px;color:#334155;font-weight:600;letter-spacing:.2px}}
input,select{{width:100%;padding:10px;margin-top:6px;margin-bottom:10px;border:1px solid #cfd8e6;border-radius:9px;background:#fff}}
button{{background:#1249b0;color:white;border:0;padding:10px 14px;border-radius:9px;font-weight:600;cursor:pointer}}
.btn-secondary{{background:#0f766e}}
.btn-dark{{background:#1e293b}}
.btn-outline{{background:#fff;color:#1e293b;border:1px solid #cbd5e1}}
.view{{display:none}}
.view.active{{display:block}}
.sidebar-toggle{{display:none}}
.sidebar-close{{display:none}}
.backdrop{{display:none}}
.backdrop.show{{display:block;position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:20}}
.terminal-panel{{position:fixed;right:22px;bottom:22px;width:620px;max-width:calc(100vw - 32px);z-index:60;border:1px solid #1f2937;background:#0d1117;border-radius:12px;box-shadow:0 20px 40px rgba(2,6,23,.5)}}
.terminal-header{{cursor:move;user-select:none;padding:10px 12px;border-bottom:1px solid #1f2937;color:#cbd5e1;display:flex;justify-content:space-between;align-items:center;background:#111827;border-radius:12px 12px 0 0}}
.terminal-title{{font-size:13px;font-weight:600}}
.terminal-state{{font-size:12px;color:#93c5fd}}
.terminal-controls button{{padding:6px 8px;margin-left:6px;font-size:12px}}
.terminal-body{{height:320px;overflow:auto;padding:10px 12px;white-space:pre-wrap;font-family:Consolas,monospace;color:#c9d1d9;font-size:12px}}
.terminal-hidden .terminal-body{{display:none}}
.terminal-hidden{{width:280px}}
@media (max-width:1100px) {{
  .layout{{display:block}}
  .row{{grid-template-columns:1fr}}
  .main{{padding:16px}}
  .sidebar{{position:fixed;left:0;top:0;bottom:0;width:280px;transform:translateX(-100%);height:100vh}}
  .sidebar.open{{transform:translateX(0)}}
  .sidebar-toggle{{display:inline-block}}
  .sidebar-close{{display:inline-block}}
}}
</style></head>
<body>
<div id="backdrop" class="backdrop"></div>
<div class="layout">
  <aside id="sidebar" class="sidebar">
    <div class="header" style="margin-bottom:12px">
      <div class="brand">DotNet Installer</div>
      <button id="closeSidebarBtn" class="btn-outline sidebar-close" type="button">Close</button>
    </div>
    <div class="navgroup">
      <div class="navtitle">Pages</div>
{nav_items_html}
    </div>
  </aside>
  <main class="main">
    <div class="header">
      <div>
        <div class="title">DotNet Control Center</div>
        <div class="subtitle">Choose a page from sidebar. Actions run with live logs in draggable terminal.</div>
      </div>
      <button id="openSidebarBtn" class="btn-outline sidebar-toggle" type="button">Menu</button>
    </div>
    {msg}

    <section id="view-home" class="view active">
      <div class="card">
        <h3>Dashboard</h3>
        <p>Detected OS: {html.escape(platform.system())}. Use sidebar pages for this OS only. Open Web Terminal from the floating panel.</p>
      </div>
    </section>

    {'''
    <section id="view-win-setup" class="view">
      <div class="row">
        <div class="card">
          <h3>Windows IIS Stack Setup</h3>
          <p>Install IIS features + .NET prerequisites only.</p>
          <form method="post" action="/run/windows_setup_iis" class="run-form" data-title="Windows IIS Stack Setup">
            <label>.NET Channel</label><input name="DotNetChannel" value="8.0">
            <button class="btn-secondary" type="submit">Install IIS Stack Only</button>
          </form>
        </div>
        <div class="card">
          <h3>Windows Docker Stack Setup</h3>
          <p>Install Docker stack prerequisites only.</p>
          <form method="post" action="/run/windows_setup_docker" class="run-form" data-title="Windows Docker Stack Setup">
            <label>.NET Channel</label><input name="DotNetChannel" value="8.0">
            <button class="btn-dark" type="submit">Install Docker Stack Only</button>
          </form>
        </div>
      </div>
    </section>
    ''' if is_windows else ''}

    {'''
    <section id="view-win-deploy" class="view">
      <div class="row">
        <div class="card">
          <h3>Windows Combined Deploy</h3>
          <p>Deploy app to IIS or Docker from one form.</p>
          <form method="post" action="/run/windows" class="run-form" data-title="Windows Combined Installer">
            <label>Deployment Mode</label><select name="DeploymentMode"><option>IIS</option><option>Docker</option></select>
            <label>.NET Channel</label><input name="DotNetChannel" value="8.0">
            <label>Source Path or URL</label><input name="SourceValue" placeholder="D:\\app\\published or https://..." required>
            <label>Domain Name</label><input name="DomainName">
            <label>Site Name</label><input name="SiteName" value="DotNetApp">
            <label>HTTP Port</label><input name="SitePort" value="80">
            <label>HTTPS Port</label><input name="HttpsPort" value="443">
            <label>Docker Host Port</label><input name="DockerHostPort" value="8080">
            <button type="submit">Run Combined Deploy</button>
          </form>
        </div>
        <div class="card">
          <h3>Windows Separate Deploy</h3>
          <p>Deploy directly to one target.</p>
          <form method="post" action="/run/windows_iis" class="run-form" data-title="Windows IIS Deployment">
            <label>Source Path or URL</label><input name="SourceValue" required>
            <label>.NET Channel</label><input name="DotNetChannel" value="8.0">
            <button type="submit">Deploy to IIS</button>
          </form>
          <div class="divider"></div>
          <form method="post" action="/run/windows_docker" class="run-form" data-title="Windows Docker Deployment">
            <label>Source Path or URL</label><input name="SourceValue" required>
            <label>.NET Channel</label><input name="DotNetChannel" value="8.0">
            <label>Docker Host Port</label><input name="DockerHostPort" value="8080">
            <button type="submit">Deploy to Docker</button>
          </form>
        </div>
      </div>
    </section>
    ''' if is_windows else ''}

    {'''
    <section id="view-linux" class="view">
      <div class="row">
        <div class="card">
          <h3>Linux Combined Deploy</h3>
          <p>Deploy app and configure Nginx + service.</p>
          <form method="post" action="/run/linux" class="run-form" data-title="Linux Combined Installer">
            <label>.NET Channel</label><input name="DOTNET_CHANNEL" value="8.0">
            <label>Source Path or URL</label><input name="SOURCE_VALUE" placeholder="/srv/app or https://..." required>
            <label>Domain Name</label><input name="DOMAIN_NAME">
            <label>Service Name</label><input name="SERVICE_NAME" value="dotnet-app">
            <label>Service Port</label><input name="SERVICE_PORT" value="5000">
            <label>HTTP Port</label><input name="HTTP_PORT" value="80">
            <label>HTTPS Port</label><input name="HTTPS_PORT" value="443">
            <button type="submit">Run Linux Deploy</button>
          </form>
        </div>
        <div class="card">
          <h3>Linux Prerequisites</h3>
          <p>Install runtime and required packages only.</p>
          <form method="post" action="/run/linux_prereq" class="run-form" data-title="Linux Prerequisites Installer">
            <label>.NET Channel</label><input name="DOTNET_CHANNEL" value="8.0">
            <button type="submit">Install Linux Prerequisites</button>
          </form>
        </div>
      </div>
    </section>
    ''' if is_linux else ''}

    {'''
    <section id="view-macos" class="view">
      <div class="card">
        <h3>macOS Support</h3>
        <p>This dashboard is running on macOS. macOS installer actions are not configured yet in this repository.</p>
      </div>
    </section>
    ''' if is_macos else ''}
  </main>
</div>

<div id="terminalPanel" class="terminal-panel">
  <div id="terminalHeader" class="terminal-header">
    <div>
      <div class="terminal-title">Web Terminal</div>
      <div id="termState" class="terminal-state">Idle</div>
    </div>
    <div class="terminal-controls">
      <button id="toggleTerminalBtn" class="btn-outline" type="button">Minimize</button>
    </div>
  </div>
  <div id="terminal" class="terminal-body">Ready. Click any installer button to run and stream output here.</div>
</div>

<script>
const sidebar = document.getElementById("sidebar");
const backdrop = document.getElementById("backdrop");
const openSidebarBtn = document.getElementById("openSidebarBtn");
const closeSidebarBtn = document.getElementById("closeSidebarBtn");
const navItems = Array.from(document.querySelectorAll(".navitem[data-view]"));
const views = Array.from(document.querySelectorAll(".view"));
const terminalEl = document.getElementById("terminal");
const termState = document.getElementById("termState");
const terminalPanel = document.getElementById("terminalPanel");
const terminalHeader = document.getElementById("terminalHeader");
const toggleTerminalBtn = document.getElementById("toggleTerminalBtn");

function appendTerminal(text) {{
  terminalEl.textContent += (terminalEl.textContent ? "\\n" : "") + text;
  terminalEl.scrollTop = terminalEl.scrollHeight;
}}
function setState(text) {{ termState.textContent = text; }}

function openSidebar() {{
  sidebar.classList.add("open");
  backdrop.classList.add("show");
}}
function closeSidebar() {{
  sidebar.classList.remove("open");
  backdrop.classList.remove("show");
}}
if (openSidebarBtn) openSidebarBtn.addEventListener("click", openSidebar);
if (closeSidebarBtn) closeSidebarBtn.addEventListener("click", closeSidebar);
backdrop.addEventListener("click", closeSidebar);

function syncSidebarForViewport() {{
  if (window.innerWidth <= 1100) {{
    sidebar.classList.remove("open");
    backdrop.classList.remove("show");
  }} else {{
    sidebar.classList.add("open");
    backdrop.classList.remove("show");
  }}
}}
syncSidebarForViewport();
window.addEventListener("resize", syncSidebarForViewport);

function activateView(viewId) {{
  views.forEach(v => v.classList.toggle("active", v.id === viewId));
  navItems.forEach(n => n.classList.toggle("active", n.dataset.view === viewId));
}}
navItems.forEach(item => {{
  item.addEventListener("click", (e) => {{
    e.preventDefault();
    activateView(item.dataset.view);
    closeSidebar();
  }});
}});

let drag = {{ active:false, x:0, y:0, left:0, top:0 }};
terminalHeader.addEventListener("mousedown", (e) => {{
  drag.active = true;
  const rect = terminalPanel.getBoundingClientRect();
  drag.x = e.clientX; drag.y = e.clientY;
  drag.left = rect.left; drag.top = rect.top;
  terminalPanel.style.left = rect.left + "px";
  terminalPanel.style.top = rect.top + "px";
  terminalPanel.style.right = "auto";
  terminalPanel.style.bottom = "auto";
}});
document.addEventListener("mousemove", (e) => {{
  if (!drag.active) return;
  const dx = e.clientX - drag.x;
  const dy = e.clientY - drag.y;
  terminalPanel.style.left = Math.max(10, drag.left + dx) + "px";
  terminalPanel.style.top = Math.max(10, drag.top + dy) + "px";
}});
document.addEventListener("mouseup", () => {{ drag.active = false; }});

toggleTerminalBtn.addEventListener("click", () => {{
  terminalPanel.classList.toggle("terminal-hidden");
  toggleTerminalBtn.textContent = terminalPanel.classList.contains("terminal-hidden") ? "Expand" : "Minimize";
}});

document.querySelectorAll(".run-form").forEach((form) => {{
  form.addEventListener("submit", async (e) => {{
    e.preventDefault();
    const title = form.dataset.title || "Installer";
    appendTerminal("============================================================");
    appendTerminal("[" + new Date().toLocaleTimeString() + "] " + title + " started");
    setState("Running: " + title);
    const fd = new FormData(form);
    const body = new URLSearchParams(fd);
    try {{
      const res = await fetch(form.action, {{
        method: "POST",
        headers: {{ "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" }},
        body: body.toString()
      }});
      const json = await res.json();
      if (!json.job_id) {{
        appendTerminal(json.output || "No output.");
        appendTerminal("[" + new Date().toLocaleTimeString() + "] " + title + " finished (exit " + (json.exit_code ?? 1) + ")");
        setState("Idle");
        return;
      }}
      let offset = 0;
      const interval = setInterval(async () => {{
        try {{
          const stateRes = await fetch("/job/" + json.job_id + "?offset=" + offset, {{
            headers: {{ "X-Requested-With": "fetch" }}
          }});
          const state = await stateRes.json();
          if (state.output) appendTerminal(state.output);
          offset = state.next_offset || offset;
          if (state.done) {{
            appendTerminal("[" + new Date().toLocaleTimeString() + "] " + title + " finished (exit " + state.exit_code + ")");
            setState("Idle");
            clearInterval(interval);
          }}
        }} catch (pollErr) {{
          appendTerminal("Polling failed: " + pollErr);
          setState("Error");
          clearInterval(interval);
        }}
      }}, 300);
    }} catch (err) {{
      appendTerminal("Request failed: " + err);
      setState("Error");
    }}
  }});
}});
</script>
</body></html>"""


def page_output(title, output, code):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Consolas,monospace;background:#0d1117;color:#c9d1d9;padding:16px}}a{{color:#58a6ff}}</style>
</head><body><h2>{html.escape(title)} (exit {code})</h2><pre>{html.escape(output)}</pre><a href="/">Back</a></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def is_local_client(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except Exception:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def parse_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def parse_request_form(self):
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        if ctype.startswith("multipart/form-data"):
            import cgi

            env = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            }
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=env, keep_blank_values=True)
            result = {}
            if not fs:
                return result
            keys = fs.keys() if hasattr(fs, "keys") else []
            for key in keys:
                item = fs[key]
                items = item if isinstance(item, list) else [item]
                folder_items = []
                for it in items:
                    if getattr(it, "filename", None):
                        if it.file:
                            if key in ("SourceFolder", "SOURCE_FOLDER"):
                                folder_items.append(it)
                            else:
                                saved = save_uploaded_stream(it.filename, it.file)
                                result.setdefault(key, []).append(saved)
                    else:
                        result.setdefault(key, []).append((it.value or "").strip())
                if folder_items:
                    saved_folder = save_uploaded_folder(folder_items)
                    result.setdefault(key, []).append(saved_folder)
            return result
        return self.parse_form()

    def set_cookie(self, sid):
        self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly")

    def get_sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sid="):
                return part[4:]
        return ""

    def is_auth(self):
        sid = self.get_sid()
        return bool(sid and sid in SESSIONS)

    def write_html(self, content, status=HTTPStatus.OK, cookie_sid=None):
        data = content.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            if cookie_sid:
                self.set_cookie(cookie_sid)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def write_json(self, payload, status=HTTPStatus.OK):
        import json
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def is_fetch(self):
        return self.headers.get("X-Requested-With", "").lower() == "fetch"

    def respond_run_result(self, title, code, output):
        if self.is_fetch():
            self.write_json({"title": title, "exit_code": code, "output": output})
        else:
            self.write_html(page_output(title, output, code))

    def do_GET(self):
        if self.path.startswith("/static/"):
            static_rel = self.path.split("?", 1)[0].replace("/static/", "", 1).lstrip("/")
            static_root = (ROOT / "dashboard").resolve()
            static_file = (static_root / static_rel).resolve()
            try:
                static_file.relative_to(static_root)
            except Exception:
                self.write_html("Invalid static path.", HTTPStatus.BAD_REQUEST)
                return
            if (not static_file.exists()) or (not static_file.is_file()):
                self.write_html("Static file not found.", HTTPStatus.NOT_FOUND)
                return
            data = static_file.read_bytes()
            ext = static_file.suffix.lower()
            if ext == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif ext == ".css":
                content_type = "text/css; charset=utf-8"
            elif ext == ".json":
                content_type = "application/json; charset=utf-8"
            else:
                content_type = "text/plain; charset=utf-8"
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
            return
        if self.path == "/":
            if self.is_local_client() or self.is_auth():
                self.write_html(page_dashboard())
            else:
                self.write_html(page_login())
            return
        if self.path.startswith("/job/"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            path_only = self.path.split("?", 1)[0]
            job_id = path_only.split("/job/", 1)[1]
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            try:
                offset = int((query.get("offset", ["0"])[0] or "0"))
            except ValueError:
                offset = 0
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self.write_json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                    return
                full_output = job["output"]
                if offset < 0:
                    offset = 0
                output_chunk = full_output[offset:]
                payload = {
                    "job_id": job_id,
                    "title": job["title"],
                    "output": output_chunk,
                    "next_offset": len(full_output),
                    "done": job["done"],
                    "exit_code": job["exit_code"],
                }
            self.write_json(payload)
            return
        self.write_html("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/login":
            form = self.parse_form()
            user = (form.get("username", [""])[0] or "").strip()
            password = (form.get("password", [""])[0] or "").strip()
            ok, error = validate_os_credentials(user, password)
            if ok:
                sid = secrets.token_hex(16)
                SESSIONS.add(sid)
                self.write_html(page_dashboard("Login successful."), cookie_sid=sid)
            else:
                self.write_html(page_login(error), HTTPStatus.UNAUTHORIZED)
            return

        if (not self.is_local_client()) and (not self.is_auth()):
            self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
            return

        form = self.parse_request_form()

        if self.path == "/run/windows":
            title = "Windows Combined Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_iis":
            form["DeploymentMode"] = ["IIS"]
            title = "Windows IIS Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_setup_iis":
            title = "Windows IIS Stack Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_setup_only(form, "iis", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_setup_only(form, "iis")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_setup_docker":
            title = "Windows Docker Stack Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_setup_only(form, "docker", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_setup_only(form, "docker")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_docker":
            form["DeploymentMode"] = ["Docker"]
            title = "Windows Docker Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux":
            title = "Linux Combined Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_installer(form, live_cb=cb, require_source=True))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_installer(form, require_source=True)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux_prereq":
            form["SOURCE_VALUE"] = [""]
            title = "Linux Prerequisites Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_installer(form, live_cb=cb, require_source=False))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_installer(form, require_source=False)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux_setup_docker":
            title = "Linux Docker Setup Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_docker_setup(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_docker_setup()
                self.respond_run_result(title, code, output)
            return

        self.write_html("Not found", HTTPStatus.NOT_FOUND)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as ex:
        print(f"Failed to bind dashboard on {args.host}:{args.port} -> {ex}")
        if getattr(ex, "errno", None) in (13,):
            print("Hint: Port requires elevated privileges. Try a higher port (e.g. 8090) or run as root/admin.")
        if getattr(ex, "errno", None) in (98, 10048):
            print("Hint: Port is already in use by another process. Choose another port.")
        return

    urls = [f"http://127.0.0.1:{args.port}"]
    if args.host not in ("127.0.0.1", "localhost", "0.0.0.0", ""):
        explicit = f"http://{args.host}:{args.port}"
        if explicit not in urls:
            urls.append(explicit)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and (not primary_ip.startswith("127.")):
            candidate = f"http://{primary_ip}:{args.port}"
            if candidate not in urls:
                urls.append(candidate)
    except Exception:
        pass

    print("Dashboard URLs:")
    for url in urls:
        print(f"- {url}")
    print("Localhost access: no login required.")
    print("Remote access: requires OS username/password of this computer.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
