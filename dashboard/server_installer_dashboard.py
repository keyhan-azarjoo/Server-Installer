#!/usr/bin/env python3
import argparse
import ssl
import ctypes
import html
import io
import ipaddress
import json
import os
import platform
import secrets
import shutil
import mimetypes
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import warnings
import zipfile
import tarfile
import traceback
import re
import shlex
import getpass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from file_manager import (
    file_manager_copy_path,
    file_manager_delete_path,
    file_manager_list,
    file_manager_make_directory,
    file_manager_read_file,
    file_manager_rename_path,
    file_manager_save_uploads,
    file_manager_write_file,
    normalize_file_manager_path as _normalize_file_manager_path,
)
try:
    from ssl_manager import (
        ssl_list_certs,
        ssl_delete_cert,
        ssl_cert_info,
        ssl_validate_pair,
        run_ssl_letsencrypt,
        run_ssl_renew_all,
        run_ssl_upload,
        run_ssl_assign,
    )
    _SSL_MANAGER_OK = True
except ImportError:
    _SSL_MANAGER_OK = False
    def ssl_list_certs(): return []
    def ssl_delete_cert(name): return 1, "ssl_manager module not available — run Dashboard Update to install it."
    def ssl_cert_info(cert_pem): return {}
    def ssl_validate_pair(cert_pem, key_pem): return False, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_letsencrypt(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_renew_all(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_upload(form, parts, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_assign(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
from ui_assets import (
    DASHBOARD_UI_SCRIPTS,
    render_dashboard_page,
    render_login_page,
    render_mongo_native_ui,
    render_output_page,
)

warnings.filterwarnings("ignore", category=DeprecationWarning)

BUILD_ID = "python-jupyter-service-2026-03-13-1048"


def _server_installer_data_dir():
    override = os.environ.get("SERVER_INSTALLER_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer"
    if platform.system() == "Darwin":
        return Path.home() / ".server-installer"
    return Path.home() / ".server-installer"


ROOT = Path(__file__).resolve().parents[1]
SERVER_INSTALLER_DATA = _server_installer_data_dir()
WINDOWS_INSTALLER = ROOT / "DotNet" / "windows" / "install-windows-dotnet-host.ps1"
LINUX_INSTALLER = ROOT / "DotNet" / "linux" / "install-linux-dotnet-runner.sh"
S3_WINDOWS_INSTALLER = ROOT / "S3" / "windows" / "setup-storage.ps1"
S3_LINUX_INSTALLER = ROOT / "S3" / "linux-macos" / "setup-storage.sh"
MONGO_WINDOWS_INSTALLER = ROOT / "Mongo" / "windows" / "setup-mongodb.ps1"
PYTHON_WINDOWS_INSTALLER = ROOT / "Python" / "windows" / "setup-python.ps1"
PYTHON_UNIX_INSTALLER = ROOT / "Python" / "linux-macos" / "setup-python.sh"
PYTHON_API_HOST_TEMPLATE = ROOT / "Python" / "common" / "serverinstaller_python_api_host.py"
PROXY_LINUX_INSTALLER = ROOT / "Proxy" / "linux-macos" / "setup-proxy.sh"
PROXY_WINDOWS_INSTALLER = ROOT / "Proxy" / "windows" / "setup-proxy.ps1"
PROXY_ROOT = ROOT / "Proxy"
PROXY_WINDOWS_STATE = SERVER_INSTALLER_DATA / "proxy" / "proxy-wsl.json"
PROXY_NATIVE_STATE = SERVER_INSTALLER_DATA / "proxy" / "proxy-state.json"
PYTHON_STATE_DIR = SERVER_INSTALLER_DATA / "python"
PYTHON_STATE_FILE = PYTHON_STATE_DIR / "python-state.json"
PYTHON_JUPYTER_STATE_FILE = PYTHON_STATE_DIR / "jupyter-state.json"
PYTHON_IGNORED_FILE = PYTHON_STATE_DIR / "ignored-python.json"
PYTHON_API_STATE_FILE = PYTHON_STATE_DIR / "python-api-state.json"
WEBSITE_STATE_DIR = SERVER_INSTALLER_DATA / "websites"
WEBSITE_STATE_FILE = WEBSITE_STATE_DIR / "websites-state.json"
SAM3_WINDOWS_INSTALLER = ROOT / "SAM3" / "windows" / "setup-sam3.ps1"
SAM3_LINUX_INSTALLER = ROOT / "SAM3" / "linux-macos" / "setup-sam3.sh"
SAM3_STATE_DIR = SERVER_INSTALLER_DATA / "sam3"
SAM3_STATE_FILE = SAM3_STATE_DIR / "sam3-state.json"
SAM3_SYSTEMD_SERVICE = "serverinstaller-sam3"

OLLAMA_STATE_DIR = SERVER_INSTALLER_DATA / "ollama"
OLLAMA_STATE_FILE = OLLAMA_STATE_DIR / "ollama-state.json"
OLLAMA_SYSTEMD_SERVICE = "serverinstaller-ollama"

TGWUI_STATE_DIR = SERVER_INSTALLER_DATA / "tgwui"
TGWUI_STATE_FILE = TGWUI_STATE_DIR / "tgwui-state.json"
TGWUI_SYSTEMD_SERVICE = "serverinstaller-tgwui"

COMFYUI_STATE_DIR = SERVER_INSTALLER_DATA / "comfyui"
COMFYUI_STATE_FILE = COMFYUI_STATE_DIR / "comfyui-state.json"
COMFYUI_SYSTEMD_SERVICE = "serverinstaller-comfyui"

WHISPER_STATE_DIR = SERVER_INSTALLER_DATA / "whisper"
WHISPER_STATE_FILE = WHISPER_STATE_DIR / "whisper-state.json"
WHISPER_SYSTEMD_SERVICE = "serverinstaller-whisper"

PIPER_STATE_DIR = SERVER_INSTALLER_DATA / "piper"
PIPER_STATE_FILE = PIPER_STATE_DIR / "piper-state.json"
PIPER_SYSTEMD_SERVICE = "serverinstaller-piper"

OPENCLAW_STATE_DIR = SERVER_INSTALLER_DATA / "openclaw"
OPENCLAW_STATE_FILE = OPENCLAW_STATE_DIR / "openclaw-state.json"
OPENCLAW_SYSTEMD_SERVICE = "serverinstaller-openclaw"
OPENCLAW_WINDOWS_INSTALLER = ROOT / "OpenClaw" / "windows" / "setup-openclaw.ps1"
OPENCLAW_LINUX_INSTALLER = ROOT / "OpenClaw" / "linux-macos" / "setup-openclaw.sh"
OPENCLAW_WINDOWS_FILES = [
    "OpenClaw/windows/setup-openclaw.ps1",
    "OpenClaw/common/openclaw_web.py",
    "OpenClaw/common/requirements.txt",
    "OpenClaw/common/web/templates/index.html",
    "OpenClaw/common/web/templates/login.html",
]
OPENCLAW_UNIX_FILES = [
    "OpenClaw/linux-macos/setup-openclaw.sh",
    "OpenClaw/common/openclaw_web.py",
    "OpenClaw/common/requirements.txt",
    "OpenClaw/common/web/templates/index.html",
    "OpenClaw/common/web/templates/login.html",
]

LMSTUDIO_STATE_DIR = SERVER_INSTALLER_DATA / "lmstudio"
LMSTUDIO_STATE_FILE = LMSTUDIO_STATE_DIR / "lmstudio-state.json"
LMSTUDIO_SYSTEMD_SERVICE = "serverinstaller-lmstudio"
LMSTUDIO_WINDOWS_INSTALLER = ROOT / "LMStudio" / "windows" / "setup-lmstudio.ps1"
LMSTUDIO_LINUX_INSTALLER = ROOT / "LMStudio" / "linux-macos" / "setup-lmstudio.sh"
LMSTUDIO_WINDOWS_FILES = [
    "LMStudio/windows/setup-lmstudio.ps1",
    "LMStudio/common/lmstudio_web.py",
    "LMStudio/common/requirements.txt",
    "LMStudio/common/web/templates/index.html",
    "LMStudio/common/web/templates/login.html",
]
LMSTUDIO_UNIX_FILES = [
    "LMStudio/linux-macos/setup-lmstudio.sh",
    "LMStudio/common/lmstudio_web.py",
    "LMStudio/common/requirements.txt",
    "LMStudio/common/web/templates/index.html",
    "LMStudio/common/web/templates/login.html",
]

OLLAMA_WINDOWS_INSTALLER = ROOT / "Ollama" / "windows" / "setup-ollama.ps1"
OLLAMA_LINUX_INSTALLER = ROOT / "Ollama" / "linux-macos" / "setup-ollama.sh"
OLLAMA_WINDOWS_FILES = [
    "Ollama/windows/setup-ollama.ps1",
    "Ollama/common/ollama_web.py",
    "Ollama/common/requirements.txt",
    "Ollama/common/web/templates/index.html",
    "Ollama/common/web/templates/login.html",
]
OLLAMA_UNIX_FILES = [
    "Ollama/linux-macos/setup-ollama.sh",
    "Ollama/common/ollama_web.py",
    "Ollama/common/requirements.txt",
    "Ollama/common/web/templates/index.html",
    "Ollama/common/web/templates/login.html",
]
JUPYTER_SYSTEMD_SERVICE = "serverinstaller-jupyter.service"
WINDOWS_LOCALS3_STATE = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "LocalS3" / "storage-server" / "install-state.json"
REPO_RAW_BASE = os.environ.get(
    "SERVER_INSTALLER_REPO_BASE",
    "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main",
)

def _repo_api_url():
    """Derive the GitHub API commits URL from REPO_RAW_BASE."""
    # REPO_RAW_BASE = https://raw.githubusercontent.com/<owner>/<repo>/<branch>
    raw = REPO_RAW_BASE.rstrip("/")
    parts = raw.split("/")
    # parts[-3]=owner, parts[-2]=repo, parts[-1]=branch
    if len(parts) >= 3:
        owner, repo, branch = parts[-3], parts[-2], parts[-1]
        return f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    return None

def _fetch_remote_commit_sha(timeout=8):
    """Return the latest commit SHA on the remote branch, or empty string on failure."""
    api_url = _repo_api_url()
    if not api_url:
        return ""
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "dashboard-version-check/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return str(data.get("sha", "")).strip()
    except Exception:
        return ""

INSTALLED_COMMIT_FILE = Path(__file__).parent / "installed-commit.txt"

def _read_installed_commit():
    try:
        return INSTALLED_COMMIT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _save_installed_commit(sha):
    try:
        INSTALLED_COMMIT_FILE.write_text(sha.strip(), encoding="utf-8")
    except Exception:
        pass

WINDOWS_SETUP_MODULES = [
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
]

# Dashboard certificate config
DASHBOARD_CERT_CONFIG_FILE = SERVER_INSTALLER_DATA / "dashboard-cert.json"
DASHBOARD_SELFSIGNED_CERT = SERVER_INSTALLER_DATA / "certs" / "dashboard.crt"
DASHBOARD_SELFSIGNED_KEY = SERVER_INSTALLER_DATA / "certs" / "dashboard.key"


def _dashboard_cert_config():
    """Read dashboard cert config. Returns dict with 'mode' and optional 'name'."""
    try:
        if DASHBOARD_CERT_CONFIG_FILE.exists():
            return json.loads(DASHBOARD_CERT_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"mode": "self-signed"}


def _set_dashboard_cert_config(mode: str, name: str = "") -> None:
    DASHBOARD_CERT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_CERT_CONFIG_FILE.write_text(
        json.dumps({"mode": mode, "name": name}, indent=2), encoding="utf-8"
    )


def _get_managed_cert_paths(name: str):
    """Return (cert_pem_path, key_pem_path) for a managed cert, or ('', '') if not found."""
    if not name:
        return "", ""
    safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", name)
    cert_dir = SERVER_INSTALLER_DATA / "ssl" / "certs" / safe
    cert_p = cert_dir / "cert.pem"
    key_p = cert_dir / "key.pem"
    if cert_p.exists() and key_p.exists():
        return str(cert_p), str(key_p)
    return "", ""


def _find_openssl_bin():
    """Return path to openssl binary, or '' if not found."""
    import shutil as _shutil
    candidate = _shutil.which("openssl")
    if candidate:
        return candidate
    if os.name == "nt":
        for p in [
            r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
            r"C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe",
        ]:
            if Path(p).exists():
                return p
        # Git for Windows
        git = _shutil.which("git")
        if git:
            git_dir = Path(git).parent.parent
            candidate = git_dir / "usr" / "bin" / "openssl.exe"
            if candidate.exists():
                return str(candidate)
    return ""


def _generate_dashboard_selfsigned():
    """Generate a self-signed dashboard cert. Returns (cert_path, key_path) or ('', '')."""
    cert_dir = DASHBOARD_SELFSIGNED_CERT.parent
    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "", ""

    openssl = _find_openssl_bin()
    if not openssl:
        return "", ""

    san_entries = ["DNS:localhost", "IP:127.0.0.1"]
    try:
        hostname = socket.gethostname()
        if hostname and hostname not in ("localhost",):
            san_entries.append(f"DNS:{hostname}")
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 53))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            entry = f"IP:{ip}"
            if entry not in san_entries:
                san_entries.append(entry)
    except Exception:
        pass

    import tempfile as _tempfile
    config_text = (
        "[req]\ndefault_bits = 2048\nprompt = no\ndefault_md = sha256\n"
        "x509_extensions = v3_req\ndistinguished_name = dn\n"
        "[dn]\nCN = localhost\n"
        "[v3_req]\n"
        f"subjectAltName = {', '.join(san_entries)}\n"
        "basicConstraints = CA:true\n"
        "keyUsage = critical, digitalSignature, keyEncipherment, keyCertSign\n"
        "extendedKeyUsage = serverAuth\n"
    )
    try:
        with _tempfile.NamedTemporaryFile("w", delete=False, suffix=".cnf", encoding="utf-8") as f:
            f.write(config_text)
            cfg_path = f.name
        result = subprocess.run(
            [openssl, "req", "-x509", "-nodes", "-newkey", "rsa:2048",
             "-keyout", str(DASHBOARD_SELFSIGNED_KEY),
             "-out", str(DASHBOARD_SELFSIGNED_CERT),
             "-days", "825", "-config", cfg_path, "-extensions", "v3_req"],
            capture_output=True, timeout=60,
        )
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        if result.returncode != 0:
            print(f"[dashboard cert] openssl failed: {result.stderr.decode(errors='ignore')}")
            return "", ""
        return str(DASHBOARD_SELFSIGNED_CERT), str(DASHBOARD_SELFSIGNED_KEY)
    except Exception as ex:
        print(f"[dashboard cert] generation error: {ex}")
        return "", ""


def _resolve_dashboard_cert(arg_cert: str = "", arg_key: str = "") -> tuple:
    """Resolve the dashboard cert/key to use. Returns (cert_path, key_path)."""
    # Explicit args take priority
    if arg_cert and arg_key and Path(arg_cert).exists() and Path(arg_key).exists():
        return arg_cert, arg_key

    # Check dashboard cert config for managed cert preference
    cfg_data = _dashboard_cert_config()
    if cfg_data.get("mode") == "managed" and cfg_data.get("name"):
        c, k = _get_managed_cert_paths(cfg_data["name"])
        if c and k:
            return c, k

    # Check if explicit args point to files that just don't exist yet — use self-signed path
    cert_path = arg_cert or str(DASHBOARD_SELFSIGNED_CERT)
    key_path = arg_key or str(DASHBOARD_SELFSIGNED_KEY)

    # If self-signed files exist, use them
    if Path(cert_path).exists() and Path(key_path).exists():
        return cert_path, key_path

    # Generate new self-signed cert
    print("[dashboard cert] Generating new self-signed certificate...")
    return _generate_dashboard_selfsigned()


def run_dashboard_apply_cert(form, live_cb=None) -> tuple:
    """Configure the dashboard certificate (self-signed or managed) and restart the service."""
    def log(msg):
        if live_cb:
            live_cb(msg + "\n")
        else:
            print(msg)

    mode = (form.get("CERT_MODE", ["self-signed"])[0] or "self-signed").strip().lower()
    name = (form.get("CERT_NAME", [""])[0] or "").strip()

    if mode == "managed":
        if not name:
            return 1, "Managed cert name is required."
        c, k = _get_managed_cert_paths(name)
        if not c or not k:
            return 1, f"Managed certificate '{name}' not found. Import it via SSL & Certificates first."
        _set_dashboard_cert_config("managed", name)
        log(f"Dashboard cert set to managed: {name}")
        log(f"  cert: {c}")
        log(f"  key:  {k}")
    else:
        _set_dashboard_cert_config("self-signed", "")
        log("Dashboard cert set to: self-signed (auto-generated)")
        # Regenerate self-signed cert
        c, k = _generate_dashboard_selfsigned()
        if not c:
            return 1, "Failed to generate self-signed certificate. Make sure openssl is installed."
        log(f"Self-signed cert generated: {c}")

    # Restart the dashboard service so the new cert takes effect
    log("\nRestarting dashboard service...")
    if os.name == "nt":
        rc, out = _restart_windows_dashboard_service()
    else:
        rc, out = _restart_linux_dashboard_service()

    if rc == 0:
        log(out or "Dashboard service restarted.")
        log("\nDone. Reload the dashboard page after a few seconds.")
        return 0, "Dashboard certificate updated and service restarted."
    else:
        log(f"Service restart note: {out or 'restart returned non-zero'}")
        log("The new certificate will take effect on next dashboard restart.")
        return 0, "Dashboard certificate saved. Restart the dashboard to apply it."


def _restart_linux_dashboard_service():
    try:
        rc, out = subprocess.run(
            ["systemctl", "restart", "server-installer-dashboard.service"],
            capture_output=True, text=True, timeout=30,
        ).returncode, ""
        return rc, "systemctl restart completed."
    except Exception as ex:
        return 1, str(ex)


def _restart_windows_dashboard_service():
    try:
        import ctypes as _ctypes
        if not _ctypes.windll.shell32.IsUserAnAdmin():
            return 1, "Restart requires Administrator privileges."
        rc, out = subprocess.run(
            ["sc.exe", "stop", "ServerInstallerDashboard"],
            capture_output=True, text=True, timeout=15,
        ).returncode, ""
        subprocess.run(
            ["sc.exe", "start", "ServerInstallerDashboard"],
            capture_output=True, text=True, timeout=15,
        )
        return 0, "Service restarted."
    except Exception as ex:
        return 1, str(ex)

S3_WINDOWS_FILES = [
    "S3/windows/setup-storage.ps1",
    "S3/windows/modules/common.ps1",
    "S3/windows/modules/minio.ps1",
    "S3/windows/modules/cleanup.ps1",
    "S3/windows/modules/iis.ps1",
    "S3/windows/modules/docker.ps1",
    "S3/windows/modules/main.ps1",
]

S3_LINUX_FILES = [
    "S3/linux-macos/setup-storage.sh",
    "S3/linux-macos/modules/core.sh",
    "S3/linux-macos/modules/cleanup.sh",
    "S3/linux-macos/modules/platform.sh",
]

MONGO_WINDOWS_FILES = [
    "Mongo/windows/setup-mongodb.ps1",
]

MONGO_UNIX_FILES = [
    "Mongo/linux-macos/setup-mongodb.sh",
]

PYTHON_WINDOWS_FILES = [
    "Python/windows/setup-python.ps1",
    "Python/common/serverinstaller_python_api_host.py",
]

PYTHON_UNIX_FILES = [
    "Python/linux-macos/setup-python.sh",
    "Python/common/serverinstaller_python_api_host.py",
]

SAM3_WINDOWS_FILES = [
    "SAM3/windows/setup-sam3.ps1",
    "SAM3/common/app.py",
    "SAM3/common/requirements.txt",
    "SAM3/common/core/detector.py",
    "SAM3/common/core/video_processor.py",
    "SAM3/common/core/tracker.py",
    "SAM3/common/core/exporter.py",
    "SAM3/common/core/utils.py",
    "SAM3/common/core/__init__.py",
    "SAM3/common/web/templates/index.html",
    "SAM3/common/web/static/js/dashboard.js",
    "SAM3/common/web/static/css/dashboard.css",
]

SAM3_UNIX_FILES = [
    "SAM3/linux-macos/setup-sam3.sh",
    "SAM3/common/app.py",
    "SAM3/common/requirements.txt",
    "SAM3/common/core/detector.py",
    "SAM3/common/core/video_processor.py",
    "SAM3/common/core/tracker.py",
    "SAM3/common/core/exporter.py",
    "SAM3/common/core/utils.py",
    "SAM3/common/core/__init__.py",
    "SAM3/common/web/templates/index.html",
    "SAM3/common/web/static/js/dashboard.js",
    "SAM3/common/web/static/css/dashboard.css",
]

PROXY_FILES = [
    "Proxy/linux-macos/setup-proxy.sh",
    "Proxy/windows/setup-proxy.ps1",
    "Proxy/common/add-user.sh",
    "Proxy/common/backup-config.sh",
    "Proxy/common/delete-user.sh",
    "Proxy/common/list-users.sh",
    "Proxy/common/status.sh",
    "Proxy/common/uninstall.sh",
    "Proxy/common/view-users.sh",
    "Proxy/panel/install-panel.sh",
    "Proxy/panel/proxy-panel.py",
    "Proxy/panel/proxy-panel.service",
    "Proxy/panel/static/app.js",
    "Proxy/panel/static/style.css",
    "Proxy/panel/templates/dashboard.html",
    "Proxy/panel/templates/login.html",
    "Proxy/layers/layer3-basic/install.sh",
    "Proxy/layers/layer4-nginx/install.sh",
    "Proxy/layers/layer6-stunnel/install.sh",
    "Proxy/layers/layer7-iran-optimized/add-user.sh",
    "Proxy/layers/layer7-iran-optimized/delete-user.sh",
    "Proxy/layers/layer7-iran-optimized/install.sh",
    "Proxy/layers/layer7-real-domain/add-user.sh",
    "Proxy/layers/layer7-real-domain/delete-user.sh",
    "Proxy/layers/layer7-real-domain/install.sh",
    "Proxy/layers/layer7-v2ray-vless/add-user.sh",
    "Proxy/layers/layer7-v2ray-vless/delete-user.sh",
    "Proxy/layers/layer7-v2ray-vless/install.sh",
    "Proxy/layers/layer7-v2ray-vmess/add-user.sh",
    "Proxy/layers/layer7-v2ray-vmess/delete-user.sh",
    "Proxy/layers/layer7-v2ray-vmess/install.sh",
]


def _iter_proxy_sync_files():
    base = PROXY_ROOT
    if not (base.exists() and (base / "common").exists() and (base / "layers").exists() and (base / "panel").exists()):
        return list(PROXY_FILES)
    files = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if "/.git/" in rel or rel.endswith("/.git") or "/__pycache__/" in rel or rel.endswith(".pyc"):
            continue
        if "/docs/" in rel:
            continue
        files.append(rel)
    for rel in PROXY_FILES:
        if rel not in files:
            files.append(rel)
    return files


PROXY_SYNC_FILES = _iter_proxy_sync_files()

SESSIONS = {}
JOBS = {}
JOBS_LOCK = threading.Lock()


def command_exists(name):
    return shutil.which(name) is not None


def resolve_windows_python():
    env_override = os.environ.get("SERVER_INSTALLER_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    state = _read_json_file(PYTHON_STATE_FILE)
    managed = str(state.get("python_executable") or "").strip()
    if managed and Path(managed).exists():
        return managed
    embedded = SERVER_INSTALLER_DATA / "python" / "python.exe"
    if embedded.exists():
        return str(embedded)
    return sys.executable


def _write_json_file(path_value, payload):
    try:
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _read_json_file(path_value):
    try:
        path = Path(path_value)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _read_json_list(path_value):
    data = _read_json_file(path_value)
    if isinstance(data, list):
        return data
    return []


def _write_json_list(path_value, items):
    safe = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        safe.append(value)
    return _write_json_file(path_value, safe)


def _normalize_python_version(version_text):
    raw = str(version_text or "").strip()
    if not raw:
        return ""
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
    if not match:
        return raw
    return match.group(1)


def _python_version_key(version_text):
    normalized = _normalize_python_version(version_text)
    parts = normalized.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else normalized


def _python_scripts_dir(python_exe):
    exe_path = Path(str(python_exe or "").strip())
    if not exe_path.exists():
        return ""
    scripts_dir = exe_path.parent / "Scripts"
    if scripts_dir.exists():
        return str(scripts_dir)
    bin_dir = exe_path.parent / "bin"
    if bin_dir.exists():
        return str(bin_dir)
    return ""


def _default_python_notebook_dir():
    if os.name == "nt":
        preferred = Path(os.environ.get("SystemDrive", "C:")) / "ServerInstaller-Notebooks"
    elif hasattr(os, "geteuid") and os.geteuid() == 0:
        preferred = Path("/root") / "notebooks"
    else:
        preferred = Path.home() / "notebooks"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return str(preferred)
    except Exception:
        return str(ROOT)


def _resolve_python_notebook_dir(value=""):
    raw = str(value or "").strip()
    if not raw:
        raw = _default_python_notebook_dir()
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(path)


def _resolve_python_from_launcher(version_hint=""):
    version_key = _python_version_key(version_hint)
    if os.name == "nt" and command_exists("py"):
        cmd = ["py"]
        if version_key:
            cmd.append(f"-{version_key}")
        cmd += ["-c", "import sys; print(sys.executable); print(sys.version.split()[0])"]
        rc, out = run_capture(cmd, timeout=20)
        if rc == 0 and out:
            lines = [x.strip() for x in out.splitlines() if x.strip()]
            if lines and Path(lines[0]).exists():
                return {
                    "python_executable": lines[0],
                    "python_version": lines[1] if len(lines) > 1 else "",
                }
    return {}


def _resolve_any_python():
    state = _read_json_file(PYTHON_STATE_FILE)
    managed = str(state.get("python_executable") or "").strip()
    if managed and Path(managed).exists():
        return {
            "python_executable": managed,
            "python_version": str(state.get("python_version") or "").strip(),
        }
    launcher = _resolve_python_from_launcher("")
    if launcher:
        return launcher
    current = resolve_windows_python() if os.name == "nt" else sys.executable
    if current and Path(current).exists():
        rc, out = run_capture([current, "--version"], timeout=10)
        return {
            "python_executable": current,
            "python_version": _normalize_python_version(out or ""),
        }
    return {}


def _python_env(python_executable):
    env = os.environ.copy()
    exe = str(python_executable or "").strip()
    if not exe:
        return env
    parts = []
    exe_dir = str(Path(exe).parent)
    if exe_dir:
        parts.append(exe_dir)
    scripts_dir = _python_scripts_dir(exe)
    if scripts_dir:
        parts.append(scripts_dir)
    if parts:
        env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
    env["SERVER_INSTALLER_PYTHON"] = exe
    return env


def _python_run_capture(args, timeout=30):
    resolved = _resolve_any_python()
    python_exe = str(resolved.get("python_executable") or "").strip()
    if not python_exe:
        return 1, "Managed Python is not installed."
    return run_capture([python_exe] + list(args), timeout=timeout)


def _hash_jupyter_password(python_executable, password_text):
    python_exe = str(python_executable or "").strip()
    password_value = str(password_text or "")
    if not python_exe or not password_value:
        return ""
    rc, out = run_capture(
        [
            python_exe,
            "-c",
            (
                "from jupyter_server.auth import passwd; "
                f"print(passwd({password_value!r}))"
            ),
        ],
        timeout=30,
    )
    if rc != 0:
        return ""
    return str(out or "").strip().splitlines()[-1].strip()


def _ensure_windows_jupyter_https_assets(python_executable, host):
    python_exe = str(python_executable or "").strip()
    host_value = str(host or "").strip() or "localhost"
    if os.name != "nt" or not python_exe:
        return "", ""
    https_dir = PYTHON_STATE_DIR / "https"
    cert_path = https_dir / "jupyter-cert.pem"
    key_path = https_dir / "jupyter-key.pem"
    try:
        https_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "", ""
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    rc_import, _ = run_capture([python_exe, "-c", "import trustme"], timeout=20)
    if rc_import != 0:
        rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "trustme"], timeout=180)
        if rc_install != 0:
            return "", ""

    script = (
        "from pathlib import Path\n"
        "import trustme\n"
        f"cert_path = Path(r'''{str(cert_path)}''')\n"
        f"key_path = Path(r'''{str(key_path)}''')\n"
        f"host = {host_value!r}\n"
        "ca = trustme.CA()\n"
        "server_cert = ca.issue_cert(host, 'localhost', '127.0.0.1')\n"
        "server_cert.cert_chain_pems[0].write_to_path(cert_path)\n"
        "server_cert.private_key_pem.write_to_path(key_path)\n"
        "print(cert_path)\n"
        "print(key_path)\n"
    )
    rc, out = run_capture([python_exe, "-c", script], timeout=60)
    if rc != 0 or not cert_path.exists() or not key_path.exists():
        return "", ""
    return str(cert_path), str(key_path)


def _ensure_windows_jupyter_proxy_support(python_executable):
    python_exe = str(python_executable or "").strip()
    if os.name != "nt" or not python_exe:
        return False
    rc_import, _ = run_capture([python_exe, "-c", "import aiohttp"], timeout=20)
    if rc_import == 0:
        return True
    rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "aiohttp"], timeout=240)
    return rc_install == 0


def _ensure_windows_jupyter_proxy_script():
    script_path = PYTHON_STATE_DIR / "serverinstaller_jupyter_proxy.py"
    script_text = r'''import argparse
import asyncio
import base64
import ssl
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


def _unauthorized():
    response = web.Response(status=401, text="Unauthorized")
    response.headers["WWW-Authenticate"] = 'Basic realm="Restricted Jupyter"'
    return response


def _authorized(request, username, password):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except Exception:
        return False
    provided_user, _, provided_pass = decoded.partition(":")
    return provided_user == username and provided_pass == password


def _request_headers(request, backend_host, backend_port):
    headers = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in {"host", "authorization", "connection", "upgrade", "proxy-connection", "keep-alive", "transfer-encoding"}:
            continue
        headers[key] = value
    headers["Host"] = request.host
    headers["X-Forwarded-For"] = request.remote or ""
    headers["X-Forwarded-Proto"] = "https"
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Port"] = str(request.url.port or 443)
    headers["X-Real-IP"] = request.remote or ""
    return headers


def _response_headers(headers):
    result = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"content-length", "transfer-encoding", "connection", "keep-alive", "content-encoding"}:
            continue
        result[key] = value
    return result


async def _proxy_http(request, session, backend_base, backend_host, backend_port, username, password):
    if not _authorized(request, username, password):
        return _unauthorized()
    target_url = f"{backend_base}{request.rel_url}"
    body = await request.read()
    async with session.request(
        request.method,
        target_url,
        headers=_request_headers(request, backend_host, backend_port),
        data=body if body else None,
        allow_redirects=False,
    ) as upstream:
        payload = await upstream.read()
        return web.Response(
            status=upstream.status,
            headers=_response_headers(upstream.headers),
            body=payload,
        )


async def _pump_client_to_upstream(ws_client, ws_upstream):
    async for msg in ws_client:
        if msg.type == WSMsgType.TEXT:
            await ws_upstream.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            await ws_upstream.send_bytes(msg.data)
        elif msg.type == WSMsgType.PING:
            await ws_upstream.ping()
        elif msg.type == WSMsgType.PONG:
            await ws_upstream.pong()
        elif msg.type == WSMsgType.CLOSE:
            await ws_upstream.close()
            break


async def _pump_upstream_to_client(ws_client, ws_upstream):
    async for msg in ws_upstream:
        if msg.type == WSMsgType.TEXT:
            await ws_client.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            await ws_client.send_bytes(msg.data)
        elif msg.type == WSMsgType.PING:
            await ws_client.ping()
        elif msg.type == WSMsgType.PONG:
            await ws_client.pong()
        elif msg.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            await ws_client.close()
            break


async def _proxy_ws(request, session, backend_ws_base, backend_host, backend_port, username, password):
    if not _authorized(request, username, password):
        return _unauthorized()
    ws_client = web.WebSocketResponse(autoping=True, autoclose=True, max_msg_size=0)
    await ws_client.prepare(request)
    target_url = f"{backend_ws_base}{request.rel_url}"
    async with session.ws_connect(
        target_url,
        headers=_request_headers(request, backend_host, backend_port),
        autoclose=True,
        autoping=True,
        max_msg_size=0,
    ) as ws_upstream:
        await asyncio.gather(
            _pump_client_to_upstream(ws_client, ws_upstream),
            _pump_upstream_to_client(ws_client, ws_upstream),
        )
    return ws_client


async def _handle(request):
    app = request.app
    connection_header = request.headers.get("Connection", "")
    upgrade_header = request.headers.get("Upgrade", "")
    wants_ws = "upgrade" in connection_header.lower() and upgrade_header.lower() == "websocket"
    if wants_ws and request.path == "/ws/pty":
        return await _handle_pty_ws(request, app["username"], app["password"])
    if wants_ws:
        return await _proxy_ws(
            request,
            app["session"],
            app["backend_ws_base"],
            app["backend_host"],
            app["backend_port"],
            app["username"],
            app["password"],
        )
    return await _proxy_http(
        request,
        app["session"],
        app["backend_base"],
        app["backend_host"],
        app["backend_port"],
        app["username"],
        app["password"],
    )


async def _handle_pty_ws(request, username, password):
    """Spawn a real shell PTY and proxy I/O over WebSocket."""
    if not _authorized(request, username, password):
        return web.Response(status=401, text="Unauthorized")
    cwd = (request.query.get("cwd", "") or "").strip() or None
    cols = max(10, min(512, int(request.query.get("cols", 80) or 80)))
    rows = max(2, min(200, int(request.query.get("rows", 24) or 24)))
    ws = web.WebSocketResponse(autoping=False, autoclose=False, max_msg_size=0)
    await ws.prepare(request)
    loop = asyncio.get_event_loop()
    if os.name == "nt":
        try:
            import winpty as _winpty
        except ImportError:
            await ws.send_str("\r\nError: pywinpty not installed.\r\n")
            await ws.close()
            return ws
        shell = os.environ.get("COMSPEC", "cmd.exe")
        try:
            proc = _winpty.PtyProcess.spawn(shell, dimensions=(rows, cols), cwd=cwd)
        except Exception as ex:
            await ws.send_str(f"\r\nFailed to start terminal: {ex}\r\n")
            await ws.close()
            return ws

        async def _pty_read():
            try:
                while not ws.closed:
                    try:
                        data = await loop.run_in_executor(None, lambda: proc.read(4096))
                        if data:
                            await ws.send_str(data)
                        elif not proc.isalive():
                            break
                    except EOFError:
                        break
                    except Exception:
                        break
            except Exception:
                pass
            if not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def _pty_write():
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        d = msg.data
                        if d.startswith('{"type":"resize"'):
                            try:
                                r = json.loads(d)
                                if r.get("type") == "resize":
                                    proc.setwinsize(max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))))
                            except Exception:
                                pass
                        else:
                            try:
                                proc.write(d)
                            except Exception:
                                break
                    elif msg.type == WSMsgType.BINARY:
                        try:
                            proc.write(msg.data.decode("utf-8", errors="replace"))
                        except Exception:
                            break
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                        break
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

        await asyncio.gather(_pty_read(), _pty_write(), return_exceptions=True)
        try:
            proc.terminate()
        except Exception:
            pass
    else:
        try:
            import pty as _pty
            import termios as _termios
            import fcntl as _fcntl
            import struct as _struct
        except ImportError as ex:
            await ws.send_str(f"\r\nError: {ex}\r\n")
            await ws.close()
            return ws
        shell = os.environ.get("SHELL", "/bin/bash")
        master_fd = None
        slave_fd = None
        proc = None
        try:
            master_fd, slave_fd = _pty.openpty()
            try:
                _fcntl.ioctl(slave_fd, _termios.TIOCSWINSZ, _struct.pack("HHHH", rows, cols, 0, 0))
            except Exception:
                pass
            env = {**os.environ, "TERM": "xterm-256color"}
            proc = subprocess.Popen(
                [shell], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                cwd=cwd, env=env, close_fds=True, start_new_session=True,
            )
            os.close(slave_fd)
            slave_fd = None
        except Exception as ex:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except Exception:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
            await ws.send_str(f"\r\nFailed to start terminal: {ex}\r\n")
            await ws.close()
            return ws

        async def _pty_read():
            try:
                while not ws.closed:
                    try:
                        data = await loop.run_in_executor(None, lambda fd=master_fd: os.read(fd, 4096))
                        if data:
                            await ws.send_bytes(data)
                    except (OSError, IOError):
                        break
            except Exception:
                pass
            if not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def _pty_write():
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        d = msg.data
                        if d.startswith('{"type":"resize"'):
                            try:
                                r = json.loads(d)
                                if r.get("type") == "resize":
                                    _fcntl.ioctl(master_fd, _termios.TIOCSWINSZ,
                                                 _struct.pack("HHHH", max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))), 0, 0))
                            except Exception:
                                pass
                        else:
                            try:
                                os.write(master_fd, d.encode())
                            except Exception:
                                break
                    elif msg.type == WSMsgType.BINARY:
                        try:
                            os.write(master_fd, msg.data)
                        except Exception:
                            break
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                        break
            except Exception:
                pass
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                os.close(master_fd)
            except Exception:
                pass

        await asyncio.gather(_pty_read(), _pty_write(), return_exceptions=True)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            os.close(master_fd)
        except Exception:
            pass
    return ws


async def _create_app(args):
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    app = web.Application(client_max_size=1024**3)
    app["username"] = args.username
    app["password"] = args.password
    app["backend_host"] = args.backend_host
    app["backend_port"] = args.backend_port
    app["backend_base"] = f"http://{args.backend_host}:{args.backend_port}"
    app["backend_ws_base"] = f"ws://{args.backend_host}:{args.backend_port}"
    app["session"] = ClientSession(timeout=timeout)
    app.router.add_route("*", "/{path_info:.*}", _handle)

    async def _cleanup(_app):
        await _app["session"].close()

    app.on_cleanup.append(_cleanup)
    return app


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--backend-host", required=True)
    parser.add_argument("--backend-port", type=int, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    args = parser.parse_args()

    app = await _create_app(args)
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(args.certfile, args.keyfile)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.listen_host, args.listen_port, ssl_context=ssl_context)
    await site.start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(_main())
'''
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_text, encoding="utf-8")
    return str(script_path)


def _python_process_running(pid):
    try:
        pid_num = int(pid)
    except Exception:
        return False
    if pid_num <= 0:
        return False
    if os.name == "nt":
        rc, out = run_capture(["tasklist", "/FI", f"PID eq {pid_num}"], timeout=15)
        return rc == 0 and str(pid_num) in str(out or "")
    try:
        os.kill(pid_num, 0)
        return True
    except Exception:
        return False


def _windows_process_cmdline(pid):
    if os.name != "nt":
        return ""
    try:
        pid_num = int(pid)
    except Exception:
        return ""
    if pid_num <= 0:
        return ""
    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid_num}\").CommandLine",
        ],
        timeout=20,
    )
    return str(out or "").strip() if rc == 0 else ""


def _windows_process_matches_managed_jupyter(pid, port=None):
    if os.name != "nt":
        return False
    cmdline = _windows_process_cmdline(pid)
    if not cmdline:
        return False
    cmdline_lower = cmdline.lower()
    if "serverinstaller_jupyter_proxy.py" in cmdline_lower:
        target_port = str(port or _read_json_file(PYTHON_JUPYTER_STATE_FILE).get("port") or "").strip()
        if target_port.isdigit():
            return f"--listen-port {target_port}" in cmdline_lower or f"--listen-port={target_port}" in cmdline_lower
        return True
    if "jupyter" not in cmdline_lower or "lab" not in cmdline_lower:
        return False

    python_state = _read_json_file(PYTHON_STATE_FILE)
    python_executable = str(python_state.get("python_executable") or "").strip().lower()
    jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    state_port = str(jupyter_state.get("port") or python_state.get("jupyter_port") or "").strip()
    target_port = str(port or state_port or "").strip()

    if python_executable:
        normalized_cmd = cmdline_lower.replace("/", "\\")
        normalized_python = python_executable.replace("/", "\\")
        if normalized_python not in normalized_cmd:
            return False

    if target_port.isdigit():
        port_flag = f"--serverapp.port={target_port}"
        if port_flag not in cmdline_lower and f":{target_port}" not in cmdline_lower:
            return False

    return True


def _linux_systemd_unit_status(unit_name):
    unit = str(unit_name or "").strip()
    if not unit or os.name == "nt" or not command_exists("systemctl"):
        return {}
    rc_active, out_active = run_capture(["systemctl", "is-active", unit], timeout=15)
    rc_enabled, out_enabled = run_capture(["systemctl", "is-enabled", unit], timeout=15)
    active = str(out_active or "").strip()
    enabled = str(out_enabled or "").strip()
    return {
        "active": active,
        "enabled": enabled,
        "running": rc_active == 0 and active == "active",
        "autostart": enabled in ("enabled", "static", "indirect"),
    }


def _detect_python_versions():
    versions = []
    seen = set()
    ignored = {str(item).strip() for item in _read_json_list(PYTHON_IGNORED_FILE) if str(item).strip()}

    def add_candidate(cmd, managed=False):
        rc, out = run_capture(cmd, timeout=20)
        if rc != 0 or not out:
            return
        lines = [line.strip() for line in str(out).splitlines() if line.strip()]
        if len(lines) < 2:
            return
        exe = lines[0]
        version = _normalize_python_version(lines[1])
        if not exe or not version:
            return
        if exe in ignored:
            return
        key = (exe.lower(), version)
        if key in seen:
            return
        seen.add(key)
        versions.append({
            "version": version,
            "python_executable": exe,
            "managed": bool(managed),
        })

    state = _read_json_file(PYTHON_STATE_FILE)
    managed_exe = str(state.get("python_executable") or "").strip()
    managed_ver = str(state.get("python_version") or "").strip()
    if managed_exe and Path(managed_exe).exists():
        add_candidate([managed_exe, "-c", "import sys; print(sys.executable); print(sys.version.split()[0])"], managed=True)
    if os.name == "nt" and command_exists("py"):
        for version in ("3.13", "3.12", "3.11", "3.10", ""):
            cmd = ["py"]
            if version:
                cmd.append(f"-{version}")
            cmd += ["-c", "import sys; print(sys.executable); print(sys.version.split()[0])"]
            add_candidate(cmd, managed=(managed_ver and _python_version_key(version) == _python_version_key(managed_ver)))
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
            resolved = shutil.which(name)
            if not resolved:
                continue
            add_candidate([resolved, "-c", "import sys; print(sys.executable); print(sys.version.split()[0])"], managed=(managed_exe and str(Path(resolved)) == managed_exe))
    versions.sort(key=lambda item: tuple(int(part) if part.isdigit() else 0 for part in (_normalize_python_version(item.get("version") or "").split("."))), reverse=True)
    return versions


def _python_state_service_item(info):
    items = []
    if info.get("installed"):
        for runtime in info.get("python_versions") or []:
            is_managed = bool(runtime.get("managed"))
            items.append({
                "kind": "python_installation" if is_managed else "python_version",
                "name": f"python-{runtime.get('version') or 'unknown'}",
                "display_name": "Managed Python" if is_managed else "Detected Python",
                "status": "installed",
                "sub_status": runtime.get("python_executable") or "",
                "detail": runtime.get("python_executable") or "",
                "autostart": False,
                "platform": "windows" if os.name == "nt" else "linux",
                "urls": [],
                "ports": [],
                "manageable": False,
                "deletable": True,
            })
    if info.get("jupyter_running"):
        port_text = str(info.get("jupyter_port") or "").strip()
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        service_kind = "service" if os.name != "nt" and info.get("service_mode") else "python_runtime"
        service_name = JUPYTER_SYSTEMD_SERVICE if service_kind == "service" else "serverinstaller-python-jupyter"
        items.append({
            "kind": service_kind,
            "name": service_name,
            "display_name": "Managed Jupyter Lab",
            "status": "running",
            "sub_status": str(info.get("service_sub_status") or "running"),
            "autostart": bool(info.get("service_autostart")),
            "platform": "windows" if os.name == "nt" else "linux",
            "urls": [info.get("jupyter_url")] if info.get("jupyter_url") else [],
            "ports": ports,
            "manageable": True,
            "deletable": True,
        })
    items.extend(_python_api_service_items())
    return items


def _cleanup_managed_jupyter():
    jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    python_state = _read_json_file(PYTHON_STATE_FILE)
    python_executable = str(python_state.get("python_executable") or "").strip()
    jupyter_port = str(jupyter_state.get("port") or python_state.get("jupyter_port") or "").strip()
    stop_python_jupyter()
    if os.name != "nt":
        if command_exists("systemctl"):
            run_capture(["systemctl", "stop", JUPYTER_SYSTEMD_SERVICE], timeout=30)
            run_capture(["systemctl", "disable", JUPYTER_SYSTEMD_SERVICE], timeout=30)
        for path in (
            Path("/etc/systemd/system") / JUPYTER_SYSTEMD_SERVICE,
            Path("/etc/nginx/conf.d") / "serverinstaller-jupyter.conf",
        ):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        cert_dir = Path("/etc/nginx/ssl/serverinstaller-jupyter")
        try:
            if cert_dir.exists():
                shutil.rmtree(cert_dir, ignore_errors=True)
        except Exception:
            pass
        if command_exists("systemctl"):
            run_capture(["systemctl", "daemon-reload"], timeout=30)
            run_capture(["systemctl", "reload", "nginx"], timeout=30)
    elif jupyter_port.isdigit():
        try:
            manage_firewall_port("close", jupyter_port, "tcp")
        except Exception:
            pass
        if python_executable and Path(python_executable).exists():
            uninstall_packages = [
                "jupyterlab",
                "notebook",
                "ipykernel",
                "jupyter-server",
                "jupyterlab-server",
                "jupyter-lsp",
                "jupyter-server-terminals",
                "notebook-shim",
                "jupyter-client",
                "jupyter-core",
                "jupyter-events",
                "nbconvert",
                "nbformat",
                "nbclient",
                "pywinpty",
                "terminado",
            ]
            run_capture(
                [python_executable, "-m", "pip", "uninstall", "-y"] + uninstall_packages,
                timeout=180,
            )
            kernelspec_dir = Path(python_executable).parent / "share" / "jupyter" / "kernels" / "python3"
            try:
                if kernelspec_dir.exists():
                    shutil.rmtree(kernelspec_dir, ignore_errors=True)
            except Exception:
                pass
    for path in (
        PYTHON_JUPYTER_STATE_FILE,
        Path("/etc/nginx/auth/serverinstaller-jupyter.htpasswd"),
        PYTHON_STATE_DIR / "jupyter.log",
    ):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
    for path in (
        PYTHON_STATE_DIR / "jupyter-config",
        PYTHON_STATE_DIR / "jupyter-data",
        PYTHON_STATE_DIR / "jupyter-runtime",
        PYTHON_STATE_DIR / "ipython",
    ):
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
    state = _read_json_file(PYTHON_STATE_FILE)
    for key in (
        "jupyter_installed",
        "jupyter_running",
        "jupyter_url",
        "jupyter_port",
        "jupyter_internal_port",
        "jupyter_username",
        "jupyter_password_hash",
        "jupyter_auth_enabled",
        "jupyter_https_enabled",
        "service_mode",
    ):
        state.pop(key, None)
    _write_json_file(PYTHON_STATE_FILE, state)
    return True, "Managed Jupyter removed."


def _cleanup_managed_python():
    state = _read_json_file(PYTHON_STATE_FILE)
    managed_exe = str(state.get("python_executable") or "").strip()
    managed_root = str(state.get("python_root") or "").strip()
    managed_install = bool(state.get("managed_install"))
    install_method = str(state.get("install_method") or "").strip().lower()
    install_package_id = str(state.get("install_package_id") or "").strip()
    _cleanup_managed_jupyter()
    if os.name == "nt" and managed_install and install_method == "winget" and install_package_id:
        run_capture(
            [
                "winget.exe",
                "uninstall",
                "--id",
                install_package_id,
                "--exact",
                "--silent",
                "--accept-source-agreements",
            ],
            timeout=240,
        )
    if os.name == "nt" and managed_install and managed_root:
        try:
            root_path = Path(managed_root)
            if root_path.exists():
                shutil.rmtree(root_path, ignore_errors=True)
        except Exception:
            pass
    if managed_exe and not managed_install:
        current = _read_json_list(PYTHON_IGNORED_FILE)
        if managed_exe not in current:
            current.append(managed_exe)
        _write_json_list(PYTHON_IGNORED_FILE, current)
    elif managed_exe:
        current = [item for item in _read_json_list(PYTHON_IGNORED_FILE) if str(item).strip() and str(item).strip() != managed_exe]
        _write_json_list(PYTHON_IGNORED_FILE, current)
    try:
        if PYTHON_STATE_DIR.exists():
            shutil.rmtree(PYTHON_STATE_DIR, ignore_errors=True)
    except Exception:
        pass
    return True, "Managed Python removed."


def _hide_detected_python(python_executable):
    path_value = str(python_executable or "").strip()
    if not path_value:
        return False, "A Python executable path is required."
    current = _read_json_list(PYTHON_IGNORED_FILE)
    if path_value not in current:
        current.append(path_value)
        _write_json_list(PYTHON_IGNORED_FILE, current)
    return True, f"Detected Python hidden: {path_value}"


def get_python_info():
    state = _read_json_file(PYTHON_STATE_FILE)
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or state.get("python_executable") or "").strip()
    python_version = str(resolved.get("python_version") or state.get("python_version") or "").strip()
    default_notebook_dir = _resolve_python_notebook_dir(
        state.get("default_notebook_dir") or state.get("notebook_dir") or ""
    )
    info = {
        "installed": bool(python_executable and Path(python_executable).exists()),
        "python_executable": python_executable,
        "python_version": _normalize_python_version(python_version),
        "python_versions": _detect_python_versions(),
        "requested_version": str(state.get("requested_version") or "").strip(),
        "jupyter_installed": False,
        "jupyter_running": False,
        "jupyter_url": "",
        "jupyter_port": str(state.get("jupyter_port") or "").strip(),
        "jupyter_username": str(state.get("jupyter_username") or "").strip(),
        "jupyter_auth_enabled": bool(state.get("jupyter_auth_enabled")),
        "jupyter_https_enabled": bool(state.get("jupyter_https_enabled")),
        "host": str(state.get("host") or "").strip(),
        "scripts_dir": _python_scripts_dir(python_executable),
        "default_notebook_dir": default_notebook_dir,
        "notebook_dir": default_notebook_dir,
        "service_mode": bool(state.get("service_mode")),
        "service_sub_status": "",
        "service_autostart": False,
        "services": [],
    }
    if info["installed"]:
        env = _python_env(python_executable)
        rc_ver, out_ver = run_capture([python_executable, "--version"], timeout=10)
        if rc_ver == 0 and out_ver:
            info["python_version"] = _normalize_python_version(out_ver)
        rc_j, out_j = run_capture([python_executable, "-m", "jupyter", "--version"], timeout=20)
        info["jupyter_installed"] = rc_j == 0 and bool(out_j)
        if out_j:
            info["jupyter_version"] = out_j.splitlines()[0].strip()
        jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
        if os.name != "nt" and (info["service_mode"] or jupyter_state.get("service_name") == JUPYTER_SYSTEMD_SERVICE):
            service_status = _linux_systemd_unit_status(JUPYTER_SYSTEMD_SERVICE)
            info["service_mode"] = True
            info["service_sub_status"] = str(service_status.get("active") or "")
            info["service_autostart"] = bool(service_status.get("autostart"))
            info["jupyter_running"] = bool(service_status.get("running"))
            info["jupyter_port"] = str(jupyter_state.get("port") or state.get("jupyter_port") or info["jupyter_port"] or "").strip()
            info["host"] = str(jupyter_state.get("host") or state.get("host") or info["host"] or "").strip()
            info["jupyter_url"] = str(jupyter_state.get("url") or state.get("jupyter_url") or "").strip()
            info["notebook_dir"] = _resolve_python_notebook_dir(
                jupyter_state.get("notebook_dir") or state.get("notebook_dir") or info["default_notebook_dir"]
            )
            info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
            info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
            info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
            if info["jupyter_installed"] and not info["jupyter_url"] and info["jupyter_port"].isdigit():
                host = info["host"] or choose_service_host()
                info["jupyter_url"] = f"https://{host}:{info['jupyter_port']}/lab"
        else:
            pid = jupyter_state.get("pid")
            if pid and _python_process_running(pid):
                info["jupyter_running"] = True
                info["jupyter_port"] = str(jupyter_state.get("port") or info["jupyter_port"] or "").strip()
                info["host"] = str(jupyter_state.get("host") or info["host"] or "").strip()
                info["jupyter_url"] = str(jupyter_state.get("url") or "").strip()
                info["notebook_dir"] = _resolve_python_notebook_dir(
                    jupyter_state.get("notebook_dir") or info["default_notebook_dir"]
                )
                info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
                info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
                info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
                info["jupyter_pid"] = pid
            elif os.name == "nt":
                port = str(jupyter_state.get("port") or info["jupyter_port"] or "").strip()
                listeners = []
                if port.isdigit():
                    for item in get_listening_ports(limit=5000):
                        proto = str(item.get("proto", "")).lower()
                        if proto.startswith("tcp") and int(item.get("port", 0)) == int(port):
                            listeners.append(item)
                if port.isdigit() and _windows_managed_python_owns_port(port, listeners):
                    info["jupyter_running"] = True
                    info["jupyter_port"] = port
                    info["host"] = str(jupyter_state.get("host") or info["host"] or choose_service_host()).strip()
                    scheme = "https" if (jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled")) else "http"
                    info["jupyter_url"] = str(jupyter_state.get("url") or f"{scheme}://{info['host']}:{port}/lab").strip()
                    info["notebook_dir"] = _resolve_python_notebook_dir(
                        jupyter_state.get("notebook_dir") or info["default_notebook_dir"]
                    )
                    info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
                    info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
                    info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
                    for item in listeners:
                        try:
                            listener_pid = int(str(item.get("pid") or "0"))
                        except Exception:
                            continue
                        if listener_pid > 0 and _windows_process_matches_managed_jupyter(listener_pid, port):
                            jupyter_state["pid"] = listener_pid
                            jupyter_state["running"] = True
                            _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
                            info["jupyter_pid"] = listener_pid
                            break
            else:
                if jupyter_state:
                    jupyter_state["pid"] = None
                    jupyter_state["running"] = False
                    _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
                info["jupyter_url"] = ""
                info["notebook_dir"] = _resolve_python_notebook_dir(
                    jupyter_state.get("notebook_dir") if jupyter_state else info["default_notebook_dir"]
                )
    info["services"] = _python_state_service_item(info)
    return info


def _safe_python_api_name(value, default_name="python-api"):
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._").lower()
    return raw or default_name


def _python_api_source_candidates(source_root):
    root = Path(source_root)
    if not root.exists():
        return []
    blocked = {"__pycache__", ".git", ".venv", "venv", "node_modules", "site-packages"}
    result = []
    for path in root.rglob("*.py"):
        parts = {part.lower() for part in path.parts}
        if blocked & parts:
            continue
        if path.name.lower().startswith("serverinstaller_"):
            continue
        result.append(path)
    return result


def _resolve_python_api_source(source_value, entry_hint="", live_cb=None):
    src = str(source_value or "").strip()
    if not src:
        raise RuntimeError("Source path/URL, uploaded file, or uploaded folder is required.")

    source_path = Path(src)
    if src.lower().startswith(("http://", "https://")):
        source_root = prepare_source_dir(src, live_cb=live_cb)
        source_path = Path(source_root)
    elif source_path.is_dir():
        pass
    elif source_path.is_file():
        pass
    else:
        source_root = prepare_source_dir(src, live_cb=live_cb)
        source_path = Path(source_root)

    if source_path.is_file():
        if source_path.suffix.lower() != ".py":
            raise RuntimeError("Direct file input must point to a Python .py file.")
        return source_path, source_path, source_path.name

    candidates = _python_api_source_candidates(source_path)
    if not candidates:
        raise RuntimeError("No Python .py files were found in the selected source.")

    if entry_hint:
        normalized = entry_hint.replace("\\", "/").strip().lstrip("/")
        if "/" not in normalized:
            by_name = [path for path in candidates if path.name.lower() == normalized.lower()]
            if by_name:
                by_name.sort(key=lambda p: (len(p.parts), str(p).lower()))
                preferred = by_name[0]
                return source_path, preferred, preferred.relative_to(source_path).as_posix()
        preferred = (source_path / normalized).resolve()
        try:
            preferred.relative_to(source_path.resolve())
        except Exception:
            raise RuntimeError("Main file must stay inside the selected source folder.")
        if not preferred.exists() or not preferred.is_file():
            raise RuntimeError(f"Main file was not found: {normalized}")
        return source_path, preferred, preferred.relative_to(source_path).as_posix()

    preferred_names = ["main.py", "app.py", "server.py", "api.py", "run.py", "wsgi.py", "asgi.py"]
    candidates.sort(key=lambda p: (preferred_names.index(p.name.lower()) if p.name.lower() in preferred_names else 999, len(p.parts), str(p).lower()))
    chosen = candidates[0]
    return source_path, chosen, chosen.relative_to(source_path).as_posix()


def _copy_python_api_source(source_root, entry_file, deploy_root):
    source_root = Path(source_root)
    entry_file = Path(entry_file)
    deploy_root = Path(deploy_root)
    app_root = deploy_root / "app"
    if app_root.exists():
        shutil.rmtree(app_root, ignore_errors=True)
    app_root.mkdir(parents=True, exist_ok=True)

    if source_root.is_file():
        target_file = app_root / entry_file.name
        shutil.copy2(source_root, target_file)
        return target_file, entry_file.name

    if entry_file.parent == source_root and len(list(source_root.iterdir())) == 1 and entry_file.is_file():
        target_file = app_root / entry_file.name
        shutil.copy2(entry_file, target_file)
        return target_file, entry_file.name

    for item in source_root.iterdir():
        target = app_root / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    copied_entry = app_root / entry_file.relative_to(source_root)
    return copied_entry, copied_entry.relative_to(app_root).as_posix()


def _ensure_python_api_runtime_deps(python_executable, app_root, extra_packages=None, live_cb=None):
    python_exe = str(python_executable or "").strip()
    if not python_exe:
        return 1, "Install Python first."
    env = _python_env(python_exe)
    req_file = Path(app_root) / "requirements.txt"
    if req_file.exists():
        if live_cb:
            live_cb(f"Installing Python app requirements from {req_file}...\n")
        code, output = run_process([python_exe, "-m", "pip", "install", "-r", str(req_file)], env=env, live_cb=live_cb)
        if code != 0:
            return code, output or "Failed to install requirements.txt."
    packages = [pkg for pkg in (extra_packages or []) if str(pkg or "").strip()]
    if packages:
        if live_cb:
            live_cb(f"Installing deployment runtime packages: {', '.join(packages)}\n")
        code, output = run_process([python_exe, "-m", "pip", "install", "--upgrade"] + packages, env=env, live_cb=live_cb)
        if code != 0:
            return code, output or "Failed to install Python deployment runtime packages."
    return 0, ""


def _python_api_venv_python(venv_dir):
    base = Path(venv_dir)
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def _create_python_api_venv(deploy_root, python_executable, app_root, extra_packages=None, live_cb=None):
    deploy_root = Path(deploy_root)
    app_root = Path(app_root)
    python_exe = str(python_executable or "").strip()
    if not python_exe:
        return "", 1, "Install Python first."
    venv_dir = deploy_root / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    if live_cb:
        live_cb(f"Creating virtual environment at {venv_dir}...\n")
    code, output = run_process([python_exe, "-m", "venv", str(venv_dir)], live_cb=live_cb)
    if code != 0:
        return "", code, output or "Failed to create Python virtual environment."
    venv_python = _python_api_venv_python(venv_dir)
    if not venv_python.exists():
        return "", 1, f"Virtual environment Python was not created: {venv_python}"
    code, output = run_process([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], live_cb=live_cb)
    if code != 0:
        return "", code, output or "Failed to bootstrap pip inside the virtual environment."
    req_file = app_root / "requirements.txt"
    if req_file.exists():
        if live_cb:
            live_cb(f"Installing Python app requirements from {req_file} into the virtual environment...\n")
        code, output = run_process([str(venv_python), "-m", "pip", "install", "-r", str(req_file)], live_cb=live_cb)
        if code != 0:
            return "", code, output or "Failed to install requirements.txt into the virtual environment."
    packages = [pkg for pkg in (extra_packages or []) if str(pkg or "").strip()]
    if packages:
        if live_cb:
            live_cb(f"Installing deployment runtime packages into the virtual environment: {', '.join(packages)}\n")
        code, output = run_process([str(venv_python), "-m", "pip", "install", "--upgrade"] + packages, live_cb=live_cb)
        if code != 0:
            return "", code, output or "Failed to install deployment runtime packages into the virtual environment."
    return str(venv_python), 0, ""


def _ensure_python_api_https_assets(python_executable, host, deploy_name):
    python_exe = str(python_executable or "").strip()
    host_value = str(host or "").strip() or "localhost"
    name = _safe_python_api_name(deploy_name, "python-api")
    cert_dir = PYTHON_STATE_DIR / "api-certs" / name
    cert_path = cert_dir / "tls-cert.pem"
    key_path = cert_dir / "tls-key.pem"
    cert_dir.mkdir(parents=True, exist_ok=True)
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)
    rc_import, _ = run_capture([python_exe, "-c", "import trustme"], timeout=20)
    if rc_import != 0:
        rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "trustme"], timeout=240)
        if rc_install != 0:
            return "", ""
    script = (
        "from pathlib import Path\n"
        "import trustme\n"
        f"cert_path = Path(r'''{str(cert_path)}''')\n"
        f"key_path = Path(r'''{str(key_path)}''')\n"
        f"host = {host_value!r}\n"
        "ca = trustme.CA()\n"
        "server_cert = ca.issue_cert(host, 'localhost', '127.0.0.1')\n"
        "server_cert.cert_chain_pems[0].write_to_path(cert_path)\n"
        "server_cert.private_key_pem.write_to_path(key_path)\n"
    )
    rc, _ = run_capture([python_exe, "-c", script], timeout=60)
    if rc != 0 or not cert_path.exists() or not key_path.exists():
        return "", ""
    return str(cert_path), str(key_path)


def _write_python_api_runtime_files(deploy_root, app_entry_rel, app_object, host, port, certfile="", keyfile=""):
    deploy_root = Path(deploy_root)
    runtime_dir = deploy_root / ".serverinstaller"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    host_script = runtime_dir / "serverinstaller_python_api_host.py"
    shutil.copy2(PYTHON_API_HOST_TEMPLATE, host_script)
    runner_script = runtime_dir / "run_api.py"
    runner_script.write_text(
        "\n".join([
            "import os",
            "import runpy",
            f"os.environ['SERVER_INSTALLER_APP_FILE'] = r'''{str((deploy_root / 'app' / app_entry_rel).resolve())}'''",
            f"os.environ['SERVER_INSTALLER_APP_OBJECT'] = r'''{str(app_object or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_HOST'] = r'''{str(host or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_PORT'] = r'''{str(port or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_CERTFILE'] = r'''{str(certfile or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_KEYFILE'] = r'''{str(keyfile or '').strip()}'''",
            f"runpy.run_path(r'''{str(host_script.resolve())}''', run_name='__main__')",
            "",
        ]),
        encoding="utf-8",
    )
    return runtime_dir, runner_script


def _prepare_python_api_deployment(form, deployment_name, live_cb=None):
    source_value = resolve_source_value(form, "PYTHON_API_SOURCE", "PYTHON_API_SOURCE_FILE", "PYTHON_API_SOURCE_FOLDER")
    if not source_value:
        raise RuntimeError("Source path/URL, uploaded file, or uploaded folder is required.")
    source_root, entry_file, entry_rel = _resolve_python_api_source(
        source_value,
        entry_hint=((form.get("PYTHON_API_MAIN_FILE", [""])[0] or "").strip() or (form.get("PYTHON_API_ENTRY_FILE", [""])[0] or "").strip()),
        live_cb=live_cb,
    )
    python_info = get_python_info()
    python_executable = str(python_info.get("python_executable") or "").strip()
    if not python_executable:
        raise RuntimeError("Install Python first on the main Python page.")
    host = (form.get("PYTHON_API_HOST_IP", [""])[0] or "").strip() or choose_service_host()
    https_port = (form.get("PYTHON_API_PORT", ["8443"])[0] or "8443").strip()
    if not https_port.isdigit():
        raise RuntimeError("HTTPS port must be numeric.")
    http_port = (form.get("PYTHON_API_HTTP_PORT", [""])[0] or "").strip()
    if http_port and not http_port.isdigit():
        raise RuntimeError("HTTP port must be numeric.")
    app_object = (form.get("PYTHON_API_APP_OBJECT", [""])[0] or "").strip()
    deploy_key = _safe_python_api_name(deployment_name)
    deploy_root = PYTHON_STATE_DIR / "api" / deploy_key
    deploy_root.mkdir(parents=True, exist_ok=True)
    copied_entry, copied_entry_rel = _copy_python_api_source(source_root, entry_file, deploy_root)
    return {
        "python_executable": python_executable,
        "host": host,
        "http_port": http_port,
        "https_port": https_port,
        "app_object": app_object,
        "deploy_key": deploy_key,
        "deploy_root": deploy_root,
        "entry_path": copied_entry,
        "entry_rel": copied_entry_rel,
    }


def _update_python_api_state(name, payload):
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        deployments = {}
    deployments[_safe_python_api_name(name)] = payload
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)


def _cleanup_python_api_state_entry(service_name, kind=""):
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return
    remove_keys = []
    for key, payload in deployments.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("name") or "").strip() != str(service_name or "").strip():
            continue
        if kind and str(payload.get("kind") or "").strip() != str(kind or "").strip():
            continue
        deploy_root = Path(str(payload.get("deploy_root") or "").strip())
        try:
            if deploy_root.exists():
                shutil.rmtree(deploy_root, ignore_errors=True)
        except Exception:
            pass
        remove_keys.append(key)
    for key in remove_keys:
        deployments.pop(key, None)
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)


def _python_api_service_items():
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return []
    items = []
    for _, payload in deployments.items():
        if not isinstance(payload, dict):
            continue
        kind = str(payload.get("kind") or "").strip().lower()
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        url = str(payload.get("url") or "").strip()
        port_text = str(payload.get("port") or "").strip()
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        running = False
        autostart = False
        sub_status = ""
        if kind == "service":
            if os.name == "nt":
                rc, out = run_capture(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        f"$svc=Get-CimInstance Win32_Service -Filter \"Name='{name}'\" -ErrorAction SilentlyContinue; if($svc){{Write-Output ($svc.State + '|' + $svc.StartMode)}}",
                    ],
                    timeout=20,
                )
                if rc == 0 and out:
                    parts = str(out).strip().split("|", 1)
                    sub_status = parts[0] if parts else ""
                    running = sub_status.lower() == "running"
                    autostart = len(parts) > 1 and parts[1].strip().lower() == "auto"
            else:
                svc = _linux_systemd_unit_status(name)
                sub_status = str(svc.get("active") or "")
                running = bool(svc.get("running"))
                autostart = bool(svc.get("autostart"))
        elif kind == "docker":
            details = _get_docker_container_details(name)
            sub_status = str(details.get("state") or "")
            running = sub_status == "running"
            autostart = str(details.get("restart_policy") or "") in ("always", "unless-stopped")
        elif kind == "iis_site" and os.name == "nt":
            rc, out = run_capture(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Import-Module WebAdministration; $site=Get-Website -Name '{name}' -ErrorAction SilentlyContinue; if($site){{Write-Output ($site.State + '|' + [string]$site.serverAutoStart)}}",
                ],
                timeout=20,
            )
            if rc == 0 and out:
                parts = str(out).strip().split("|", 1)
                sub_status = parts[0] if parts else ""
                running = sub_status.lower() == "started"
                autostart = len(parts) > 1 and parts[1].strip().lower() == "true"
        items.append({
            "kind": kind or "service",
            "name": name,
            "display_name": "Python API",
            "status": "running" if running else "stopped",
            "sub_status": sub_status or ("running" if running else "stopped"),
            "autostart": autostart,
            "platform": "windows" if os.name == "nt" else "linux",
            "urls": [url] if url else [],
            "ports": ports,
            "manageable": True,
            "deletable": True,
            "detail": str(payload.get("entry_file") or ""),
            "python_api": True,
            "target_page": "python-system" if kind == "service" else ("python-docker" if kind == "docker" else ("python-iis" if kind == "iis_site" else "python-api")),
            "deployment_key": str(payload.get("deployment_key") or ""),
            "form_name": str(payload.get("form_name") or name),
            "project_path": str(payload.get("project_path") or ""),
            "deploy_root": str(payload.get("deploy_root") or ""),
            "main_file": str(payload.get("entry_file") or ""),
            "host": str(payload.get("host") or ""),
            "port_value": str(payload.get("port") or ""),
            "service_log": str(payload.get("service_log") or ""),
        })
    return items


def _safe_website_name(value, default_name="ServerInstallerWebsite"):
    text = re.sub(r"[^A-Za-z0-9 _.-]+", "", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._-")
    return text or default_name


def _safe_website_runtime_name(value, default_name="serverinstaller-website"):
    text = re.sub(r"[^A-Za-z0-9.-]+", "-", str(value or "").strip().lower()).strip("-.")
    return text or default_name


def _website_state_key(value):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned or "website"


def _update_website_state(name, payload):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        deployments = {}
    deployments[_website_state_key(name)] = payload
    state["deployments"] = deployments
    _write_json_file(WEBSITE_STATE_FILE, state)


def _cleanup_website_state_entry(site_name):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return
    remove_keys = []
    for key, payload in deployments.items():
        if not isinstance(payload, dict):
            remove_keys.append(key)
            continue
        if str(payload.get("name") or "").strip().lower() == str(site_name or "").strip().lower():
            remove_keys.append(key)
    for key in remove_keys:
        deployments.pop(key, None)
    state["deployments"] = deployments
    _write_json_file(WEBSITE_STATE_FILE, state)


def _website_state_payload(site_name):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return {}
    target = str(site_name or "").strip().lower()
    for payload in deployments.values():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("name") or "").strip().lower() == target:
            return payload
    return {}


def _website_state_payload_by_key(site_key):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return {}
    payload = deployments.get(str(site_key or "").strip())
    return payload if isinstance(payload, dict) else {}


def _cleanup_existing_website_runtime(payload):
    if not isinstance(payload, dict):
        return
    name = str(payload.get("name") or "").strip()
    target = str(payload.get("target") or "").strip().lower()
    if not name:
        return
    if target == "docker" and command_exists("docker"):
        run_capture(["docker", "rm", "-f", name], timeout=60)
        image_name = str(payload.get("image_name") or "").strip()
        if image_name:
            run_capture(["docker", "rmi", "-f", image_name], timeout=30)
        return
    if target == "iis" and os.name == "nt":
        ps = "\n".join([
            "Import-Module WebAdministration",
            f"$siteName = {_ps_single_quote(name)}",
            "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
            f"if (Test-Path ('IIS:\\AppPools\\{name}')) {{ Stop-WebAppPool -Name '{name}' -ErrorAction SilentlyContinue | Out-Null; Remove-WebAppPool -Name '{name}' -ErrorAction SilentlyContinue | Out-Null }}",
        ])
        run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=90)
        return
    if target == "service" and os.name == "nt":
        run_capture(["sc.exe", "stop", name], timeout=30)
        run_capture(["sc.exe", "delete", name], timeout=30)
        return
    if target == "service" and platform.system() == "Darwin":
        plist_name = str(payload.get("plist_name") or f"com.serverinstaller.website.{_safe_website_runtime_name(name)}").strip()
        plist_path = f"/Library/LaunchDaemons/{plist_name}.plist"
        prefix = _sudo_prefix()
        run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=30)
        run_capture(prefix + ["rm", "-f", plist_path], timeout=30)
        return
    if target == "service":
        unit_name = name if name.endswith(".service") else f"{name}.service"
        prefix = _sudo_prefix()
        run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
        run_capture(prefix + ["systemctl", "disable", unit_name], timeout=30)
        run_capture(prefix + ["rm", "-f", f"/etc/systemd/system/{unit_name}"], timeout=30)
        run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)


def _detect_static_website_root(source_root: Path, website_kind="auto"):
    root = Path(source_root).resolve()
    kind = str(website_kind or "auto").strip().lower()
    candidate_dirs = []

    def add_candidate(path_obj):
        try:
            candidate = Path(path_obj).resolve()
        except Exception:
            return
        if not candidate.exists() or not candidate.is_dir():
            return
        if candidate not in candidate_dirs:
            candidate_dirs.append(candidate)

    if kind == "flutter":
        add_candidate(root / "build" / "web")
    elif kind in ("static", "web", "next-export"):
        add_candidate(root / "out")
        add_candidate(root / "dist")
        add_candidate(root / "build")

    for rel in (
        "build/web",
        "out",
        "dist",
        "build",
        "public",
        ".next/static",
        "",
    ):
        add_candidate(root / rel if rel else root)

    for candidate in list(candidate_dirs):
        index_file = candidate / "index.html"
        if index_file.exists():
            return candidate, str(candidate.relative_to(root)) if candidate != root else "."

    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        if (candidate / "index.html").exists():
            return candidate, str(candidate.relative_to(root))

    # No index.html found anywhere — use the source root as-is so the
    # web server can serve whatever files were uploaded.
    return root, "."


def _read_text_if_exists(path_value):
    path_obj = Path(path_value)
    if not path_obj.exists() or not path_obj.is_file():
        return ""
    try:
        return path_obj.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _find_php_public_root(source_root: Path):
    root = Path(source_root).resolve()
    for rel in ("public", "web", ""):
        candidate = root / rel if rel else root
        if candidate.is_dir() and any((candidate / name).exists() for name in ("index.php", "router.php")):
            return candidate, (str(candidate.relative_to(root)) if candidate != root else ".")
    for candidate in root.rglob("*"):
        if candidate.is_dir() and (candidate / "index.php").exists():
            return candidate, str(candidate.relative_to(root))
    raise RuntimeError("Could not find a PHP web root. Expected index.php in the project root or a public/ folder.")


def _detect_website_stack(source_root: Path):
    root = Path(source_root).resolve()
    package_json = root / "package.json"
    pubspec = root / "pubspec.yaml"
    composer_json = root / "composer.json"
    next_config = any((root / name).exists() for name in ("next.config.js", "next.config.mjs", "next.config.ts"))
    next_dir = (root / ".next").exists()
    out_dir = (root / "out" / "index.html").exists()
    dist_dir = (root / "dist" / "index.html").exists()
    flutter_build = (root / "build" / "web" / "index.html").exists()
    php_index = any((root / rel).exists() for rel in ("index.php", "public/index.php", "web/index.php"))

    package_data = {}
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            package_data = {}
    deps = {}
    if isinstance(package_data, dict):
        deps = {
            **(package_data.get("dependencies") if isinstance(package_data.get("dependencies"), dict) else {}),
            **(package_data.get("devDependencies") if isinstance(package_data.get("devDependencies"), dict) else {}),
        }
    scripts = package_data.get("scripts") if isinstance(package_data.get("scripts"), dict) else {}
    is_next = ("next" in deps) or next_config or next_dir
    is_next_export = is_next and (
        out_dir or
        "export" in scripts or
        "next export" in json.dumps(scripts)
    )
    if is_next_export and out_dir:
        return {"kind": "next-export", "runtime": "static", "stack_label": "Next Export / Static Website"}
    if is_next:
        return {"kind": "nextjs", "runtime": "node", "stack_label": "Next.js Website"}
    pubspec_text = _read_text_if_exists(pubspec)
    if pubspec.exists() and ("flutter:" in pubspec_text.lower() or flutter_build):
        return {"kind": "flutter", "runtime": "static", "stack_label": "Flutter Web Website"}
    if composer_json.exists() or php_index:
        return {"kind": "php", "runtime": "php", "stack_label": "PHP Website"}
    if out_dir:
        return {"kind": "next-export", "runtime": "static", "stack_label": "Next Export / Static Website"}
    if dist_dir or flutter_build or (root / "index.html").exists():
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Check for index.html in common subdirectories
    for sub in ("public", "www", "wwwroot", "html", "htdocs", "web", "static"):
        if (root / sub / "index.html").exists():
            return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Check for any .html file at root level
    if any(f.suffix.lower() == ".html" for f in root.iterdir() if f.is_file()):
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Default to static for any directory with files — let the web server serve whatever is there
    if any(root.iterdir()):
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    raise RuntimeError("Source folder is empty. Upload or point to a folder with your website files.")


def _copy_website_source(source_root: Path, deploy_root: Path):
    if deploy_root.exists():
        shutil.rmtree(deploy_root, ignore_errors=True)
    blocked = {".git", "__pycache__", ".venv", "venv", "node_modules", ".next/cache", "vendor/.cache"}

    def ignore_func(_dir, names):
        ignored = []
        for name in names:
            normalized = name.replace("\\", "/")
            if name in blocked or normalized in blocked:
                ignored.append(name)
        return ignored

    shutil.copytree(source_root, deploy_root, ignore=ignore_func)


def _choose_website_target(requested_target, detected_runtime):
    target = str(requested_target or "auto").strip().lower()
    runtime = str(detected_runtime or "static").strip().lower()
    valid_targets = ("service", "docker", "iis", "nginx", "nodejs", "kubernetes", "pm2")
    if target == "auto":
        if runtime == "static":
            if os.name == "nt" and get_iis_info().get("installed"):
                return "iis"
            if command_exists("docker"):
                return "docker"
            if command_exists("nginx"):
                return "nginx"
            return "service"
        if runtime == "node":
            if command_exists("docker"):
                return "docker"
            if command_exists("pm2"):
                return "pm2"
            if command_exists("node"):
                return "nodejs"
            return "service"
        if runtime == "php":
            if command_exists("docker"):
                return "docker"
            if command_exists("nginx"):
                return "nginx"
            return "service"
    return target if target in valid_targets else "service"


def _validate_website_target(stack_kind, runtime, target):
    stack = str(stack_kind or "").strip().lower()
    selected = str(target or "").strip().lower()
    runtime_value = str(runtime or "").strip().lower()
    if selected == "iis":
        if os.name != "nt":
            raise RuntimeError("IIS target is only available on Windows.")
        if runtime_value != "static":
            raise RuntimeError(f"{stack or 'This'} website cannot run directly on IIS from this dashboard. Use Docker or OS service.")
    if selected == "docker":
        if sys.platform == "darwin":
            _docker_add_macos_path()
        if not command_exists("docker"):
            # Auto-install Docker
            _install_website_engine("docker")
            if sys.platform == "darwin":
                _docker_add_macos_path()
            if not command_exists("docker"):
                raise RuntimeError("Docker target requires Docker to be installed and running.")
    if selected == "nginx":
        if os.name == "nt":
            raise RuntimeError("Nginx is not available on Windows. Use IIS or Docker instead.")
        if runtime_value == "node":
            raise RuntimeError("Next.js requires a Node.js runtime. Nginx cannot serve it directly. Use Docker, Node.js, or PM2.")
        if not command_exists("nginx"):
            _install_website_engine("nginx")
            if not command_exists("nginx"):
                raise RuntimeError("Nginx installation failed. Install it manually or use Docker.")
    if selected == "nodejs":
        if runtime_value == "php":
            raise RuntimeError("PHP code cannot run on Node.js. Use Nginx, Docker, or the OS service target.")
        if not command_exists("node"):
            _install_website_engine("nodejs")
            if not command_exists("node"):
                raise RuntimeError("Node.js installation failed. Install it manually.")
    if selected == "pm2":
        if runtime_value == "php":
            raise RuntimeError("PHP code cannot run under PM2. Use Nginx or Docker.")
        if not command_exists("pm2"):
            _install_website_engine("pm2")
            if not command_exists("pm2"):
                raise RuntimeError("PM2 installation failed. Install Node.js and run 'npm install -g pm2'.")
    if selected == "kubernetes":
        if os.name == "nt":
            raise RuntimeError("Kubernetes deployment from this dashboard requires Linux. Enable Kubernetes in Docker Desktop on Windows.")
        if not (command_exists("kubectl") or command_exists("k3s")):
            _install_website_engine("kubernetes")
            if not (command_exists("kubectl") or command_exists("k3s")):
                raise RuntimeError("Kubernetes installation failed.")
    if selected == "service" and runtime_value == "node" and not (command_exists("node") and command_exists("npm")):
        raise RuntimeError("Next.js service target requires Node.js and npm on the host.")
    if selected == "service" and runtime_value == "php" and not command_exists("php"):
        raise RuntimeError("PHP service target requires php on the host.")


def _detect_website_engines():
    """Detect which runtime engines are available on this system."""
    engines = {}

    def _cmd_version(cmd, flag="--version"):
        try:
            r = subprocess.run([cmd, flag], capture_output=True, timeout=10, text=True)
            if r.returncode == 0:
                ver = (r.stdout or r.stderr or "").strip().splitlines()[0].strip()
                # Clean up version string
                for prefix in ("Docker version ", "nginx version: nginx/", "v", "pm2 "):
                    if ver.lower().startswith(prefix.lower()):
                        ver = ver[len(prefix):].split(",")[0].split(" ")[0].strip()
                        break
                return ver
        except Exception:
            pass
        return ""

    # Docker
    if command_exists("docker"):
        engines["docker"] = {"installed": True, "version": _cmd_version("docker", "--version")}
    else:
        engines["docker"] = {"installed": False}

    # Nginx
    if command_exists("nginx"):
        engines["nginx"] = {"installed": True, "version": _cmd_version("nginx", "-v")}
    else:
        engines["nginx"] = {"installed": False}

    # IIS (Windows only)
    if os.name == "nt":
        iis_info = get_iis_info()
        engines["iis"] = {"installed": bool(iis_info.get("installed")), "version": str(iis_info.get("version") or "")}
    else:
        engines["iis"] = {"installed": False}

    # Node.js
    if command_exists("node"):
        engines["nodejs"] = {"installed": True, "version": _cmd_version("node", "--version")}
    else:
        engines["nodejs"] = {"installed": False}

    # Kubernetes (kubectl + k3s/microk8s)
    k8s_installed = False
    k8s_version = ""
    if command_exists("kubectl"):
        k8s_installed = True
        k8s_version = _cmd_version("kubectl", "version --client --short") or _cmd_version("kubectl", "version")
    elif command_exists("k3s"):
        k8s_installed = True
        k8s_version = _cmd_version("k3s", "--version")
    elif command_exists("microk8s"):
        k8s_installed = True
        k8s_version = "microk8s"
    engines["kubernetes"] = {"installed": k8s_installed, "version": k8s_version}

    # PM2
    if command_exists("pm2"):
        engines["pm2"] = {"installed": True, "version": _cmd_version("pm2", "--version")}
    else:
        engines["pm2"] = {"installed": False}

    # OS Service (always available)
    if os.name == "nt":
        engines["service"] = {"installed": True, "version": "Windows Service"}
    else:
        engines["service"] = {"installed": True, "version": "systemd" if command_exists("systemctl") else "launchd" if sys.platform == "darwin" else "service"}

    return engines


def _install_website_engine(engine_id, live_cb=None):
    """Install a runtime engine. Returns (exit_code, output_text)."""
    engine_id = str(engine_id or "").strip().lower()
    output_lines = []

    def log(msg):
        output_lines.append(msg)
        if live_cb:
            live_cb(msg + "\n")

    log(f"=== Installing {engine_id} ===")

    if engine_id == "docker":
        return _install_engine_docker(log)
    elif engine_id == "nginx":
        return _install_engine_nginx(log)
    elif engine_id == "nodejs":
        return _install_engine_nodejs(log)
    elif engine_id == "kubernetes":
        return _install_engine_kubernetes(log)
    elif engine_id == "pm2":
        return _install_engine_pm2(log)
    elif engine_id == "iis":
        return _install_engine_iis(log)
    else:
        log(f"Unknown engine: {engine_id}")
        return 1, "\n".join(output_lines)


def _run_install_cmd(cmd, log, timeout=300):
    """Run an installation command, streaming output."""
    log(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        if isinstance(cmd, str):
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log(line.rstrip())
        proc.wait(timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        log("Command timed out.")
        return 1
    except Exception as e:
        log(f"Error: {e}")
        return 1


def _docker_add_macos_path():
    """Add Docker Desktop binary paths to PATH on macOS."""
    docker_paths = [
        "/Applications/Docker.app/Contents/Resources/bin",
        "/usr/local/bin",
        str(Path.home() / ".docker" / "bin"),
    ]
    current_path = os.environ.get("PATH", "")
    for dp in docker_paths:
        if dp not in current_path and Path(dp).exists():
            os.environ["PATH"] = dp + os.pathsep + current_path
            current_path = os.environ["PATH"]


def _docker_wait_macos(log):
    """Wait for Docker Desktop to finish initialization on macOS."""
    import time
    log("Waiting for Docker Desktop to initialize...")
    # First add Docker bin to PATH
    _docker_add_macos_path()
    # Docker Desktop creates symlinks in /usr/local/bin after first launch
    # Also check the embedded binary directly
    docker_bin = "/Applications/Docker.app/Contents/Resources/bin/docker"
    for i in range(60):
        time.sleep(3)
        _docker_add_macos_path()
        # Check if docker CLI is available via PATH or direct path
        if command_exists("docker"):
            log("Docker CLI found in PATH.")
            # Now wait for Docker daemon to be ready
            try:
                rc, out = run_capture(["docker", "info"], timeout=10)
                if rc == 0:
                    log("Docker is ready.")
                    return 0, "Docker installed."
            except Exception:
                pass
            log(f"Docker CLI available, waiting for daemon... ({i+1}/60)")
        elif Path(docker_bin).exists():
            # Docker binary exists but not in PATH yet — use it directly
            os.environ["PATH"] = str(Path(docker_bin).parent) + os.pathsep + os.environ.get("PATH", "")
            log(f"Found Docker at {docker_bin}, waiting for daemon... ({i+1}/60)")
            try:
                rc, out = run_capture([docker_bin, "info"], timeout=10)
                if rc == 0:
                    log("Docker is ready.")
                    return 0, "Docker installed."
            except Exception:
                pass
        else:
            log(f"Waiting for Docker... ({i+1}/60)")
    # If we get here, Docker Desktop is installed but not ready yet
    if command_exists("docker") or Path(docker_bin).exists():
        log("Docker Desktop is installed but still initializing.")
        log("Please wait for Docker Desktop to finish setup, then retry.")
        return 0, "Docker installed. Docker Desktop is still initializing — retry in a moment."
    return 1, "Docker Desktop installed but CLI not found. Restart Docker Desktop."


def _install_engine_docker(log):
    """Install Docker."""
    # On macOS, Docker Desktop puts the CLI in a non-standard path
    if sys.platform == "darwin":
        _docker_add_macos_path()
    if command_exists("docker"):
        log("Docker is already installed.")
        return 0, "Docker is already installed."

    if os.name == "nt":
        log("On Windows, Docker Desktop must be installed manually.")
        log("Download from: https://www.docker.com/products/docker-desktop/")
        return 1, "Docker Desktop must be installed manually on Windows."

    if sys.platform == "darwin":
        # macOS Apple Silicon: install Rosetta 2 first (required for Docker)
        import platform as _plat
        if _plat.machine() == "arm64":
            log("Installing Rosetta 2 (required for Docker on Apple Silicon)...")
            _run_install_cmd(["softwareupdate", "--install-rosetta", "--agree-to-license"], log, timeout=120)
        # macOS: use brew to install Docker
        log("macOS detected. Installing Docker via Homebrew...")
        if command_exists("brew"):
            code = _run_install_cmd(["brew", "install", "--cask", "docker"], log, timeout=300)
            if code == 0:
                log("Docker Desktop installed. Opening it...")
                _run_install_cmd(["open", "/Applications/Docker.app"], log, timeout=10)
                _docker_add_macos_path()
                return _docker_wait_macos(log)
            else:
                log("brew install failed. Install Docker Desktop manually:")
                log("https://www.docker.com/products/docker-desktop/")
                return 1, "Docker installation failed."
        else:
            # No brew — download Docker Desktop .dmg directly
            log("Homebrew not found. Downloading Docker Desktop directly...")
            import platform as _plat
            arch = _plat.machine()
            if arch == "arm64":
                dmg_url = "https://desktop.docker.com/mac/main/arm64/Docker.dmg"
            else:
                dmg_url = "https://desktop.docker.com/mac/main/amd64/Docker.dmg"
            dmg_path = "/tmp/Docker.dmg"
            code = _run_install_cmd(["curl", "-fSL", dmg_url, "-o", dmg_path], log, timeout=300)
            if code == 0 and Path(dmg_path).exists():
                log("Mounting Docker.dmg...")
                _run_install_cmd(["hdiutil", "attach", dmg_path, "-nobrowse"], log, timeout=30)
                _run_install_cmd(["cp", "-R", "/Volumes/Docker/Docker.app", "/Applications/"], log, timeout=60)
                _run_install_cmd(["hdiutil", "detach", "/Volumes/Docker"], log, timeout=15)
                Path(dmg_path).unlink(missing_ok=True)
                log("Docker Desktop installed. Opening...")
                _run_install_cmd(["open", "/Applications/Docker.app"], log, timeout=10)
                _docker_add_macos_path()
                return _docker_wait_macos(log)
            else:
                log("Download failed. Install Docker Desktop manually:")
                log("https://www.docker.com/products/docker-desktop/")
                return 1, "Docker installation failed."
    else:
        # Linux
        log("Installing Docker via official script...")
        code = _run_install_cmd("curl -fsSL https://get.docker.com | sh", log)
        if code == 0:
            _run_install_cmd(["systemctl", "enable", "--now", "docker"], log)
            log("Docker installed successfully.")
        return code, "Docker installation complete." if code == 0 else "Docker installation failed."


def _install_engine_nginx(log):
    """Install Nginx."""
    if command_exists("nginx"):
        log("Nginx is already installed.")
        return 0, "Nginx is already installed."

    if os.name == "nt":
        log("Nginx is not supported on Windows through this installer. Use IIS or Docker instead.")
        return 1, "Nginx not supported on Windows."

    # Detect package manager
    if command_exists("apt-get"):
        log("Installing Nginx via apt...")
        _run_install_cmd(["apt-get", "update", "-y"], log)
        code = _run_install_cmd(["apt-get", "install", "-y", "nginx"], log)
    elif command_exists("dnf"):
        log("Installing Nginx via dnf...")
        code = _run_install_cmd(["dnf", "install", "-y", "nginx"], log)
    elif command_exists("yum"):
        log("Installing Nginx via yum...")
        code = _run_install_cmd(["yum", "install", "-y", "nginx"], log)
    elif command_exists("brew"):
        log("Installing Nginx via Homebrew...")
        code = _run_install_cmd(["brew", "install", "nginx"], log)
    else:
        log("No supported package manager found (apt/dnf/yum/brew).")
        return 1, "No supported package manager found."

    if code == 0:
        if command_exists("systemctl"):
            _run_install_cmd(["systemctl", "enable", "--now", "nginx"], log)
        log("Nginx installed successfully.")
    return code, "Nginx installation complete." if code == 0 else "Nginx installation failed."


def _install_engine_nodejs(log):
    """Install Node.js."""
    if command_exists("node"):
        log("Node.js is already installed.")
        return 0, "Node.js is already installed."

    if os.name == "nt":
        log("Installing Node.js via winget...")
        code = _run_install_cmd(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements", "--accept-source-agreements"], log)
        if code != 0:
            log("winget failed. Trying direct download...")
            log("Download Node.js from: https://nodejs.org/")
            return 1, "Please install Node.js manually from https://nodejs.org/"
    else:
        log("Installing Node.js via NodeSource...")
        if command_exists("apt-get"):
            _run_install_cmd("curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["apt-get", "install", "-y", "nodejs"], log)
        elif command_exists("dnf"):
            _run_install_cmd("curl -fsSL https://rpm.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["dnf", "install", "-y", "nodejs"], log)
        elif command_exists("yum"):
            _run_install_cmd("curl -fsSL https://rpm.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["yum", "install", "-y", "nodejs"], log)
        elif command_exists("brew"):
            code = _run_install_cmd(["brew", "install", "node"], log)
        else:
            log("No supported package manager found.")
            return 1, "No supported package manager found."

    if code == 0:
        log("Node.js installed successfully.")
    return code, "Node.js installation complete." if code == 0 else "Node.js installation failed."


def _install_engine_kubernetes(log):
    """Install lightweight Kubernetes (K3s on Linux)."""
    if command_exists("kubectl") or command_exists("k3s"):
        log("Kubernetes is already installed.")
        return 0, "Kubernetes is already installed."

    if os.name == "nt":
        log("Kubernetes on Windows requires Docker Desktop with Kubernetes enabled, or WSL2 with K3s.")
        return 1, "Enable Kubernetes in Docker Desktop settings."

    log("Installing K3s (lightweight Kubernetes)...")
    code = _run_install_cmd("curl -sfL https://get.k3s.io | sh -", log)
    if code == 0:
        log("K3s installed successfully. kubectl is available via 'k3s kubectl'.")
    return code, "K3s installation complete." if code == 0 else "K3s installation failed."


def _install_engine_pm2(log):
    """Install PM2 (Node.js process manager)."""
    if command_exists("pm2"):
        log("PM2 is already installed.")
        return 0, "PM2 is already installed."

    if not command_exists("npm"):
        log("PM2 requires Node.js/npm. Installing Node.js first...")
        node_code, _ = _install_engine_nodejs(log)
        if node_code != 0:
            return node_code, "Failed to install Node.js (required for PM2)."

    log("Installing PM2 globally via npm...")
    code = _run_install_cmd(["npm", "install", "-g", "pm2"], log)
    if code == 0:
        if os.name != "nt" and command_exists("pm2"):
            _run_install_cmd(["pm2", "startup"], log)
        log("PM2 installed successfully.")
    return code, "PM2 installation complete." if code == 0 else "PM2 installation failed."


def _install_engine_iis(log):
    """Install IIS (Windows only)."""
    if os.name != "nt":
        log("IIS is only available on Windows.")
        return 1, "IIS is only available on Windows."

    iis_info = get_iis_info()
    if iis_info.get("installed"):
        log("IIS is already installed.")
        return 0, "IIS is already installed."

    log("Installing IIS via DISM...")
    features = [
        "IIS-WebServerRole",
        "IIS-WebServer",
        "IIS-CommonHttpFeatures",
        "IIS-StaticContent",
        "IIS-DefaultDocument",
        "IIS-DirectoryBrowsing",
        "IIS-HttpErrors",
        "IIS-HttpRedirect",
        "IIS-ManagementConsole",
        "IIS-RequestFiltering",
        "IIS-HttpCompressionStatic",
    ]
    for feature in features:
        code = _run_install_cmd(
            ["dism", "/Online", "/Enable-Feature", f"/FeatureName:{feature}", "/All", "/NoRestart"],
            log
        )
        if code != 0:
            log(f"Warning: Feature {feature} returned code {code}")
    log("IIS installation complete. A restart may be required.")
    return 0, "IIS installation complete."


def resolve_unix_python():
    for name in ("python3", "python"):
        path_value = shutil.which(name)
        if path_value:
            return path_value
    return sys.executable


def _prepare_website_deployment(form=None, live_cb=None):
    form = form or {}
    source_value = resolve_source_value(form, "WEBSITE_SOURCE", "WEBSITE_SOURCE_FILE", "WEBSITE_SOURCE_FOLDER")
    if not source_value:
        raise RuntimeError("Project path, uploaded archive, or uploaded folder is required.")
    source_root = prepare_source_dir(source_value, live_cb=live_cb)
    site_name = _safe_website_name((form.get("WEBSITE_SITE_NAME", ["ServerInstallerWebsite"])[0] or "").strip(), "ServerInstallerWebsite")
    runtime_name = _safe_website_runtime_name((form.get("WEBSITE_RUNTIME_NAME", [""])[0] or "").strip() or site_name, "serverinstaller-website")
    site_key = _website_state_key(site_name)
    requested_kind = (form.get("WEBSITE_KIND", ["auto"])[0] or "auto").strip().lower()
    if requested_kind not in ("auto", "static", "flutter", "next-export", "nextjs", "php"):
        requested_kind = "auto"
    target = (form.get("WEBSITE_TARGET", ["auto"])[0] or "auto").strip().lower()
    bind_ip = (form.get("WEBSITE_BIND_IP", [""])[0] or "").strip() or "*"
    domain = (form.get("WEBSITE_DOMAIN", [""])[0] or "").strip()
    host = domain or (bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host())
    port_text = (form.get("WEBSITE_PORT", [""])[0] or "").strip()
    site_port = int(port_text) if port_text.isdigit() and 1 <= int(port_text) <= 65535 else 0
    https_port_text = (form.get("WEBSITE_HTTPS_PORT", [""])[0] or "").strip()
    https_port = int(https_port_text) if https_port_text.isdigit() and 1 <= int(https_port_text) <= 65535 else 0
    if not site_port and not https_port:
        raise RuntimeError("At least one port (HTTP or HTTPS) is required.")
    ssl_cert_name = (form.get("WEBSITE_SSL_CERT", ["self_signed"])[0] or "self_signed").strip()
    deploy_root = WEBSITE_STATE_DIR / site_key
    if requested_kind == "auto":
        detected = _detect_website_stack(source_root)
        detected_kind = str(detected.get("kind") or "static").strip().lower()
        runtime = str(detected.get("runtime") or "static").strip().lower()
        stack_label = str(detected.get("stack_label") or "Website").strip()
    else:
        detected_kind = requested_kind
        runtime_map = {"static": "static", "flutter": "static", "next-export": "static", "nextjs": "node", "php": "php"}
        runtime = runtime_map.get(requested_kind, "static")
        stack_label = _website_stack_label(requested_kind)
    effective_kind = detected_kind if requested_kind == "auto" else requested_kind
    if effective_kind in ("static", "flutter", "next-export"):
        publish_root, publish_rel = _detect_static_website_root(source_root, website_kind=effective_kind)
        if deploy_root.exists():
            shutil.rmtree(deploy_root, ignore_errors=True)
        shutil.copytree(publish_root, deploy_root)
        content_root = deploy_root
        content_rel = publish_rel
    elif effective_kind == "php":
        source_publish_root, publish_rel = _find_php_public_root(source_root)
        _copy_website_source(source_root, deploy_root)
        content_rel = publish_rel
        content_root = deploy_root / publish_rel if publish_rel not in ("", ".") else deploy_root
        runtime = "php"
        stack_label = "PHP Website"
    elif effective_kind == "nextjs":
        _copy_website_source(source_root, deploy_root)
        publish_rel = "."
        content_rel = "."
        content_root = deploy_root
        runtime = "node"
        stack_label = "Next.js Website"
    else:
        raise RuntimeError(f"Unsupported website type '{effective_kind}'.")
    selected_target = _choose_website_target(target, runtime)
    _validate_website_target(effective_kind, runtime, selected_target)
    if live_cb:
        live_cb(f"Detected website type: {stack_label} ({runtime}). Selected target: {selected_target}.\n")
    return {
        "site_name": site_name,
        "runtime_name": runtime_name,
        "site_key": site_key,
        "existing_payload": _website_state_payload_by_key(site_key),
        "website_kind": effective_kind,
        "detected_kind": detected_kind,
        "runtime": runtime,
        "stack_label": stack_label,
        "target": selected_target,
        "bind_ip": bind_ip,
        "domain": domain,
        "host": host,
        "site_port": site_port,
        "https_port": https_port,
        "ssl_cert_name": ssl_cert_name,
        "source_root": str(source_root),
        "publish_root": str(content_root),
        "publish_rel": publish_rel,
        "content_rel": content_rel,
        "deploy_root": str(deploy_root),
    }


def _write_website_state_entry(payload):
    _update_website_state(str(payload.get("name") or payload.get("form_name") or "website"), payload)


def _website_stack_label(website_kind):
    return {
        "flutter": "Flutter / Static Website",
        "next-export": "Next Export / Static Website",
        "nextjs": "Next.js Website",
        "php": "PHP Website",
        "static": "Static Website",
        "auto": "Static Website",
    }.get(str(website_kind or "auto").strip().lower(), "Static Website")


def _cleanup_website_artifacts(runtime_name, remove_files=True):
    payload = _website_state_payload(runtime_name)
    deploy_root = Path(str(payload.get("deploy_root") or "")).expanduser() if payload else None
    image_name = str(payload.get("image_name") or "").strip() if payload else ""
    if remove_files and deploy_root and str(deploy_root).strip():
        shutil.rmtree(deploy_root, ignore_errors=True)
    if image_name and command_exists("docker"):
        run_capture(["docker", "rmi", "-f", image_name], timeout=30)
    _cleanup_website_state_entry(runtime_name)


def _website_service_items():
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return []
    items = []
    for payload in deployments.values():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        port_text = str(payload.get("port") or "").strip()
        url = str(payload.get("url") or "").strip()
        bind_ip = str(payload.get("bind_ip") or "").strip()
        runtime_target = str(payload.get("target") or "").strip().lower()
        running = False
        sub_status = ""
        autostart = False
        item_kind = "service"
        if runtime_target == "docker":
            item_kind = "docker"
            details = _get_docker_container_details(name)
            sub_status = str(details.get("state") or "")
            running = sub_status == "running"
            autostart = str(details.get("restart_policy") or "") in ("always", "unless-stopped")
        elif runtime_target == "iis":
            item_kind = "iis_site"
            rc, out = run_capture(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Import-Module WebAdministration; $site=Get-Website -Name '{name}' -ErrorAction SilentlyContinue; if($site){{Write-Output ($site.State + '|' + [string]$site.serverAutoStart + '|' + [string]$site.PhysicalPath)}}",
                ],
                timeout=20,
            )
            physical_path = str(payload.get("deploy_root") or "")
            if rc == 0 and out:
                parts = str(out).strip().split("|", 2)
                sub_status = parts[0] if parts else ""
                running = sub_status.lower() == "started"
                autostart = len(parts) > 1 and parts[1].strip().lower() == "true"
                if len(parts) > 2 and parts[2].strip():
                    physical_path = parts[2].strip()
        else:
            physical_path = str(payload.get("deploy_root") or "")
            if os.name == "nt":
                item_kind = "service"
                state_text, start_mode = _windows_service_state(name)
                sub_status = state_text
                running = state_text.lower() == "running"
                autostart = start_mode.lower() == "auto"
            elif platform.system() == "Darwin":
                item_kind = "website_launchd"
                plist_name = str(payload.get("plist_name") or "").strip()
                rc, out = run_capture(["launchctl", "print", f"system/{plist_name}"], timeout=20)
                running = rc == 0
                sub_status = "running" if running else "stopped"
                autostart = bool(plist_name)
            else:
                item_kind = "service"
                svc = _linux_systemd_unit_status(name)
                sub_status = str(svc.get("active") or "")
                running = bool(svc.get("running"))
                autostart = bool(svc.get("autostart"))
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        https_port_text = str(payload.get("https_port") or "").strip()
        if https_port_text.isdigit() and int(https_port_text) > 0:
            ports.append({"port": int(https_port_text), "protocol": "tcp"})
        https_url = str(payload.get("https_url") or "").strip()
        # Use saved urls array if available (includes both domain and IP URLs)
        saved_urls = payload.get("urls")
        if isinstance(saved_urls, list) and saved_urls:
            all_urls = [str(u) for u in saved_urls if u]
        else:
            all_urls = []
            if url:
                all_urls.append(url)
            if https_url:
                all_urls.append(https_url)
        items.append({
            "kind": item_kind,
            "name": name,
            "display_name": f"{str(payload.get('stack_label') or 'Website').strip()} - {physical_path or '-'}",
            "status": "running" if running else "stopped",
            "sub_status": sub_status or ("running" if running else "stopped"),
            "autostart": autostart,
            "platform": "windows" if os.name == "nt" else "unknown",
            "urls": all_urls,
            "ports": ports,
            "manageable": True,
            "deletable": True,
            "website": True,
            "target_page": "website",
            "form_name": str(payload.get("form_name") or name),
            "project_path": str(payload.get("deploy_root") or payload.get("source_root") or ""),
            "deploy_root": str(payload.get("deploy_root") or ""),
            "host": bind_ip if bind_ip and bind_ip != "*" else str(payload.get("host") or ""),
            "port_value": port_text,
            "https_port_value": https_port_text if https_port_text.isdigit() and int(https_port_text) > 0 else "",
            "stack_label": str(payload.get("stack_label") or "Static Website"),
            "publish_rel": str(payload.get("publish_rel") or "."),
            "kind_value": str(payload.get("website_kind") or "auto"),
            "target_value": runtime_target or "service",
        })
    return items


def get_website_info():
    items = _website_service_items()
    return {
        "installed": len(items) > 0,
        "count": len(items),
        "sites": items,
    }


def _write_windows_website_service_file(deploy_root: Path, runtime_name: str, bind_ip: str, port: int):
    service_script = deploy_root / "serverinstaller_static_website_service.py"
    service_script.write_text(
        "\n".join([
            "import os",
            "import sys",
            "import threading",
            "import socketserver",
            "import http.server",
            "import win32event",
            "import win32service",
            "import win32serviceutil",
            "import servicemanager",
            "",
            f"SERVICE_NAME = {runtime_name!r}",
            f"ROOT_DIR = {str(deploy_root)!r}",
            f"BIND_HOST = {('0.0.0.0' if bind_ip in ('', '*') else bind_ip)!r}",
            f"PORT = {int(port)}",
            "",
            "class ReusableTCPServer(socketserver.ThreadingTCPServer):",
            "    allow_reuse_address = True",
            "",
            "class StaticWebsiteHandler(http.server.SimpleHTTPRequestHandler):",
            "    def __init__(self, *args, **kwargs):",
            "        super().__init__(*args, directory=ROOT_DIR, **kwargs)",
            "",
            "class StaticWebsiteService(win32serviceutil.ServiceFramework):",
            "    _svc_name_ = SERVICE_NAME",
            "    _svc_display_name_ = SERVICE_NAME",
            "    _svc_description_ = 'Server Installer managed static website service'",
            "",
            "    def __init__(self, args):",
            "        win32serviceutil.ServiceFramework.__init__(self, args)",
            "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
            "        self.httpd = None",
            "",
            "    def SvcStop(self):",
            "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
            "        if self.httpd is not None:",
            "            try:",
            "                self.httpd.shutdown()",
            "            except Exception:",
            "                pass",
            "            try:",
            "                self.httpd.server_close()",
            "            except Exception:",
            "                pass",
            "        win32event.SetEvent(self.stop_event)",
            "",
            "    def SvcDoRun(self):",
            "        os.chdir(ROOT_DIR)",
            "        self.httpd = ReusableTCPServer((BIND_HOST, PORT), StaticWebsiteHandler)",
            "        worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)",
            "        worker.start()",
            "        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)",
            "",
            "if __name__ == '__main__':",
            "    if len(sys.argv) == 1:",
            "        servicemanager.Initialize()",
            "        servicemanager.PrepareToHostSingle(StaticWebsiteService)",
            "        servicemanager.StartServiceCtrlDispatcher()",
            "    else:",
            "        win32serviceutil.HandleCommandLine(StaticWebsiteService)",
            "",
        ]),
        encoding="utf-8",
    )
    return service_script


def _find_windows_command(preferred_names):
    for name in preferred_names:
        path_value = shutil.which(name)
        if path_value:
            return path_value
    return preferred_names[0] if preferred_names else ""


def _website_node_start_command(deploy, host_override=""):
    host_value = str(host_override or deploy["bind_ip"] or "").strip()
    host_value = "0.0.0.0" if host_value in ("", "*") else host_value
    port_value = int(deploy["site_port"])
    return {
        "workdir": str(Path(deploy["deploy_root"]).resolve()),
        "install_cmd_unix": "npm install",
        "build_cmd_unix": "npm run build",
        "start_cmd_unix": f"npm run start -- --hostname {shlex.quote(host_value)} --port {port_value}",
        "npm_cmd_windows": _find_windows_command(["npm.cmd", "npm.exe", "npm"]),
        "node_cmd_windows": _find_windows_command(["node.exe", "node"]),
        "host_value": host_value,
        "port_value": port_value,
    }


def _website_php_start_command(deploy, host_override=""):
    host_value = str(host_override or deploy["bind_ip"] or "").strip()
    host_value = "0.0.0.0" if host_value in ("", "*") else host_value
    port_value = int(deploy["site_port"])
    public_rel = str(deploy.get("content_rel") or ".").strip()
    public_dir = Path(deploy["deploy_root"]) / public_rel if public_rel not in ("", ".") else Path(deploy["deploy_root"])
    return {
        "workdir": str(Path(deploy["deploy_root"]).resolve()),
        "php_cmd_windows": _find_windows_command(["php.exe", "php"]),
        "php_cmd_unix": shutil.which("php") or "php",
        "host_value": host_value,
        "port_value": port_value,
        "public_dir": str(public_dir.resolve()),
    }


def _prepare_nextjs_project(deploy, live_cb=None):
    cfg = _website_node_start_command(deploy)
    workdir = cfg["workdir"]
    if os.name == "nt":
        npm_cmd = cfg["npm_cmd_windows"]
        code, output = run_process([npm_cmd, "install"], live_cb=live_cb)
        if code != 0:
            return code, output or "npm install failed."
        code, output = run_process([npm_cmd, "run", "build"], live_cb=live_cb)
        if code != 0:
            return code, output or "npm run build failed."
        return 0, ""
    shell_cmd = "/bin/sh"
    install_build = f"cd {shlex.quote(workdir)} && npm install && npm run build"
    code, output = run_process([shell_cmd, "-lc", install_build], live_cb=live_cb)
    return code, output


def run_windows_website_service(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Website OS service deployment is only available on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    python_executable = resolve_windows_python()
    venv_dir = Path(deploy["deploy_root"]) / ".runtime"
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    rc, out = run_capture([python_executable, "-m", "venv", str(venv_dir)], timeout=240)
    if rc != 0:
        return 1, out or "Failed to create Windows runtime environment for website service."
    venv_python = _python_api_venv_python(venv_dir)
    rc, out = run_capture([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "pywin32"], timeout=600)
    if rc != 0:
        return 1, out or "Failed to install Windows service runtime dependencies."
    rc_post, out_post = run_capture([venv_python, "-m", "pywin32_postinstall", "-install"], timeout=180)
    if rc_post != 0 and live_cb:
        text = str(out_post or "").strip()
        if "No module named pywin32_postinstall" in text:
            live_cb("pywin32_postinstall is not available in this pywin32 build; continuing with direct service host setup.\n")
        else:
            live_cb((text or "pywin32 postinstall returned a non-zero exit code.") + "\n")
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    if runtime == "static":
        service_script = _write_windows_website_service_file(Path(deploy["deploy_root"]), deploy["runtime_name"], deploy["bind_ip"], deploy["site_port"])
    elif runtime == "node":
        node_cfg = _website_node_start_command(deploy)
        code, output = _prepare_nextjs_project(deploy, live_cb=live_cb)
        if code != 0:
            return code, output
        service_script = Path(deploy["deploy_root"]) / "serverinstaller_nextjs_service.py"
        service_script.write_text(
            "\n".join([
                "import os",
                "import subprocess",
                "import sys",
                "import time",
                "import win32event",
                "import win32service",
                "import win32serviceutil",
                "import servicemanager",
                "",
                f"SERVICE_NAME = {deploy['runtime_name']!r}",
                f"WORKDIR = {node_cfg['workdir']!r}",
                f"NPM_CMD = {node_cfg['npm_cmd_windows']!r}",
                f"HOST_VALUE = {node_cfg['host_value']!r}",
                f"PORT_VALUE = {node_cfg['port_value']!r}",
                "",
                "class NextWebsiteService(win32serviceutil.ServiceFramework):",
                "    _svc_name_ = SERVICE_NAME",
                "    _svc_display_name_ = SERVICE_NAME",
                "    _svc_description_ = 'Server Installer managed Next.js website service'",
                "",
                "    def __init__(self, args):",
                "        win32serviceutil.ServiceFramework.__init__(self, args)",
                "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
                "        self.proc = None",
                "",
                "    def SvcStop(self):",
                "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
                "        if self.proc is not None and self.proc.poll() is None:",
                "            try:",
                "                self.proc.terminate()",
                "                self.proc.wait(timeout=20)",
                "            except Exception:",
                "                pass",
                "        win32event.SetEvent(self.stop_event)",
                "",
                "    def SvcDoRun(self):",
                "        os.chdir(WORKDIR)",
                "        self.proc = subprocess.Popen([NPM_CMD, 'run', 'start', '--', '--hostname', HOST_VALUE, '--port', str(PORT_VALUE)], cwd=WORKDIR)",
                "        while win32event.WaitForSingleObject(self.stop_event, 1000) != win32event.WAIT_OBJECT_0:",
                "            if self.proc.poll() is not None:",
                "                raise RuntimeError(f'Next.js process exited with code {self.proc.returncode}.')",
                "",
                "if __name__ == '__main__':",
                "    if len(sys.argv) == 1:",
                "        servicemanager.Initialize()",
                "        servicemanager.PrepareToHostSingle(NextWebsiteService)",
                "        servicemanager.StartServiceCtrlDispatcher()",
                "    else:",
                "        win32serviceutil.HandleCommandLine(NextWebsiteService)",
                "",
            ]),
            encoding="utf-8",
        )
    elif runtime == "php":
        php_cfg = _website_php_start_command(deploy)
        service_script = Path(deploy["deploy_root"]) / "serverinstaller_php_service.py"
        service_script.write_text(
            "\n".join([
                "import os",
                "import subprocess",
                "import sys",
                "import win32event",
                "import win32service",
                "import win32serviceutil",
                "import servicemanager",
                "",
                f"SERVICE_NAME = {deploy['runtime_name']!r}",
                f"WORKDIR = {php_cfg['workdir']!r}",
                f"PHP_CMD = {php_cfg['php_cmd_windows']!r}",
                f"PUBLIC_DIR = {php_cfg['public_dir']!r}",
                f"HOST_VALUE = {php_cfg['host_value']!r}",
                f"PORT_VALUE = {php_cfg['port_value']!r}",
                "",
                "class PhpWebsiteService(win32serviceutil.ServiceFramework):",
                "    _svc_name_ = SERVICE_NAME",
                "    _svc_display_name_ = SERVICE_NAME",
                "    _svc_description_ = 'Server Installer managed PHP website service'",
                "",
                "    def __init__(self, args):",
                "        win32serviceutil.ServiceFramework.__init__(self, args)",
                "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
                "        self.proc = None",
                "",
                "    def SvcStop(self):",
                "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
                "        if self.proc is not None and self.proc.poll() is None:",
                "            try:",
                "                self.proc.terminate()",
                "                self.proc.wait(timeout=20)",
                "            except Exception:",
                "                pass",
                "        win32event.SetEvent(self.stop_event)",
                "",
                "    def SvcDoRun(self):",
                "        os.chdir(WORKDIR)",
                "        self.proc = subprocess.Popen([PHP_CMD, '-S', f'{HOST_VALUE}:{PORT_VALUE}', '-t', PUBLIC_DIR], cwd=WORKDIR)",
                "        while win32event.WaitForSingleObject(self.stop_event, 1000) != win32event.WAIT_OBJECT_0:",
                "            if self.proc.poll() is not None:",
                "                raise RuntimeError(f'PHP process exited with code {self.proc.returncode}.')",
                "",
                "if __name__ == '__main__':",
                "    if len(sys.argv) == 1:",
                "        servicemanager.Initialize()",
                "        servicemanager.PrepareToHostSingle(PhpWebsiteService)",
                "        servicemanager.StartServiceCtrlDispatcher()",
                "    else:",
                "        win32serviceutil.HandleCommandLine(PhpWebsiteService)",
                "",
            ]),
            encoding="utf-8",
        )
    else:
        return 1, f"Unsupported website runtime '{runtime}' for Windows service deployment."
    run_capture(["sc.exe", "stop", deploy["runtime_name"]], timeout=30)
    run_capture([venv_python, str(service_script), "remove"], timeout=60)
    rc, out = run_capture([venv_python, str(service_script), "--startup", "auto", "install"], timeout=180)
    service_started = False
    if rc == 0:
        rc2, out2 = run_capture([venv_python, str(service_script), "start"], timeout=120)
        if rc2 == 0:
            # Verify service is actually running
            import time
            time.sleep(2)
            state_text, _ = _windows_service_state(deploy["runtime_name"])
            service_started = state_text.lower() == "running"
    if not service_started:
        # Fallback: run as a background process (pywin32 service framework often fails)
        if live_cb:
            live_cb("Windows service registration failed or didn't start. Launching as background process...\n")
        import subprocess
        subprocess.Popen(
            [venv_python, str(service_script), "--foreground"] if runtime != "static" else [venv_python, "-m", "http.server", str(deploy["site_port"]), "--bind", "0.0.0.0" if deploy["bind_ip"] in ("", "*") else deploy["bind_ip"], "--directory", str(deploy["deploy_root"])],
            cwd=str(deploy["deploy_root"]),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if live_cb:
            live_cb("Website started as background process.\n")
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    _write_website_state_entry({
        "name": deploy["runtime_name"],
        "form_name": deploy["site_name"],
        "kind": "service",
        "target": "service",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    return 0, f"Website OS service deployed.\nService: {deploy['runtime_name']}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_unix_website_service(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Unix website service deployment is not available on Windows hosts."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    bind_host = "0.0.0.0" if deploy["bind_ip"] in ("", "*") else deploy["bind_ip"]
    python_executable = resolve_unix_python()
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    prefix = _sudo_prefix()
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    if runtime == "static":
        runner_script = Path(deploy["deploy_root"]) / "serve_static_site.py"
        runner_script.write_text(
            "\n".join([
                "import functools",
                "import http.server",
                "import socketserver",
                "",
                f"ROOT_DIR = {str(Path(deploy['deploy_root']).resolve())!r}",
                f"BIND_HOST = {bind_host!r}",
                f"PORT = {int(deploy['site_port'])}",
                "",
                "class ReusableTCPServer(socketserver.ThreadingTCPServer):",
                "    allow_reuse_address = True",
                "",
                "handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT_DIR)",
                "with ReusableTCPServer((BIND_HOST, PORT), handler) as httpd:",
                "    httpd.serve_forever()",
                "",
            ]),
            encoding="utf-8",
        )
        exec_start = f"{shlex.quote(str(python_executable))} {shlex.quote(str(runner_script))}"
    elif runtime == "node":
        node_cfg = _website_node_start_command(deploy, host_override=bind_host)
        code, output = _prepare_nextjs_project(deploy, live_cb=live_cb)
        if code != 0:
            return code, output
        exec_start = f"/bin/sh -lc {shlex.quote(node_cfg['start_cmd_unix'])}"
    elif runtime == "php":
        php_cfg = _website_php_start_command(deploy, host_override=bind_host)
        exec_start = f"{shlex.quote(str(php_cfg['php_cmd_unix']))} -S {bind_host}:{int(deploy['site_port'])} -t {shlex.quote(str(php_cfg['public_dir']))}"
    else:
        return 1, f"Unsupported website runtime '{runtime}' for OS service deployment."
    if platform.system() == "Darwin":
        plist_name = f"com.serverinstaller.website.{deploy['runtime_name']}"
        plist_path = Path("/Library/LaunchDaemons") / f"{plist_name}.plist"
        plist_temp = Path(deploy["deploy_root"]) / f"{plist_name}.plist"
        plist_temp.write_text(
            "\n".join([
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0">',
                "<dict>",
                f"  <key>Label</key><string>{plist_name}</string>",
                "  <key>ProgramArguments</key>",
                "  <array>",
                *([f"    <string>{part}</string>" for part in ([str(python_executable), str(runner_script)] if runtime == "static" else (["/bin/sh", "-lc", node_cfg['install_cmd_unix'] + ' && ' + node_cfg['build_cmd_unix'] + ' && ' + node_cfg['start_cmd_unix']] if runtime == "node" else [str(php_cfg['php_cmd_unix']), "-S", f"{bind_host}:{int(deploy['site_port'])}", "-t", str(php_cfg['public_dir'])]))]),
                "  </array>",
                f"  <key>WorkingDirectory</key><string>{str(Path(deploy['deploy_root']).resolve())}</string>",
                "  <key>RunAtLoad</key><true/>",
                "  <key>KeepAlive</key><true/>",
                "  <key>StandardOutPath</key><string>/tmp/serverinstaller-website.log</string>",
                "  <key>StandardErrorPath</key><string>/tmp/serverinstaller-website.log</string>",
                "</dict>",
                "</plist>",
                "",
            ]),
            encoding="utf-8",
        )
        run_capture(prefix + ["launchctl", "bootout", "system", str(plist_path)], timeout=30)
        run_capture(prefix + ["cp", str(plist_temp), str(plist_path)], timeout=30)
        rc, out = run_capture(prefix + ["launchctl", "bootstrap", "system", str(plist_path)], timeout=60)
        if rc != 0:
            return 1, out or f"Failed to bootstrap launchd website '{plist_name}'."
        _write_website_state_entry({
            "name": deploy["runtime_name"],
            "form_name": deploy["site_name"],
            "kind": "website_launchd",
            "target": "service",
            "website_kind": deploy["website_kind"],
            "stack_label": deploy["stack_label"],
            "url": url,
            "bind_ip": deploy["bind_ip"],
            "host": deploy["host"],
            "port": deploy["site_port"],
            "deploy_root": deploy["deploy_root"],
            "source_root": deploy["source_root"],
            "publish_root": deploy["publish_root"],
            "publish_rel": deploy["publish_rel"],
            "plist_name": plist_name,
        })
        manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
        return 0, f"Website launchd service deployed.\nService: {plist_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"
    unit_name = f"{deploy['runtime_name']}.service"
    unit_temp = Path(deploy["deploy_root"]) / unit_name
    unit_temp.write_text(
        "\n".join([
            "[Unit]",
            f"Description={deploy['site_name']}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={str(Path(deploy['deploy_root']).resolve())}",
            f"ExecStart={exec_start}",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
    run_capture(prefix + ["cp", str(unit_temp), f"/etc/systemd/system/{unit_name}"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    rc, out = run_capture(prefix + ["systemctl", "enable", "--now", unit_name], timeout=60)
    if rc != 0:
        return 1, out or f"Failed to enable website service '{unit_name}'."
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    _write_website_state_entry({
        "name": unit_name,
        "form_name": deploy["site_name"],
        "kind": "service",
        "target": "service",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    return 0, f"Website OS service deployed.\nService: {unit_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_website_docker(form=None, live_cb=None):
    form = form or {}
    if not command_exists("docker"):
        return 1, "Docker is not available on this host."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    dockerfile = Path(deploy["deploy_root"]) / "Dockerfile"
    if runtime == "static":
        dockerfile.write_text(
            "\n".join([
                "FROM nginx:alpine",
                "WORKDIR /usr/share/nginx/html",
                "RUN rm -rf /usr/share/nginx/html/*",
                "COPY ./ /usr/share/nginx/html/",
                "EXPOSE 80",
                'CMD ["nginx", "-g", "daemon off;"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = 80
    elif runtime == "node":
        dockerfile.write_text(
            "\n".join([
                "FROM node:20-alpine",
                "WORKDIR /app",
                "COPY . ./",
                "RUN npm install",
                "RUN npm run build",
                f"EXPOSE {int(deploy['site_port'])}",
                f'CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "{int(deploy["site_port"])}"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = int(deploy["site_port"])
    elif runtime == "php":
        public_rel = str(deploy.get("content_rel") or ".").strip()
        php_root = f"/app/{public_rel}" if public_rel not in ("", ".") else "/app"
        dockerfile.write_text(
            "\n".join([
                "FROM php:8.2-cli-alpine",
                "WORKDIR /app",
                "COPY . /app/",
                f"EXPOSE {int(deploy['site_port'])}",
                f'CMD ["php", "-S", "0.0.0.0:{int(deploy["site_port"])}", "-t", "{php_root}"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = int(deploy["site_port"])
    else:
        return 1, f"Unsupported website runtime '{runtime}' for Docker deployment."
    image_name = f"{deploy['runtime_name']}-image"
    container_name = deploy["runtime_name"]
    run_capture(["docker", "rm", "-f", container_name], timeout=30)
    run_capture(["docker", "rmi", "-f", image_name], timeout=30)
    code, output = run_process(["docker", "build", "-t", image_name, str(deploy["deploy_root"])], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."
    publish_binding = f"{deploy['site_port']}:{container_port}"
    bind_host = str(deploy["bind_ip"] or "").strip()
    if bind_host and bind_host not in ("*", "0.0.0.0"):
        publish_binding = f"{bind_host}:{deploy['site_port']}:{container_port}"
    code, output = run_process(
        [
            "docker", "run", "-d",
            "--restart", "unless-stopped",
            "--name", container_name,
            "--label", "com.serverinstaller.website=true",
            "-p", publish_binding,
            image_name,
        ],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    _write_website_state_entry({
        "name": container_name,
        "form_name": deploy["site_name"],
        "kind": "docker",
        "target": "docker",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
        "image_name": image_name,
    })
    return 0, f"Website Docker deployment completed.\nContainer: {container_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_windows_website_iis(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Website IIS deployment is currently available on Windows hosts only."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    iis_info = get_iis_info()
    if not iis_info.get("installed"):
        return 1, "IIS is not installed. Use the DotNet IIS setup page first."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    https_port = deploy.get("https_port", 0)
    if live_cb:
        live_cb(f"Deploying IIS website '{deploy['site_name']}' from {deploy['publish_root']}\n")
        if https_port:
            live_cb(f"HTTPS port: {https_port}\n")
    ssl_cert_name = deploy.get("ssl_cert_name", "self_signed")
    bind_ip = deploy['bind_ip'] if deploy['bind_ip'] != '*' else '*'
    domain = deploy.get("domain", "").strip()
    dns_name = domain or deploy['host']

    # Build HTTPS binding commands if an HTTPS port was specified
    http_port = deploy["site_port"]
    https_ps_lines = []
    if https_port:
        # Include domain in cert if set
        cert_dns_names = [dns_name, "localhost", "127.0.0.1"]
        if domain and domain not in cert_dns_names:
            cert_dns_names.insert(0, domain)
        dns_list = ",".join([f"'{d}'" for d in cert_dns_names])
        https_ps_lines = [
            f"New-WebBinding -Name $siteName -Protocol 'https' -Port {int(https_port)} -IPAddress $ip -ErrorAction SilentlyContinue | Out-Null",
            f"$cert = New-SelfSignedCertificate -DnsName @({dns_list}) -CertStoreLocation 'cert:\\LocalMachine\\My' -FriendlyName ('ServerInstaller Website ' + $siteName)",
            "$bindingPath = ($(if ($ip -eq '*') { '0.0.0.0' } else { $ip })) + '!' + " + str(int(https_port)),
            "if (Test-Path ('IIS:\\SslBindings\\' + $bindingPath)) { Remove-Item ('IIS:\\SslBindings\\' + $bindingPath) -Force -ErrorAction SilentlyContinue }",
            "New-Item ('IIS:\\SslBindings\\' + $bindingPath) -Thumbprint $cert.Thumbprint -SSLFlags 0 | Out-Null",
        ]

    # When only HTTPS is set (no HTTP port), create the site on the HTTPS port with SSL;
    # when only HTTP is set, create normally; when both, create on HTTP and add HTTPS binding.
    initial_port = http_port if http_port else https_port
    initial_protocol_args = "-Ssl" if (not http_port and https_port) else ""

    # Create site with plain port bindings (NO host headers - responds to any hostname)
    # Domain access works via DNS/hosts file, not IIS host headers
    ps_lines = [
        "Import-Module WebAdministration",
        f"$siteName = {_ps_single_quote(deploy['site_name'])}",
        f"$appPool = {_ps_single_quote(deploy['site_name'])}",
        f"$physicalPath = {_ps_single_quote(deploy['deploy_root'])}",
        f"$ip = {_ps_single_quote(bind_ip)}",
        f"$port = {int(initial_port)}",
        # Remove existing site completely
        "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
        "if (Test-Path ('IIS:\\AppPools\\' + $appPool)) { Stop-WebAppPool -Name $appPool -ErrorAction SilentlyContinue | Out-Null; Remove-WebAppPool -Name $appPool -ErrorAction SilentlyContinue | Out-Null }",
        # Create fresh app pool and site
        "New-WebAppPool -Name $appPool | Out-Null",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name managedRuntimeVersion -Value ''",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name processModel.identityType -Value 4",
        f"New-Website -Name $siteName -PhysicalPath $physicalPath -Port $port -IPAddress $ip {initial_protocol_args} -ApplicationPool $appPool | Out-Null".replace("  ", " "),
        *(https_ps_lines if http_port else []),
    ]
    ps_lines.append("Start-Website -Name $siteName | Out-Null")

    # Add domain to hosts file so it resolves on this machine
    if domain:
        ip_for_hosts = bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host()
        _add_hosts_entry(domain, ip_for_hosts, live_cb=live_cb)

    ps = "\n".join(ps_lines)
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=180)
    if rc != 0:
        return 1, out or f"Failed to create IIS website '{deploy['site_name']}'."
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
    if https_port:
        manage_firewall_port("open", https_port, "tcp", host=deploy.get("host"))

    # Build URLs (use domain if set, otherwise IP)
    url_host = deploy['host']
    urls = []
    if http_port:
        http_url = f"http://{url_host}" if http_port == 80 else f"http://{url_host}:{http_port}"
        urls.append(http_url)
    else:
        http_url = ""
    if https_port:
        https_url = f"https://{url_host}" if https_port == 443 else f"https://{url_host}:{https_port}"
        urls.append(https_url)
    else:
        https_url = ""
    # Also build IP-based URLs for display if domain is set
    ip_host = bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host()
    if domain and ip_host != domain:
        if http_port:
            ip_http = f"http://{ip_host}" if http_port == 80 else f"http://{ip_host}:{http_port}"
            urls.append(ip_http)
        if https_port:
            ip_https = f"https://{ip_host}" if https_port == 443 else f"https://{ip_host}:{https_port}"
            urls.append(ip_https)
    url = urls[0] if urls else ""

    _write_website_state_entry({
        "name": deploy["site_name"],
        "form_name": deploy["site_name"],
        "kind": "iis_site",
        "target": "iis",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "urls": urls,
        "https_url": https_url,
        "bind_ip": deploy["bind_ip"],
        "domain": domain,
        "host": deploy["host"],
        "port": http_port,
        "https_port": https_port,
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    result_lines = [f"Website IIS deployment completed.", f"Site: {deploy['site_name']}"]
    if domain:
        result_lines.append(f"Domain: {domain}")
    for u in urls:
        result_lines.append(f"URL: {u}")
    result_lines.append(f"Content: {deploy['publish_root']}")
    if domain:
        result_lines.append(f"\nDomain '{domain}' added to this server's hosts file.")
        result_lines.append(f"To access from other devices, add this to their hosts file:")
        if os.name == "nt":
            result_lines.append(f"  Windows: C:\\Windows\\System32\\drivers\\etc\\hosts")
        else:
            result_lines.append(f"  Linux/Mac: /etc/hosts")
        result_lines.append(f"  {ip_host}  {domain}")
    return 0, "\n".join(result_lines) + "\n"


def run_website_deploy(form=None, live_cb=None):
    form = form or {}
    target = (form.get("WEBSITE_TARGET", ["service"])[0] or "service").strip().lower()
    engine = (form.get("WEBSITE_ENGINE", [""])[0] or "").strip().lower()
    # Map engine → target if engine is specified but target is generic
    if engine and engine != target:
        target = engine if engine in ("docker", "iis", "nginx", "nodejs", "kubernetes", "pm2") else target
        form["WEBSITE_TARGET"] = [target]
    if target == "iis":
        return run_windows_website_iis(form=form, live_cb=live_cb)
    if target == "docker":
        return run_website_docker(form=form, live_cb=live_cb)
    if target == "kubernetes":
        return _run_website_kubernetes(form=form, live_cb=live_cb)
    if target == "nginx":
        return _run_website_nginx(form=form, live_cb=live_cb)
    if target == "nodejs":
        return _run_website_nodejs(form=form, live_cb=live_cb)
    if target == "pm2":
        return _run_website_pm2(form=form, live_cb=live_cb)
    if os.name == "nt":
        return run_windows_website_service(form=form, live_cb=live_cb)
    return run_unix_website_service(form=form, live_cb=live_cb)


def _run_website_nginx(form=None, live_cb=None):
    """Deploy website using Nginx."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to Nginx: {deploy['site_name']}\n")
    # Ensure nginx is installed
    if not command_exists("nginx"):
        if live_cb:
            live_cb("Nginx not found. Installing...\n")
        code, msg = _install_website_engine("nginx", live_cb=live_cb)
        if code != 0:
            return code, msg
    site_conf_name = f"serverinstaller-{deploy['runtime_name']}"
    content_root = deploy["publish_root"]
    port = deploy["site_port"] or 80
    server_name = deploy.get("domain") or "_"
    # Build nginx config
    conf_lines = [
        f"server {{",
        f"    listen {port};",
        f"    server_name {server_name};",
        f"    root {content_root};",
        f"    index index.html index.htm index.php;",
        f"",
    ]
    if deploy.get("runtime") == "php":
        conf_lines += [
            f"    location ~ \\.php$ {{",
            f"        fastcgi_pass unix:/run/php/php-fpm.sock;",
            f"        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;",
            f"        include fastcgi_params;",
            f"    }}",
        ]
    conf_lines += [
        f"    location / {{",
        f"        try_files $uri $uri/ /index.html =404;",
        f"    }}",
        f"}}",
    ]
    conf_text = "\n".join(conf_lines) + "\n"
    # Write config
    nginx_sites = Path("/etc/nginx/sites-enabled")
    nginx_conf_d = Path("/etc/nginx/conf.d")
    if nginx_sites.exists():
        conf_path = nginx_sites / f"{site_conf_name}.conf"
    elif nginx_conf_d.exists():
        conf_path = nginx_conf_d / f"{site_conf_name}.conf"
    else:
        return 1, "Cannot find /etc/nginx/sites-enabled or /etc/nginx/conf.d."
    conf_path.write_text(conf_text, encoding="utf-8")
    if live_cb:
        live_cb(f"Wrote Nginx config to {conf_path}\n")
    # Test and reload
    rc, out = run_capture(["nginx", "-t"], timeout=15)
    if rc != 0:
        return 1, f"Nginx config test failed:\n{out}"
    rc, out = run_capture(["nginx", "-s", "reload"], timeout=15)
    if rc != 0:
        if command_exists("systemctl"):
            rc, out = run_capture(["systemctl", "reload", "nginx"], timeout=15)
    manage_firewall_port("open", str(port), "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}:{port}"
    _write_website_state_entry({
        "name": deploy["runtime_name"], "form_name": deploy["site_name"],
        "kind": "website_nginx", "target": "nginx",
        "website_kind": deploy["website_kind"], "stack_label": deploy["stack_label"],
        "url": url, "bind_ip": deploy["bind_ip"], "host": deploy["host"],
        "port": port, "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"], "publish_root": deploy["publish_root"],
        "conf_path": str(conf_path),
    })
    return 0, f"Website deployed to Nginx.\nConfig: {conf_path}\nURL: {url}\nContent: {content_root}\n"


def _run_website_nodejs(form=None, live_cb=None):
    """Deploy website using Node.js (serve or next start)."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to Node.js: {deploy['site_name']}\n")
    if not command_exists("node"):
        if live_cb:
            live_cb("Node.js not found. Installing...\n")
        code, msg = _install_website_engine("nodejs", live_cb=live_cb)
        if code != 0:
            return code, msg
    # For Node.js, fall through to the OS service deployer which already handles node runtime
    form["WEBSITE_TARGET"] = ["service"]
    if os.name == "nt":
        return run_windows_website_service(form=form, live_cb=live_cb)
    return run_unix_website_service(form=form, live_cb=live_cb)


def _run_website_pm2(form=None, live_cb=None):
    """Deploy website using PM2 process manager."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to PM2: {deploy['site_name']}\n")
    if not command_exists("pm2"):
        if live_cb:
            live_cb("PM2 not found. Installing...\n")
        code, msg = _install_website_engine("pm2", live_cb=live_cb)
        if code != 0:
            return code, msg
    port = deploy["site_port"] or 3000
    app_name = deploy["runtime_name"]
    content_root = deploy["publish_root"]
    # Determine start command
    if deploy.get("runtime") == "node" and deploy.get("website_kind") == "nextjs":
        # Next.js — npm start
        if live_cb:
            live_cb("Installing npm dependencies...\n")
        try:
            subprocess.run(["npm", "install"], cwd=content_root, timeout=300, capture_output=True)
            subprocess.run(["npm", "run", "build"], cwd=content_root, timeout=300, capture_output=True)
        except Exception:
            pass
        start_script = f"PORT={port} npm start"
    else:
        # Static — use npx serve
        if not command_exists("serve"):
            run_capture(["npm", "install", "-g", "serve"], timeout=60)
        start_script = f"serve -s {content_root} -l {port}"
    # Stop existing PM2 process with same name
    run_capture(["pm2", "delete", app_name], timeout=15)
    # Start with PM2
    rc, out = run_capture(["pm2", "start", "--name", app_name, "--", "bash", "-c", start_script], timeout=60)
    if rc != 0:
        # Try alternative: use pm2 ecosystem file
        ecosystem = {
            "name": app_name,
            "script": "npx",
            "args": f"serve -s {content_root} -l {port}" if deploy.get("runtime") != "node" else "npm start",
            "cwd": content_root,
            "env": {"PORT": str(port)},
        }
        eco_path = Path(content_root) / "ecosystem.config.js"
        eco_path.write_text(f"module.exports = {{ apps: [{json.dumps(ecosystem)}] }};", encoding="utf-8")
        rc, out = run_capture(["pm2", "start", str(eco_path)], timeout=60)
    if rc == 0:
        run_capture(["pm2", "save"], timeout=15)
    manage_firewall_port("open", str(port), "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}:{port}"
    _write_website_state_entry({
        "name": deploy["runtime_name"], "form_name": deploy["site_name"],
        "kind": "website_pm2", "target": "pm2",
        "website_kind": deploy["website_kind"], "stack_label": deploy["stack_label"],
        "url": url, "bind_ip": deploy["bind_ip"], "host": deploy["host"],
        "port": port, "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"], "publish_root": deploy["publish_root"],
    })
    return rc, f"Website deployed to PM2.\nApp: {app_name}\nURL: {url}\nContent: {content_root}\n" if rc == 0 else f"PM2 deployment failed:\n{out}"


def _run_website_kubernetes(form=None, live_cb=None):
    """Deploy website to Kubernetes (K3s)."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to Kubernetes: {deploy['site_name']}\n")
    kubectl = "kubectl" if command_exists("kubectl") else "k3s kubectl" if command_exists("k3s") else None
    if not kubectl:
        code, msg = _install_website_engine("kubernetes", live_cb=live_cb)
        if code != 0:
            return code, msg
        kubectl = "kubectl" if command_exists("kubectl") else "k3s kubectl"
    # Build Docker image first (K8s needs an image)
    if not command_exists("docker"):
        return 1, "Kubernetes deployment requires Docker to build images. Install Docker first."
    app_name = deploy["runtime_name"].replace("_", "-").lower()
    port = deploy["site_port"] or 80
    content_root = deploy["publish_root"]
    image_tag = f"serverinstaller/{app_name}:latest"
    # Create Dockerfile
    dockerfile = Path(content_root) / "Dockerfile.serverinstaller"
    if deploy.get("runtime") == "node" and deploy.get("website_kind") == "nextjs":
        dockerfile.write_text("FROM node:lts-alpine\nWORKDIR /app\nCOPY . .\nRUN npm install && npm run build\nEXPOSE 3000\nCMD [\"npm\", \"start\"]\n", encoding="utf-8")
    else:
        dockerfile.write_text(f"FROM nginx:alpine\nCOPY . /usr/share/nginx/html\nEXPOSE 80\n", encoding="utf-8")
    # Build image
    if live_cb:
        live_cb(f"Building Docker image {image_tag}...\n")
    rc, out = run_capture(["docker", "build", "-f", str(dockerfile), "-t", image_tag, content_root], timeout=300)
    if rc != 0:
        return 1, f"Docker build failed:\n{out}"
    # Create K8s manifests
    k8s_manifest = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app_name}
  template:
    metadata:
      labels:
        app: {app_name}
    spec:
      containers:
      - name: {app_name}
        image: {image_tag}
        imagePullPolicy: Never
        ports:
        - containerPort: {80 if deploy.get("runtime") != "node" else 3000}
---
apiVersion: v1
kind: Service
metadata:
  name: {app_name}
spec:
  type: NodePort
  selector:
    app: {app_name}
  ports:
  - port: {80 if deploy.get("runtime") != "node" else 3000}
    nodePort: {port}
    targetPort: {80 if deploy.get("runtime") != "node" else 3000}
"""
    manifest_path = Path(content_root) / "k8s-manifest.yaml"
    manifest_path.write_text(k8s_manifest, encoding="utf-8")
    if live_cb:
        live_cb(f"Applying Kubernetes manifest...\n")
    if isinstance(kubectl, str) and " " in kubectl:
        rc, out = run_capture(kubectl.split() + ["apply", "-f", str(manifest_path)], timeout=60)
    else:
        rc, out = run_capture([kubectl, "apply", "-f", str(manifest_path)], timeout=60)
    manage_firewall_port("open", str(port), "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}:{port}"
    _write_website_state_entry({
        "name": deploy["runtime_name"], "form_name": deploy["site_name"],
        "kind": "website_k8s", "target": "kubernetes",
        "website_kind": deploy["website_kind"], "stack_label": deploy["stack_label"],
        "url": url, "bind_ip": deploy["bind_ip"], "host": deploy["host"],
        "port": port, "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"], "publish_root": deploy["publish_root"],
        "image": image_tag, "manifest_path": str(manifest_path),
    })
    return rc, f"Website deployed to Kubernetes.\nDeployment: {app_name}\nURL: {url}\nImage: {image_tag}\n" if rc == 0 else f"Kubernetes deployment failed:\n{out}"


def _windows_service_state(service_name):
    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"$svc=Get-CimInstance Win32_Service -Filter \"Name='{service_name}'\" -ErrorAction SilentlyContinue; if($svc){{Write-Output ($svc.State + '|' + $svc.StartMode)}}",
        ],
        timeout=20,
    )
    if rc != 0 or not out:
        return "", ""
    parts = str(out).strip().split("|", 1)
    state = parts[0].strip() if parts else ""
    start_mode = parts[1].strip() if len(parts) > 1 else ""
    return state, start_mode


def run_windows_python_api_service(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python API OS service deployment is only available on Windows from this page."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    service_name = _safe_python_api_name((form.get("PYTHON_API_SERVICE_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, service_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    certfile, keyfile = _ensure_python_api_https_assets(deploy["python_executable"], deploy["host"], service_name)
    if not certfile or not keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API service."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme", "pywin32"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    rc_post, out_post = run_capture([venv_python, "-m", "pywin32_postinstall", "-install"], timeout=180)
    if rc_post != 0 and live_cb:
        text = str(out_post or "").strip()
        if "No module named pywin32_postinstall" in text:
            live_cb("pywin32_postinstall is not available in this pywin32 build; continuing with direct service host setup.\n")
        else:
            live_cb((text or "pywin32 postinstall returned a non-zero exit code.") + "\n")
    # Copy pywintypes DLLs to the venv root so pythonservice.exe can load them.
    # pywin32_postinstall normally does this to the system Python dir; for a venv
    # we replicate the DLLs next to pythonservice.exe (the venv root).
    venv_root = Path(venv_python).resolve().parent
    pywin32_sys32 = venv_root / "Lib" / "site-packages" / "pywin32_system32"
    if pywin32_sys32.is_dir():
        for dll in pywin32_sys32.glob("pywintypes*.dll"):
            dst = venv_root / dll.name
            if not dst.exists():
                try:
                    shutil.copy2(str(dll), str(dst))
                    if live_cb:
                        live_cb(f"Copied {dll.name} to venv root for service DLL resolution.\n")
                except Exception as exc:
                    if live_cb:
                        live_cb(f"Warning: could not copy {dll.name}: {exc}\n")
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        deploy["host"],
        deploy["https_port"],
        certfile=certfile,
        keyfile=keyfile,
    )
    service_script = deploy["deploy_root"] / ".serverinstaller" / "windows_service.py"
    service_log = deploy["deploy_root"] / ".serverinstaller" / "service-runtime.log"
    service_script.write_text(
        "\n".join([
            "import os",
            "import subprocess",
            "import sys",
            "import time",
            "# Bootstrap pywin32 DLL dirs before importing pywin32 modules.",
            "# Required in venvs where pywin32_postinstall has not been run.",
            "def _bootstrap_pywin32():",
            "    venv_root = os.path.dirname(os.path.abspath(sys.executable))",
            "    try:",
            "        import site",
            "        bases = list(site.getsitepackages())",
            "    except Exception:",
            "        bases = []",
            "    bases.append(os.path.join(venv_root, 'Lib', 'site-packages'))",
            "    for base in bases:",
            "        dll_dir = os.path.join(base, 'pywin32_system32')",
            "        if os.path.isdir(dll_dir):",
            "            if hasattr(os, 'add_dll_directory'):",
            "                try: os.add_dll_directory(dll_dir)",
            "                except Exception: pass",
            "            if dll_dir not in sys.path: sys.path.insert(0, dll_dir)",
            "        for rel in ('win32', os.path.join('win32', 'lib'), 'pythonwin'):",
            "            p = os.path.join(base, rel)",
            "            if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)",
            "_bootstrap_pywin32()",
            "import win32event",
            "import servicemanager",
            "import win32service",
            "import win32serviceutil",
            "",
            f"RUNNER = r'''{str(runner_script.resolve())}'''",
            f"LOG_PATH = r'''{str(service_log.resolve())}'''",
            f"SERVICE_NAME = {service_name!r}",
            f"DISPLAY_NAME = {service_name.replace('-', ' ').title()!r}",
            "",
            "class PythonApiService(win32serviceutil.ServiceFramework):",
            "    _svc_name_ = SERVICE_NAME",
            "    _svc_display_name_ = DISPLAY_NAME",
            "    _svc_description_ = 'Server Installer managed Python API service'",
            "    def __init__(self, args):",
            "        win32serviceutil.ServiceFramework.__init__(self, args)",
            "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
            "        self.proc = None",
            "        self.log_handle = None",
            "    def SvcStop(self):",
            "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
            "        if self.proc and self.proc.poll() is None:",
            "            self.proc.terminate()",
            "            try:",
            "                self.proc.wait(timeout=15)",
            "            except Exception:",
            "                self.proc.kill()",
            "        if self.log_handle:",
            "            self.log_handle.flush()",
            "            self.log_handle.close()",
            "        win32event.SetEvent(self.stop_event)",
            "    def SvcDoRun(self):",
            "        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)",
            "        self.log_handle = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)",
            "        self.log_handle.write(f'[{time.strftime(\"%Y-%m-%d %H:%M:%S\")}] Service starting\\n')",
            f"        self.proc = subprocess.Popen([r'''{venv_python}''', RUNNER], cwd=r'''{str(deploy['deploy_root'].resolve())}''', stdout=self.log_handle, stderr=subprocess.STDOUT, creationflags=0x08000000)",
            "        self.ReportServiceStatus(win32service.SERVICE_RUNNING)",
            "        servicemanager.LogInfoMsg(f'{SERVICE_NAME} started')",
            "        while True:",
            "            status = win32event.WaitForSingleObject(self.stop_event, 2000)",
            "            if status == win32event.WAIT_OBJECT_0:",
            "                break",
            "            if self.proc.poll() is not None:",
            "                if self.log_handle:",
            "                    self.log_handle.write(f'[{time.strftime(\"%Y-%m-%d %H:%M:%S\")}] Runner exited with code {self.proc.returncode}\\n')",
            "                    self.log_handle.flush()",
            "                raise RuntimeError(f'Python API process exited with code {self.proc.returncode}.')",
            "",
            "if __name__ == '__main__':",
            "    if len(sys.argv) == 1:",
            "        servicemanager.Initialize()",
            "        servicemanager.PrepareToHostSingle(PythonApiService)",
            "        servicemanager.StartServiceCtrlDispatcher()",
            "    else:",
            "        win32serviceutil.HandleCommandLine(PythonApiService)",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture([deploy["python_executable"], str(service_script), "remove"], timeout=60)
    code, output = run_process([venv_python, str(service_script), "--startup", "auto", "install"], live_cb=live_cb)
    if code != 0:
        return code, output or "Failed to install the Windows Python API service."
    code, output = run_process([venv_python, str(service_script), "start"], live_cb=live_cb)
    if code != 0 and live_cb:
        live_cb((output or "Service start command returned a non-zero exit code.") + "\n")
    deadline = time.time() + 25
    service_state = ""
    start_mode = ""
    while time.time() < deadline:
        service_state, start_mode = _windows_service_state(service_name)
        if service_state.lower() == "running":
            break
        time.sleep(1)
    if service_state.lower() != "running":
        try:
            runtime_log = service_log.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            runtime_log = ""
        detail = runtime_log[-4000:] if runtime_log else (output or "Service did not reach the Running state.")
        return 1, f"Windows service '{service_name}' failed to start.\nService state: {service_state or 'unknown'}\n{detail}"
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(service_name, {
        "kind": "service",
        "name": service_name,
        "form_name": service_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
        "service_log": str(service_log),
    })
    return 0, f"Python API OS service deployed.\nService: {service_name}\nURL: {url}\nEntry file: {deploy['entry_rel']}\n"


def run_unix_python_api_service(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Python API OS service deployment from this page is for Linux/macOS hosts."
    ensure_repo_files(PYTHON_UNIX_FILES, live_cb=live_cb)
    service_name = _safe_python_api_name((form.get("PYTHON_API_SERVICE_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, service_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    certfile, keyfile = _ensure_python_api_https_assets(deploy["python_executable"], deploy["host"], service_name)
    if not certfile or not keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API service."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        deploy["host"],
        deploy["https_port"],
        certfile=certfile,
        keyfile=keyfile,
    )
    prefix = _sudo_prefix()
    unit_name = f"{service_name}.service"
    unit_temp = deploy["deploy_root"] / f"{unit_name}"
    unit_temp.write_text(
        "\n".join([
            "[Unit]",
            f"Description={service_name}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={str(deploy['deploy_root'])}",
            f"ExecStart={shlex.quote(str(venv_python))} {shlex.quote(str(runner_script))}",
            "Restart=always",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
    run_capture(prefix + ["cp", str(unit_temp), f"/etc/systemd/system/{unit_name}"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    rc_enable, out_enable = run_capture(prefix + ["systemctl", "enable", "--now", unit_name], timeout=60)
    if rc_enable != 0:
        return 1, out_enable or f"Failed to enable and start {unit_name}."
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    http_port = deploy.get("http_port", "")
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
        _setup_nginx_http_redirect(service_name, http_port, deploy["https_port"], live_cb=live_cb)
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(service_name, {
        "kind": "service",
        "name": unit_name,
        "form_name": service_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API OS service deployed.\nService: {unit_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_python_api_docker(form=None, live_cb=None):
    form = form or {}
    if not command_exists("docker"):
        return 1, "Docker is not available on this host."
    deployment_name = _safe_python_api_name((form.get("PYTHON_API_CONTAINER_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, deployment_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    # Generate TLS certs on the host first, then copy them into the build context
    host_certfile, host_keyfile = _ensure_python_api_https_assets(deploy["python_executable"], "0.0.0.0", deployment_name)
    if not host_certfile or not host_keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API Docker container."
    runtime_dir, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        "0.0.0.0",
        deploy["https_port"],
        certfile="/app/.serverinstaller/tls-cert.pem",
        keyfile="/app/.serverinstaller/tls-key.pem",
    )
    shutil.copy2(host_certfile, runtime_dir / "tls-cert.pem")
    shutil.copy2(host_keyfile, runtime_dir / "tls-key.pem")
    # Rewrite run_api.py to use container-internal paths (not host paths)
    _entry_rel = deploy["entry_rel"]
    _app_object = str(deploy["app_object"] or "").strip()
    _https_port = str(deploy["https_port"]).strip()
    runner_script.write_text(
        "\n".join([
            "import os",
            "import runpy",
            f"os.environ['SERVER_INSTALLER_APP_FILE'] = '/app/app/{_entry_rel}'",
            f"os.environ['SERVER_INSTALLER_APP_OBJECT'] = r'''{_app_object}'''",
            "os.environ['SERVER_INSTALLER_HOST'] = '0.0.0.0'",
            f"os.environ['SERVER_INSTALLER_PORT'] = r'''{_https_port}'''",
            "os.environ['SERVER_INSTALLER_CERTFILE'] = '/app/.serverinstaller/tls-cert.pem'",
            "os.environ['SERVER_INSTALLER_KEYFILE'] = '/app/.serverinstaller/tls-key.pem'",
            "runpy.run_path('/app/.serverinstaller/serverinstaller_python_api_host.py', run_name='__main__')",
            "",
        ]),
        encoding="utf-8",
    )
    dockerfile = deploy["deploy_root"] / "Dockerfile"
    dockerfile.write_text(
        "\n".join([
            "FROM python:3.12-slim",
            "WORKDIR /app",
            "COPY app/ /app/app/",
            "COPY .serverinstaller/ /app/.serverinstaller/",
            "RUN python -m venv /opt/serverinstaller-venv \\",
            " && /opt/serverinstaller-venv/bin/python -m pip install --upgrade pip setuptools wheel uvicorn \\",
            " && if [ -f /app/app/requirements.txt ]; then /opt/serverinstaller-venv/bin/python -m pip install -r /app/app/requirements.txt; fi",
            f"EXPOSE {deploy['https_port']}",
            "ENV PATH=/opt/serverinstaller-venv/bin:$PATH",
            f'CMD ["/opt/serverinstaller-venv/bin/python", "/app/.serverinstaller/{runner_script.name}"]',
            "",
        ]),
        encoding="utf-8",
    )
    image_name = deployment_name
    run_capture(["docker", "rm", "-f", deployment_name], timeout=30)
    code, output = run_process(["docker", "build", "-t", image_name, str(deploy["deploy_root"])], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."
    code, output = run_process(
        [
            "docker", "run", "-d",
            "--restart", "unless-stopped",
            "--name", deployment_name,
            "-p", f"{deploy['https_port']}:{deploy['https_port']}",
            image_name,
        ],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    http_port = deploy.get("http_port", "")
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
        _setup_nginx_http_redirect(deployment_name, http_port, deploy["https_port"], live_cb=live_cb)
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(deployment_name, {
        "kind": "docker",
        "name": deployment_name,
        "form_name": deployment_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API Docker deployment completed.\nContainer: {deployment_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_python_api_update_source(service_name, source_path, live_cb=None):
    deploy_key = _safe_python_api_name(service_name)
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return 1, "No Python API deployments found."
    payload = deployments.get(deploy_key)
    if not payload:
        return 1, f"Deployment '{service_name}' not found in state."
    deploy_root = Path(str(payload.get("deploy_root") or ""))
    entry_hint = str(payload.get("entry_file") or "")
    kind = str(payload.get("kind") or "service").lower()
    svc_name = str(payload.get("name") or "")
    if not deploy_root.exists():
        return 1, f"Deployment directory not found: {deploy_root}"
    src = str(source_path or "").strip()
    if not src:
        return 1, "Source path is required."
    if live_cb:
        live_cb(f"[INFO] Updating files from: {src}\n")
    try:
        source_root, entry_file, entry_rel = _resolve_python_api_source(src, entry_hint=entry_hint, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"[INFO] Copying files to {deploy_root / 'app'}...\n")
    try:
        copied_entry, copied_entry_rel = _copy_python_api_source(source_root, entry_file, deploy_root)
    except Exception as ex:
        return 1, f"Failed to copy files: {ex}"
    payload["entry_file"] = copied_entry_rel
    payload["project_path"] = str(deploy_root / "app")
    deployments[deploy_key] = payload
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)
    if live_cb:
        live_cb(f"[INFO] Files updated. Restarting service '{svc_name}'...\n")
    if kind == "service":
        prefix = _sudo_prefix()
        if os.name != "nt":
            rc, out = run_capture(prefix + ["systemctl", "restart", svc_name], timeout=30)
            if rc != 0 and live_cb:
                live_cb(f"[WARN] Restart failed: {out}\n")
        else:
            run_capture(["sc.exe", "stop", svc_name], timeout=15)
            run_capture(["sc.exe", "start", svc_name], timeout=30)
    elif kind == "docker":
        rc, out = run_capture(["docker", "restart", svc_name], timeout=30)
        if rc != 0 and live_cb:
            live_cb(f"[WARN] Docker restart: {out}\n")
    if live_cb:
        live_cb(f"[INFO] Done. Entry file: {copied_entry_rel}\n")
    return 0, f"Files updated and service restarted.\nEntry: {copied_entry_rel}\n"


def run_windows_python_api_iis(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python API IIS deployment is only available on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    site_name = (form.get("PYTHON_API_SITE_NAME", ["ServerInstallerPythonApi"])[0] or "ServerInstallerPythonApi").strip()
    site_key = _safe_python_api_name(site_name, "serverinstaller-python-api-iis")
    try:
        deploy = _prepare_python_api_deployment(form, site_key, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    https_port = deploy["https_port"]
    if is_local_tcp_port_listening(https_port):
        usage = get_port_usage(https_port, "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested IIS HTTPS port {https_port} is already in use. Choose another port."
    internal_port = str(pick_free_local_tcp_port(range(18080, 18280)) or "")
    if not internal_port:
        return 1, "Could not find a free internal port for IIS-backed Python API hosting."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        "127.0.0.1",
        internal_port,
    )
    logs_dir = deploy["deploy_root"] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    web_config = deploy["deploy_root"] / "web.config"
    web_config.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="aspNetCore" path="*" verb="*" modules="AspNetCoreModuleV2" resourceType="Unspecified" />
    </handlers>
    <aspNetCore processPath="{html.escape(str(venv_python))}" arguments="{html.escape(str(runner_script))}" stdoutLogEnabled="true" stdoutLogFile="{html.escape(str(logs_dir / 'stdout'))}" hostingModel="OutOfProcess">
      <environmentVariables>
        <environmentVariable name="SERVER_INSTALLER_APP_FILE" value="{html.escape(str((deploy['deploy_root'] / 'app' / deploy['entry_rel']).resolve()))}" />
        <environmentVariable name="SERVER_INSTALLER_APP_OBJECT" value="{html.escape(str(deploy['app_object']))}" />
        <environmentVariable name="SERVER_INSTALLER_HOST" value="127.0.0.1" />
        <environmentVariable name="SERVER_INSTALLER_PORT" value="{html.escape(str(internal_port))}" />
      </environmentVariables>
    </aspNetCore>
  </system.webServer>
</configuration>
""",
        encoding="utf-8",
    )
    bind_ip = (form.get("PYTHON_API_HOST_IP", [""])[0] or "").strip() or "*"
    dns_name = deploy["host"] if re.match(r"^[A-Za-z0-9.-]+$", deploy["host"]) else "localhost"
    http_port = deploy.get("http_port", "")
    http_binding_ps = []
    if http_port and http_port.isdigit():
        http_binding_ps = [f"New-WebBinding -Name $siteName -Protocol 'http' -Port {int(http_port)} -IPAddress $ip -ErrorAction SilentlyContinue | Out-Null"]
    ps = "\n".join([
        "Import-Module WebAdministration",
        f"$siteName = {_ps_single_quote(site_name)}",
        f"$appPool = {_ps_single_quote(site_name)}",
        f"$physicalPath = {_ps_single_quote(str(deploy['deploy_root']))}",
        f"$ip = {_ps_single_quote(bind_ip if bind_ip != '*' else '*')}",
        f"$port = {int(https_port)}",
        f"$dnsName = {_ps_single_quote(dns_name)}",
        "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
        "if (-not (Test-Path ('IIS:\\AppPools\\' + $appPool))) { New-WebAppPool -Name $appPool | Out-Null }",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name managedRuntimeVersion -Value ''",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name processModel.identityType -Value 4",
        "New-Website -Name $siteName -PhysicalPath $physicalPath -Port $port -IPAddress $ip -Ssl -ApplicationPool $appPool | Out-Null",
        *http_binding_ps,
        "$cert = New-SelfSignedCertificate -DnsName @($dnsName,'localhost','127.0.0.1') -CertStoreLocation 'cert:\\LocalMachine\\My' -FriendlyName ('ServerInstaller Python API ' + $siteName)",
        "$bindingPath = ($ip -eq '*' ? '0.0.0.0' : $ip) + '!' + $port",
        "if (Test-Path ('IIS:\\SslBindings\\' + $bindingPath)) { Remove-Item ('IIS:\\SslBindings\\' + $bindingPath) -Force -ErrorAction SilentlyContinue }",
        "New-Item ('IIS:\\SslBindings\\' + $bindingPath) -Thumbprint $cert.Thumbprint -SSLFlags 0 | Out-Null",
        "Start-Website -Name $siteName | Out-Null",
    ])
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=180)
    if rc != 0:
        return 1, out or f"Failed to create IIS site '{site_name}'."
    manage_firewall_port("open", https_port, "tcp", host=deploy.get("host"))
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
    url = f"https://{deploy['host']}:{https_port}"
    _update_python_api_state(site_key, {
        "kind": "iis_site",
        "name": site_name,
        "form_name": site_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": https_port,
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API IIS deployment completed.\nSite: {site_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_windows_python_installer(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python installer is currently configured for Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    env = os.environ.copy()
    version = (form.get("PYTHON_VERSION", ["3.12"])[0] or "3.12").strip()
    install_jupyter = (form.get("PYTHON_INSTALL_JUPYTER", ["yes"])[0] or "yes").strip().lower()
    host_ip = (form.get("PYTHON_HOST_IP", [""])[0] or "").strip()
    jupyter_port = (form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip()
    notebook_dir = _resolve_python_notebook_dir((form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip())
    system_user = (form.get("SYSTEM_USERNAME", [""])[0] or "").strip()
    system_password = (form.get("SYSTEM_PASSWORD", [""])[0] or "").strip()
    env["PYTHON_VERSION"] = version
    env["PYTHON_INSTALL_JUPYTER"] = "1" if install_jupyter in ("1", "true", "yes", "y", "on") else "0"
    env["PYTHON_JUPYTER_PORT"] = jupyter_port
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    if host_ip:
        env["PYTHON_HOST_IP"] = host_ip
    code, output = run_process(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PYTHON_WINDOWS_INSTALLER)],
        env=env,
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    state = _read_json_file(PYTHON_STATE_FILE)
    if host_ip:
        state["host"] = host_ip
    if jupyter_port:
        state["jupyter_port"] = jupyter_port
    state["default_notebook_dir"] = notebook_dir
    state["notebook_dir"] = notebook_dir
    if system_user:
        state["jupyter_username"] = system_user
    state["jupyter_password_hash"] = ""
    state["jupyter_auth_enabled"] = bool(system_user and system_password)
    state["jupyter_https_enabled"] = True
    _write_json_file(PYTHON_STATE_FILE, state)
    if install_jupyter in ("1", "true", "yes", "y", "on"):
        start_code, start_output = start_python_jupyter(
            host=host_ip or str(state.get("host") or choose_service_host()),
            port=jupyter_port,
            notebook_dir=notebook_dir,
            auth_username=system_user,
            auth_password=system_password,
            live_cb=live_cb,
        )
        if start_output:
            output = f"{output.rstrip()}\n{start_output}".strip()
        if start_code != 0:
            return start_code, output
    return 0, output


def run_unix_python_installer(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Unix Python installer can only run on Linux or macOS hosts."
    ensure_repo_files(PYTHON_UNIX_FILES, live_cb=live_cb)
    env = os.environ.copy()
    version = (form.get("PYTHON_VERSION", ["3.12"])[0] or "3.12").strip()
    install_jupyter = "yes"
    host_ip = (form.get("PYTHON_HOST_IP", [""])[0] or "").strip()
    jupyter_port = (form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip()
    notebook_dir = _resolve_python_notebook_dir((form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip())
    system_user = (form.get("SYSTEM_USERNAME", [""])[0] or "").strip()
    system_password = (form.get("SYSTEM_PASSWORD", [""])[0] or "").strip()
    env["PYTHON_VERSION"] = version
    env["PYTHON_INSTALL_JUPYTER"] = "1"
    env["PYTHON_JUPYTER_PORT"] = jupyter_port
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    env["PYTHON_NOTEBOOK_DIR"] = notebook_dir
    if host_ip:
        env["PYTHON_HOST_IP"] = host_ip
    if system_user:
        env["PYTHON_JUPYTER_USER"] = system_user
    if system_password:
        env["PYTHON_JUPYTER_PASSWORD"] = system_password
    cmd = ["bash", str(PYTHON_UNIX_INSTALLER)]
    if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
        cmd = ["sudo", "env"]
        for key in ("PYTHON_VERSION", "PYTHON_INSTALL_JUPYTER", "PYTHON_JUPYTER_PORT", "PYTHON_HOST_IP", "PYTHON_NOTEBOOK_DIR", "PYTHON_JUPYTER_USER", "PYTHON_JUPYTER_PASSWORD", "SERVER_INSTALLER_DATA_DIR"):
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(PYTHON_UNIX_INSTALLER)]
    code, output = run_process(cmd, env=env, live_cb=live_cb)
    if code != 0:
        return code, output
    state = _read_json_file(PYTHON_STATE_FILE)
    if host_ip:
        state["host"] = host_ip
    if jupyter_port:
        state["jupyter_port"] = jupyter_port
        state["jupyter_url"] = f"https://{host_ip or str(state.get('host') or choose_service_host())}:{jupyter_port}/lab"
    state["default_notebook_dir"] = notebook_dir
    state["notebook_dir"] = notebook_dir
    if host_ip:
        state["host"] = host_ip
    if system_user:
        state["jupyter_username"] = system_user
    if system_user or state.get("jupyter_username"):
        state["jupyter_auth_enabled"] = True
    state["jupyter_https_enabled"] = True
    state["service_mode"] = True
    _write_json_file(PYTHON_STATE_FILE, state)
    return 0, output


def run_python_command(form=None, live_cb=None):
    form = form or {}
    command_text = (form.get("PYTHON_CMD", [""])[0] or "").strip()
    if not command_text:
        return 1, "PYTHON_CMD is required."
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or "").strip()
    if not python_executable:
        return 1, "Install Python first."
    env = _python_env(python_executable)
    if live_cb:
        live_cb(f"[INFO] Running command with Python: {python_executable}\n")
    cmd = ["cmd.exe", "/c", command_text] if os.name == "nt" else ["bash", "-lc", command_text]
    return run_process(cmd, env=env, live_cb=live_cb)


def start_python_jupyter(host="", port="8888", notebook_dir="", auth_username="", auth_password="", live_cb=None):
    if os.name != "nt":
        state = _read_json_file(PYTHON_STATE_FILE)
        if state.get("service_mode") and command_exists("systemctl"):
            rc, out = run_capture(["systemctl", "restart", JUPYTER_SYSTEMD_SERVICE], timeout=60)
            if rc == 0:
                url = str(state.get("jupyter_url") or f"https://{state.get('host') or choose_service_host()}:{state.get('jupyter_port') or port or '8888'}/lab").strip()
                message = out or f"Jupyter Lab service restarted at {url}."
                if live_cb:
                    live_cb(message + "\n")
                return 0, message
            return 1, (out or f"Failed to restart {JUPYTER_SYSTEMD_SERVICE}.")
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or "").strip()
    if not python_executable:
        return 1, "Install Python first."
    python_state = _read_json_file(PYTHON_STATE_FILE)
    auth_username = str(auth_username or "").strip()
    auth_password = str(auth_password or "")
    rc_j, out_j = run_capture([python_executable, "-m", "jupyter", "--version"], timeout=20)
    if rc_j != 0:
        return 1, "Jupyter is not installed for the managed Python interpreter."
    stop_python_jupyter()
    host = (host or choose_service_host()).strip() or "127.0.0.1"
    port = str(port or "8888").strip() or "8888"
    if not port.isdigit():
        return 1, "Jupyter port must be numeric."
    is_windows_proxy_mode = os.name == "nt"
    if is_windows_proxy_mode and (not auth_username or not auth_password):
        return 1, "Windows Jupyter requires the current OS username and password."
    if is_local_tcp_port_listening(port):
        usage = get_port_usage(port, "tcp")
        if usage.get("managed_owner"):
            stop_python_jupyter()
            deadline = time.time() + 10
            while time.time() < deadline and is_local_tcp_port_listening(port):
                time.sleep(0.5)
        if is_local_tcp_port_listening(port):
            return 1, f"Requested Jupyter port {port} is already in use. Choose another port."
    notebook_dir = _resolve_python_notebook_dir(notebook_dir)
    bind_host = host
    public_port = port
    backend_port = port
    jupyter_config_dir = PYTHON_STATE_DIR / "jupyter-config"
    jupyter_data_dir = PYTHON_STATE_DIR / "jupyter-data"
    jupyter_runtime_dir = PYTHON_STATE_DIR / "jupyter-runtime"
    ipython_dir = PYTHON_STATE_DIR / "ipython"
    for path in (jupyter_config_dir, jupyter_data_dir, jupyter_runtime_dir, ipython_dir):
        path.mkdir(parents=True, exist_ok=True)
    jupyter_config_file = jupyter_config_dir / "jupyter_server_config.py"
    if os.name == "nt":
        if host not in ("127.0.0.1", "localhost", "::1"):
            bind_host = "0.0.0.0"
        ok_fw, _ = manage_firewall_port("open", port, "tcp", host=host)
        if not ok_fw and live_cb:
            live_cb(f"[WARN] Failed to open Windows Firewall for TCP {port}. Jupyter may be unreachable from other devices.\n")
    PYTHON_JUPYTER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_path = PYTHON_STATE_DIR / "jupyter.log"
    certfile = ""
    keyfile = ""
    scheme = "http"
    if os.name == "nt":
        certfile, keyfile = _ensure_windows_jupyter_https_assets(python_executable, host)
        if certfile and keyfile:
            scheme = "https"
        if not _ensure_windows_jupyter_proxy_support(python_executable):
            return 1, "Failed to install Windows Jupyter proxy support."
        backend_port_value = pick_free_local_tcp_port([
            18888,
            18889,
            18890,
            18891,
            18892,
            18893,
            18894,
            18895,
            18896,
            18897,
            18898,
            18899,
        ])
        if not backend_port_value or str(backend_port_value) == str(public_port):
            backend_port_value = pick_free_local_tcp_port(range(18900, 19050))
        if not backend_port_value:
            return 1, "Could not find a free internal port for Windows Jupyter."
        backend_port = str(backend_port_value)
        config_text = (
            "c = get_config()\n"
            "c.ServerApp.allow_remote_access = True\n"
            "c.ServerApp.open_browser = False\n"
            "c.ServerApp.trust_xheaders = True\n"
            f"c.ServerApp.allow_origin = {f'https://{host}:{public_port}'!r}\n"
            f"c.ServerApp.local_hostnames = {[host, '127.0.0.1', 'localhost']!r}\n"
            f"c.ServerApp.ip = {'127.0.0.1'!r}\n"
            f"c.ServerApp.port = {int(backend_port)}\n"
            f"c.ServerApp.root_dir = {notebook_dir!r}\n"
            "c.ServerApp.token = ''\n"
            "c.ServerApp.password = ''\n"
            "c.ServerApp.terminals_enabled = True\n"
            "c.ServerApp.jpserver_extensions = {\n"
            "    'jupyterlab': True,\n"
            "    'jupyter_server_terminals': True,\n"
            "}\n"
            "c.TerminalManager.shell_command = ['cmd.exe']\n"
        )
        jupyter_config_file.write_text(config_text, encoding="utf-8")
    args = [
        python_executable,
        "-m",
        "jupyter",
        "lab",
        "--no-browser",
        f"--ServerApp.ip={'127.0.0.1' if is_windows_proxy_mode else bind_host}",
        f"--ServerApp.port={backend_port}",
        "--ServerApp.port_retries=0",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.trust_xheaders=True",
        f"--ServerApp.allow_origin=https://{host}:{public_port}",
        f"--ServerApp.local_hostnames={host},127.0.0.1,localhost",
        f"--ServerApp.root_dir={notebook_dir}",
    ]
    if os.name == "nt":
        args.append(f"--config={jupyter_config_file}")
    args.append("--ServerApp.token=")
    args.append("--ServerApp.password=")
    if certfile and keyfile and not is_windows_proxy_mode:
        args.append(f"--ServerApp.certfile={certfile}")
        args.append(f"--ServerApp.keyfile={keyfile}")
    env = _python_env(python_executable)
    env["JUPYTER_CONFIG_DIR"] = str(jupyter_config_dir)
    env["JUPYTER_DATA_DIR"] = str(jupyter_data_dir)
    env["JUPYTER_RUNTIME_DIR"] = str(jupyter_runtime_dir)
    env["JUPYTER_NO_CONFIG"] = "1"
    env["JUPYTER_PREFER_ENV_PATH"] = "1"
    env["JUPYTER_ALLOW_INSECURE_WRITES"] = "true"
    env["IPYTHONDIR"] = str(ipython_dir)
    try:
        log_handle = open(log_path, "ab")
        if os.name == "nt":
            args.append("--ServerApp.terminals_enabled=True")
        kwargs = {
            "cwd": notebook_dir,
            "env": env,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(args, **kwargs)
        backend_proc = proc
        proxy_proc = None
        deadline = time.time() + 20
        while time.time() < deadline:
            if is_local_tcp_port_listening(backend_port):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.5)
        if not is_local_tcp_port_listening(backend_port):
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                log_text = ""
            if proc.poll() is not None:
                return 1, (log_text.strip() or f"Jupyter Lab exited early with code {proc.returncode}.")
            return 1, (log_text.strip() or f"Jupyter Lab did not start listening on port {backend_port}.")
        if is_windows_proxy_mode:
            proxy_script = _ensure_windows_jupyter_proxy_script()
            proxy_args = [
                python_executable,
                proxy_script,
                "--listen-host", bind_host,
                "--listen-port", public_port,
                "--backend-host", "127.0.0.1",
                "--backend-port", backend_port,
                "--username", auth_username,
                "--password", auth_password,
                "--certfile", certfile,
                "--keyfile", keyfile,
            ]
            proxy_kwargs = {
                "cwd": notebook_dir,
                "env": env,
                "stdout": log_handle,
                "stderr": subprocess.STDOUT,
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            }
            proxy_proc = subprocess.Popen(proxy_args, **proxy_kwargs)
            deadline = time.time() + 20
            while time.time() < deadline:
                if is_local_tcp_port_listening(public_port):
                    break
                if proxy_proc.poll() is not None:
                    break
                time.sleep(0.5)
            if not is_local_tcp_port_listening(public_port):
                try:
                    log_text = log_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    log_text = ""
                if proxy_proc.poll() is not None:
                    return 1, (log_text.strip() or f"Windows Jupyter proxy exited early with code {proxy_proc.returncode}.")
                return 1, (log_text.strip() or f"Windows Jupyter proxy did not start listening on port {public_port}.")
        url = f"{scheme}://{host}:{public_port}/lab"
        state = _read_json_file(PYTHON_STATE_FILE)
        state["host"] = host
        state["jupyter_port"] = public_port
        state["default_notebook_dir"] = notebook_dir
        state["notebook_dir"] = notebook_dir
        if is_windows_proxy_mode:
            state["jupyter_username"] = auth_username
            state["jupyter_auth_enabled"] = True
            state["jupyter_https_enabled"] = True
            state["jupyter_password_hash"] = ""
        _write_json_file(PYTHON_STATE_FILE, state)
        _write_json_file(PYTHON_JUPYTER_STATE_FILE, {
            "pid": proxy_proc.pid if proxy_proc is not None else proc.pid,
            "backend_pid": backend_proc.pid if is_windows_proxy_mode else None,
            "host": host,
            "port": public_port,
            "backend_port": backend_port if is_windows_proxy_mode else public_port,
            "url": url,
            "log_path": str(log_path),
            "notebook_dir": notebook_dir,
            "username": auth_username if is_windows_proxy_mode else str(python_state.get("jupyter_username") or "").strip(),
            "auth_enabled": bool(auth_username and auth_password) if is_windows_proxy_mode else bool(python_state.get("jupyter_password_hash")),
            "https_enabled": bool(certfile and keyfile) if is_windows_proxy_mode else bool(certfile and keyfile),
            "running": True,
        })
        message = f"Jupyter Lab started at {url}."
        if live_cb:
            live_cb(message + "\n")
        return 0, message
    except Exception as ex:
        return 1, f"Failed to start Jupyter Lab: {ex}"


def stop_python_jupyter(live_cb=None):
    state = _read_json_file(PYTHON_STATE_FILE)
    if os.name != "nt" and state.get("service_mode") and command_exists("systemctl"):
        rc, out = run_capture(["systemctl", "stop", JUPYTER_SYSTEMD_SERVICE], timeout=60)
        if rc != 0:
            return 1, (out or f"Failed to stop {JUPYTER_SYSTEMD_SERVICE}.")
        jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
        if jupyter_state:
            jupyter_state["running"] = False
            _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
        message = "Jupyter Lab service stopped."
        if live_cb:
            live_cb(message + "\n")
        return 0, message
    state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    pid = state.get("pid")
    backend_pid = state.get("backend_pid")
    port = str(state.get("port") or _read_json_file(PYTHON_STATE_FILE).get("jupyter_port") or "").strip()
    killed_any = False
    try:
        pid_num = int(pid)
    except Exception:
        pid_num = 0
    if pid_num > 0:
        if os.name == "nt":
            rc, out = run_capture(["taskkill", "/PID", str(pid_num), "/F"], timeout=20)
        else:
            rc, out = run_capture(["kill", "-TERM", str(pid_num)], timeout=20)
        if rc != 0 and _python_process_running(pid_num):
            return 1, (out or f"Failed to stop Jupyter process {pid_num}.")
        killed_any = True
    try:
        backend_pid_num = int(backend_pid)
    except Exception:
        backend_pid_num = 0
    if backend_pid_num > 0 and backend_pid_num != pid_num:
        if os.name == "nt":
            rc, out = run_capture(["taskkill", "/PID", str(backend_pid_num), "/F"], timeout=20)
        else:
            rc, out = run_capture(["kill", "-TERM", str(backend_pid_num)], timeout=20)
        if rc != 0 and _python_process_running(backend_pid_num):
            return 1, (out or f"Failed to stop Jupyter backend process {backend_pid_num}.")
        killed_any = True
    if os.name == "nt" and port.isdigit():
        listener_pids = []
        for item in get_listening_ports(limit=5000):
            proto = str(item.get("proto", "")).lower()
            if not proto.startswith("tcp"):
                continue
            if int(item.get("port", 0)) != int(port):
                continue
            try:
                listener_pid = int(str(item.get("pid") or "0"))
            except Exception:
                continue
            if listener_pid <= 0 or listener_pid == pid_num:
                continue
            if _windows_process_matches_managed_jupyter(listener_pid, port):
                listener_pids.append(listener_pid)
        for listener_pid in sorted(set(listener_pids)):
            rc, out = run_capture(["taskkill", "/PID", str(listener_pid), "/F"], timeout=20)
            if rc != 0 and _python_process_running(listener_pid):
                return 1, (out or f"Failed to stop Jupyter process {listener_pid}.")
            killed_any = True
    if not killed_any:
        return 0, "Jupyter Lab is not running."
    state["pid"] = None
    state["backend_pid"] = None
    state["running"] = False
    _write_json_file(PYTHON_JUPYTER_STATE_FILE, state)
    message = "Jupyter Lab stopped."
    if live_cb:
        live_cb(message + "\n")
    return 0, message


def run_capture(cmd, timeout=20):
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "").strip()
    except Exception as ex:
        return 1, str(ex)


def _curl_status(url, insecure=False, timeout=6):
    if not command_exists("curl"):
        return None
    cmd = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout)]
    if insecure:
        cmd.insert(1, "-k")
    cmd.append(url)
    rc, out = run_capture(cmd, timeout=timeout + 2)
    if rc != 0:
        return None
    code = (out or "").strip()
    return code if code else None


def get_uptime_seconds():
    if os.name == "nt":
        try:
            return int(ctypes.windll.kernel32.GetTickCount64() / 1000)
        except Exception:
            return None
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return None


def get_memory_info():
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            used = int(stat.ullTotalPhys - stat.ullAvailPhys)
            return {
                "total_bytes": int(stat.ullTotalPhys),
                "available_bytes": int(stat.ullAvailPhys),
                "used_bytes": used,
                "used_percent": int(stat.dwMemoryLoad),
            }
        except Exception:
            return {}

    try:
        mem = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, rest = line.split(":", 1)
                value = rest.strip().split()[0]
                mem[key.strip()] = int(value) * 1024
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", mem.get("MemFree", 0))
        used = max(0, total - avail)
        used_percent = int((used / total) * 100) if total else 0
        return {
            "total_bytes": total,
            "available_bytes": avail,
            "used_bytes": used,
            "used_percent": used_percent,
        }
    except Exception:
        return {}


def get_ip_addresses():
    ips = set()
    try:
        host = socket.gethostname()
        for ip in socket.gethostbyname_ex(host)[2]:
            if ip and (not ip.startswith("127.")):
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        if ip and (not ip.startswith("127.")):
            ips.add(ip)
    except Exception:
        pass
    if not ips:
        ips.add("127.0.0.1")
    return sorted(ips)


def get_public_ipv4(timeout_sec=3):
    urls = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipv4.icanhazip.com",
    ]
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="ignore").strip()
                if raw:
                    ip = raw.splitlines()[0].strip()
                    try:
                        ipaddress.ip_address(ip)
                        if not ip.startswith("127."):
                            return ip
                    except Exception:
                        continue
        except Exception:
            continue
    return ""


def choose_s3_host(preferred=""):
    preferred = (preferred or "").strip()
    if preferred and preferred not in ("localhost", "127.0.0.1"):
        return preferred
    public_ip = get_public_ipv4()
    if public_ip:
        return public_ip
    for ip in get_ip_addresses():
        if ip and not ip.startswith("127."):
            return ip
    return "localhost"


def choose_service_host():
    """Pick the best host IP for service URLs — prefer LAN IP over public IP."""
    # Prefer local/LAN IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x) over public
    for ip in get_ip_addresses():
        if ip and not ip.startswith("127."):
            return ip
    public_ip = get_public_ipv4()
    if public_ip:
        return public_ip
    return "localhost"


def get_windows_locals3_config():
    return _read_json_file(WINDOWS_LOCALS3_STATE)


def get_windows_locals3_host():
    state = get_windows_locals3_config()
    for key in ("display_host", "selected_host", "lan_ip"):
        value = str(state.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_nginx_listen_and_server(conf_text):
    listens = []
    server_names = []
    for line in conf_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if s.startswith("listen "):
            parts = s.replace(";", "").split()
            if len(parts) >= 2:
                listen_val = parts[1]
                ssl = ("ssl" in parts[2:]) or ("ssl" in s)
                try:
                    port = int(listen_val.split(":")[-1])
                    listens.append({"port": port, "ssl": ssl})
                except Exception:
                    continue
        if s.startswith("server_name "):
            names = s.replace(";", "").split()[1:]
            server_names.extend([n for n in names if n])
    return listens, server_names


def _urls_from_nginx_conf(conf_path, preferred_host=""):
    conf = Path(conf_path)
    if not conf.exists():
        return [], []
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [], []
    listens, server_names = _parse_nginx_listen_and_server(text)
    if not server_names:
        server_names = [preferred_host or choose_service_host()]
    urls = []
    ports = []
    for listen in listens:
        port = listen.get("port")
        ssl = listen.get("ssl", False)
        scheme = "https" if ssl or port == 443 else "http"
        for name in server_names:
            host = name if name not in ("_", "localhost", "127.0.0.1") else (preferred_host or choose_service_host())
            if port in (80, 443):
                urls.append(f"{scheme}://{host}")
            else:
                urls.append(f"{scheme}://{host}:{port}")
        if port:
            ports.append({"port": port, "protocol": "tcp"})
    return sorted(set(urls)), ports


def _parse_docker_ports(ports_text):
    ports = []
    if not ports_text:
        return ports
    for chunk in ports_text.split(","):
        s = chunk.strip()
        if "->" not in s:
            continue
        left, right = s.split("->", 1)
        proto = "tcp"
        if "/" in right:
            proto = right.split("/")[-1].strip()
        host_part = left.split(":")[-1].strip()
        if host_part.isdigit():
            ports.append({"port": int(host_part), "protocol": proto})
    return ports


def _get_docker_container_details(name):
    details = {
        "ports": [],
        "labels": {},
        "restart_policy": "",
        "image": "",
        "state": "",
    }
    rc, out = run_capture(["docker", "inspect", name], timeout=30)
    if rc != 0 or not out:
        return details
    try:
        raw = json.loads(out)
        obj = raw[0] if isinstance(raw, list) and raw else {}
        config = obj.get("Config", {}) or {}
        host_config = obj.get("HostConfig", {}) or {}
        network = obj.get("NetworkSettings", {}) or {}
        ports = []
        bindings = network.get("Ports", {}) or {}
        for container_port, host_bindings in bindings.items():
            proto = "tcp"
            if "/" in str(container_port):
                proto = str(container_port).split("/")[-1].strip().lower() or "tcp"
            if not host_bindings:
                continue
            for binding in host_bindings:
                host_port = str((binding or {}).get("HostPort", "")).strip()
                if host_port.isdigit():
                    ports.append({"port": int(host_port), "protocol": proto})
        details["ports"] = sorted(
            {(p["port"], p["protocol"]) for p in ports},
            key=lambda item: (item[0], item[1]),
        )
        details["ports"] = [{"port": p, "protocol": proto} for p, proto in details["ports"]]
        details["labels"] = config.get("Labels", {}) or {}
        details["restart_policy"] = str(((host_config.get("RestartPolicy", {}) or {}).get("Name", "")) or "").strip()
        details["image"] = str(config.get("Image", "") or "").strip()
        details["state"] = str(((obj.get("State", {}) or {}).get("Status", "")) or "").strip()
    except Exception:
        return details
    return details


def get_network_totals():
    if os.name == "nt":
        rc, out = run_capture(["netstat", "-e"], timeout=15)
        if rc == 0 and out:
            rx = None
            tx = None
            for line in out.splitlines():
                s = line.strip()
                if s.startswith("Bytes"):
                    parts = [p for p in s.split() if p]
                    if len(parts) >= 3:
                        try:
                            rx = int(parts[1].replace(",", ""))
                            tx = int(parts[2].replace(",", ""))
                        except Exception:
                            pass
                    break
            if rx is not None and tx is not None:
                return {"rx_bytes": rx, "tx_bytes": tx}
        return {}

    try:
        rx_total = 0
        tx_total = 0
        with open("/proc/net/dev", "r", encoding="utf-8") as f:
            lines = f.readlines()[2:]
        for line in lines:
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            vals = [v for v in data.strip().split() if v]
            if len(vals) < 16:
                continue
            rx_total += int(vals[0])
            tx_total += int(vals[8])
        return {"rx_bytes": rx_total, "tx_bytes": tx_total}
    except Exception:
        return {}


def get_cpu_usage_percent():
    if os.name == "nt":
        rc, out = run_capture(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average",
            ],
            timeout=15,
        )
        if rc == 0 and out:
            try:
                return float(out.splitlines()[-1].strip())
            except Exception:
                return None
        return None

    try:
        if hasattr(os, "getloadavg"):
            load1 = os.getloadavg()[0]
            cpus = os.cpu_count() or 1
            return max(0.0, min(100.0, (load1 / cpus) * 100.0))
    except Exception:
        pass
    return None


def get_dotnet_info():
    info = {"installed": False, "version": "", "sdks": [], "runtimes": []}
    rc, out = run_capture(["dotnet", "--version"])
    if rc == 0 and out:
        info["installed"] = True
        info["version"] = out.splitlines()[0].strip()
        rc_sdks, out_sdks = run_capture(["dotnet", "--list-sdks"])
        if rc_sdks == 0 and out_sdks:
            info["sdks"] = [x.strip() for x in out_sdks.splitlines() if x.strip()]
        rc_rt, out_rt = run_capture(["dotnet", "--list-runtimes"])
        if rc_rt == 0 and out_rt:
            info["runtimes"] = [x.strip() for x in out_rt.splitlines() if x.strip()]
    return info


def get_docker_info():
    info = {"installed": False, "version": "", "server_version": "", "running": False, "os_type": ""}
    rc, out = run_capture(["docker", "--version"])
    if rc == 0 and out:
        info["installed"] = True
        info["version"] = out.splitlines()[0].strip()
        rc2, out2 = run_capture(["docker", "version", "--format", "{{.Server.Version}}"])
        if rc2 == 0 and out2:
            info["server_version"] = out2.strip()
            info["running"] = True
        rc3, out3 = run_capture(["docker", "info", "--format", "{{.OSType}}"])
        if rc3 == 0 and out3:
            info["os_type"] = out3.strip().lower()
    return info


def get_windows_s3_docker_support():
    support = {"supported": True, "reason": ""}
    if os.name != "nt":
        return support

    machine = (platform.machine() or "").strip().lower()
    if machine not in ("amd64", "x86_64", "arm64", "aarch64"):
        support["supported"] = False
        support["reason"] = f"Docker Desktop requires a 64-bit Windows host. Detected architecture: {machine or 'unknown'}."
        return support

    try:
        winver = sys.getwindowsversion()
        major = int(getattr(winver, "major", 0) or 0)
        build = int(getattr(winver, "build", 0) or 0)
        if major < 10:
            support["supported"] = False
            support["reason"] = "Docker Desktop requires Windows 10 or newer."
            return support
        if build and build < 19041:
            support["supported"] = False
            support["reason"] = f"Docker Desktop requires Windows build 19041 or newer. Detected build: {build}."
            return support
    except Exception:
        pass

    return support


def get_iis_info():
    info = {"available": False, "installed": False, "version": "", "service": "unknown"}
    if os.name != "nt":
        return info

    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole).State",
        ]
    )
    if rc == 0 and out:
        info["available"] = True
        info["installed"] = "Enabled" in out

    rc_svc, out_svc = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-Service W3SVC -ErrorAction SilentlyContinue).Status",
        ]
    )
    if rc_svc == 0 and out_svc:
        info["service"] = out_svc.strip().splitlines()[0]

    rc_ver, out_ver = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "[System.Environment]::OSVersion.VersionString",
        ]
    )
    if rc_ver == 0 and out_ver:
        info["version"] = out_ver.strip().splitlines()[0]
    return info


def get_mongo_info():
    info = {
        "installed": False,
        "server_version": "",
        "web_version": "",
        "https_url": "",
        "connection_string": "",
        "auth_enabled": False,
        "host": "",
        "admin_user": "",
        "admin_password": "",
    }
    preferred_host = choose_service_host()

    if os.name == "nt":
        native = get_windows_native_mongo_info()
        if native.get("installed"):
            info["installed"] = True
        if native.get("version"):
            info["server_version"] = str(native.get("version") or "")
        connection = str(native.get("connection") or "").strip()
        port = str(native.get("port") or "").strip()
        host = str(native.get("host") or "").strip()
        if connection:
            info["connection_string"] = connection
        elif port.isdigit():
            info["connection_string"] = f"mongodb://{host or preferred_host}:{int(port)}/"
        if native.get("mode") == "native":
            info["web_version"] = str(native.get("web_version") or "native")
        info["auth_enabled"] = bool(native.get("auth_enabled"))
        info["host"] = host
        info["admin_user"] = str(native.get("admin_user") or "")
        info["admin_password"] = str(native.get("admin_password") or "")

    if command_exists("docker"):
        for name in ("localmongo-mongodb", "localmongo-web", "localmongo-https"):
            details = _get_docker_container_details(name)
            if details.get("image"):
                info["installed"] = True
            if name == "localmongo-mongodb" and details.get("image"):
                image = details["image"]
                if ":" in image:
                    info["server_version"] = image.rsplit(":", 1)[1]
                for p in details.get("ports", []):
                    if int(p.get("port", 0)) > 0:
                        info["connection_string"] = (
                            f"mongodb://{preferred_host}:{int(p['port'])}/"
                        )
                        break
            if name == "localmongo-web" and details.get("image"):
                image = details["image"]
                if ":" in image:
                    info["web_version"] = image.rsplit(":", 1)[1]
            if name == "localmongo-https":
                for p in details.get("ports", []):
                    port = int(p.get("port", 0))
                    if port <= 0:
                        continue
                    info["https_url"] = f"https://{preferred_host}" if port == 443 else f"https://{preferred_host}:{port}"
                    break
    return info


def parse_port_from_addr(addr):
    text = (addr or "").strip()
    if not text:
        return None
    if text.startswith("[") and "]:" in text:
        return text.rsplit("]:", 1)[1]
    if ":" in text:
        return text.rsplit(":", 1)[1]
    return None


def _urls_from_windows_locals3_log(preferred_host=""):
    log_path = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "LocalS3" / "storage-server" / "minio" / "minio.log"
    if not log_path.exists():
        return [], []
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [], []

    urls = []
    ports = []
    for match in re.finditer(r"(?im)^\s*(API|WebUI):\s+(https?://\S+)\s*$", text):
        url = str(match.group(2) or "").strip()
        if not url:
            continue
        try:
            parsed = urlparse(url)
            # Prefer the hostname embedded in the MinIO log URL (set from MINIO_SERVER_URL,
            # which is the user-selected IP). Only fall back to preferred_host / auto-detection
            # when the log URL is on localhost / loopback.
            log_host = str(parsed.hostname or "").strip()
            if log_host and log_host not in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                host = log_host
            else:
                host = preferred_host or get_windows_locals3_host() or choose_service_host()
            scheme = parsed.scheme or "https"
            port = parsed.port or (443 if scheme == "https" else 80)
            normalized = f"{scheme}://{host}" if port in (80, 443) else f"{scheme}://{host}:{port}"
            urls.append(normalized)
            ports.append({"port": int(port), "protocol": "tcp"})
        except Exception:
            continue

    dedup_urls = sorted(set(urls))
    dedup_ports = []
    seen_ports = set()
    for item in ports:
        key = (item.get("port"), item.get("protocol"))
        if key in seen_ports:
            continue
        seen_ports.add(key)
        dedup_ports.append(item)
    return dedup_urls, dedup_ports


def _get_proc_net_tcp_ports():
    """
    Read ALL listening TCP ports from /proc/net/tcp and /proc/net/tcp6.
    Resolves process names via /proc/<pid>/fd socket inode lookup.
    Returns list of {port, proto, process, pid, processes, pids, state}.
    Only available on Linux (no-op on other platforms).
    """
    if os.name == "nt" or not Path("/proc/net/tcp").exists():
        return []
    import re as _re

    # Build inode -> (pid, comm) map by scanning /proc/<pid>/fd
    inode_to_proc = {}
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            pid = pid_dir.name
            try:
                comm = (pid_dir / "comm").read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                comm = ""
            fd_dir = pid_dir / "fd"
            try:
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(str(fd))
                        m = _re.match(r"socket:\[(\d+)\]", target)
                        if m:
                            inode_to_proc[m.group(1)] = (pid, comm)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    result = {}  # port -> entry dict
    for filepath in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) < 10 or parts[0] == "sl":
                continue
            if parts[3] != "0A":  # 0A = TCP_LISTEN
                continue
            local = parts[1]
            port_hex = local.split(":")[-1]
            try:
                port = int(port_hex, 16)
            except Exception:
                continue
            if not (1 <= port <= 65535):
                continue
            inode = parts[9]
            pid, comm = inode_to_proc.get(inode, ("", ""))
            if port not in result:
                result[port] = {
                    "proto": "tcp",
                    "port": port,
                    "process": comm,
                    "pid": pid,
                    "processes": [comm] if comm else [],
                    "pids": [pid] if pid else [],
                    "state": "LISTEN",
                }
    return list(result.values())


def get_listening_ports(limit=200):
    ports = []
    if os.name == "nt":
        rc, out = run_capture(["netstat", "-ano", "-p", "tcp"], timeout=30)
        if rc == 0 and out:
            for line in out.splitlines():
                line = line.strip()
                if not line.startswith("TCP"):
                    continue
                parts = [p for p in line.split() if p]
                if len(parts) < 5:
                    continue
                state = parts[3]
                if state != "LISTENING":
                    continue
                port = parse_port_from_addr(parts[1])
                pid = parts[4]
                if not (port and port.isdigit()):
                    continue
                ports.append({"proto": "tcp", "port": int(port), "pid": pid, "state": state})
        rc_u, out_u = run_capture(["netstat", "-ano", "-p", "udp"], timeout=30)
        if rc_u == 0 and out_u:
            for line in out_u.splitlines():
                line = line.strip()
                if not line.startswith("UDP"):
                    continue
                parts = [p for p in line.split() if p]
                if len(parts) < 4:
                    continue
                port = parse_port_from_addr(parts[1])
                pid = parts[3]
                if not (port and port.isdigit()):
                    continue
                ports.append({"proto": "udp", "port": int(port), "pid": pid, "state": "LISTEN"})
    else:
        rc, out = run_capture(["ss", "-ltnupH"], timeout=30)
        if rc == 0 and out:
            import re as _re
            seen = {}  # (proto, port) -> dict
            for line in out.splitlines():
                parts = [p for p in line.split() if p]
                if len(parts) < 5:
                    continue
                proto = parts[0]
                local_addr = parts[4]
                proc_str = " ".join(parts[5:]) if len(parts) > 5 else ""
                port = parse_port_from_addr(local_addr)
                if not (port and port.isdigit()):
                    continue
                proc_names = list(dict.fromkeys(_re.findall(r'"([^"]+)"', proc_str)))
                pid_list = list(dict.fromkeys(_re.findall(r'pid=(\d+)', proc_str)))
                key = (proto, int(port))
                if key not in seen:
                    seen[key] = {
                        "proto": proto,
                        "port": int(port),
                        "process": proc_names[0] if proc_names else "",
                        "pid": pid_list[0] if pid_list else "",
                        "processes": proc_names,
                        "pids": pid_list,
                        "state": parts[1],
                    }
                else:
                    for n in proc_names:
                        if n not in seen[key]["processes"]:
                            seen[key]["processes"].append(n)
                    for pid in pid_list:
                        if pid not in seen[key]["pids"]:
                            seen[key]["pids"].append(pid)
                    if seen[key]["processes"]:
                        seen[key]["process"] = seen[key]["processes"][0]
                    if seen[key]["pids"]:
                        seen[key]["pid"] = seen[key]["pids"][0]
            ports = list(seen.values())

        # Supplement with /proc/net/tcp to catch any ports ss missed (e.g. isolated nginx)
        proc_entries = _get_proc_net_tcp_ports()
        ss_ports = {p["port"] for p in ports}
        for entry in proc_entries:
            if entry["port"] not in ss_ports:
                ports.append(entry)

    ports.sort(key=lambda x: (x.get("port", 0), x.get("proto", "")))
    return ports[:limit]


def _sudo_prefix():
    if os.name == "nt":
        return []
    if os.geteuid() == 0:
        return []
    if command_exists("sudo"):
        return ["sudo"]
    return []


def _setup_nginx_http_redirect(service_name, http_port, https_port, live_cb=None):
    """Add/update an nginx config that redirects HTTP→HTTPS for the given service."""
    cert_dir = f"/etc/nginx/ssl/{service_name}"
    nginx_script = f"""
set -euo pipefail
command -v nginx >/dev/null 2>&1 || {{ echo "nginx not found; skipping HTTP redirect setup."; exit 0; }}
mkdir -p "{cert_dir}"
CONF="/etc/nginx/conf.d/{service_name}.conf"
if [[ -f "$CONF" ]]; then
  if grep -q "listen {http_port};" "$CONF" 2>/dev/null; then
    echo "nginx HTTP redirect for {service_name} on port {http_port} already configured."
    exit 0
  fi
fi
cat >> "$CONF" <<'NGINX'
server {{
    listen {http_port};
    server_name _;
    return 308 https://$host:{https_port}$request_uri;
}}
NGINX
nginx -t && (systemctl is-active --quiet nginx && systemctl reload nginx || systemctl restart nginx)
echo "nginx HTTP redirect configured: port {http_port} -> HTTPS {https_port}"
"""
    sudo_prefix = []
    if os.name != "nt" and os.geteuid() != 0 and subprocess.run(
        ["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0:
        sudo_prefix = ["sudo"]
    run_process(sudo_prefix + ["bash", "-c", nginx_script], live_cb=live_cb)


def _lookup_service_ports(name, kind):
    """Return list of {port, protocol} dicts for a service, looked up from state files and OS.
    Called before deletion so ports can be closed in the firewall afterwards."""
    svc_name = _safe_service_name(name)
    ports = []

    # 1. Python API state file
    try:
        py_state = _read_json_file(PYTHON_API_STATE_FILE)
        for payload in (py_state.get("deployments") or {}).values():
            if not isinstance(payload, dict):
                continue
            if str(payload.get("name") or "").strip() == svc_name:
                for key in ("port", "http_port"):
                    pt = str(payload.get(key) or "").strip()
                    if pt.isdigit():
                        ports.append({"port": int(pt), "protocol": "tcp"})
                if ports:
                    return ports
    except Exception:
        pass

    # 2. Website state file
    try:
        web_state = _read_json_file(WEBSITE_STATE_FILE)
        for payload in (web_state.get("deployments") or {}).values():
            if not isinstance(payload, dict):
                continue
            names = {str(payload.get("name") or "").strip(), str(payload.get("form_name") or "").strip()}
            if svc_name in names or svc_name.replace(".service", "") in names:
                pt = str(payload.get("port") or "").strip()
                if pt.isdigit():
                    return [{"port": int(pt), "protocol": "tcp"}]
    except Exception:
        pass

    # 3. Docker: inspect for published host ports
    if kind == "docker" and command_exists("docker"):
        try:
            details = _get_docker_container_details(svc_name)
            if details.get("ports"):
                return details["ports"]
        except Exception:
            pass

    # 4. IIS site: query bindings
    if kind == "iis_site" and os.name == "nt":
        try:
            rc, out = run_capture(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 f"Import-Module WebAdministration; Get-WebBinding -Name '{svc_name}' | Select bindingInformation | ConvertTo-Json -Depth 2"],
                timeout=20,
            )
            if rc == 0 and out:
                raw = json.loads(out)
                binds = raw if isinstance(raw, list) else [raw]
                for b in binds:
                    bind = str((b or {}).get("bindingInformation", "") or "")
                    port = parse_port_from_addr(bind)
                    if port and str(port).isdigit():
                        ports.append({"port": int(port), "protocol": "tcp"})
        except Exception:
            pass
        return ports

    # 5. Linux systemd: nginx conf
    if kind in ("service", "website_launchd") and os.name != "nt":
        base_name = svc_name.replace(".service", "")
        for conf_path in (
            f"/etc/nginx/conf.d/{base_name}.conf",
            f"/opt/locals3/nginx/nginx-standalone.conf",
            "/etc/nginx/conf.d/locals3.conf",
        ):
            _, found = _urls_from_nginx_conf(conf_path)
            if found:
                return found

    return ports


def _is_internal_ip(ip):
    """Return True if ip is a loopback, link-local, or RFC-1918 private address."""
    if not ip:
        return False
    ip = str(ip).strip().lower()
    if ip in ("localhost", "::1", "0:0:0:0:0:0:0:1", "0.0.0.0"):
        return True
    try:
        import ipaddress
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        return False


def manage_firewall_port(action, port, protocol, host=None):
    action = (action or "").strip().lower()
    protocol = (protocol or "").strip().lower()
    if action == "open" and host and host in ("localhost", "127.0.0.1", "::1"):
        return True, f"Skipped firewall: port {port} bound to loopback host {host}"
    if action not in ("open", "close"):
        return False, "Action must be open or close."
    if protocol not in ("tcp", "udp"):
        return False, "Protocol must be tcp or udp."
    if not str(port).isdigit():
        return False, "Port must be numeric."
    port_num = int(port)
    if port_num < 1 or port_num > 65535:
        return False, "Port must be between 1 and 65535."

    if os.name == "nt":
        if not is_windows_admin():
            return False, "Port management on Windows requires Administrator."
        rule_name = f"ServerInstaller-Managed-{protocol.upper()}-{port_num}"
        if action == "open":
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    f"if (-not (Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue)) "
                    f"{{ New-NetFirewallRule -DisplayName '{rule_name}' -Direction Inbound -Action Allow "
                    f"-Protocol {protocol.upper()} -LocalPort {port_num} | Out-Null }}"
                ),
            ]
        else:
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule",
            ]
        rc, out = run_capture(cmd, timeout=30)
        return rc == 0, (out or f"Firewall rule {action} completed.")

    prefix = _sudo_prefix()
    if command_exists("ufw"):
        if action == "open":
            cmd = prefix + ["ufw", "allow", f"{port_num}/{protocol}"]
        else:
            cmd = prefix + ["ufw", "delete", "allow", f"{port_num}/{protocol}"]
        rc, out = run_capture(cmd, timeout=30)
        return rc == 0, (out or f"ufw {action} completed.")

    if command_exists("firewall-cmd"):
        rc_state, _ = run_capture(prefix + ["firewall-cmd", "--state"], timeout=15)
        if rc_state == 0:
            if action == "open":
                run_capture(prefix + ["firewall-cmd", "--add-port", f"{port_num}/{protocol}"], timeout=20)
                rc, out = run_capture(prefix + ["firewall-cmd", "--permanent", "--add-port", f"{port_num}/{protocol}"], timeout=20)
            else:
                run_capture(prefix + ["firewall-cmd", "--remove-port", f"{port_num}/{protocol}"], timeout=20)
                rc, out = run_capture(prefix + ["firewall-cmd", "--permanent", "--remove-port", f"{port_num}/{protocol}"], timeout=20)
            run_capture(prefix + ["firewall-cmd", "--reload"], timeout=20)
            return rc == 0, (out or f"firewalld {action} completed.")

    if command_exists("iptables"):
        if action == "open":
            cmd = prefix + ["iptables", "-I", "INPUT", "-p", protocol, "--dport", str(port_num), "-j", "ACCEPT"]
        else:
            cmd = prefix + ["iptables", "-D", "INPUT", "-p", protocol, "--dport", str(port_num), "-j", "ACCEPT"]
        rc, out = run_capture(cmd, timeout=20)
        return rc == 0, (out or f"iptables {action} completed.")

    return False, "No supported firewall manager found (ufw, firewalld, or iptables on Linux)."


def get_port_usage(port, protocol="tcp"):
    if not str(port).isdigit():
        return {"ok": False, "error": "Port must be numeric."}
    p = int(port)
    if p < 1 or p > 65535:
        return {"ok": False, "error": "Port out of range."}
    proto = (protocol or "tcp").strip().lower()
    listeners = []
    for item in get_listening_ports(limit=5000):
        item_proto = str(item.get("proto", "")).lower()
        if proto == "tcp" and (not item_proto.startswith("tcp")):
            continue
        if proto == "udp" and (not item_proto.startswith("udp")):
            continue
        if int(item.get("port", 0)) == p:
            listeners.append(item)
    managed_owner = False
    owner_hint = ""
    if proto == "tcp" and len(listeners) > 0:
        try:
            if os.name == "nt" and _windows_managed_python_owns_port(p, listeners):
                managed_owner = True
                owner_hint = "python-jupyter-managed"
            elif os.name == "nt" and _windows_locals3_owns_port(p):
                managed_owner = True
                owner_hint = "locals3-managed"
            elif os.name == "nt" and _windows_localmongo_owns_port(p):
                managed_owner = True
                owner_hint = "localmongo-managed"
            elif _website_owns_port(p):
                managed_owner = True
                owner_hint = "website-managed"
            elif _linux_locals3_owns_port(p):
                managed_owner = True
                owner_hint = "locals3-managed"
        except Exception:
            pass
    return {"ok": True, "busy": len(listeners) > 0, "listeners": listeners, "managed_owner": managed_owner, "owner_hint": owner_hint}


def _windows_managed_python_owns_port(port, listeners=None):
    if os.name != "nt":
        return False
    try:
        target = int(str(port).strip())
    except Exception:
        return False
    state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    if not isinstance(state, dict) or not state:
        return False
    state_port = str(state.get("port") or "").strip()
    if state_port.isdigit() and int(state_port) != target:
        return False
    pid = state.get("pid")
    try:
        pid_num = int(pid)
    except Exception:
        pid_num = 0
    active_listeners = listeners if isinstance(listeners, list) else []
    if not active_listeners:
        for item in get_listening_ports(limit=5000):
            proto = str(item.get("proto", "")).lower()
            if proto.startswith("tcp") and int(item.get("port", 0)) == target:
                active_listeners.append(item)
    if pid_num > 0 and _python_process_running(pid_num):
        for item in active_listeners:
            try:
                if int(str(item.get("pid") or "0")) == pid_num:
                    return True
            except Exception:
                continue
    for item in active_listeners:
        try:
            listener_pid = int(str(item.get("pid") or "0"))
        except Exception:
            continue
        if listener_pid <= 0:
            continue
        if _windows_process_matches_managed_jupyter(listener_pid, target):
                return True
    return False


def _safe_service_name(name):
    value = (name or "").strip()
    if not value:
        return ""
    if not re.match(r"^[A-Za-z0-9_.@-]+$", value):
        return ""
    return value


def get_windows_native_mongo_info():
    if os.name != "nt":
        return {}
    ps = (
        # Scan all LocalMongoDB-* instance directories for install-info.json, pick newest
        "$pd=$env:ProgramData; "
        "$metas=@(); "
        "Get-ChildItem -Path $pd -Filter 'LocalMongoDB-*' -Directory -ErrorAction SilentlyContinue | ForEach-Object { "
        "  $f=Join-Path $_.FullName 'install-info.json'; "
        "  if(Test-Path $f){ $metas+=[PSCustomObject]@{Path=$f;Modified=(Get-Item $f -ErrorAction SilentlyContinue).LastWriteTime} } "
        "}; "
        # Also check legacy path without instance suffix
        "$legacyMeta=Join-Path (Join-Path $pd 'LocalMongoDB') 'install-info.json'; "
        "if(Test-Path $legacyMeta){ $metas+=[PSCustomObject]@{Path=$legacyMeta;Modified=(Get-Item $legacyMeta -ErrorAction SilentlyContinue).LastWriteTime} }; "
        "$meta=if($metas.Count -gt 0){ ($metas | Sort-Object Modified -Descending | Select-Object -First 1).Path } else { $null }; "
        "$obj=[ordered]@{installed=$false;version='';connection='';port='';host='';mode='';web_version='';auth_enabled=$false;status='';admin_user='';admin_password=''}; "
        "if($meta){ "
        "  try { "
        "    $m=Get-Content -LiteralPath $meta -Raw | ConvertFrom-Json; "
        "    if($m.version){$obj.version=[string]$m.version}; "
        "    if($m.connection_string){$obj.connection=[string]$m.connection_string}; "
        "    if($m.mongo_port){$obj.port=[string]$m.mongo_port}; "
        "    if($m.host){$obj.host=[string]$m.host}; "
        "    if($m.mode){$obj.mode=[string]$m.mode}; "
        "    if($m.web_version){$obj.web_version=[string]$m.web_version}; "
        "    if($null -ne $m.auth_enabled){$obj.auth_enabled=[bool]$m.auth_enabled}; "
        "    if($m.admin_user){$obj.admin_user=[string]$m.admin_user}; "
        "    if($m.admin_password){$obj.admin_password=[string]$m.admin_password}; "
        "    $obj.installed=$true; "
        "  } catch {} "
        "  $svcName=if($m -and $m.service_name){ [string]$m.service_name } else { 'LocalMongoDB' }; "
        "  $svc=Get-Service -Name $svcName -ErrorAction SilentlyContinue; "
        "  if($svc){ $obj.installed=$true; $obj.status=[string]$svc.Status }; "
        "  $cfgDir=Split-Path $meta; "
        "  $cfg=Join-Path $cfgDir 'config\\mongod.cfg'; "
        "  if((-not $obj.port) -and (Test-Path $cfg)){ "
        "    $match=Select-String -Path $cfg -Pattern '^\\s*port\\s*:\\s*(\\d+)' -AllMatches -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "    if($match){$obj.port=[string]$match.Matches[0].Groups[1].Value} "
        "  } "
        "  if((-not $obj.version) -and (Test-Path (Join-Path $cfgDir 'mongodb\\bin\\mongod.exe'))){ "
        "    try { "
        "      $ver=& (Join-Path $cfgDir 'mongodb\\bin\\mongod.exe') --version 2>$null | Out-String; "
        "      if($ver -match 'db version v([0-9A-Za-z\\.\\-]+)'){ $obj.version=$matches[1] } "
        "    } catch {} "
        "  } "
        "} "
        "$obj | ConvertTo-Json -Depth 3"
    )
    rc, out = run_capture(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        timeout=20,
    )
    if rc != 0 or not out:
        return {}
    try:
        data = json.loads(out)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def find_windows_mongosh_exe():
    if os.name != "nt":
        return ""
    candidates = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "LocalMongoDB" / "mongosh" / "bin" / "mongosh.exe",
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "LocalMongoDB" / "mongodb" / "bin" / "mongosh.exe",
    ]
    for base in filter(None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), r"C:\Program Files"]):
        root = Path(base) / "MongoDB"
        if root.exists():
            candidates.extend(root.rglob("mongosh.exe"))
    for path in candidates:
        try:
            if path and Path(path).exists():
                return str(Path(path))
        except Exception:
            continue
    rc, out = run_capture(["where", "mongosh"], timeout=10)
    if rc == 0 and out:
        for line in out.splitlines():
            p = line.strip().strip('"')
            if p.lower().endswith("mongosh.exe") and Path(p).exists():
                return p
    return ""


def get_windows_native_mongo_uri(loopback=True, username=None, password=None):
    info = get_windows_native_mongo_info() if os.name == "nt" else {}
    port = str(info.get("port") or "27017").strip()
    configured_host = str(info.get("host") or "").strip()
    host = "127.0.0.1" if loopback else (configured_host or choose_service_host())
    if str(info.get("auth_enabled") or "").lower() in ("true", "1") or bool(info.get("auth_enabled")):
        user = str(username or "admin").strip() or "admin"
        secret = "" if password is None else str(password)
        if not secret:
            secret = "StrongPassword123"
        return (
            f"mongodb://{quote(user)}:{quote(secret)}"
            f"@{host}:{port}/admin?authSource=admin"
        )
    return f"mongodb://{host}:{port}/admin"


def run_windows_mongosh_json(body_js, timeout=40, username=None, password=None):
    if os.name != "nt":
        return False, {"error": "Windows native Mongo UI is only available on Windows."}
    mongosh = find_windows_mongosh_exe()
    if not mongosh:
        return False, {"error": "mongosh.exe not found. Re-run the Windows MongoDB installer."}
    uri = get_windows_native_mongo_uri(loopback=True, username=username, password=password)
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", str(ROOT))))
    temp_dir.mkdir(parents=True, exist_ok=True)
    script_path = temp_dir / f"codex-mongo-native-{secrets.token_hex(8)}.js"
    begin = "__CODEX_MONGO_JSON_BEGIN__"
    end = "__CODEX_MONGO_JSON_END__"
    wrapper = f"""
try {{
  const __result = (() => {{
{body_js}
  }})();
  print("{begin}");
  print(EJSON.stringify({{ ok: true, result: __result }}, null, 2));
  print("{end}");
}} catch (e) {{
  print("{begin}");
  print(EJSON.stringify({{ ok: false, error: String((e && (e.stack || e.message)) || e) }}, null, 2));
  print("{end}");
  quit(1);
}}
"""
    script_path.write_text(wrapper, encoding="utf-8")
    try:
        rc, out = run_capture([mongosh, uri, "--quiet", "--file", str(script_path)], timeout=timeout)
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
    text = out or ""
    start = text.find(begin)
    stop = text.find(end, start + len(begin)) if start >= 0 else -1
    if start < 0 or stop < 0:
        return False, {"error": (text.strip() or "mongosh did not return JSON output.")}
    payload_text = text[start + len(begin):stop].strip()
    try:
        payload = json.loads(payload_text)
    except Exception as ex:
        return False, {"error": f"Failed to parse mongosh output: {ex}", "raw": payload_text}
    if rc != 0 and payload.get("ok") is not True:
        return False, payload
    if payload.get("ok") is not True:
        return False, payload
    return True, payload.get("result")


def mongo_native_overview(username=None, password=None):
    body_js = """
const adminDb = db.getSiblingDB('admin');
const build = adminDb.runCommand({ buildInfo: 1 }) || {};
const list = adminDb.adminCommand({ listDatabases: 1, nameOnly: true }) || {};
return {
  version: build.version || "",
  databases: (list.databases || []).map((x) => ({
    name: x.name || "",
    sizeOnDisk: x.sizeOnDisk || 0,
    empty: !!x.empty
  }))
};
"""
    return run_windows_mongosh_json(body_js, timeout=40, username=username, password=password)


def mongo_native_collections(db_name, username=None, password=None):
    db_name = str(db_name or "").strip()
    if not db_name:
        return False, {"error": "Database name is required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
return {{
  database: {json.dumps(db_name)},
  collections: (targetDb.getCollectionInfos() || []).map((c) => ({{
    name: c.name || "",
    type: c.type || "collection"
  }}))
}};
"""
    return run_windows_mongosh_json(body_js, timeout=40, username=username, password=password)


def mongo_native_documents(db_name, collection_name, limit=50, username=None, password=None):
    db_name = str(db_name or "").strip()
    collection_name = str(collection_name or "").strip()
    try:
        limit = max(1, min(200, int(limit)))
    except Exception:
        limit = 50
    if not db_name or not collection_name:
        return False, {"error": "Database and collection are required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
const docs = targetDb.getCollection({json.dumps(collection_name)}).find({{}}, {{}}).limit({limit}).toArray();
return {{
  database: {json.dumps(db_name)},
  collection: {json.dumps(collection_name)},
  limit: {limit},
  documents: docs
}};
"""
    return run_windows_mongosh_json(body_js, timeout=50, username=username, password=password)


def mongo_native_run_script(db_name, script_text, username=None, password=None):
    db_name = str(db_name or "admin").strip() or "admin"
    script_text = str(script_text or "").strip()
    if not script_text:
        return False, {"error": "Script is required."}
    body_js = f"""
const db = globalThis.db.getSiblingDB({json.dumps(db_name)});
{script_text}
"""
    return run_windows_mongosh_json(body_js, timeout=60, username=username, password=password)


def _resolve_service_host(service_name, fallback):
    """Return the user-selected host stored in website state for *service_name*,
    falling back to *fallback* when no stored host is available."""
    payload = _website_state_payload(service_name)
    stored = str(payload.get("host") or "").strip()
    if stored and stored not in ("localhost", "127.0.0.1"):
        return stored
    return fallback


def get_service_items():
    items = []
    managed_patterns = re.compile(
        r"(locals3|minio|dotnet-app|dotnet|aspnet|kestrel|dotnetapp|localmongo|mongodb|mongo-express|mongod|docker|dockerd|containerd|com\.docker\.service|docker desktop service|docker engine|python|jupyter|serverinstaller-pythonjupyter)",
        re.IGNORECASE,
    )
    preferred_host = get_windows_locals3_host() or choose_service_host()
    native_mongo = get_windows_native_mongo_info() if os.name == "nt" else {}
    mongo_info = get_mongo_info()
    python_info = get_python_info()

    # Build per-instance MongoDB metadata map: service_name -> metadata dict
    all_mongo_meta: dict = {}
    if os.name == "nt":
        pd_path = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        try:
            for inst_dir in pd_path.glob("LocalMongoDB-*"):
                meta_file = inst_dir / "install-info.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
                        svc_nm = str(meta.get("service_name") or "").strip() or inst_dir.name
                        all_mongo_meta[svc_nm] = meta
                    except Exception:
                        pass
        except Exception:
            pass
        # Legacy fallback (no instance suffix)
        legacy_meta_file = pd_path / "LocalMongoDB" / "install-info.json"
        if legacy_meta_file.exists():
            try:
                meta = json.loads(legacy_meta_file.read_text(encoding="utf-8", errors="replace"))
                svc_nm = str(meta.get("service_name") or "LocalMongoDB").strip()
                if svc_nm not in all_mongo_meta:
                    all_mongo_meta[svc_nm] = meta
            except Exception:
                pass
    else:
        # Linux native installs: scan /opt/localmongodb-* directories
        try:
            for inst_dir in Path("/opt").glob("localmongodb-*"):
                meta_file = inst_dir / "install-info.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
                        svc_nm = str(meta.get("service_name") or "").strip() or inst_dir.name
                        all_mongo_meta[svc_nm] = meta
                    except Exception:
                        pass
        except Exception:
            pass

    def _mongo_service_extra(name):
        """Return ports, host, compass_uri for a native MongoDB service item."""
        inst_meta = all_mongo_meta.get(name) or native_mongo
        port_str = str(inst_meta.get("mongo_port") or inst_meta.get("port") or "").strip()
        host_val = str(inst_meta.get("host") or "").strip()
        admin_user = str(inst_meta.get("admin_user") or "admin").strip() or "admin"
        admin_password = str(inst_meta.get("admin_password") or "").strip()
        auth_enabled = bool(inst_meta.get("auth_enabled"))
        port_list = [{"port": int(port_str), "protocol": "tcp"}] if port_str.isdigit() else []
        display_host = host_val or preferred_host
        if port_str.isdigit():
            p = int(port_str)
            from urllib.parse import quote as _q
            # Native MongoDB instances always configure an admin user.
            # Always include credentials so Compass can authenticate.
            # If the password wasn't recorded in metadata (e.g. auth init failed),
            # fall back to the installer default so the URI is usable.
            credential_pass = admin_password or "StrongPassword123"
            compass_uri = f"mongodb://{_q(admin_user, safe='')}:{_q(credential_pass, safe='')}@{display_host}:{p}/admin?authSource=admin"
        else:
            compass_uri = ""
        return port_list, host_val, compass_uri, admin_user, admin_password

    if os.name == "nt":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Get-Service | Where-Object { Test-Path ('HKLM:\\SYSTEM\\CurrentControlSet\\Services\\' + $_.Name) } | Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Depth 2",
        ]
        rc, out = run_capture(cmd, timeout=60)
        if rc == 0 and out:
            try:
                raw = json.loads(out)
                rows = raw if isinstance(raw, list) else [raw]
                for row in rows:
                    name = str(row.get("Name", "")).strip()
                    if not name:
                        continue
                    display_name = str(row.get("DisplayName", "")).strip()
                    if not managed_patterns.search(f"{name} {display_name}"):
                        continue
                    if _is_mongo_name(name):
                        port_list, host_val, compass_uri, adm_user, adm_pass = _mongo_service_extra(name)
                    else:
                        port_list, host_val, compass_uri, adm_user, adm_pass = [], "", "", "", ""
                    item: dict = {
                        "kind": "service",
                        "name": name,
                        "display_name": display_name,
                        "status": str(row.get("Status", "")).strip(),
                        "start_type": str(row.get("StartType", "")).strip(),
                        "platform": "windows",
                        "urls": [],
                        "ports": port_list,
                    }
                    if _is_mongo_name(name):
                        item["host"] = host_val
                        item["compass_uri"] = compass_uri
                        item["admin_user"] = adm_user
                        item["admin_password"] = adm_pass
                    items.append(item)
            except Exception:
                pass
        # Include LocalS3 scheduled task as managed daemon.
        rc_task, out_task = run_capture(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "$t=Get-ScheduledTask -TaskName 'LocalS3-MinIO' -ErrorAction SilentlyContinue; if($t){ $i=Get-ScheduledTaskInfo -TaskName 'LocalS3-MinIO' -ErrorAction SilentlyContinue; [PSCustomObject]@{Name='LocalS3-MinIO';State=($i.State);Enabled=($t.Settings.Enabled)} | ConvertTo-Json -Depth 2 }",
            ],
            timeout=30,
        )
        if rc_task == 0 and out_task:
            try:
                task_obj = json.loads(out_task)
                task_urls = []
                task_ports = []
                if _is_locals3_name(task_obj.get("Name", "")):
                    rc_bind, out_bind = run_capture(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-Command",
                            "Import-Module WebAdministration -ErrorAction SilentlyContinue; "
                            "Get-WebBinding -Name 'LocalS3' | Select-Object protocol,bindingInformation | ConvertTo-Json -Depth 2",
                        ],
                        timeout=20,
                    )
                    if rc_bind == 0 and out_bind:
                        try:
                            raw_bind = json.loads(out_bind)
                            binds = raw_bind if isinstance(raw_bind, list) else [raw_bind]
                            seen_bind_ports: set = set()
                            for b in binds:
                                proto = str(b.get("protocol", "http") or "http").lower()
                                bind = str(b.get("bindingInformation", "") or "")
                                # IIS bindingInformation format: "IP:PORT:HOSTNAME"
                                # e.g. "*:7551:", "127.0.0.1:7551:", "192.168.1.205:7551:"
                                bind_parts = bind.split(":")
                                if len(bind_parts) < 2:
                                    continue
                                bind_ip_part = bind_parts[0].strip()
                                port_str = bind_parts[1].strip()
                                if not port_str.isdigit():
                                    continue
                                port = int(port_str)
                                # Skip loopback bindings — they exist for internal health
                                # checks only and should not appear as user-facing URLs.
                                if bind_ip_part in ("127.0.0.1", "::1"):
                                    continue
                                if port not in seen_bind_ports:
                                    task_ports.append({"port": port, "protocol": "tcp"})
                                    seen_bind_ports.add(port)
                                scheme = "https" if proto == "https" else "http"
                                # Use the specific IP from the binding when available;
                                # fall back to preferred_host for wildcard bindings.
                                host = (
                                    bind_ip_part
                                    if bind_ip_part and bind_ip_part not in ("*", "0.0.0.0", "::")
                                    else preferred_host
                                )
                                if port in (80, 443):
                                    task_urls.append(f"{scheme}://{host}")
                                else:
                                    task_urls.append(f"{scheme}://{host}:{port}")
                        except Exception:
                            pass
                    if not task_urls:
                        task_urls, task_ports = _urls_from_windows_locals3_log(preferred_host=preferred_host)
                items.append(
                    {
                        "kind": "task",
                        "name": str(task_obj.get("Name", "LocalS3-MinIO")),
                        "display_name": "LocalS3 MinIO Scheduled Task",
                        "status": str(task_obj.get("State", "") or ""),
                        "autostart": bool(task_obj.get("Enabled", True)),
                        "platform": "windows",
                        "urls": sorted(set(task_urls)),
                        "ports": task_ports,
                    }
                )
            except Exception:
                pass
        rc_py_task, out_py_task = run_capture(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "$t=Get-ScheduledTask -TaskName 'ServerInstaller-PythonJupyter' -ErrorAction SilentlyContinue; if($t){ $i=Get-ScheduledTaskInfo -TaskName 'ServerInstaller-PythonJupyter' -ErrorAction SilentlyContinue; [PSCustomObject]@{Name='ServerInstaller-PythonJupyter';State=($i.State);Enabled=($t.Settings.Enabled)} | ConvertTo-Json -Depth 2 }",
            ],
            timeout=30,
        )
        if rc_py_task == 0 and out_py_task:
            try:
                task_obj = json.loads(out_py_task)
                items.append(
                    {
                        "kind": "task",
                        "name": str(task_obj.get("Name", "ServerInstaller-PythonJupyter")),
                        "display_name": "Managed Python Jupyter Task",
                        "status": str(task_obj.get("State", "") or ""),
                        "autostart": bool(task_obj.get("Enabled", True)),
                        "platform": "windows",
                        "urls": [python_info.get("jupyter_url")] if python_info.get("jupyter_url") else [],
                        "ports": ([{"port": int(python_info.get("jupyter_port")), "protocol": "tcp"}] if str(python_info.get("jupyter_port", "")).isdigit() else []),
                    }
                )
            except Exception:
                pass

        # Include managed IIS websites.
        # Try PowerShell WebAdministration first, fall back to appcmd.exe
        iis_sites_found = False
        rc_sites, out_sites = run_capture(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Import-Module WebAdministration -ErrorAction SilentlyContinue; Get-Website | Select-Object Name,State,PhysicalPath,ServerAutoStart | ConvertTo-Json -Depth 3",
            ],
            timeout=30,
        )
        if rc_sites == 0 and out_sites:
            try:
                raw_sites = json.loads(out_sites)
                site_rows = raw_sites if isinstance(raw_sites, list) else [raw_sites]
                for s in site_rows:
                    name = str(s.get("Name", "")).strip()
                    if not name:
                        continue
                    # Include all IIS sites except the built-in default
                    if name.lower() == "default web site":
                        continue
                    urls = []
                    ports = []
                    rc_bind, out_bind = run_capture(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-Command",
                            f"Import-Module WebAdministration -ErrorAction SilentlyContinue; Get-WebBinding -Name '{name}' | Select-Object protocol,bindingInformation | ConvertTo-Json -Depth 2",
                        ],
                        timeout=20,
                    )
                    if rc_bind == 0 and out_bind:
                        try:
                            raw_bind = json.loads(out_bind)
                            binds = raw_bind if isinstance(raw_bind, list) else [raw_bind]
                            for b in binds:
                                proto = str(b.get("protocol", "http") or "http").lower()
                                bind = str(b.get("bindingInformation", "") or "")
                                port = parse_port_from_addr(bind)
                                if port and str(port).isdigit():
                                    ports.append({"port": int(port), "protocol": "tcp"})
                                    scheme = "https" if proto == "https" else "http"
                                    bind_parts = bind.split(":")
                                    bind_ip_part = bind_parts[0].strip() if bind_parts else ""
                                    host = (
                                        bind_ip_part
                                        if bind_ip_part and bind_ip_part not in ("*", "0.0.0.0", "::")
                                        else _resolve_service_host(name, preferred_host)
                                    )
                                    if int(port) in (80, 443):
                                        urls.append(f"{scheme}://{host}")
                                    else:
                                        urls.append(f"{scheme}://{host}:{port}")
                        except Exception:
                            pass
                    items.append(
                        {
                            "kind": "iis_site",
                            "name": name,
                            "display_name": str(s.get("PhysicalPath", "")).strip(),
                            "status": str(s.get("State", "")).strip(),
                            "autostart": bool(s.get("ServerAutoStart", True)),
                            "platform": "windows",
                            "urls": sorted(set(urls)),
                            "ports": ports,
                            "project_path": str(s.get("PhysicalPath", "")).strip(),
                        }
                    )
                    iis_sites_found = True
            except Exception:
                pass

        # Fallback: use appcmd.exe when WebAdministration module is unavailable
        if not iis_sites_found:
            appcmd = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "inetsrv", "appcmd.exe")
            if os.path.isfile(appcmd):
                rc_cmd, out_cmd = run_capture([appcmd, "list", "site"], timeout=20)
                if rc_cmd == 0 and out_cmd:
                    # Parse: SITE "Name" (id:N,bindings:proto/addr:port:host,...,state:State)
                    for line in out_cmd.strip().splitlines():
                        line = line.strip()
                        m = re.match(r'^SITE\s+"([^"]+)"\s+\((.+)\)\s*$', line)
                        if not m:
                            continue
                        name = m.group(1).strip()
                        if not name or name.lower() == "default web site":
                            continue
                        meta = m.group(2)
                        # Extract state
                        state_m = re.search(r'state:(\w+)', meta)
                        status = state_m.group(1) if state_m else "Unknown"
                        # Extract bindings
                        urls = []
                        ports = []
                        bind_m = re.search(r'bindings:(.+?)(?:,state:|$)', meta)
                        if bind_m:
                            for part in bind_m.group(1).split(","):
                                part = part.strip()
                                # format: proto/addr:port:host
                                slash = part.find("/")
                                if slash < 0:
                                    continue
                                proto = part[:slash].strip().lower()
                                rest = part[slash + 1:]
                                segments = rest.split(":")
                                if len(segments) >= 2:
                                    bind_ip_part = segments[0].strip() if len(segments) >= 3 else ""
                                    port_str = segments[-2] if len(segments) >= 3 else segments[-1]
                                    if port_str.isdigit():
                                        port_num = int(port_str)
                                        ports.append({"port": port_num, "protocol": "tcp"})
                                        scheme = "https" if proto == "https" else "http"
                                        appcmd_host = (
                                            bind_ip_part
                                            if bind_ip_part and bind_ip_part not in ("*", "0.0.0.0", "::")
                                            else _resolve_service_host(name, preferred_host)
                                        )
                                        if port_num in (80, 443):
                                            urls.append(f"{scheme}://{appcmd_host}")
                                        else:
                                            urls.append(f"{scheme}://{appcmd_host}:{port_num}")
                        # Deduplicate
                        seen_ports = set()
                        deduped_ports = []
                        for pp in ports:
                            if pp["port"] not in seen_ports:
                                seen_ports.add(pp["port"])
                                deduped_ports.append(pp)
                        items.append(
                            {
                                "kind": "iis_site",
                                "name": name,
                                "display_name": name,
                                "status": status,
                                "autostart": True,
                                "platform": "windows",
                                "urls": sorted(set(urls)),
                                "ports": deduped_ports,
                            }
                        )
    elif command_exists("systemctl"):
        rc, out = run_capture(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend"],
            timeout=60,
        )
        if rc == 0 and out:
            for line in out.splitlines():
                text = line.rstrip()
                if not text:
                    continue
                parts = [p for p in text.split() if p]
                if len(parts) < 4:
                    continue
                name = parts[0]
                load = parts[1]
                active = parts[2]
                sub = parts[3]
                desc = " ".join(parts[4:]) if len(parts) > 4 else ""
                if not managed_patterns.search(f"{name} {desc}"):
                    continue
                active_state = active
                sub_state = sub
                unit_desc = desc
                unit_file_state = ""
                rc_show, out_show = run_capture(
                    ["systemctl", "show", name, "-p", "ActiveState", "-p", "SubState", "-p", "UnitFileState", "-p", "Description"],
                    timeout=20,
                )
                if rc_show == 0 and out_show:
                    for raw_line in out_show.splitlines():
                        line = str(raw_line or "").strip()
                        if line.startswith("ActiveState="):
                            active_state = line.split("=", 1)[1].strip() or active_state
                        elif line.startswith("SubState="):
                            sub_state = line.split("=", 1)[1].strip() or sub_state
                        elif line.startswith("UnitFileState="):
                            unit_file_state = line.split("=", 1)[1].strip().lower()
                        elif line.startswith("Description="):
                            unit_desc = line.split("=", 1)[1].strip() or unit_desc
                if not unit_file_state:
                    rc_enabled, out_enabled = run_capture(["systemctl", "is-enabled", name], timeout=20)
                    if rc_enabled == 0:
                        unit_file_state = str(out_enabled or "").strip().lower()
                autostart = unit_file_state in ("enabled", "static")
                urls = []
                ports = []
                base_name = name.replace(".service", "")
                if _is_locals3_name(base_name):
                    # Derive the instance name from the service name (e.g. "locals3-minio" -> "locals3", "foo-minio" -> "foo")
                    inst_name = re.sub(r"[-_](?:minio|nginx)$", "", base_name, flags=re.IGNORECASE) or "locals3"
                    urls, ports = _urls_from_nginx_conf(f"/etc/nginx/conf.d/{inst_name}.conf", preferred_host=preferred_host)
                    if not urls:
                        urls, ports = _urls_from_nginx_conf(f"/opt/{inst_name}/nginx/nginx-standalone.conf", preferred_host=preferred_host)
                    # Add direct MinIO ports from all instance service files
                    for mp in _get_linux_minio_direct_ports():
                        if not any(p.get("port") == mp["port"] for p in ports):
                            ports.append(mp)
                else:
                    urls, ports = _urls_from_nginx_conf(f"/etc/nginx/conf.d/{base_name}.conf", preferred_host=_resolve_service_host(name, preferred_host))
                items.append(
                    {
                        "kind": "service",
                        "name": name,
                        "display_name": unit_desc,
                        "status": active_state,
                        "sub_status": sub_state,
                        "load": load,
                        "autostart": autostart,
                        "platform": "linux",
                        "urls": urls,
                        "ports": ports,
                    }
                )

    if command_exists("docker"):
        rc, out = run_capture(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Labels}}"], timeout=30)
        if rc == 0 and out:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                name = parts[0].strip()
                status = parts[1].strip()
                image = parts[2].strip()
                labels = parts[3].strip() if len(parts) > 3 else ""
                if not name:
                    continue
                managed = ("com.locals3.installer=true" in labels) or managed_patterns.search(f"{name} {image}") is not None
                if not managed and "com.localmongo.installer=true" in labels:
                    managed = True
                if not managed:
                    continue
                details = _get_docker_container_details(name)
                restart_policy = details.get("restart_policy", "")
                ports = list(details.get("ports", []))
                container_labels = details.get("labels", {})
                # Collect all ports labelled as HTTPS by the container
                https_ports_set = set()
                for label_key in ("com.serverinstaller.https_port", "com.serverinstaller.https_console_port"):
                    val = str(container_labels.get(label_key, "") or "").strip()
                    if val.isdigit():
                        hp = int(val)
                        https_ports_set.add(hp)
                        if not any(p.get("port") == hp for p in ports):
                            ports.append({"port": hp, "protocol": "tcp"})
                # Keep backwards-compat alias
                nginx_https_port_str = str(container_labels.get("com.serverinstaller.https_port", "") or "").strip()
                urls = []
                docker_host = _resolve_service_host(name, preferred_host)
                for p in ports:
                    p_port = p.get("port")
                    scheme = "https" if (
                        p_port == 443 or
                        p_port in https_ports_set or
                        container_labels.get("com.localmongo.role") == "https"
                    ) else "http"
                    host = docker_host
                    if container_labels.get("com.localmongo.role") == "mongodb":
                        continue
                    if p_port in (80, 443):
                        urls.append(f"{scheme}://{host}")
                    else:
                        urls.append(f"{scheme}://{host}:{p_port}")
                items.append(
                    {
                        "kind": "docker",
                        "name": name,
                        "display_name": details.get("image") or image,
                        "status": details.get("state") or status,
                        "autostart": restart_policy in ("always", "unless-stopped"),
                        "platform": "docker",
                        "urls": sorted(set(urls)),
                        "ports": ports,
                    }
                )

    has_mongo_items = any(_is_mongo_name(x.get("name", "")) or _is_mongo_name(x.get("display_name", "")) for x in items)
    if (not has_mongo_items) and mongo_info.get("installed"):
        fallback_ports = []
        fallback_urls = []
        connection = str(mongo_info.get("connection_string") or "").strip()
        https_url = str(mongo_info.get("https_url") or "").strip()
        if connection:
            try:
                port_text = connection.replace("mongodb://", "").split("/", 1)[0].rsplit(":", 1)[1]
                if str(port_text).isdigit():
                    fallback_ports.append({"port": int(port_text), "protocol": "tcp"})
            except Exception:
                pass
        if https_url:
            fallback_urls.append(https_url)

        if os.name == "nt":
            items.append(
                {
                    "kind": "service",
                    "name": "LocalMongoDB",
                    "display_name": "MongoDB Windows Service",
                    "status": str(native_mongo.get("status") or "Running"),
                    "start_type": "Automatic",
                    "platform": "windows",
                    "urls": fallback_urls,
                    "ports": fallback_ports,
                }
            )
        elif command_exists("systemctl"):
            items.append(
                {
                    "kind": "service",
                    "name": "localmongo-stack.service",
                    "display_name": "LocalMongoDB",
                    "status": "active",
                    "sub_status": "running",
                    "autostart": True,
                    "platform": "linux",
                    "urls": fallback_urls,
                    "ports": fallback_ports,
                }
            )
        else:
            items.append(
                {
                    "kind": "docker",
                    "name": "localmongo-mongodb",
                    "display_name": f"MongoDB {mongo_info.get('server_version') or ''}".strip(),
                    "status": "running",
                    "autostart": True,
                    "platform": "docker",
                    "urls": fallback_urls,
                    "ports": fallback_ports,
                }
            )

    has_python_items = any(_is_python_name(x.get("name", "")) or _is_python_name(x.get("display_name", "")) for x in items)
    if (not has_python_items) and python_info.get("installed"):
        items.extend(_python_state_service_item(python_info))

    items.sort(key=lambda x: (x.get("kind", ""), x.get("name", "").lower()))
    return items


def _is_locals3_name(name):
    return bool(re.search(r"locals3|minio", str(name or ""), re.IGNORECASE))


def _is_website_name(name):
    return bool(_website_state_payload(name))


def _is_dotnet_name(name):
    return bool(re.search(r"dotnet|aspnet|kestrel|dotnetapp", str(name or ""), re.IGNORECASE))


def _is_mongo_name(name):
    return bool(re.search(r"localmongo|mongodb|mongo-express|mongod", str(name or ""), re.IGNORECASE))


def _is_proxy_name(name):
    return bool(re.search(r"proxy-panel|serverinstaller-proxywsl|xray|stunnel4|stunnel|nginx|ssh", str(name or ""), re.IGNORECASE))


def _is_docker_name(name):
    return bool(re.search(r"docker|dockerd|containerd|com\.docker\.service|docker desktop service|docker engine", str(name or ""), re.IGNORECASE))


def _is_python_name(name):
    return bool(re.search(r"python|jupyter", str(name or ""), re.IGNORECASE))


def _proxy_service_probe(units, prefix=None):
    prefix = prefix or []
    results = []
    for unit in units:
        display = unit
        actual = unit if unit.endswith(".service") else f"{unit}.service"
        rc, out = run_capture(prefix + ["systemctl", "show", actual, "--property=Id,ActiveState,SubState,UnitFileState", "--no-pager"], timeout=15)
        if rc != 0:
            continue
        row = {}
        for line in (out or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                row[k.strip()] = v.strip()
        active = row.get("ActiveState", "")
        sub = row.get("SubState", "")
        results.append({
            "kind": "service",
            "name": row.get("Id", actual),
            "display_name": display,
            "status": active,
            "sub_status": sub,
            "autostart": row.get("UnitFileState", "") == "enabled",
        })
    return results


def get_proxy_info():
    info = {
        "available": PROXY_ROOT.exists(),
        "installed": False,
        "layer": "",
        "panel_url": "",
        "services": [],
        "mode": "native" if os.name != "nt" else "wsl",
        "distro": "",
    }
    if not info["available"]:
        return info

    if os.name == "nt":
        state = _read_json_file(PROXY_WINDOWS_STATE)
        distro = str(state.get("distro") or os.environ.get("PROXY_WSL_DISTRO", "Ubuntu")).strip()
        state_port = str(state.get("port") or "8443").strip()
        state_host = str(state.get("host") or choose_service_host() or "127.0.0.1").strip()
        info["distro"] = distro
        info["layer"] = str(state.get("layer") or "").strip()
        info["panel_url"] = str(state.get("url") or f"https://{state_host}:{state_port}").strip()
        rc, out = run_capture(["wsl.exe", "-d", distro, "--user", "root", "--", "bash", "-lc", "if [ -f /opt/proxy-panel/panel.conf ]; then cat /opt/proxy-panel/panel.conf; fi"], timeout=20)
        if rc == 0 and out.strip():
            try:
                conf = json.loads(out)
                info["installed"] = True
                info["layer"] = str(conf.get("layer") or info["layer"]).strip()
                port = str(conf.get("port") or "8443").strip()
                info["panel_url"] = f"https://{state_host}:{port}"
            except Exception:
                pass
        info["services"] = [
            {
                "kind": "task",
                "name": "ServerInstaller-ProxyWSL",
                "display_name": f"Proxy WSL Autostart ({distro})",
                "status": "ready" if info["installed"] else "stopped",
                "sub_status": "",
                "autostart": info["installed"],
            }
        ]
        probe_script = "systemctl is-active proxy-panel xray stunnel4 nginx 2>/dev/null || true"
        rc, out = run_capture(["wsl.exe", "-d", distro, "--user", "root", "--", "bash", "-lc", probe_script], timeout=20)
        if rc == 0 and info["installed"]:
            info["services"].append({
                "kind": "service",
                "name": "proxy-panel",
                "display_name": f"WSL proxy services ({distro})",
                "status": "active" if "active" in (out or "") else "unknown",
                "sub_status": "",
                "autostart": True,
            })
        return info

    native_state = _read_json_file(PROXY_NATIVE_STATE)
    conf = _read_json_file("/opt/proxy-panel/panel.conf")
    if conf:
        info["installed"] = True
        info["layer"] = str(conf.get("layer") or "").strip()
        port = str(conf.get("port") or "8443").strip()
        host = str(native_state.get("host") or choose_service_host()).strip() or choose_service_host()
        info["panel_url"] = f"https://{host}:{port}"
    units = ["proxy-panel", "xray", "stunnel4", "nginx", "ssh"]
    info["services"] = _proxy_service_probe(units, prefix=_sudo_prefix()) if command_exists("systemctl") else []
    return info


def _is_sam3_name(name):
    low = str(name or "").lower()
    return "sam3" in low or "serverinstaller-sam3" in low


def get_sam3_info():
    state = _read_json_file(SAM3_STATE_FILE)
    # Compute default paths (always available, even before install)
    default_install_dir = str(SAM3_STATE_DIR / "app")
    default_model_dir = str(SAM3_STATE_DIR / "app" / "models")
    default_model_path = str(SAM3_STATE_DIR / "app" / "models" / "sam3.pt")
    # Use state values if available, otherwise defaults
    model_path = str(state.get("model_path") or "").strip() or default_model_path
    install_dir = str(state.get("install_dir") or "").strip() or default_install_dir
    model_dir = str(Path(model_path).parent) if model_path else default_model_dir
    # Check actual file on disk
    model_exists = Path(model_path).exists() and Path(model_path).stat().st_size > 1000000
    # "installed" means the service was set up (state file has service_name and install_dir)
    _has_service = bool(state.get("service_name")) and bool(state.get("install_dir"))
    if _has_service and os.name != "nt":
        _has_service = Path(f"/etc/systemd/system/{SAM3_SYSTEMD_SERVICE}.service").exists()
    elif _has_service and os.name == "nt":
        _has_service = bool(state.get("install_dir")) and Path(str(state.get("install_dir") or "")).exists()
    info = {
        "installed": _has_service,
        "service_name": str(state.get("service_name") or "").strip(),
        "install_dir": install_dir,
        "venv_dir": str(state.get("venv_dir") or "").strip(),
        "python_executable": str(state.get("python_executable") or "").strip(),
        "model_path": model_path,
        "model_dir": model_dir,
        "default_model_dir": default_model_dir,
        "model_downloaded": model_exists,
        "device": str(state.get("device") or "cpu").strip(),
        "detected_gpus": state.get("detected_gpus") or [],
        "detected_gpu_type": str(state.get("detected_gpu_type") or "").strip(),
        "detected_gpu_name": str(state.get("detected_gpu_name") or "").strip(),
        "detected_gpu_vram": str(state.get("detected_gpu_vram") or "").strip(),
        "host": str(state.get("host") or "").strip(),
        "domain": str(state.get("domain") or "").strip(),
        "http_port": str(state.get("http_port") or "5000").strip(),
        "https_port": str(state.get("https_port") or "5443").strip(),
        "http_url": str(state.get("http_url") or "").strip(),
        "https_url": str(state.get("https_url") or "").strip(),
        "deploy_mode": str(state.get("deploy_mode") or "os").strip(),
        "auth_enabled": bool(state.get("auth_enabled")),
        "auth_username": str(state.get("auth_username") or "").strip(),
        "use_os_auth": bool(state.get("use_os_auth")),
        "cert_path": str(state.get("cert_path") or "").strip(),
        "key_path": str(state.get("key_path") or "").strip(),
        "running": bool(state.get("running")),
        "services": [],
    }
    # Always rebuild URLs from host + port to ensure the user-selected IP is used
    _url_host = info.get("domain") or info["host"] or ""
    if not _url_host or _url_host in ("0.0.0.0", "*"):
        _url_host = choose_service_host() or "127.0.0.1"
    if info["http_port"]:
        info["http_url"] = f"http://{_url_host}:{info['http_port']}"
    if info["https_port"] and info["https_port"] not in ("0", ""):
        info["https_url"] = f"https://{_url_host}:{info['https_port']}"
    # Check systemd service status on Linux
    if os.name != "nt" and info["installed"] and command_exists("systemctl"):
        service_status = _linux_systemd_unit_status(f"{SAM3_SYSTEMD_SERVICE}.service")
        info["running"] = bool(service_status.get("running"))
        info["service_sub_status"] = str(service_status.get("active") or "")
        info["service_autostart"] = bool(service_status.get("autostart"))
        info["services"].append({
            "name": SAM3_SYSTEMD_SERVICE,
            "display_name": "SAM3 AI Detection Service",
            "kind": "systemd",
            "status": "running" if service_status.get("running") else "stopped",
            "sub_status": str(service_status.get("active") or ""),
            "manageable": True,
            "deletable": True,
            "project_path": info["install_dir"],
            "ports": [p for p in [info["http_port"], info["https_port"]] if p],
            "urls": [u for u in [info["http_url"], info["https_url"]] if u],
        })
    # Check Windows: scheduled task, NSSM service, or running process
    elif os.name == "nt" and info["installed"]:
        svc_name = str(state.get("service_name") or "ServerInstaller-SAM3")
        # Check if running: try sc.exe, then schtasks, then check port
        try:
            rc, out = run_capture(["sc.exe", "query", svc_name], timeout=10)
            if rc == 0 and "RUNNING" in out.upper():
                info["running"] = True
        except Exception:
            pass
        if not info["running"]:
            try:
                rc, out = run_capture(["schtasks", "/Query", "/TN", svc_name, "/FO", "CSV"], timeout=10)
                if rc == 0 and "Running" in out:
                    info["running"] = True
            except Exception:
                pass
        if not info["running"]:
            # Check if SAM3 port is listening
            http_p = str(state.get("http_port") or "").strip()
            if http_p.isdigit():
                try:
                    import subprocess
                    r = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-Command",
                         f"Get-NetTCPConnection -LocalPort {http_p} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1"],
                        capture_output=True, text=True, timeout=10
                    )
                    if r.stdout.strip():
                        info["running"] = True
                except Exception:
                    pass
        info["services"].append({
            "name": svc_name,
            "display_name": "SAM3 AI Detection Service",
            "kind": "service",
            "status": "running" if info.get("running") else "stopped",
            "manageable": True,
            "deletable": True,
            "project_path": info["install_dir"],
            "ports": [p for p in [info["http_port"], info["https_port"]] if p],
            "urls": [u for u in [info["http_url"], info["https_url"]] if u],
        })
    # Re-check model file on disk (may have been downloaded separately)
    if not info["model_downloaded"] and info["model_path"] and Path(info["model_path"]).exists():
        if Path(info["model_path"]).stat().st_size > 1000000:
            info["model_downloaded"] = True
    return info


# ── Generic AI service info helper ──────────────────────────────────────────
def _get_ai_service_info(state_file, state_dir, systemd_service, display_name, default_port="11434"):
    """Generic info builder for AI services (Ollama, TGWUI, ComfyUI, Whisper, Piper)."""
    state = _read_json_file(state_file)
    default_install_dir = str(state_dir / "app")
    install_dir = str(state.get("install_dir") or "").strip() or default_install_dir
    _has_service = bool(state.get("service_name")) and bool(state.get("install_dir") or state.get("installed"))
    if _has_service and os.name != "nt":
        _has_service = Path(f"/etc/systemd/system/{systemd_service}.service").exists() or bool(state.get("installed"))
    elif _has_service and os.name == "nt":
        _has_service = bool(state.get("install_dir")) and Path(str(state.get("install_dir") or "")).exists() or bool(state.get("installed"))
    # Also check if the binary exists even without state
    if not _has_service:
        bin_name = systemd_service.replace("serverinstaller-", "")
        if command_exists(bin_name):
            _has_service = True
    info = {
        "installed": _has_service,
        "service_name": str(state.get("service_name") or systemd_service).strip(),
        "install_dir": install_dir,
        "host": str(state.get("host") or "").strip(),
        "domain": str(state.get("domain") or "").strip(),
        "http_port": str(state.get("http_port") or (default_port if _has_service else "")).strip(),
        "https_port": str(state.get("https_port") or "").strip(),
        "http_url": str(state.get("http_url") or "").strip(),
        "https_url": str(state.get("https_url") or "").strip(),
        "deploy_mode": str(state.get("deploy_mode") or "os").strip(),
        "auth_enabled": bool(state.get("auth_enabled")),
        "auth_username": str(state.get("auth_username") or "").strip(),
        "running": bool(state.get("running")),
        "device": str(state.get("device") or "cpu").strip(),
        "detected_gpu_name": str(state.get("detected_gpu_name") or "").strip(),
        "model_size": str(state.get("model_size") or "").strip(),
        "voice": str(state.get("voice") or "").strip(),
        "version": str(state.get("version") or "").strip(),
        "services": [],
    }
    # Always rebuild URLs from host + port to match user-selected IP
    _url_host = info.get("domain") or info["host"] or ""
    if not _url_host or _url_host in ("0.0.0.0", "*"):
        _url_host = choose_service_host() or "127.0.0.1"
    if info["http_port"]:
        info["http_url"] = f"http://{_url_host}:{info['http_port']}"
    if info.get("https_port") and info["https_port"] not in ("0", ""):
        info["https_url"] = f"https://{_url_host}:{info['https_port']}"
    # Check systemd service status on Linux
    if os.name != "nt" and info["installed"] and command_exists("systemctl"):
        svc_status = _linux_systemd_unit_status(f"{systemd_service}.service")
        info["running"] = bool(svc_status.get("running"))
        info["services"].append({
            "name": systemd_service, "display_name": display_name,
            "kind": "systemd",
            "status": "running" if svc_status.get("running") else "stopped",
            "sub_status": str(svc_status.get("active") or ""),
            "manageable": True, "deletable": True,
            "project_path": info["install_dir"],
            "ports": [p for p in [info["http_port"], info["https_port"]] if p],
            "urls": [u for u in [info["http_url"], info["https_url"]] if u],
        })
    elif sys.platform == "darwin" and info["installed"]:
        # macOS: check launchd plist or running background process
        _macos_running = False
        # Check launchd
        plist_path = f"/Library/LaunchDaemons/{systemd_service}.plist"
        plist_user = str(Path.home() / "Library" / "LaunchAgents" / f"{systemd_service}.plist")
        if Path(plist_path).exists() or Path(plist_user).exists():
            try:
                rc, out = run_capture(["launchctl", "list", systemd_service], timeout=5)
                _macos_running = rc == 0
            except Exception:
                pass
        # Check if port is listening (background process)
        if not _macos_running:
            hp = str(info.get("http_port") or "").strip()
            if hp.isdigit():
                try:
                    _macos_running = is_local_tcp_port_listening(int(hp))
                except Exception:
                    pass
        # Check if the binary process is running
        if not _macos_running:
            bin_name = systemd_service.replace("serverinstaller-", "")
            try:
                rc, out = run_capture(["pgrep", "-f", bin_name], timeout=5)
                if rc == 0 and out.strip():
                    _macos_running = True
            except Exception:
                pass
        info["running"] = _macos_running
        info["services"].append({
            "name": systemd_service, "display_name": display_name,
            "kind": "launchd" if (Path(plist_path).exists() or Path(plist_user).exists()) else "process",
            "status": "running" if _macos_running else "stopped",
            "manageable": True, "deletable": True,
            "project_path": info["install_dir"],
            "ports": [p for p in [info["http_port"], info["https_port"]] if p],
            "urls": [u for u in [info["http_url"], info["https_url"]] if u],
        })
    elif os.name == "nt" and info["installed"]:
        svc_name = str(state.get("service_name") or systemd_service.replace("serverinstaller-", "ServerInstaller-").title())
        # Check if running
        try:
            rc, out = run_capture(["sc.exe", "query", svc_name], timeout=10)
            if rc == 0 and "RUNNING" in out.upper():
                info["running"] = True
        except Exception:
            pass
        if not info["running"]:
            try:
                rc, out = run_capture(["schtasks", "/Query", "/TN", svc_name, "/FO", "CSV"], timeout=10)
                if rc == 0 and "Running" in out:
                    info["running"] = True
            except Exception:
                pass
        if not info["running"]:
            hp = str(state.get("http_port") or "").strip()
            if hp.isdigit() and is_local_tcp_port_listening(int(hp)):
                info["running"] = True
        info["services"].append({
            "name": svc_name, "display_name": display_name,
            "kind": "service",
            "status": "running" if info.get("running") else "stopped",
            "manageable": True, "deletable": True,
            "project_path": info["install_dir"],
            "ports": [p for p in [info["http_port"], info["https_port"]] if p],
            "urls": [u for u in [info["http_url"], info["https_url"]] if u],
        })
    # Also check if port is listening even without service registration
    if not info["running"] and info["http_port"]:
        try:
            if is_local_tcp_port_listening(int(info["http_port"])):
                info["running"] = True
                if not info["services"]:
                    info["services"].append({
                        "name": systemd_service, "display_name": display_name,
                        "kind": "process", "status": "running",
                        "manageable": True, "deletable": False,
                        "ports": [info["http_port"]],
                        "urls": [info["http_url"]] if info["http_url"] else [],
                    })
        except Exception:
            pass
    return info


def get_ollama_info():
    return _get_ai_service_info(OLLAMA_STATE_FILE, OLLAMA_STATE_DIR, OLLAMA_SYSTEMD_SERVICE, "Ollama LLM Service", "11434")


def get_openclaw_info():
    info = _get_ai_service_info(OPENCLAW_STATE_FILE, OPENCLAW_STATE_DIR, OPENCLAW_SYSTEMD_SERVICE, "OpenClaw Agent", "18789")
    # Also check the real gateway service (clawdbot-gateway)
    if not info.get("running") and os.name != "nt" and command_exists("systemctl"):
        try:
            svc_status = _linux_systemd_unit_status("clawdbot-gateway.service")
            if svc_status.get("running"):
                info["running"] = True
                info["installed"] = True
        except Exception:
            pass
    return info


def get_lmstudio_info():
    return _get_ai_service_info(LMSTUDIO_STATE_FILE, LMSTUDIO_STATE_DIR, LMSTUDIO_SYSTEMD_SERVICE, "LM Studio", "1234")


def get_tgwui_info():
    return _get_ai_service_info(TGWUI_STATE_FILE, TGWUI_STATE_DIR, TGWUI_SYSTEMD_SERVICE, "Text Generation WebUI", "7860")


def get_comfyui_info():
    return _get_ai_service_info(COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, COMFYUI_SYSTEMD_SERVICE, "ComfyUI", "8188")


def get_whisper_info():
    return _get_ai_service_info(WHISPER_STATE_FILE, WHISPER_STATE_DIR, WHISPER_SYSTEMD_SERVICE, "Whisper STT Service", "9000")


def get_piper_info():
    return _get_ai_service_info(PIPER_STATE_FILE, PIPER_STATE_DIR, PIPER_SYSTEMD_SERVICE, "Piper TTS Service", "5500")


# ── Generic AI service installer ────────────────────────────────────────────
def _run_ai_service_install(service_id, form, state_file, state_dir, systemd_service, display_name, default_port, install_cmd_map, live_cb=None):
    """Generic installer for AI services. install_cmd_map = {os_name: [commands]}."""
    form = form or {}
    output_lines = []
    def log(msg):
        output_lines.append(msg)
        if live_cb:
            live_cb(msg + "\n")

    host_ip = (form.get(f"{service_id.upper()}_HOST_IP", [""])[0] or "").strip() or "0.0.0.0"
    http_port = (form.get(f"{service_id.upper()}_HTTP_PORT", [default_port])[0] or default_port).strip()
    https_port = (form.get(f"{service_id.upper()}_HTTPS_PORT", [""])[0] or "").strip()
    domain = (form.get(f"{service_id.upper()}_DOMAIN", [""])[0] or "").strip()
    username = (form.get(f"{service_id.upper()}_USERNAME", [""])[0] or "").strip()
    password = (form.get(f"{service_id.upper()}_PASSWORD", [""])[0] or "").strip()
    extra = {}
    for k, v in form.items():
        if k.startswith(f"{service_id.upper()}_"):
            extra[k] = (v[0] if isinstance(v, list) else v)

    log(f"=== Installing {display_name} ===")
    log(f"Host: {host_ip}, Port: {http_port}")

    state_dir.mkdir(parents=True, exist_ok=True)
    install_dir = state_dir / "app"

    # Determine host for URL
    host = domain or (host_ip if host_ip not in ("", "*", "0.0.0.0") else choose_service_host())
    http_url = f"http://{host}:{http_port}" if http_port else ""
    https_url = f"https://{host}:{https_port}" if https_port else ""

    # Run install commands
    cmds = install_cmd_map.get(os.name, install_cmd_map.get("posix", []))
    code = 0
    for cmd in cmds:
        if callable(cmd):
            code = cmd(log, install_dir, form, extra)
        elif isinstance(cmd, str):
            code = _run_install_cmd(cmd, log, timeout=600)
        else:
            code = _run_install_cmd(cmd, log, timeout=600)
        if code != 0:
            log(f"Command failed with code {code}")
            break

    if code == 0:
        # Save state
        state = _read_json_file(state_file)
        state.update({
            "installed": True,
            "service_name": systemd_service,
            "install_dir": str(install_dir),
            "host": host_ip,
            "domain": domain,
            "http_port": http_port,
            "https_port": https_port,
            "http_url": http_url,
            "https_url": https_url,
            "deploy_mode": "os",
            "auth_enabled": bool(username),
            "auth_username": username,
        })
        state.update({k.lower(): v for k, v in extra.items()})
        _write_json_file(state_file, state)

        # Open firewall
        if http_port:
            manage_firewall_port("open", http_port, "tcp", host=host)
        if https_port:
            manage_firewall_port("open", https_port, "tcp", host=host)

        log(f"\n=== {display_name} installed successfully ===")
        if http_url:
            log(f"URL: {http_url}")

    return code, "\n".join(output_lines)


def _install_ollama_os(log, install_dir, form, extra):
    """Install Ollama binary."""
    if command_exists("ollama"):
        log("Ollama is already installed.")
        return 0
    if os.name == "nt":
        log("Installing Ollama for Windows...")
        code = _run_install_cmd(["winget", "install", "-e", "--id", "Ollama.Ollama", "--accept-package-agreements", "--accept-source-agreements"], log, timeout=300)
        if code != 0:
            log("Trying direct download...")
            code = _run_install_cmd("powershell.exe -NoProfile -Command \"Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%TEMP%\\OllamaSetup.exe'; Start-Process '%TEMP%\\OllamaSetup.exe' -ArgumentList '/S' -Wait\"", log, timeout=300)
        return code
    else:
        log("Installing Ollama via official script...")
        return _run_install_cmd("curl -fsSL https://ollama.com/install.sh | sh", log, timeout=300)


def _install_tgwui_os(log, install_dir, form, extra):
    """Install Text Generation WebUI."""
    install_dir = Path(install_dir)
    if install_dir.exists() and (install_dir / "server.py").exists():
        log("Text Generation WebUI already installed.")
        return 0
    log("Cloning Text Generation WebUI repository...")
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    code = _run_install_cmd(["git", "clone", "https://github.com/oobabooga/text-generation-webui.git", str(install_dir)], log, timeout=600)
    if code != 0:
        return code
    log("Running one-click installer...")
    if os.name == "nt":
        start_script = install_dir / "start_windows.bat"
        if start_script.exists():
            code = _run_install_cmd([str(start_script), "--auto-launch", "--listen"], log, timeout=900)
    else:
        start_script = install_dir / "start_linux.sh"
        if start_script.exists():
            code = _run_install_cmd(["bash", str(start_script), "--auto-launch", "--listen"], log, timeout=900)
        else:
            log("Setting up Python venv...")
            code = _run_install_cmd(f"cd {install_dir} && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt", log, timeout=900)
    return code


def _install_comfyui_os(log, install_dir, form, extra):
    """Install ComfyUI."""
    install_dir = Path(install_dir)
    if install_dir.exists() and (install_dir / "main.py").exists():
        log("ComfyUI already installed.")
        return 0
    log("Cloning ComfyUI repository...")
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    code = _run_install_cmd(["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(install_dir)], log, timeout=600)
    if code != 0:
        return code
    log("Installing Python dependencies...")
    if os.name == "nt":
        code = _run_install_cmd(f"cd /d \"{install_dir}\" && python -m venv venv && venv\\Scripts\\pip install -r requirements.txt", log, timeout=600)
    else:
        code = _run_install_cmd(f"cd \"{install_dir}\" && python3 -m venv venv && venv/bin/pip install -r requirements.txt", log, timeout=600)
    return code


def _install_whisper_os(log, install_dir, form, extra):
    """Install Whisper API server."""
    install_dir = Path(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)
    model_size = extra.get("WHISPER_MODEL_SIZE", "base")
    log(f"Installing Whisper with model size: {model_size}")
    if os.name == "nt":
        code = _run_install_cmd(f"cd /d \"{install_dir}\" && python -m venv venv && venv\\Scripts\\pip install openai-whisper faster-whisper flask", log, timeout=600)
    else:
        code = _run_install_cmd(f"cd \"{install_dir}\" && python3 -m venv venv && venv/bin/pip install openai-whisper faster-whisper flask", log, timeout=600)
    if code != 0:
        return code
    # Create a simple Flask server for Whisper
    server_py = install_dir / "whisper_server.py"
    server_py.write_text(f'''#!/usr/bin/env python3
"""Whisper speech-to-text API server."""
import os, sys, json, tempfile
from flask import Flask, request, jsonify
app = Flask(__name__)
model = None
MODEL_SIZE = "{model_size}"

def get_model():
    global model
    if model is None:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(MODEL_SIZE, device="auto", compute_type="auto")
        except Exception:
            import whisper
            model = whisper.load_model(MODEL_SIZE)
    return model

@app.route("/", methods=["GET"])
def index():
    return jsonify({{"service": "whisper", "model": MODEL_SIZE, "status": "running"}})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({{"error": "No audio file provided"}}), 400
    audio = request.files["audio"]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio.save(tmp.name)
        tmp_path = tmp.name
    try:
        m = get_model()
        if hasattr(m, "transcribe") and hasattr(m.transcribe, "__code__"):
            # faster-whisper
            segments, info = m.transcribe(tmp_path)
            text = " ".join([s.text for s in segments])
            return jsonify({{"ok": True, "text": text.strip(), "language": info.language}})
        else:
            result = m.transcribe(tmp_path)
            return jsonify({{"ok": True, "text": result["text"].strip(), "language": result.get("language", "")}})
    except Exception as e:
        return jsonify({{"ok": False, "error": str(e)}}), 500
    finally:
        os.unlink(tmp_path)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({{"ok": True, "status": "healthy", "model": MODEL_SIZE}})

if __name__ == "__main__":
    port = int(os.environ.get("WHISPER_PORT", "9000"))
    host = os.environ.get("WHISPER_HOST", "0.0.0.0")
    app.run(host=host, port=port)
''', encoding="utf-8")
    log("Whisper server created successfully.")
    return 0


def _install_piper_os(log, install_dir, form, extra):
    """Install Piper TTS."""
    install_dir = Path(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)
    voice = extra.get("PIPER_VOICE", "en_US-lessac-medium")
    log(f"Installing Piper TTS with voice: {voice}")
    if os.name == "nt":
        code = _run_install_cmd(f"cd /d \"{install_dir}\" && python -m venv venv && venv\\Scripts\\pip install piper-tts flask", log, timeout=600)
    else:
        # Try system package first
        if command_exists("apt-get"):
            _run_install_cmd(["apt-get", "install", "-y", "piper"], log, timeout=120)
        code = _run_install_cmd(f"cd \"{install_dir}\" && python3 -m venv venv && venv/bin/pip install piper-tts flask", log, timeout=600)
    if code != 0:
        return code
    # Create a simple Flask server for Piper
    server_py = install_dir / "piper_server.py"
    server_py.write_text(f'''#!/usr/bin/env python3
"""Piper text-to-speech API server."""
import os, io, subprocess, tempfile
from flask import Flask, request, jsonify, send_file
app = Flask(__name__)
DEFAULT_VOICE = "{voice}"

@app.route("/", methods=["GET"])
def index():
    return jsonify({{"service": "piper-tts", "voice": DEFAULT_VOICE, "status": "running"}})

@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {{}}
    text = data.get("text", "") or request.form.get("text", "")
    voice_name = data.get("voice", DEFAULT_VOICE)
    if not text:
        return jsonify({{"error": "No text provided"}}), 400
    try:
        import piper
        v = piper.PiperVoice.load(voice_name)
        buf = io.BytesIO()
        import wave
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(v.config.sample_rate)
            for audio_bytes in v.synthesize_stream_raw(text):
                wav.writeframes(audio_bytes)
        buf.seek(0)
        return send_file(buf, mimetype="audio/wav", download_name="speech.wav")
    except Exception as e:
        # Fallback: try CLI piper
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                proc = subprocess.run(
                    ["piper", "--model", voice_name, "--output_file", tmp.name],
                    input=text, capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0:
                    return send_file(tmp.name, mimetype="audio/wav", download_name="speech.wav")
        except Exception:
            pass
        return jsonify({{"ok": False, "error": str(e)}}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({{"ok": True, "status": "healthy", "voice": DEFAULT_VOICE}})

if __name__ == "__main__":
    port = int(os.environ.get("PIPER_PORT", "5500"))
    host = os.environ.get("PIPER_HOST", "0.0.0.0")
    app.run(host=host, port=port)
''', encoding="utf-8")
    log("Piper TTS server created successfully.")
    return 0


# ── AI service install entry points ─────────────────────────────────────────
def run_ollama_os_install(form=None, live_cb=None):
    """Install Ollama using the platform-specific installer script (like SAM3)."""
    form = form or {}
    if os.name == "nt":
        return run_windows_ollama_installer(form, live_cb=live_cb)
    return run_unix_ollama_installer(form, live_cb=live_cb)


def run_windows_ollama_installer(form=None, live_cb=None):
    """Run the Ollama Windows PowerShell installer."""
    form = form or {}
    if os.name != "nt":
        return 1, "Windows Ollama installer can only run on Windows hosts."
    ensure_repo_files(OLLAMA_WINDOWS_FILES, live_cb=live_cb, refresh=True)
    env = os.environ.copy()
    for key in ["OLLAMA_HOST_IP", "OLLAMA_HTTP_PORT", "OLLAMA_HTTPS_PORT", "OLLAMA_DOMAIN",
                 "OLLAMA_USERNAME", "OLLAMA_PASSWORD"]:
        val = (form.get(key, [""])[0] or "").strip()
        if val:
            env[key] = val
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    code, output = run_process(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OLLAMA_WINDOWS_INSTALLER)],
        env=env, live_cb=live_cb,
    )
    return code, output


def run_unix_ollama_installer(form=None, live_cb=None):
    """Run the Ollama Linux/macOS bash installer."""
    form = form or {}
    if os.name == "nt":
        return 1, "Unix Ollama installer can only run on Linux or macOS."
    ensure_repo_files(OLLAMA_UNIX_FILES, live_cb=live_cb, refresh=True)
    env = os.environ.copy()
    env_keys = ["OLLAMA_HOST_IP", "OLLAMA_HTTP_PORT", "OLLAMA_HTTPS_PORT", "OLLAMA_DOMAIN",
                 "OLLAMA_USERNAME", "OLLAMA_PASSWORD"]
    for key in env_keys:
        val = (form.get(key, [""])[0] or "").strip()
        if val:
            env[key] = val
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    cmd = ["bash", str(OLLAMA_LINUX_INSTALLER)]
    if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
        cmd = ["sudo", "env"]
        for key in env_keys + ["SERVER_INSTALLER_DATA_DIR"]:
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(OLLAMA_LINUX_INSTALLER)]
    code, output = run_process(cmd, env=env, live_cb=live_cb)
    return code, output


def run_ollama_start(live_cb=None):
    """Start the Ollama service."""
    log = lambda m: live_cb(m + "\n") if live_cb else None
    if os.name != "nt" and command_exists("systemctl"):
        rc, out = run_capture(["systemctl", "start", OLLAMA_SYSTEMD_SERVICE], timeout=30)
        run_capture(["systemctl", "start", f"{OLLAMA_SYSTEMD_SERVICE}-webui"], timeout=30)
        if rc == 0:
            state = _read_json_file(OLLAMA_STATE_FILE)
            state["running"] = True
            _write_json_file(OLLAMA_STATE_FILE, state)
        return rc, out or "Ollama started."
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Run", "/TN", "ServerInstaller-Ollama"], timeout=15)
            state = _read_json_file(OLLAMA_STATE_FILE)
            state["running"] = True
            _write_json_file(OLLAMA_STATE_FILE, state)
            return 0, "Ollama started."
        except Exception as e:
            return 1, str(e)
    return 1, "Could not start Ollama."


def run_ollama_stop(live_cb=None):
    """Stop the Ollama service."""
    if os.name != "nt" and command_exists("systemctl"):
        run_capture(["systemctl", "stop", f"{OLLAMA_SYSTEMD_SERVICE}-webui"], timeout=30)
        rc, out = run_capture(["systemctl", "stop", OLLAMA_SYSTEMD_SERVICE], timeout=30)
    elif os.name == "nt":
        run_capture(["schtasks", "/End", "/TN", "ServerInstaller-Ollama"], timeout=15)
        rc, out = 0, "Ollama stopped."
    else:
        rc, out = 1, "Cannot stop Ollama."
    state = _read_json_file(OLLAMA_STATE_FILE)
    state["running"] = False
    _write_json_file(OLLAMA_STATE_FILE, state)
    return rc, out or "Ollama stopped."


def run_ollama_delete(live_cb=None):
    """Delete the Ollama service and clean up."""
    log = lambda m: live_cb(m + "\n") if live_cb else None
    run_ollama_stop(live_cb=live_cb)
    if os.name != "nt" and command_exists("systemctl"):
        for svc in [f"{OLLAMA_SYSTEMD_SERVICE}-webui", OLLAMA_SYSTEMD_SERVICE]:
            run_capture(["systemctl", "disable", svc], timeout=15)
            run_capture(["systemctl", "stop", svc], timeout=15)
            svc_file = Path(f"/etc/systemd/system/{svc}.service")
            if svc_file.exists():
                svc_file.unlink()
        run_capture(["systemctl", "daemon-reload"], timeout=15)
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-Ollama", "/F"], timeout=15)
        except Exception:
            pass
    # Clean up install dir
    install_dir = OLLAMA_STATE_DIR / "app"
    if install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)
    if OLLAMA_STATE_FILE.exists():
        OLLAMA_STATE_FILE.unlink()
    return 0, "Ollama service deleted."


# ── LM Studio install/start/stop/delete ──────────────────────────────────────
def run_lmstudio_os_install(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        ensure_repo_files(LMSTUDIO_WINDOWS_FILES, live_cb=live_cb, refresh=True)
        env = os.environ.copy()
        for key in ["LMSTUDIO_HOST_IP", "LMSTUDIO_HTTP_PORT", "LMSTUDIO_HTTPS_PORT", "LMSTUDIO_DOMAIN", "LMSTUDIO_USERNAME", "LMSTUDIO_PASSWORD"]:
            val = (form.get(key, [""])[0] or "").strip()
            if val: env[key] = val
        env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
        return run_process(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LMSTUDIO_WINDOWS_INSTALLER)], env=env, live_cb=live_cb)
    else:
        ensure_repo_files(LMSTUDIO_UNIX_FILES, live_cb=live_cb, refresh=True)
        env = os.environ.copy()
        env_keys = ["LMSTUDIO_HOST_IP", "LMSTUDIO_HTTP_PORT", "LMSTUDIO_HTTPS_PORT", "LMSTUDIO_DOMAIN", "LMSTUDIO_USERNAME", "LMSTUDIO_PASSWORD"]
        for key in env_keys:
            val = (form.get(key, [""])[0] or "").strip()
            if val: env[key] = val
        env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
        cmd = ["bash", str(LMSTUDIO_LINUX_INSTALLER)]
        if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
            cmd = ["sudo", "env"] + [f"{k}={env.get(k, '')}" for k in env_keys + ["SERVER_INSTALLER_DATA_DIR"] if env.get(k)] + ["bash", str(LMSTUDIO_LINUX_INSTALLER)]
        return run_process(cmd, env=env, live_cb=live_cb)


def run_lmstudio_start(live_cb=None):
    if os.name != "nt" and command_exists("systemctl"):
        run_capture(["systemctl", "start", f"{LMSTUDIO_SYSTEMD_SERVICE}-webui"], timeout=30)
        state = _read_json_file(LMSTUDIO_STATE_FILE)
        state["running"] = True
        _write_json_file(LMSTUDIO_STATE_FILE, state)
        return 0, "LM Studio started."
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Run", "/TN", "ServerInstaller-LMStudio"], timeout=15)
            state = _read_json_file(LMSTUDIO_STATE_FILE)
            state["running"] = True
            _write_json_file(LMSTUDIO_STATE_FILE, state)
            return 0, "LM Studio started."
        except Exception as e:
            return 1, str(e)
    return 1, "Could not start LM Studio."


def run_lmstudio_stop(live_cb=None):
    if os.name != "nt" and command_exists("systemctl"):
        run_capture(["systemctl", "stop", f"{LMSTUDIO_SYSTEMD_SERVICE}-webui"], timeout=30)
    elif os.name == "nt":
        run_capture(["schtasks", "/End", "/TN", "ServerInstaller-LMStudio"], timeout=15)
    state = _read_json_file(LMSTUDIO_STATE_FILE)
    state["running"] = False
    _write_json_file(LMSTUDIO_STATE_FILE, state)
    return 0, "LM Studio stopped."


def run_lmstudio_delete(live_cb=None):
    run_lmstudio_stop(live_cb=live_cb)
    if os.name != "nt" and command_exists("systemctl"):
        for svc in [f"{LMSTUDIO_SYSTEMD_SERVICE}-webui"]:
            run_capture(["systemctl", "disable", svc], timeout=15)
            svc_file = Path(f"/etc/systemd/system/{svc}.service")
            if svc_file.exists(): svc_file.unlink()
        run_capture(["systemctl", "daemon-reload"], timeout=15)
    elif os.name == "nt":
        try: run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-LMStudio", "/F"], timeout=15)
        except Exception: pass
    install_dir = LMSTUDIO_STATE_DIR / "app"
    if install_dir.exists(): shutil.rmtree(install_dir, ignore_errors=True)
    if LMSTUDIO_STATE_FILE.exists(): LMSTUDIO_STATE_FILE.unlink()
    return 0, "LM Studio service deleted."


# ── OpenClaw install/start/stop/delete ────────────────────────────────────────
def run_openclaw_os_install(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        ensure_repo_files(OPENCLAW_WINDOWS_FILES, live_cb=live_cb, refresh=True)
        env = os.environ.copy()
        all_keys = ["OPENCLAW_HOST_IP", "OPENCLAW_HTTP_PORT", "OPENCLAW_HTTPS_PORT", "OPENCLAW_DOMAIN",
                    "OPENCLAW_USERNAME", "OPENCLAW_PASSWORD",
                    "OPENCLAW_TELEGRAM_TOKEN", "OPENCLAW_DISCORD_TOKEN", "OPENCLAW_SLACK_TOKEN", "OPENCLAW_WHATSAPP_PHONE",
                    "OPENCLAW_LLM_PROVIDER", "OPENCLAW_LLM_MODEL", "OPENCLAW_OPENAI_KEY", "OPENCLAW_ANTHROPIC_KEY"]
        for key in all_keys:
            val = (form.get(key, [""])[0] or "").strip()
            if val: env[key] = val
        env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
        return run_process(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OPENCLAW_WINDOWS_INSTALLER)], env=env, live_cb=live_cb)
    else:
        ensure_repo_files(OPENCLAW_UNIX_FILES, live_cb=live_cb, refresh=True)
        env = os.environ.copy()
        env_keys = ["OPENCLAW_HOST_IP", "OPENCLAW_HTTP_PORT", "OPENCLAW_HTTPS_PORT", "OPENCLAW_DOMAIN",
                    "OPENCLAW_USERNAME", "OPENCLAW_PASSWORD",
                    "OPENCLAW_TELEGRAM_TOKEN", "OPENCLAW_DISCORD_TOKEN", "OPENCLAW_SLACK_TOKEN", "OPENCLAW_WHATSAPP_PHONE",
                    "OPENCLAW_LLM_PROVIDER", "OPENCLAW_LLM_MODEL", "OPENCLAW_OPENAI_KEY", "OPENCLAW_ANTHROPIC_KEY"]
        for key in env_keys:
            val = (form.get(key, [""])[0] or "").strip()
            if val: env[key] = val
        env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
        cmd = ["bash", str(OPENCLAW_LINUX_INSTALLER)]
        if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
            cmd = ["sudo", "env"] + [f"{k}={env.get(k, '')}" for k in env_keys + ["SERVER_INSTALLER_DATA_DIR"] if env.get(k)] + ["bash", str(OPENCLAW_LINUX_INSTALLER)]
        return run_process(cmd, env=env, live_cb=live_cb)


def run_openclaw_start(live_cb=None):
    if os.name != "nt" and command_exists("systemctl"):
        # Try the real OpenClaw gateway service first, then our wrapper
        for svc in ["clawdbot-gateway", OPENCLAW_SYSTEMD_SERVICE]:
            rc, _ = run_capture(["systemctl", "start", svc], timeout=30)
            if rc == 0:
                state = _read_json_file(OPENCLAW_STATE_FILE); state["running"] = True; _write_json_file(OPENCLAW_STATE_FILE, state)
                return 0, f"OpenClaw started ({svc})."
        return 1, "Could not start OpenClaw."
    elif os.name == "nt":
        try: run_capture(["schtasks", "/Run", "/TN", "ServerInstaller-OpenClaw"], timeout=15); return 0, "OpenClaw started."
        except Exception as e: return 1, str(e)
    return 1, "Could not start."


def run_openclaw_stop(live_cb=None):
    if os.name != "nt" and command_exists("systemctl"):
        for svc in ["clawdbot-gateway", OPENCLAW_SYSTEMD_SERVICE]:
            run_capture(["systemctl", "stop", svc], timeout=30)
    elif os.name == "nt":
        run_capture(["schtasks", "/End", "/TN", "ServerInstaller-OpenClaw"], timeout=15)
    # Also kill any openclaw gateway processes
    if os.name != "nt":
        run_capture(["pkill", "-f", "openclaw gateway"], timeout=10)
    state = _read_json_file(OPENCLAW_STATE_FILE); state["running"] = False; _write_json_file(OPENCLAW_STATE_FILE, state)
    return 0, "OpenClaw stopped."


def run_openclaw_delete(live_cb=None):
    run_openclaw_stop(live_cb=live_cb)
    if os.name != "nt" and command_exists("systemctl"):
        run_capture(["systemctl", "disable", OPENCLAW_SYSTEMD_SERVICE], timeout=15)
        svc_file = Path(f"/etc/systemd/system/{OPENCLAW_SYSTEMD_SERVICE}.service")
        if svc_file.exists(): svc_file.unlink()
        run_capture(["systemctl", "daemon-reload"], timeout=15)
    elif os.name == "nt":
        try: run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-OpenClaw", "/F"], timeout=15)
        except Exception: pass
    if (OPENCLAW_STATE_DIR / "app").exists(): shutil.rmtree(OPENCLAW_STATE_DIR / "app", ignore_errors=True)
    if OPENCLAW_STATE_FILE.exists(): OPENCLAW_STATE_FILE.unlink()
    return 0, "OpenClaw deleted."


def run_openclaw_docker(form=None, live_cb=None):
    """Deploy real OpenClaw gateway as a Docker container with Node.js."""
    form = form or {}
    http_port = (form.get("OPENCLAW_HTTP_PORT", ["18789"])[0] or "18789").strip()
    https_port = (form.get("OPENCLAW_HTTPS_PORT", [""])[0] or "").strip()
    host = (form.get("OPENCLAW_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
    username = (form.get("OPENCLAW_USERNAME", [""])[0] or "").strip()
    password = (form.get("OPENCLAW_PASSWORD", [""])[0] or "").strip()
    # Channel tokens
    telegram_token = (form.get("OPENCLAW_TELEGRAM_TOKEN", [""])[0] or "").strip()
    discord_token = (form.get("OPENCLAW_DISCORD_TOKEN", [""])[0] or "").strip()
    slack_token = (form.get("OPENCLAW_SLACK_TOKEN", [""])[0] or "").strip()
    whatsapp_phone = (form.get("OPENCLAW_WHATSAPP_PHONE", [""])[0] or "").strip()
    # LLM config
    llm_provider = (form.get("OPENCLAW_LLM_PROVIDER", ["ollama (local)"])[0] or "ollama (local)").strip()
    llm_model = (form.get("OPENCLAW_LLM_MODEL", ["llama3.2:3b"])[0] or "llama3.2:3b").strip()
    openai_key = (form.get("OPENCLAW_OPENAI_KEY", [""])[0] or "").strip()
    anthropic_key = (form.get("OPENCLAW_ANTHROPIC_KEY", [""])[0] or "").strip()
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Installing OpenClaw via Docker ===")

    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        log("Docker not found. Installing Docker first...")
        _install_engine_docker(log)
        if sys.platform == "darwin":
            _docker_add_macos_path()
    if not command_exists("docker"):
        return 1, "Docker is not available. Install Docker Desktop manually."

    container_name = "serverinstaller-openclaw"
    run_capture(["docker", "stop", container_name], timeout=15)
    run_capture(["docker", "rm", container_name], timeout=15)

    # Build real OpenClaw container with Node.js
    log("Building OpenClaw container (Node.js + real OpenClaw gateway)...")
    build_dir = str(OPENCLAW_STATE_DIR / "docker-build")
    Path(build_dir).mkdir(parents=True, exist_ok=True)

    # Create entrypoint that skips interactive onboard and starts gateway
    # Use socat to forward 0.0.0.0:port to 127.0.0.1:port
    # This lets OpenClaw bind to loopback (no controlUi error) while Docker port mapping works
    gw_internal_port = str(int(http_port) + 1)
    entrypoint_sh = f"""#!/bin/bash
echo "=== OpenClaw Docker Container ==="
echo "Port: {http_port}"

# Configure gateway to allow external origins (required for non-loopback access)
mkdir -p /root/.openclaw
openclaw config set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true 2>/dev/null || true
openclaw config set gateway.controlUi.allowedOrigins '["*"]' 2>/dev/null || true
openclaw config set gateway.trustedProxies '["127.0.0.1","::1"]' 2>/dev/null || true

# Start gateway on loopback
openclaw gateway --allow-unconfigured --bind loopback --port {gw_internal_port} --verbose &
GW_PID=$!
sleep 3

# Forward 0.0.0.0:port -> 127.0.0.1:internal_port using socat
echo "Starting port forwarder 0.0.0.0:{http_port} -> 127.0.0.1:{gw_internal_port}"
socat TCP-LISTEN:{http_port},fork,reuseaddr TCP:127.0.0.1:{gw_internal_port} &

wait $GW_PID
"""
    Path(build_dir, "entrypoint.sh").write_text(entrypoint_sh, encoding="utf-8")

    dockerfile = f"""FROM node:22-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl python3 build-essential socat && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally
RUN npm install -g openclaw@latest

# Pre-create config dir
RUN mkdir -p /root/.openclaw

# Gateway port
ENV OPENCLAW_PORT={http_port}
EXPOSE {http_port}

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
"""
    Path(build_dir, "Dockerfile").write_text(dockerfile, encoding="utf-8")

    code = _run_install_cmd(["docker", "build", "--no-cache", "-t", "serverinstaller/openclaw:latest", build_dir], log, timeout=600)
    if code != 0:
        return code, "\n".join(output)

    # Run container with host network access for Ollama
    docker_cmd = ["docker", "run", "-d", "--name", container_name,
                  "-p", f"{http_port}:{http_port}",
                  "--add-host", "host.docker.internal:host-gateway",
                  "-v", "openclaw-data:/root/.openclaw",
                  "--restart", "unless-stopped"]
    # Pass channel tokens and LLM config as env vars
    env_map = {
        "TELEGRAM_BOT_TOKEN": telegram_token,
        "DISCORD_TOKEN": discord_token,
        "SLACK_BOT_TOKEN": slack_token,
        "WHATSAPP_PHONE": whatsapp_phone,
        "OPENAI_API_KEY": openai_key,
        "ANTHROPIC_API_KEY": anthropic_key,
        "OPENCLAW_MODEL": llm_model,
    }
    for k, v in env_map.items():
        if v:
            docker_cmd += ["-e", f"{k}={v}"]
    docker_cmd.append("serverinstaller/openclaw:latest")
    log("Starting OpenClaw gateway container...")
    if telegram_token:
        log(f"Telegram bot configured.")
    if discord_token:
        log(f"Discord bot configured.")
    if slack_token:
        log(f"Slack bot configured.")
    if openai_key:
        log(f"OpenAI API key configured.")
    if anthropic_key:
        log(f"Anthropic API key configured.")
    code2 = _run_install_cmd(docker_cmd, log, timeout=60)

    # Save state
    OPENCLAW_STATE_DIR.mkdir(parents=True, exist_ok=True)
    display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
    http_url = f"http://{display_host}:{http_port}"
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    state = _read_json_file(OPENCLAW_STATE_FILE)
    state.update({
        "installed": True, "service_name": container_name,
        "deploy_mode": "docker", "host": host,
        "http_port": http_port, "https_port": https_port,
        "http_url": http_url, "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "running": code2 == 0,
    })
    _write_json_file(OPENCLAW_STATE_FILE, state)
    manage_firewall_port("open", http_port, "tcp")

    # Wait and check container logs
    import time
    time.sleep(5)
    try:
        rc, logs = run_capture(["docker", "logs", "--tail", "20", container_name], timeout=10)
        if logs:
            log("\nContainer logs:")
            log(logs.strip())
    except Exception:
        pass

    # Check if container is running
    try:
        rc, status = run_capture(["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Status}}"], timeout=10)
        if status.strip():
            log(f"\nContainer status: {status.strip()}")
        else:
            log("\nWARNING: Container may have stopped. Check: docker logs " + container_name)
    except Exception:
        pass

    log("\n" + "=" * 60)
    log(" OpenClaw Docker Deployment Complete!")
    log("=" * 60)
    log(f" Dashboard:      {http_url}")
    if https_url:
        log(f" HTTPS:          {https_url}")
    if username:
        log(f" Auth:           {username} / ****")
    log(f" Container:      {container_name}")
    log(f" Logs:           docker logs {container_name}")
    log("=" * 60)
    return code2, "\n".join(output)

def run_tgwui_os_install(form=None, live_cb=None):
    return _run_ai_service_install("tgwui", form, TGWUI_STATE_FILE, TGWUI_STATE_DIR, TGWUI_SYSTEMD_SERVICE, "Text Generation WebUI", "7860",
        {"nt": [_install_tgwui_os], "posix": [_install_tgwui_os]}, live_cb=live_cb)

def run_comfyui_os_install(form=None, live_cb=None):
    return _run_ai_service_install("comfyui", form, COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, COMFYUI_SYSTEMD_SERVICE, "ComfyUI", "8188",
        {"nt": [_install_comfyui_os], "posix": [_install_comfyui_os]}, live_cb=live_cb)

def run_whisper_os_install(form=None, live_cb=None):
    return _run_ai_service_install("whisper", form, WHISPER_STATE_FILE, WHISPER_STATE_DIR, WHISPER_SYSTEMD_SERVICE, "Whisper STT", "9000",
        {"nt": [_install_whisper_os], "posix": [_install_whisper_os]}, live_cb=live_cb)

def run_piper_os_install(form=None, live_cb=None):
    return _run_ai_service_install("piper", form, PIPER_STATE_FILE, PIPER_STATE_DIR, PIPER_SYSTEMD_SERVICE, "Piper TTS", "5500",
        {"nt": [_install_piper_os], "posix": [_install_piper_os]}, live_cb=live_cb)


# ── Docker install for AI services ──────────────────────────────────────────
def run_ollama_docker(form=None, live_cb=None):
    form = form or {}
    http_port = (form.get("OLLAMA_HTTP_PORT", [""])[0] or "").strip()
    https_port = (form.get("OLLAMA_HTTPS_PORT", [""])[0] or "").strip()
    host = (form.get("OLLAMA_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
    username = (form.get("OLLAMA_USERNAME", [""])[0] or "").strip()
    password = (form.get("OLLAMA_PASSWORD", [""])[0] or "").strip()
    web_port = http_port or https_port or "11434"
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Installing Ollama via Docker ===")
    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        log("Docker not found. Installing Docker first...")
        _install_engine_docker(log)
        if sys.platform == "darwin":
            _docker_add_macos_path()
    if not command_exists("docker"):
        return 1, "Docker is not available. Install Docker Desktop manually."

    # Stop existing containers
    run_capture(["docker", "stop", "serverinstaller-ollama"], timeout=15)
    run_capture(["docker", "rm", "serverinstaller-ollama"], timeout=15)
    run_capture(["docker", "stop", "serverinstaller-ollama-webui"], timeout=15)
    run_capture(["docker", "rm", "serverinstaller-ollama-webui"], timeout=15)

    # Step 1: Run Ollama server container (internal, no port exposed to host)
    log("Starting Ollama server container...")
    cmd = ["docker", "run", "-d", "--name", "serverinstaller-ollama",
           "-v", "ollama-data:/root/.ollama",
           "--restart", "unless-stopped"]
    # GPU support
    try:
        rc, out = run_capture(["docker", "info", "--format", "{{.Runtimes}}"], timeout=10)
        if "nvidia" in str(out).lower():
            cmd.extend(["--gpus", "all"])
            log("NVIDIA GPU detected — enabling GPU passthrough.")
    except Exception:
        pass
    cmd.append("ollama/ollama:latest")
    code = _run_install_cmd(cmd, log, timeout=300)
    if code != 0:
        return code, "\n".join(output)

    # Get Ollama container IP for web UI to connect
    import time
    time.sleep(3)
    try:
        rc, ollama_ip = run_capture(["docker", "inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", "serverinstaller-ollama"], timeout=10)
        ollama_ip = ollama_ip.strip()
    except Exception:
        ollama_ip = ""
    if not ollama_ip:
        ollama_ip = "serverinstaller-ollama"
    log(f"Ollama server running at {ollama_ip}:11434")

    # Step 2: Build and run Web UI container
    log("\nBuilding Ollama Web UI...")
    ensure_repo_files(OLLAMA_UNIX_FILES if os.name != "nt" else OLLAMA_WINDOWS_FILES, live_cb=live_cb, refresh=True)
    common_dir = str(ROOT / "Ollama" / "common")
    webui_build = str(OLLAMA_STATE_DIR / "docker-webui")
    Path(webui_build).mkdir(parents=True, exist_ok=True)

    # Copy web UI files
    for item in Path(common_dir).rglob("*"):
        if item.is_file() and "__pycache__" not in str(item) and "venv" not in str(item):
            rel = item.relative_to(common_dir)
            dest = Path(webui_build) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))

    # Create Dockerfile for web UI
    expose_ports = web_port
    if https_port:
        expose_ports += f" {https_port}"
    dockerfile = f"""FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir flask requests
ENV OLLAMA_API_BASE=http://{ollama_ip}:11434
ENV OLLAMA_WEBUI_PORT={web_port}
ENV OLLAMA_HTTPS_PORT={https_port}
ENV OLLAMA_AUTH_USERNAME={username}
ENV OLLAMA_AUTH_PASSWORD={password}
EXPOSE {expose_ports}
CMD ["python", "ollama_web.py"]
"""
    Path(webui_build, "Dockerfile").write_text(dockerfile, encoding="utf-8")

    # Build web UI image
    code2 = _run_install_cmd(["docker", "build", "--no-cache", "-t", "serverinstaller/ollama-webui:latest", webui_build], log, timeout=300)
    if code2 != 0:
        log("Web UI build failed. Falling back to raw Ollama API on port.")
        # Fallback: expose Ollama API directly
        run_capture(["docker", "stop", "serverinstaller-ollama"], timeout=15)
        run_capture(["docker", "rm", "serverinstaller-ollama"], timeout=15)
        cmd_fallback = ["docker", "run", "-d", "--name", "serverinstaller-ollama",
                        "-p", f"{web_port}:11434", "-v", "ollama-data:/root/.ollama",
                        "--restart", "unless-stopped", "ollama/ollama:latest"]
        _run_install_cmd(cmd_fallback, log, timeout=300)
    else:
        # Run web UI container linked to Ollama
        webui_cmd = ["docker", "run", "-d", "--name", "serverinstaller-ollama-webui",
                     "-p", f"{web_port}:{web_port}",
                     "--link", "serverinstaller-ollama:ollama",
                     "-e", f"OLLAMA_API_BASE=http://serverinstaller-ollama:11434",
                     "-e", f"OLLAMA_WEBUI_PORT={web_port}",
                     "-e", f"OLLAMA_HTTPS_PORT={https_port}",
                     "-e", f"OLLAMA_AUTH_USERNAME={username}",
                     "-e", f"OLLAMA_AUTH_PASSWORD={password}",
                     "--restart", "unless-stopped"]
        if https_port:
            webui_cmd += ["-p", f"{https_port}:{https_port}"]
        webui_cmd.append("serverinstaller/ollama-webui:latest")
        code3 = _run_install_cmd(webui_cmd, log, timeout=60)
        if code3 != 0:
            log("Web UI container failed to start.")

    # Save state
    OLLAMA_STATE_DIR.mkdir(parents=True, exist_ok=True)
    display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
    http_url = f"http://{display_host}:{web_port}" if http_port else ""
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    state = _read_json_file(OLLAMA_STATE_FILE)
    state.update({
        "installed": True, "service_name": "serverinstaller-ollama",
        "deploy_mode": "docker", "host": host,
        "http_port": http_port, "https_port": https_port,
        "http_url": http_url or f"http://{display_host}:{web_port}",
        "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "running": True,
    })
    _write_json_file(OLLAMA_STATE_FILE, state)
    manage_firewall_port("open", web_port, "tcp")

    # Show results
    log("\n" + "=" * 60)
    log(" Ollama Docker Deployment Complete!")
    log("=" * 60)
    if http_url:
        log(f" Web UI (HTTP):  {http_url}")
    else:
        log(f" Web UI:         http://{display_host}:{web_port}")
    if https_url:
        log(f" Web UI (HTTPS): {https_url}")
    if username:
        log(f" Auth:           {username} / ****")
    log(f" Ollama API:     http://{display_host}:{web_port}/api/tags")
    log("=" * 60)
    return 0, "\n".join(output)


def run_lmstudio_docker(form=None, live_cb=None):
    """Deploy LM Studio Web UI as a Docker container connected to host LM Studio server."""
    form = form or {}
    http_port = (form.get("LMSTUDIO_HTTP_PORT", [""])[0] or "").strip()
    https_port = (form.get("LMSTUDIO_HTTPS_PORT", [""])[0] or "").strip()
    host = (form.get("LMSTUDIO_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
    username = (form.get("LMSTUDIO_USERNAME", [""])[0] or "").strip()
    password = (form.get("LMSTUDIO_PASSWORD", [""])[0] or "").strip()
    web_port = http_port or https_port or "8084"
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Installing LM Studio Web UI via Docker ===")

    # Step 1: Ensure LM Studio is installed and server is running on the host
    log("Checking LM Studio on host...")
    lms_server_running = False
    try:
        import urllib.request
        req = urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=3)
        lms_server_running = req.status == 200
    except Exception:
        pass

    if lms_server_running:
        log("LM Studio server is running on port 1234.")
    else:
        log("LM Studio server not detected on port 1234. Trying to start it...")

        # Check if LM Studio is installed
        lms_installed = command_exists("lms") or (sys.platform == "darwin" and Path("/Applications/LM Studio.app").exists())
        if not lms_installed:
            log("LM Studio not found. Installing via OS installer...")
            # Run the OS installer first
            ensure_repo_files(LMSTUDIO_UNIX_FILES if os.name != "nt" else LMSTUDIO_WINDOWS_FILES, live_cb=live_cb, refresh=True)
            install_form = dict(form)
            # Don't pass HTTP/HTTPS ports to OS installer — Docker handles that
            install_form.pop("LMSTUDIO_HTTP_PORT", None)
            install_form.pop("LMSTUDIO_HTTPS_PORT", None)
            code_inst, out_inst = run_lmstudio_os_install(install_form, live_cb=live_cb)
            if code_inst == 0:
                log("LM Studio installed on host.")
            else:
                log(f"LM Studio OS install returned code {code_inst}")

        # Find lms CLI at known locations
        lms_cmd = None
        lms_search_paths = [
            "lms",
            str(Path.home() / ".lmstudio" / "bin" / "lms"),
            "/Applications/LM Studio.app/Contents/Resources/bin/lms",
            str(Path.home() / ".cache" / "lm-studio" / "bin" / "lms"),
        ]
        for lp in lms_search_paths:
            if lp == "lms" and command_exists("lms"):
                lms_cmd = "lms"
                break
            elif lp != "lms" and Path(lp).exists():
                lms_cmd = lp
                break

        # Try lms CLI to start the server
        lms_started = False
        if lms_cmd:
            log(f"Found lms CLI at: {lms_cmd}")
            log("Starting LM Studio server...")
            try:
                rc, out = run_capture([lms_cmd, "server", "start"], timeout=30)
                log(f"lms server start: exit={rc}")
                if out.strip():
                    log(out.strip()[:200])
            except Exception as e:
                log(f"lms server start failed: {e}")
            # Try loading a model if server started
            import time
            time.sleep(3)
            try:
                rc2, models_out = run_capture([lms_cmd, "ls"], timeout=15)
                if rc2 == 0 and models_out.strip():
                    log(f"Available models:\n{models_out.strip()[:300]}")
                    # Try to load the first model
                    lines = [l.strip() for l in models_out.strip().splitlines() if l.strip() and not l.startswith("---") and not l.startswith("Model")]
                    if lines:
                        first_model = lines[0].split()[0] if lines[0].split() else lines[0]
                        log(f"Loading model: {first_model}")
                        try:
                            rc3, _ = run_capture([lms_cmd, "load", first_model], timeout=60)
                        except Exception:
                            pass
            except Exception:
                pass
            # Wait for server
            for i in range(10):
                time.sleep(2)
                try:
                    req = urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=2)
                    if req.status == 200:
                        lms_started = True
                        log("LM Studio server is running!")
                        break
                except Exception:
                    pass
            if not lms_started:
                log("Server not responding yet after lms start.")

        # Try opening LM Studio app on macOS if CLI didn't work
        if not lms_started and sys.platform == "darwin":
            log("Opening LM Studio app...")
            try:
                _run_install_cmd(["open", "-a", "LM Studio"], log, timeout=10)
                import time
                for i in range(20):
                    time.sleep(3)
                    try:
                        req = urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=2)
                        if req.status == 200:
                            lms_started = True
                            log("LM Studio server is now running.")
                            break
                    except Exception:
                        pass
                    if i % 5 == 4:
                        log(f"Still waiting for LM Studio server... ({i+1}/20)")
                        log("Please start the server: Developer > Start Server")
            except Exception:
                pass
        if not lms_started and not lms_server_running:
            log("")
            log("=" * 50)
            log("LM Studio server could not be auto-started.")
            log("Please do these steps manually:")
            log("  1. Open LM Studio app on this computer")
            log("  2. Download and load a model (e.g. Llama 3)")
            log("  3. Go to Developer tab > Start Server")
            log("  4. The web UI will connect automatically")
            log("=" * 50)
            log("")

    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        log("Docker not found. Installing Docker first...")
        _install_engine_docker(log)
        if sys.platform == "darwin":
            _docker_add_macos_path()
    if not command_exists("docker"):
        return 1, "Docker is not available. Install Docker Desktop manually."

    # Stop existing container
    run_capture(["docker", "stop", "serverinstaller-lmstudio-webui"], timeout=15)
    run_capture(["docker", "rm", "serverinstaller-lmstudio-webui"], timeout=15)

    # Build web UI
    log("\nBuilding LM Studio Web UI...")
    ensure_repo_files(LMSTUDIO_UNIX_FILES if os.name != "nt" else LMSTUDIO_WINDOWS_FILES, live_cb=live_cb, refresh=True)
    common_dir = str(ROOT / "LMStudio" / "common")
    webui_build = str(LMSTUDIO_STATE_DIR / "docker-webui")
    Path(webui_build).mkdir(parents=True, exist_ok=True)

    # Copy web UI files
    for item in Path(common_dir).rglob("*"):
        if item.is_file() and "__pycache__" not in str(item) and "venv" not in str(item):
            rel = item.relative_to(common_dir)
            dest = Path(webui_build) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))

    # LM Studio runs on the host, not in Docker. Use host.docker.internal to reach it.
    lms_api_base = "http://host.docker.internal:1234"
    expose_ports = web_port
    if https_port:
        expose_ports += f" {https_port}"
    dockerfile = f"""FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir flask requests
ENV LMSTUDIO_API_BASE={lms_api_base}
ENV LMSTUDIO_WEB_PORT={web_port}
ENV LMSTUDIO_HTTPS_PORT={https_port}
ENV LMSTUDIO_AUTH_USERNAME={username}
ENV LMSTUDIO_AUTH_PASSWORD={password}
EXPOSE {expose_ports}
CMD ["python", "lmstudio_web.py"]
"""
    Path(webui_build, "Dockerfile").write_text(dockerfile, encoding="utf-8")

    code = _run_install_cmd(["docker", "build", "--no-cache", "-t", "serverinstaller/lmstudio-webui:latest", webui_build], log, timeout=300)
    if code != 0:
        return code, "\n".join(output)

    # Run web UI container with host networking access
    webui_cmd = ["docker", "run", "-d", "--name", "serverinstaller-lmstudio-webui",
                 "-p", f"{web_port}:{web_port}",
                 "--add-host", "host.docker.internal:host-gateway",
                 "-e", f"LMSTUDIO_API_BASE={lms_api_base}",
                 "-e", f"LMSTUDIO_WEB_PORT={web_port}",
                 "-e", f"LMSTUDIO_HTTPS_PORT={https_port}",
                 "-e", f"LMSTUDIO_AUTH_USERNAME={username}",
                 "-e", f"LMSTUDIO_AUTH_PASSWORD={password}",
                 "--restart", "unless-stopped"]
    if https_port:
        webui_cmd += ["-p", f"{https_port}:{https_port}"]
    webui_cmd.append("serverinstaller/lmstudio-webui:latest")
    code2 = _run_install_cmd(webui_cmd, log, timeout=60)

    # Save state
    LMSTUDIO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
    http_url = f"http://{display_host}:{web_port}" if http_port else f"http://{display_host}:{web_port}"
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    state = _read_json_file(LMSTUDIO_STATE_FILE)
    state.update({
        "installed": True, "service_name": "serverinstaller-lmstudio-webui",
        "deploy_mode": "docker", "host": host,
        "http_port": http_port or web_port, "https_port": https_port,
        "http_url": http_url, "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "running": code2 == 0,
    })
    _write_json_file(LMSTUDIO_STATE_FILE, state)
    manage_firewall_port("open", web_port, "tcp")

    log("\n" + "=" * 60)
    log(" LM Studio Web UI Docker Deployment Complete!")
    log("=" * 60)
    log(f" Web UI:         {http_url}")
    if https_url:
        log(f" Web UI (HTTPS): {https_url}")
    log(f" LM Studio API:  http://localhost:1234 (on host)")
    if username:
        log(f" Auth:           {username} / ****")
    log(" Note: Start the local server in LM Studio desktop app")
    log("=" * 60)
    return code2, "\n".join(output)


def _run_ai_docker_generic(service_id, image, form, default_port, container_port, display_name, state_file, state_dir, live_cb=None, extra_args=None):
    """Generic Docker install for AI services."""
    form = form or {}
    port = (form.get(f"{service_id.upper()}_HTTP_PORT", [default_port])[0] or default_port).strip()
    host = (form.get(f"{service_id.upper()}_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log(f"=== Installing {display_name} via Docker ===")
    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        _install_engine_docker(log)
        if sys.platform == "darwin":
            _docker_add_macos_path()
    if not command_exists("docker"):
        log("Docker is not available. Install Docker Desktop manually from https://www.docker.com/products/docker-desktop/")
        return 1, "\n".join(output)
    container_name = f"serverinstaller-{service_id}"
    # Remove existing
    run_capture(["docker", "rm", "-f", container_name], timeout=15)
    cmd = ["docker", "run", "-d", "--name", container_name,
           "-p", f"{port}:{container_port}", "--restart", "unless-stopped"]
    # GPU support
    try:
        rc, out = run_capture(["docker", "info", "--format", "{{.Runtimes}}"], timeout=10)
        if "nvidia" in str(out).lower():
            cmd.extend(["--gpus", "all"])
            log("NVIDIA GPU detected.")
    except Exception:
        pass
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(image)
    log(f"Running: {' '.join(cmd)}")
    code = _run_install_cmd(cmd, log, timeout=600)
    if code == 0:
        state_dir.mkdir(parents=True, exist_ok=True)
        display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
        state = _read_json_file(state_file)
        state.update({"installed": True, "service_name": container_name, "deploy_mode": "docker",
                       "host": host, "http_port": port, "http_url": f"http://{display_host}:{port}"})
        _write_json_file(state_file, state)
        manage_firewall_port("open", port, "tcp")
        log(f"\n{display_name} running on port {port}")
    return code, "\n".join(output)


def run_tgwui_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("tgwui", "atinoda/text-generation-webui:default-nightly", form, "7860", "7860", "Text Generation WebUI", TGWUI_STATE_FILE, TGWUI_STATE_DIR, live_cb)

def run_comfyui_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("comfyui", "yanwk/comfyui-boot:latest", form, "8188", "8188", "ComfyUI", COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, live_cb)

def run_whisper_docker(form=None, live_cb=None):
    model = (form or {}).get("WHISPER_MODEL_SIZE", ["base"])
    model_size = model[0] if isinstance(model, list) else model
    return _run_ai_docker_generic("whisper", "onerahmet/openai-whisper-asr-webservice:latest", form, "9000", "9000", "Whisper STT",
        WHISPER_STATE_FILE, WHISPER_STATE_DIR, live_cb, extra_args=["-e", f"ASR_MODEL={model_size}"])

def run_piper_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("piper", "rhasspy/wyoming-piper:latest", form, "5500", "10200", "Piper TTS", PIPER_STATE_FILE, PIPER_STATE_DIR, live_cb,
        extra_args=["-v", "piper-data:/data", "-e", "PIPER_VOICE=en_US-lessac-medium"])


# ── AI service name detection helpers ────────────────────────────────────────
def _is_ollama_name(name):
    return bool(re.search(r'ollama', str(name or ""), re.IGNORECASE))

def _is_tgwui_name(name):
    return bool(re.search(r'tgwui|text.generation.webui|oobabooga', str(name or ""), re.IGNORECASE))

def _is_comfyui_name(name):
    return bool(re.search(r'comfyui|comfy.ui', str(name or ""), re.IGNORECASE))

def _is_whisper_name(name):
    return bool(re.search(r'whisper', str(name or ""), re.IGNORECASE))

def _is_piper_name(name):
    return bool(re.search(r'piper', str(name or ""), re.IGNORECASE))


def filter_service_items(scope):
    scope = str(scope or "all").strip().lower()
    items = get_service_items()
    if scope == "all":
        return items
    if scope == "website":
        return _website_service_items()
    if scope == "docker":
        return [x for x in items if x.get("kind") == "docker" or _is_docker_name(x.get("name", "")) or _is_docker_name(x.get("display_name", ""))]
    if scope == "mongo":
        return [x for x in items if _is_mongo_name(x.get("name", "")) or _is_mongo_name(x.get("display_name", ""))]
    if scope == "s3":
        return [x for x in items if _is_locals3_name(x.get("name", "")) or _is_locals3_name(x.get("display_name", ""))]
    if scope == "dotnet":
        return [x for x in items if x.get("kind") == "iis_site" or _is_dotnet_name(x.get("name", "")) or _is_dotnet_name(x.get("display_name", ""))]
    if scope == "proxy":
        proxy_info = get_proxy_info()
        proxy_items = proxy_info.get("services") or []
        if proxy_items:
            return proxy_items
        return [x for x in items if _is_proxy_name(x.get("name", "")) or _is_proxy_name(x.get("display_name", ""))]
    if scope == "python":
        python_info = get_python_info()
        python_items = python_info.get("services") or []
        if python_items:
            return python_items
        return [x for x in items if _is_python_name(x.get("name", "")) or _is_python_name(x.get("display_name", ""))]
    if scope == "sam3":
        sam3_info = get_sam3_info()
        sam3_items = sam3_info.get("services") or []
        if sam3_items:
            return sam3_items
        return [x for x in items if _is_sam3_name(x.get("name", "")) or _is_sam3_name(x.get("display_name", ""))]
    # New AI services
    ai_scope_map = {
        "ollama": (get_ollama_info, _is_ollama_name),
        "lmstudio": (get_lmstudio_info, lambda n: bool(re.search(r'lmstudio|lm.studio', str(n or ""), re.IGNORECASE))),
        "openclaw": (get_openclaw_info, lambda n: bool(re.search(r'openclaw', str(n or ""), re.IGNORECASE))),
        "tgwui": (get_tgwui_info, _is_tgwui_name),
        "comfyui": (get_comfyui_info, _is_comfyui_name),
        "whisper": (get_whisper_info, _is_whisper_name),
        "piper": (get_piper_info, _is_piper_name),
    }
    if scope in ai_scope_map:
        get_info_fn, is_name_fn = ai_scope_map[scope]
        info = get_info_fn()
        svc_items = info.get("services") or []
        if svc_items:
            return svc_items
        return [x for x in items if is_name_fn(x.get("name", "")) or is_name_fn(x.get("display_name", ""))]
    # Generic AI services — use state file if exists
    _generic_ai_scopes = ["vllm", "llamacpp", "deepseek", "localai", "sdwebui", "fooocus", "coqui", "bark", "rvc", "openwebui", "chromadb", "custom"]
    if scope in _generic_ai_scopes:
        state_file = SERVER_INSTALLER_DATA / scope / f"{scope}-state.json"
        info = _get_ai_service_info(state_file, SERVER_INSTALLER_DATA / scope, f"serverinstaller-{scope}", scope, "8080")
        svc_items = info.get("services") or []
        if svc_items:
            return svc_items
        pat = re.compile(re.escape(scope), re.IGNORECASE)
        return [x for x in items if pat.search(str(x.get("name", ""))) or pat.search(str(x.get("display_name", "")))]
    return items


def _safe_linux_app_path(path_value, svc_name=""):
    if not path_value:
        return ""
    p = str(path_value).strip()
    if not p.startswith("/"):
        return ""
    safe_bases = ("/opt/", "/srv/", "/var/www/", "/usr/local/", "/home/", "/root/")
    if not any(p.startswith(base) for base in safe_bases):
        return ""
    if p in ("/opt", "/srv", "/var/www", "/usr/local", "/home", "/root"):
        return ""
    low = p.lower()
    svc_low = str(svc_name or "").lower().replace(".service", "")
    if _is_dotnet_name(svc_name) and (("dotnet" in low) or ("aspnet" in low) or (svc_low and svc_low in low)):
        return p
    if _is_locals3_name(svc_name) and ("locals3" in low):
        return p
    if _is_website_name(svc_name) and (("server-installer" in low and "website" in low) or (svc_low and svc_low in low)):
        return p
    return ""


def _windows_cleanup_localmongo(svc_name="LocalMongoDB"):
    if not is_windows_admin():
        return False, "Administrator is required."
    safe = _safe_service_name(svc_name) or "LocalMongoDB"
    # Derive data root from service name (LocalMongoDB-{instance} → ProgramData\LocalMongoDB-{instance})
    data_root_name = safe  # same as service name
    ps = (
        "$ErrorActionPreference='SilentlyContinue'\n"
        "Import-Module WebAdministration -ErrorAction SilentlyContinue\n"
        f"if (Test-Path \"IIS:\\Sites\\{safe}\") {{\n"
        f"  Stop-Website -Name '{safe}' | Out-Null\n"
        f"  Remove-Website -Name '{safe}' | Out-Null\n"
        "}\n"
        # --- Kill mongod.exe first so the service process is dead before we touch SCM ---
        f"$instRoot = (Join-Path $env:ProgramData '{data_root_name}').ToLower()\n"
        "Get-WmiObject Win32_Process -Filter \"Name='mongod.exe'\" -ErrorAction SilentlyContinue | ForEach-Object {\n"
        "  $exe = if($_.ExecutablePath){ $_.ExecutablePath.ToLower() } else { '' }\n"
        "  $cmd = if($_.CommandLine){ $_.CommandLine.ToLower() } else { '' }\n"
        "  if($exe.StartsWith($instRoot) -or $cmd -match [regex]::Escape($instRoot)){\n"
        "    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue\n"
        "  }\n"
        "}\n"
        # Use sc.exe stop + sc.exe query so no .NET ServiceController handle is kept open.
        # A live ServiceController ($svc) holds an SCM handle that blocks finalization of
        # sc.exe delete and keeps the service visible in services.msc.
        f"sc.exe stop '{safe}' | Out-Null\n"
        "$waited = 0\n"
        "do {\n"
        "  Start-Sleep -Seconds 1; $waited++\n"
        f"  $qout = (sc.exe query '{safe}' 2>$null) -join ' '\n"
        "} while ($waited -lt 30 -and $qout -notmatch 'STOPPED')\n"
        "Start-Sleep -Seconds 1\n"
        # Delete the service entry. With no .NET handles open, sc.exe delete causes the SCM
        # to immediately finalize removal — the service vanishes from services.msc on next refresh.
        f"sc.exe delete '{safe}' | Out-Null\n"
        # Belt-and-suspenders: also nuke the registry key so Get-Service never sees it again.
        f"Remove-Item -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\{safe}' -Recurse -Force -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Seconds 1\n"
        "$bindings = @('0.0.0.0:9445','127.0.0.1:9445')\n"
        "foreach($binding in $bindings){\n"
        "  netsh http delete sslcert ipport=$binding 1>$null 2>$null | Out-Null\n"
        "}\n"
        "if(Get-Command docker -ErrorAction SilentlyContinue){\n"
        f"  docker rm -f {safe}-https {safe}-web {safe}-mongodb 1>$null 2>$null | Out-Null\n"
        f"  docker network rm {safe}-net 1>$null 2>$null | Out-Null\n"
        f"  docker volume rm -f {safe}-data 1>$null 2>$null | Out-Null\n"
        "}\n"
        f"schtasks /End /TN \"{safe}-Autostart\" 1>$null 2>$null | Out-Null\n"
        f"schtasks /Delete /TN \"{safe}-Autostart\" /F 1>$null 2>$null | Out-Null\n"
        f"$root = Join-Path $env:ProgramData '{data_root_name}'\n"
        "if(Test-Path $root){ Remove-Item -Recurse -Force -Path $root -ErrorAction SilentlyContinue }\n"
        "Get-NetFirewallRule -DisplayName 'ServerInstaller-Managed-TCP-27017' -ErrorAction SilentlyContinue | Remove-NetFirewallRule\n"
        "try {\n"
        "  $cert = Get-ChildItem Cert:\\LocalMachine\\Root | Where-Object { $_.Subject -match 'CN=Caddy Local Authority' -or $_.FriendlyName -match 'Caddy' }\n"
        "  foreach($item in $cert){ Remove-Item -Path $item.PSPath -Force -ErrorAction SilentlyContinue }\n"
        "} catch {}\n"
    )
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=150)
    return rc == 0, (out or f"MongoDB instance '{safe}' removed.")


def _linux_cleanup_localmongo(prefix):
    run_capture(prefix + ["systemctl", "disable", "--now", "localmongo-stack"], timeout=60)
    run_capture(prefix + ["rm", "-f", "/etc/systemd/system/localmongo-stack.service"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    run_capture(prefix + ["launchctl", "bootout", "system", "/Library/LaunchDaemons/com.localmongo.stack.plist"], timeout=30)
    run_capture(prefix + ["rm", "-f", "/Library/LaunchDaemons/com.localmongo.stack.plist"], timeout=30)
    if command_exists("docker"):
        run_capture(prefix + ["docker", "rm", "-f", "localmongo-https", "localmongo-web", "localmongo-mongodb"], timeout=60)
        run_capture(prefix + ["docker", "network", "rm", "localmongo-net"], timeout=30)
        run_capture(prefix + ["docker", "volume", "rm", "-f", "localmongo-data"], timeout=30)
    run_capture(prefix + ["rm", "-rf", "/opt/localmongo"], timeout=30)
    run_capture(prefix + ["rm", "-rf", "/usr/local/localmongo"], timeout=30)
    run_capture(prefix + ["rm", "-f", "/usr/local/share/ca-certificates/localmongo.crt"], timeout=30)
    run_capture(prefix + ["update-ca-certificates"], timeout=60)
    return True, "LocalMongoDB service and managed files removed."


def _linux_cleanup_locals3(prefix):
    cmds = [
        ["systemctl", "stop", "locals3-minio"],
        ["systemctl", "disable", "locals3-minio"],
        ["rm", "-f", "/etc/systemd/system/locals3-minio.service"],
        ["rm", "-f", "/etc/default/locals3-minio"],
        ["rm", "-f", "/etc/nginx/conf.d/locals3.conf"],
        ["rm", "-f", "/usr/local/share/ca-certificates/locals3.crt"],
        ["rm", "-rf", "/opt/locals3"],
        ["pkill", "-f", "nginx -c /opt/locals3/nginx/nginx-standalone.conf"],
    ]
    for cmd in cmds:
        run_capture(prefix + cmd, timeout=60)
    if command_exists("docker"):
        run_capture(prefix + ["docker", "rm", "-f", "minio", "nginx", "console"], timeout=60)
        run_capture(prefix + ["docker", "ps", "-aq", "--filter", "label=com.locals3.installer=true"], timeout=30)
        rc_ids, out_ids = run_capture(prefix + ["docker", "ps", "-aq", "--filter", "label=com.locals3.installer=true"], timeout=30)
        if rc_ids == 0 and out_ids.strip():
            ids = [x.strip() for x in out_ids.splitlines() if x.strip()]
            if ids:
                run_capture(prefix + ["docker", "rm", "-f"] + ids, timeout=60)
        run_capture(prefix + ["docker", "volume", "rm", "-f", "locals3-minio-data"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    run_capture(prefix + ["systemctl", "reload", "nginx"], timeout=30)
    run_capture(prefix + ["update-ca-certificates"], timeout=60)
    return True, "LocalS3 service and managed files removed."


def _linux_cleanup_dotnet_service(prefix, unit_name):
    unit = unit_name if unit_name.endswith(".service") else f"{unit_name}.service"
    run_capture(prefix + ["systemctl", "stop", unit], timeout=30)
    run_capture(prefix + ["systemctl", "disable", unit], timeout=30)

    fragment = ""
    working_dir = ""
    rc_show, out_show = run_capture(prefix + ["systemctl", "show", unit, "-p", "FragmentPath", "-p", "WorkingDirectory"], timeout=30)
    if rc_show == 0 and out_show:
        for line in out_show.splitlines():
            if line.startswith("FragmentPath="):
                fragment = line.split("=", 1)[1].strip()
            elif line.startswith("WorkingDirectory="):
                working_dir = line.split("=", 1)[1].strip()

    if fragment and fragment.startswith("/etc/systemd/system/"):
        run_capture(prefix + ["rm", "-f", fragment], timeout=30)
    else:
        run_capture(prefix + ["rm", "-f", f"/etc/systemd/system/{unit}"], timeout=30)

    base = unit.replace(".service", "")
    run_capture(prefix + ["rm", "-f", f"/etc/nginx/conf.d/{base}.conf"], timeout=30)
    run_capture(prefix + ["rm", "-rf", f"/etc/nginx/ssl/{base}"], timeout=30)

    safe_work = _safe_linux_app_path(working_dir, svc_name=unit)
    if safe_work:
        run_capture(prefix + ["rm", "-rf", safe_work], timeout=60)

    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    run_capture(prefix + ["systemctl", "reload", "nginx"], timeout=30)
    return True, f"Service '{unit}' and managed files removed."


def _linux_cleanup_website_service(prefix, unit_name):
    payload = _website_state_payload(unit_name)
    deploy_root = str(payload.get("deploy_root") or "").strip()
    if platform.system() == "Darwin":
        plist_name = str(payload.get("plist_name") or f"com.serverinstaller.website.{_safe_website_runtime_name(unit_name)}").strip()
        plist_path = f"/Library/LaunchDaemons/{plist_name}.plist"
        run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=30)
        run_capture(prefix + ["rm", "-f", plist_path], timeout=30)
    else:
        unit = unit_name if unit_name.endswith(".service") else f"{unit_name}.service"
        run_capture(prefix + ["systemctl", "stop", unit], timeout=30)
        run_capture(prefix + ["systemctl", "disable", unit], timeout=30)
        run_capture(prefix + ["rm", "-f", f"/etc/systemd/system/{unit}"], timeout=30)
        run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    if deploy_root:
        run_capture(prefix + ["rm", "-rf", deploy_root], timeout=60)
    _cleanup_website_artifacts(unit_name, remove_files=False)
    return True, f"Website '{unit_name}' and managed files removed."


def _windows_cleanup_locals3():
    if not is_windows_admin():
        return False, "Administrator is required."
    ps = r"""
$ErrorActionPreference='SilentlyContinue'
Import-Module WebAdministration -ErrorAction SilentlyContinue
foreach($site in @('LocalS3','LocalS3-IIS','LocalS3-Console')){
  if(Test-Path "IIS:\Sites\$site"){ Stop-Website -Name $site | Out-Null; Remove-Website -Name $site | Out-Null }
}
schtasks /End /TN "LocalS3-MinIO" 1>$null 2>$null | Out-Null
schtasks /Delete /TN "LocalS3-MinIO" /F 1>$null 2>$null | Out-Null
if(Get-Command docker -ErrorAction SilentlyContinue){
  $ids = docker ps -aq --filter "label=com.locals3.installer=true" 2>$null
  if($ids){ docker rm -f $ids 1>$null 2>$null | Out-Null }
  docker rm -f minio nginx console 1>$null 2>$null | Out-Null
  docker volume rm -f locals3-minio-data 1>$null 2>$null | Out-Null
}
foreach($p in @("$env:ProgramData\LocalS3","$env:ProgramData\LocalS3\storage-server","$env:TEMP\locals3-root-ca.cer")){
  if(Test-Path $p){ Remove-Item -Recurse -Force -Path $p -ErrorAction SilentlyContinue }
}
"""
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=120)
    return rc == 0, (out or "LocalS3 managed files cleaned.")


def _windows_remove_iis_site_and_path(site_name):
    if not is_windows_admin():
        return False, "Administrator is required."
    if _is_mongo_name(site_name):
        return _windows_cleanup_localmongo(svc_name)
    ps = (
        "Import-Module WebAdministration -ErrorAction SilentlyContinue; "
        f"$s=Get-Website -Name '{site_name}' -ErrorAction SilentlyContinue; "
        "if($s){ $p=$s.physicalPath; Stop-Website -Name $s.Name -ErrorAction SilentlyContinue | Out-Null; "
        "Remove-Website -Name $s.Name -ErrorAction SilentlyContinue | Out-Null; "
        "if($p -and (Test-Path $p)){ Remove-Item -Recurse -Force -Path $p -ErrorAction SilentlyContinue } }; "
        f"if (Test-Path ('IIS:\\AppPools\\{site_name}')) {{ Stop-WebAppPool -Name '{site_name}' -ErrorAction SilentlyContinue | Out-Null; Remove-WebAppPool -Name '{site_name}' -ErrorAction SilentlyContinue | Out-Null }}"
    )
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=60)
    return rc == 0, (out or f"IIS site '{site_name}' and files removed.")


def _windows_remove_service_and_files(svc_name):
    if not is_windows_admin():
        return False, "Administrator is required."
    if _is_mongo_name(svc_name):
        return _windows_cleanup_localmongo(svc_name)
    website_payload = _website_state_payload(svc_name)
    ps = (
        f"$s=Get-CimInstance Win32_Service -Filter \"Name='{svc_name}'\" -ErrorAction SilentlyContinue; "
        "$bin=''; if($s){$bin=$s.PathName}; "
        f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue; "
        f"sc.exe delete \"{svc_name}\" | Out-Null; "
        "$exe=''; if($bin){ if($bin.StartsWith('\"')){$exe=($bin -split '\"')[1]} else {$exe=($bin -split ' ')[0]} }; "
        "$dir=''; if($exe){$dir=Split-Path -Parent $exe}; "
        "if($dir -and (Test-Path $dir)){ "
        "$d=$dir.ToLowerInvariant(); "
        "if($d.Contains('locals3') -or $d.Contains('dotnet') -or $d.Contains('aspnet') -or $d.Contains('kestrel') -or $d.Contains('server-installer\\python\\api') -or $d.Contains('server-installer/python/api')){ "
        "Remove-Item -Recurse -Force -Path $dir -ErrorAction SilentlyContinue } }"
    )
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=90)
    if rc == 0 and website_payload:
        deploy_root = str(website_payload.get("deploy_root") or "").strip()
        if deploy_root:
            shutil.rmtree(deploy_root, ignore_errors=True)
    return rc == 0, (out or f"Service '{svc_name}' and managed files removed.")


def manage_service(action, name, kind, detail=""):
    action = (action or "").strip().lower()
    kind = (kind or "service").strip().lower()
    svc_name = _safe_service_name(name)
    is_managed_jupyter_service = svc_name in (JUPYTER_SYSTEMD_SERVICE, "serverinstaller-jupyter")
    if action not in ("start", "stop", "restart", "delete", "autostart_on", "autostart_off", "set_startup_type", "change_binding"):
        return False, "Supported actions: start, stop, restart, delete, autostart_on, autostart_off, set_startup_type, change_binding."

    if action == "change_binding":
        import json as _json
        try:
            params = _json.loads(detail) if detail else {}
        except Exception:
            return False, "Invalid binding params (expected JSON)."
        old_port = params.get("old_port")
        new_port = params.get("new_port")
        new_host = (params.get("new_host") or "").strip()
        if not new_port or int(new_port) < 1 or int(new_port) > 65535:
            return False, "Invalid new port number."
        new_port = int(new_port)
        old_port = int(old_port) if old_port else None
        messages = []
        # IIS site: update binding via PowerShell
        if kind == "iis_site" and os.name == "nt":
            if not is_windows_admin():
                return False, "Administrator is required to update IIS bindings."
            bind_ip = new_host or "*"
            ps = (
                f"Import-Module WebAdministration; "
                f"Get-WebBinding -Name '{svc_name}' | Remove-WebBinding; "
                f"New-WebBinding -Name '{svc_name}' -Protocol http -Port {new_port} -IPAddress '{bind_ip}'; "
                f"Start-Website -Name '{svc_name}' -ErrorAction SilentlyContinue"
            )
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=60)
            if not rc == 0:
                return False, (out or f"Failed to update IIS binding for '{svc_name}'.")
            messages.append(f"IIS binding updated to port {new_port}.")
        else:
            messages.append(f"Service binding change requested for '{svc_name}' (kind={kind}). Firewall will be updated; restart the service to apply new port.")
        # Update firewall: close old port, open new port
        if old_port and old_port != new_port:
            manage_firewall_port("close", str(old_port), "tcp")
            messages.append(f"Closed firewall port {old_port}/tcp.")
        manage_firewall_port("open", str(new_port), "tcp")
        messages.append(f"Opened firewall port {new_port}/tcp.")
        return True, " ".join(messages)
    if not svc_name:
        return False, "Invalid service name."

    if kind == "docker":
        if not command_exists("docker"):
            return False, "Docker is not available."
        if action == "autostart_on":
            rc, out = run_capture(["docker", "update", "--restart", "unless-stopped", svc_name], timeout=30)
            return rc == 0, (out or f"Auto-start enabled for docker container '{svc_name}'.")
        if action == "autostart_off":
            rc, out = run_capture(["docker", "update", "--restart", "no", svc_name], timeout=30)
            return rc == 0, (out or f"Auto-start disabled for docker container '{svc_name}'.")
        if action == "set_startup_type":
            _DOCKER_POLICIES = {"unless-stopped", "always", "on-failure", "no"}
            policy = (detail or "").strip().lower()
            if policy not in _DOCKER_POLICIES:
                return False, f"Invalid restart policy '{policy}'. Valid: {', '.join(sorted(_DOCKER_POLICIES))}"
            rc, out = run_capture(["docker", "update", "--restart", policy, svc_name], timeout=30)
            return rc == 0, (out or f"Restart policy set to '{policy}' for '{svc_name}'.")
        if action == "delete":
            rc, out = run_capture(["docker", "rm", "-f", svc_name], timeout=60)
            if rc == 0 and _is_python_name(svc_name):
                _cleanup_python_api_state_entry(svc_name, "docker")
            if rc == 0 and _is_website_name(svc_name):
                _cleanup_website_artifacts(svc_name)
            if _is_locals3_name(svc_name):
                if os.name == "nt":
                    _windows_cleanup_locals3()
                else:
                    _linux_cleanup_locals3(_sudo_prefix())
            if _is_mongo_name(svc_name) and os.name == "nt":
                _windows_cleanup_localmongo(svc_name)
            elif _is_mongo_name(svc_name):
                _linux_cleanup_localmongo(_sudo_prefix())
            return rc == 0, (out or f"Docker container '{svc_name}' deleted.")
        if action in ("start", "stop", "restart"):
            rc, out = run_capture(["docker", action, svc_name], timeout=60)
            return rc == 0, (out or f"Docker container '{svc_name}' {action} requested.")
        return False, "Unsupported docker action."

    if kind == "task" and os.name == "nt":
        if not is_windows_admin():
            return False, "Administrator is required."
        if action == "start":
            rc, out = run_capture(["schtasks", "/Run", "/TN", svc_name], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' started.")
        if action == "stop":
            rc, out = run_capture(["schtasks", "/End", "/TN", svc_name], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' stopped.")
        if action == "restart":
            run_capture(["schtasks", "/End", "/TN", svc_name], timeout=20)
            rc, out = run_capture(["schtasks", "/Run", "/TN", svc_name], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' restarted.")
        if action == "delete":
            rc, out = run_capture(["schtasks", "/Delete", "/TN", svc_name, "/F"], timeout=30)
            if rc == 0 and _is_locals3_name(svc_name):
                _windows_cleanup_locals3()
            return rc == 0, (out or f"Task '{svc_name}' deleted.")
        if action == "autostart_on":
            rc, out = run_capture(["schtasks", "/Change", "/TN", svc_name, "/ENABLE"], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' auto-start enabled.")
        if action == "autostart_off":
            rc, out = run_capture(["schtasks", "/Change", "/TN", svc_name, "/DISABLE"], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' auto-start disabled.")
        if action == "set_startup_type":
            flag = "/ENABLE" if (detail or "").strip().lower() == "enabled" else "/DISABLE"
            rc, out = run_capture(["schtasks", "/Change", "/TN", svc_name, flag], timeout=30)
            return rc == 0, (out or f"Task '{svc_name}' startup type updated.")
        return False, "Unsupported task action."

    if kind == "iis_site" and os.name == "nt":
        if not is_windows_admin():
            return False, "Administrator is required."
        if action == "start":
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Import-Module WebAdministration; Start-Website -Name '{svc_name}'"], timeout=30)
            return rc == 0, (out or f"IIS site '{svc_name}' started.")
        if action == "stop":
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Import-Module WebAdministration; Stop-Website -Name '{svc_name}'"], timeout=30)
            return rc == 0, (out or f"IIS site '{svc_name}' stopped.")
        if action == "restart":
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Import-Module WebAdministration; Stop-Website -Name '{svc_name}' -ErrorAction SilentlyContinue; Start-Website -Name '{svc_name}'"], timeout=30)
            return rc == 0, (out or f"IIS site '{svc_name}' restarted.")
        if action == "delete":
            if _is_locals3_name(svc_name):
                return _windows_cleanup_locals3()
            if _is_mongo_name(svc_name):
                return _windows_cleanup_localmongo(svc_name)
            ok, message = _windows_remove_iis_site_and_path(svc_name)
            if ok and _is_python_name(svc_name):
                _cleanup_python_api_state_entry(svc_name, "iis_site")
            if ok and _is_website_name(svc_name):
                _cleanup_website_artifacts(svc_name)
            return ok, message
        if action in ("autostart_on", "autostart_off", "set_startup_type"):
            val = "$true" if action == "autostart_on" or (action == "set_startup_type" and (detail or "").strip().lower() == "auto") else "$false"
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Import-Module WebAdministration; Set-ItemProperty \"IIS:\\Sites\\{svc_name}\" -Name serverAutoStart -Value {val}"], timeout=30)
            return rc == 0, (out or f"IIS site '{svc_name}' auto-start updated.")
        return False, "Unsupported IIS action."

    if kind == "python_runtime":
        if action == "start":
            info = get_python_info()
            code, output = start_python_jupyter(
                host=str(info.get("host") or choose_service_host()),
                port=str(info.get("jupyter_port") or "8888"),
                auth_username=str(info.get("jupyter_username") or ""),
            )
            return code == 0, output
        if action == "stop":
            code, output = stop_python_jupyter()
            return code == 0, output
        if action == "restart":
            stop_python_jupyter()
            info = get_python_info()
            code, output = start_python_jupyter(
                host=str(info.get("host") or choose_service_host()),
                port=str(info.get("jupyter_port") or "8888"),
                auth_username=str(info.get("jupyter_username") or ""),
            )
            return code == 0, output
        if action == "delete":
            return _cleanup_managed_jupyter()
        if action in ("autostart_on", "autostart_off"):
            return False, "Auto-start is not configured for managed Jupyter yet."
        return False, "Unsupported Python runtime action."

    if kind == "python_installation":
        if action == "delete":
            return _cleanup_managed_python()
        return False, "Unsupported managed Python action."

    if kind == "python_version":
        if action == "delete":
            return _hide_detected_python(detail)
        return False, "Detected Python entries only support delete."

    # SAM3 systemd service
    if _is_sam3_name(svc_name):
        if action == "start":
            code, output = run_sam3_start()
            return code == 0, output
        if action == "stop":
            code, output = run_sam3_stop()
            return code == 0, output
        if action == "restart":
            run_sam3_stop()
            code, output = run_sam3_start()
            return code == 0, output
        if action == "delete":
            del_model = "delete_model" in str(detail or "").lower()
            code, output = run_sam3_delete(delete_model=del_model)
            return code == 0, output
        return False, "Unsupported SAM3 action."

    if _is_ollama_name(svc_name):
        if action == "start":
            code, output = run_ollama_start()
            return code == 0, output
        if action == "stop":
            code, output = run_ollama_stop()
            return code == 0, output
        if action == "restart":
            run_ollama_stop()
            code, output = run_ollama_start()
            return code == 0, output
        if action == "delete":
            code, output = run_ollama_delete()
            return code == 0, output
        return False, "Unsupported Ollama action."

    if re.search(r'openclaw', str(svc_name or ""), re.IGNORECASE):
        if action == "start": code, out = run_openclaw_start(); return code == 0, out
        if action == "stop": code, out = run_openclaw_stop(); return code == 0, out
        if action == "restart": run_openclaw_stop(); code, out = run_openclaw_start(); return code == 0, out
        if action == "delete": code, out = run_openclaw_delete(); return code == 0, out

    if re.search(r'lmstudio|lm.studio', str(svc_name or ""), re.IGNORECASE):
        if action == "start": return (run_lmstudio_start()[0] == 0, run_lmstudio_start()[1])
        if action == "stop": return (run_lmstudio_stop()[0] == 0, run_lmstudio_stop()[1])
        if action == "restart": run_lmstudio_stop(); code, out = run_lmstudio_start(); return code == 0, out
        if action == "delete": code, out = run_lmstudio_delete(); return code == 0, out

    if kind == "website_launchd":
        if os.name == "nt":
            return False, "launchd website actions are not available on Windows."
        payload = _website_state_payload(svc_name)
        plist_name = str(payload.get("plist_name") or f"com.serverinstaller.website.{_safe_website_runtime_name(svc_name)}").strip()
        plist_path = f"/Library/LaunchDaemons/{plist_name}.plist"
        prefix = _sudo_prefix()
        if action == "start":
            run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=30)
            rc, out = run_capture(prefix + ["launchctl", "bootstrap", "system", plist_path], timeout=60)
            return rc == 0, (out or f"launchd website '{plist_name}' started.")
        if action == "stop":
            rc, out = run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=60)
            return rc == 0, (out or f"launchd website '{plist_name}' stopped.")
        if action == "restart":
            run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=30)
            rc, out = run_capture(prefix + ["launchctl", "bootstrap", "system", plist_path], timeout=60)
            return rc == 0, (out or f"launchd website '{plist_name}' restarted.")
        if action == "delete":
            return _linux_cleanup_website_service(prefix, svc_name)
        if action in ("autostart_on", "autostart_off"):
            return False, "Auto-start is controlled by launchd for managed website services."
        return False, "Unsupported launchd website action."

    if is_managed_jupyter_service:
        if action == "start":
            info = get_python_info()
            code, output = start_python_jupyter(
                host=str(info.get("host") or choose_service_host()),
                port=str(info.get("jupyter_port") or "8888"),
                auth_username=str(info.get("jupyter_username") or ""),
            )
            return code == 0, output
        if action == "stop":
            code, output = stop_python_jupyter()
            return code == 0, output
        if action == "restart":
            stop_python_jupyter()
            info = get_python_info()
            code, output = start_python_jupyter(
                host=str(info.get("host") or choose_service_host()),
                port=str(info.get("jupyter_port") or "8888"),
                auth_username=str(info.get("jupyter_username") or ""),
            )
            return code == 0, output
        if action == "delete":
            return _cleanup_managed_jupyter()

    if os.name == "nt":
        if not is_windows_admin():
            return False, "Stopping services on Windows requires Administrator."
        if action == "delete" and _is_docker_name(svc_name):
            return False, "Delete is not supported for Docker engine services from the dashboard."
        if action == "delete":
            if _is_locals3_name(svc_name):
                return _windows_cleanup_locals3()
            if _is_mongo_name(svc_name):
                return _windows_cleanup_localmongo(svc_name)
            ok, message = _windows_remove_service_and_files(svc_name)
            if ok and _is_python_name(svc_name):
                _cleanup_python_api_state_entry(svc_name, "service")
            if ok and _is_website_name(svc_name):
                _cleanup_website_artifacts(svc_name, remove_files=False)
            return ok, message
        if action == "set_startup_type":
            _WIN_TYPES = {"Automatic", "Manual", "Disabled"}
            startup_type = (detail or "").strip()
            if startup_type not in _WIN_TYPES:
                return False, f"Invalid startup type '{startup_type}'. Valid: Automatic, Manual, Disabled"
            cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                   f"Set-Service -Name '{svc_name}' -StartupType {startup_type} -ErrorAction Stop"]
            rc, out = run_capture(cmd, timeout=60)
            return rc == 0, (out or f"Startup type set to '{startup_type}' for '{svc_name}'.")
        ps_map = {
            "start": f"Start-Service -Name '{svc_name}' -ErrorAction Stop",
            "stop": f"Stop-Service -Name '{svc_name}' -Force -ErrorAction Stop",
            "restart": f"Restart-Service -Name '{svc_name}' -Force -ErrorAction Stop",
            "autostart_on": f"Set-Service -Name '{svc_name}' -StartupType Automatic -ErrorAction Stop",
            "autostart_off": f"Set-Service -Name '{svc_name}' -StartupType Disabled -ErrorAction Stop",
        }
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_map[action]]
        rc, out = run_capture(cmd, timeout=60)
        return rc == 0, (out or f"Action '{action}' requested for {svc_name}.")

    prefix = _sudo_prefix()
    if command_exists("systemctl"):
        candidates = [svc_name]
        if not svc_name.endswith(".service"):
            candidates.append(f"{svc_name}.service")

        for unit in candidates:
            if action == "delete" and _is_docker_name(unit):
                return False, "Delete is not supported for Docker engine services from the dashboard."
            if action == "autostart_on":
                rc, out = run_capture(prefix + ["systemctl", "enable", unit], timeout=60)
                if rc == 0:
                    return True, (out or f"Auto-start enabled for {unit}.")
                continue
            if action == "autostart_off":
                rc, out = run_capture(prefix + ["systemctl", "disable", unit], timeout=60)
                if rc == 0:
                    return True, (out or f"Auto-start disabled for {unit}.")
                continue
            if action == "set_startup_type":
                sub = "enable" if (detail or "").strip().lower() == "enabled" else "disable"
                rc, out = run_capture(prefix + ["systemctl", sub, unit], timeout=60)
                if rc == 0:
                    return True, (out or f"Startup type updated for {unit}.")
                continue
            if action == "delete":
                if unit.startswith("/") or ".." in unit:
                    return False, "Invalid unit name for delete."
                if _is_locals3_name(unit):
                    return _linux_cleanup_locals3(prefix)
                if _is_dotnet_name(unit):
                    return _linux_cleanup_dotnet_service(prefix, unit)
                if _is_website_name(unit):
                    return _linux_cleanup_website_service(prefix, unit)
                run_capture(prefix + ["systemctl", "stop", unit], timeout=30)
                run_capture(prefix + ["systemctl", "disable", unit], timeout=30)
                unit_file = f"/etc/systemd/system/{unit}"
                rc, out = run_capture(prefix + ["rm", "-f", unit_file], timeout=30)
                run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
                if rc == 0:
                    if _is_python_name(unit):
                        _cleanup_python_api_state_entry(unit, "service")
                    if _is_website_name(unit):
                        _cleanup_website_artifacts(unit, remove_files=False)
                    return True, (out or f"Service unit '{unit}' deleted.")
                continue
            rc, out = run_capture(prefix + ["systemctl", action, unit], timeout=60)
            if rc == 0:
                return True, (out or f"Action '{action}' requested for {unit}.")

        # Fallback to legacy service command if systemctl stop fails for all candidates.
        if command_exists("service") and action in ("start", "stop", "restart"):
            base_name = svc_name[:-8] if svc_name.endswith(".service") else svc_name
            rc, out = run_capture(prefix + ["service", base_name, action], timeout=60)
            if rc == 0:
                return True, (out or f"Action '{action}' requested for {base_name}.")

        return False, f"Failed to run action '{action}' for service '{svc_name}'."

    return False, "No supported service manager found."


def get_system_status(scope="all"):
    scope = str(scope or "all").strip().lower()
    load = None
    try:
        if hasattr(os, "getloadavg"):
            la = os.getloadavg()
            load = {"1m": la[0], "5m": la[1], "15m": la[2]}
    except Exception:
        load = None

    software = {}
    if scope in ("all", "dotnet"):
        software["dotnet"] = get_dotnet_info()
    if scope in ("all", "docker"):
        software["docker"] = get_docker_info()
    if scope in ("all", "mongo"):
        software["docker"] = get_docker_info()
        software["mongo"] = get_mongo_info()
        if os.name == "nt":
            software["iis"] = get_iis_info()
    elif scope in ("all", "s3"):
        software["docker"] = get_docker_info()
        if os.name == "nt":
            software["iis"] = get_iis_info()
    if scope in ("all", "proxy"):
        software["proxy"] = get_proxy_info()
    if scope in ("all", "python"):
        software["python_service"] = get_python_info()
    if scope in ("all", "website"):
        software["website"] = get_website_info()
        if os.name == "nt":
            software["iis"] = get_iis_info()
    if scope in ("all", "sam3"):
        software["sam3_service"] = get_sam3_info()
    if scope in ("all", "ollama"):
        software["ollama_service"] = get_ollama_info()
    if scope in ("all", "lmstudio"):
        software["lmstudio_service"] = get_lmstudio_info()
    if scope in ("all", "openclaw"):
        software["openclaw_service"] = get_openclaw_info()
    if scope in ("all", "tgwui"):
        software["tgwui_service"] = get_tgwui_info()
    if scope in ("all", "comfyui"):
        software["comfyui_service"] = get_comfyui_info()
    if scope in ("all", "whisper"):
        software["whisper_service"] = get_whisper_info()
    if scope in ("all", "piper"):
        software["piper_service"] = get_piper_info()

    status = {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "is_admin": is_windows_admin() if os.name == "nt" else (os.geteuid() == 0 if hasattr(os, "geteuid") else True),
        "is_local_system": is_windows_local_system() if os.name == "nt" else False,
        "os": platform.system(),
        "os_release": platform.release(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "uptime_seconds": get_uptime_seconds(),
        "cpu_count": os.cpu_count(),
        "cpu_usage_percent": get_cpu_usage_percent(),
        "load": load,
        "memory": get_memory_info(),
        "network_totals": get_network_totals(),
        "ips": get_ip_addresses(),
        "public_ip": get_public_ipv4(),
        "listening_ports": get_listening_ports(),
        "software": software,
    }
    return status


def is_windows_admin():
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_windows_local_system():
    if os.name != "nt":
        return False
    username = str(os.environ.get("USERNAME") or "").strip().lower()
    userdomain = str(os.environ.get("USERDOMAIN") or "").strip().lower()
    if username == "system":
        return True
    return userdomain == "nt authority" and username == "system"


def _ps_single_quote(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _add_hosts_entry(domain, ip, live_cb=None):
    """Add a domain→IP entry to the system hosts file."""
    try:
        if os.name == "nt":
            hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
        else:
            hosts_path = Path("/etc/hosts")

        entry = f"{ip}  {domain}"
        existing = ""
        try:
            existing = hosts_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

        if domain in existing:
            if live_cb:
                live_cb(f"Domain '{domain}' already in hosts file.\n")
            return

        with open(str(hosts_path), "a", encoding="utf-8") as f:
            f.write(f"\n{entry}\n")

        if live_cb:
            live_cb(f"Added '{entry}' to {hosts_path}\n")
    except Exception as ex:
        if live_cb:
            live_cb(f"[WARN] Could not update hosts file: {ex}\n")


def get_active_windows_user():
    if os.name != "nt":
        return ""
    rc, out = run_capture(["query", "user"], timeout=15)
    if rc != 0 or not out:
        return ""
    for line in out.splitlines():
        match = re.match(r"^\s*>?(?P<user>\S+)\s+\S+\s+\d+\s+Active\b", line)
        if match:
            return match.group("user").strip()
    return ""


def run_windows_interactive_powershell_file(script_path, env=None, live_cb=None, timeout=3600):
    if os.name != "nt":
        return 1, "Interactive Windows runner is only available on Windows hosts."
    active_user = get_active_windows_user()
    if not active_user:
        return 1, "No active signed-in Windows user session was found."
    job_dir = SERVER_INSTALLER_DATA / "jobs" / "interactive"
    job_dir.mkdir(parents=True, exist_ok=True)
    token = f"{int(time.time())}-{secrets.token_hex(4)}"
    task_name = f"ServerInstaller-Interactive-{token}"
    runner_path = job_dir / f"{token}-runner.ps1"
    log_path = job_dir / f"{token}.log"
    exit_path = job_dir / f"{token}.exit"
    env = env or os.environ.copy()
    passthrough_keys = sorted(
        key for key, value in env.items()
        if str(value or "").strip()
    )
    runner_lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$logFile = {_ps_single_quote(str(log_path))}",
        f"$exitFile = {_ps_single_quote(str(exit_path))}",
        f"$targetScript = {_ps_single_quote(str(script_path))}",
        "$null = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($logFile))",
        "Set-Content -Path $logFile -Value '' -Encoding UTF8",
    ]
    for key in passthrough_keys:
        runner_lines.append(f"$env:{key} = {_ps_single_quote(env.get(key, ''))}")
    runner_lines += [
        "try {",
        "  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $targetScript *>&1 | Tee-Object -FilePath $logFile -Append",
        "  $code = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }",
        "} catch {",
        "  ($_ | Out-String) | Tee-Object -FilePath $logFile -Append | Out-Null",
        "  $code = 1",
        "}",
        "Set-Content -Path $exitFile -Value $code -Encoding ASCII",
        "exit $code",
    ]
    runner_path.write_text("\r\n".join(runner_lines) + "\r\n", encoding="utf-8")

    register_ps = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$taskName = {_ps_single_quote(task_name)}",
        f"$runner = {_ps_single_quote(str(runner_path))}",
        f"$user = {_ps_single_quote(active_user)}",
        "schtasks /Delete /TN $taskName /F 1>$null 2>$null | Out-Null",
        "$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File \"' + $runner + '\"')",
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries",
        "Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null",
        "Start-ScheduledTask -TaskName $taskName",
    ])
    rc, out = run_capture(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", register_ps],
        timeout=60,
    )
    if rc != 0:
        try:
            runner_path.unlink(missing_ok=True)
        except Exception:
            pass
        return 1, out or "Failed to start interactive installer task."

    chunks = []
    offset = 0
    deadline = time.time() + max(30, int(timeout))
    try:
        while time.time() < deadline:
            if log_path.exists():
                try:
                    content = log_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""
                if offset < len(content):
                    new_text = content[offset:]
                    offset = len(content)
                    chunks.append(new_text)
                    if live_cb and new_text:
                        live_cb(new_text)
            if exit_path.exists():
                break
            time.sleep(0.7)
        if not exit_path.exists():
            return 1, "".join(chunks).rstrip() + ("\nTimed out waiting for interactive installer task." if chunks else "Timed out waiting for interactive installer task.")
        try:
            exit_code = int(exit_path.read_text(encoding="ascii", errors="ignore").strip() or "1")
        except Exception:
            exit_code = 1
        return exit_code, "".join(chunks).strip()
    finally:
        cleanup_ps = "\n".join([
            f"$taskName = {_ps_single_quote(task_name)}",
            "Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null",
        ])
        run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cleanup_ps], timeout=30)
        for path in (runner_path, exit_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


def validate_os_credentials(username, password):
    username = (username or "").strip()
    if not username or not password:
        return False, "Username and password are required."

    # Check custom dashboard credentials first (works on ALL platforms)
    try:
        creds_file = SERVER_INSTALLER_DATA / "dashboard-credentials.json"
        if not creds_file.exists():
            # Search ALL possible locations (sudo user, root, real user, etc.)
            search_paths = [
                Path.home() / ".server-installer" / "dashboard-credentials.json",
                Path("/var/root/.server-installer/dashboard-credentials.json"),
                Path("/root/.server-installer/dashboard-credentials.json"),
                Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "dashboard-credentials.json",
            ]
            # Also check each user's home on macOS
            if sys.platform == "darwin":
                try:
                    for entry in Path("/Users").iterdir():
                        if entry.is_dir() and not entry.name.startswith("."):
                            search_paths.append(entry / ".server-installer" / "dashboard-credentials.json")
                except Exception:
                    pass
            for alt in search_paths:
                try:
                    if alt.exists():
                        creds_file = alt
                        break
                except Exception:
                    pass
        if creds_file.exists():
            import hashlib
            creds = json.loads(creds_file.read_text(encoding="utf-8"))
            stored_user = str(creds.get("username", "")).strip()
            stored_hash = str(creds.get("password_hash", "")).strip()
            if stored_user and stored_hash:
                input_hash = hashlib.sha256(password.encode()).hexdigest()
                if username == stored_user and input_hash == stored_hash:
                    return True, ""
    except Exception:
        pass

    # Also check environment variable credentials
    env_user = os.environ.get("DASHBOARD_CUSTOM_USER", "").strip()
    env_hash = os.environ.get("DASHBOARD_CUSTOM_PASS_HASH", "").strip()
    if env_user and env_hash:
        import hashlib
        if username == env_user and hashlib.sha256(password.encode()).hexdigest() == env_hash:
            return True, ""

    # Then try OS-level authentication
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

    # macOS: use dscl to authenticate against Open Directory
    if sys.platform == "darwin":
        last_err = ""
        # Try all combinations of directory node and user path format
        attempts = [
            ["dscl", "/Local/Default", "-authonly", f"/Users/{username}", password],
            ["dscl", ".", "-authonly", f"/Users/{username}", password],
            ["dscl", "/Local/Default", "-authonly", username, password],
            ["dscl", ".", "-authonly", username, password],
            ["dscl", "/Search", "-authonly", f"/Users/{username}", password],
        ]
        for cmd in attempts:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    return True, ""
                last_err = (proc.stderr or proc.stdout or "").strip()
            except Exception as ex:
                last_err = str(ex)
        # Log the error for debugging
        print(f"[AUTH] macOS dscl auth failed for '{username}': {last_err}")
        return False, "Invalid macOS username or password."

    # Linux: use crypt/spwd or PAM
    try:
        import crypt
        import spwd

        hashed = spwd.getspnam(username).sp_pwdp
        if not hashed or hashed in ("x", "*", "!", "!!"):
            # Try PAM as fallback
            try:
                rc, _ = run_capture(["su", "-c", "true", username], timeout=10)
                # su requires stdin password — use a different approach
                raise Exception("spwd unavailable")
            except Exception:
                return False, "This account cannot be validated by password."
        return (crypt.crypt(password, hashed) == hashed, "Invalid Linux username/password.")
    except ImportError:
        # crypt/spwd not available (Python 3.13+ removed crypt)
        # Fallback: use PAM via subprocess
        try:
            proc = subprocess.run(
                ["python3", "-c", f"import pam; p=pam.pam(); print(p.authenticate('{username}','{password}'))"],
                capture_output=True, text=True, timeout=10,
            )
            if "True" in proc.stdout:
                return True, ""
        except Exception:
            pass
        # Last resort: try su
        try:
            import pty
            # Can't easily do su non-interactively, so try dscl even on Linux
            rc, _ = run_capture(["dscl", "/Local/Default", "-authonly", username, password], timeout=10)
            if rc == 0:
                return True, ""
        except Exception:
            pass
        return False, "Could not validate credentials. Install python3-pam or run as root."
    except PermissionError:
        return False, "Run dashboard as root to validate Linux system credentials for remote login."
    except Exception:
        return False, "Invalid username/password."


def run_process(cmd, env=None, live_cb=None, input_text=None):
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    chunks = []
    try:
        if input_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(input_text)
                proc.stdin.flush()
            except Exception:
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        if proc.stdout is not None:
            # Stream character-level output so long-running commands are visible live
            # even when underlying tools do not flush newline-delimited lines.
            while True:
                ch = proc.stdout.read(1)
                if ch == "":
                    if proc.poll() is not None:
                        break
                    continue
                chunks.append(ch)
                if live_cb:
                    live_cb(ch)
        proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.returncode, "".join(chunks)


def upload_root_dir():
    candidates = []
    if os.name == "nt":
        d_drive = Path("D:/")
        if d_drive.exists():
            candidates.append(d_drive / "Server-Installer" / "uploads")
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "Server-Installer" / "uploads")
        candidates.append(Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "uploads")
        temp_dir = os.environ.get("TEMP")
        if temp_dir:
            candidates.append(Path(temp_dir) / "Server-Installer" / "uploads")
    else:
        candidates = [
            Path("/var/tmp/server-installer/uploads"),
            Path("/tmp/server-installer/uploads"),
        ]

    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / f".probe-{secrets.token_hex(4)}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return cand
        except Exception:
            continue

    raise RuntimeError("No writable upload directory found.")


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

    # If archive expands to a single wrapper directory, use that as source root.
    children = [p for p in extract_dir.iterdir()]
    chosen_dir = extract_dir
    if len(children) == 1 and children[0].is_dir():
        chosen_dir = children[0]

    # Cleanup transient artifacts created only for transport.
    shutil.rmtree(source_dir, ignore_errors=True)
    try:
        zip_path.unlink(missing_ok=True)
    except Exception:
        pass

    return str(chosen_dir)


def save_uploaded_archive_or_file(item):
    saved = save_uploaded_stream(item.filename, item.file)
    path_obj = Path(saved)
    lower = path_obj.name.lower()
    if lower.endswith(".zip"):
        extract_dir = upload_root_dir() / f"extract-{int(time.time())}-{secrets.token_hex(4)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path_obj, "r") as zf:
            zf.extractall(extract_dir)
        return str(extract_dir)
    if lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar"):
        extract_dir = upload_root_dir() / f"extract-{int(time.time())}-{secrets.token_hex(4)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        mode = "r:gz" if (lower.endswith(".tar.gz") or lower.endswith(".tgz")) else "r:"
        with tarfile.open(path_obj, mode) as tf:
            tf.extractall(extract_dir)
        return str(extract_dir)
    return saved


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


def _download_file_with_timeout(url, target_path, timeout_sec=30):
    with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
        data = resp.read()
    with open(target_path, "wb") as fh:
        fh.write(data)


def ensure_repo_files(relative_paths, live_cb=None, refresh=True, retries=2):
    for rel in relative_paths:
        rel_path = Path(rel)
        target = ROOT / rel_path
        exists_before = target.exists()
        if exists_before and (not refresh):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = target.with_suffix(target.suffix + ".download")
        url = f"{REPO_RAW_BASE}/{rel_path.as_posix()}"
        if exists_before and refresh:
            message = f"Updating required file: {rel_path.as_posix()}"
        else:
            message = f"Downloading required file on demand: {rel_path.as_posix()}"
        if live_cb:
            live_cb(message + "\n")
        else:
            print(message)

        last_error = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                _download_file_with_timeout(url, tmp_target, timeout_sec=30)
                os.replace(tmp_target, target)
                last_error = None
                break
            except Exception as ex:
                last_error = ex
                if tmp_target.exists():
                    tmp_target.unlink(missing_ok=True)
                if live_cb:
                    live_cb(f"[WARN] Download attempt {attempt} failed for {rel_path.as_posix()}: {ex}\n")
                if attempt < max(1, retries):
                    time.sleep(1)
        if last_error is not None:
            if target.exists():
                warn_msg = f"[WARN] Using cached file for {rel_path.as_posix()} after update failure: {last_error}"
                if live_cb:
                    live_cb(warn_msg + "\n")
                else:
                    print(warn_msg)
                continue
            raise RuntimeError(f"Failed to download required file '{rel_path.as_posix()}': {last_error}") from last_error


def is_local_tcp_port_listening(port):
    try:
        p = int(str(port).strip())
    except Exception:
        return False
    if p < 1 or p > 65535:
        return False
    listeners = get_listening_ports(limit=5000)
    for item in listeners:
        proto = str(item.get("proto", "")).lower()
        if not proto.startswith("tcp"):
            continue
        if int(item.get("port", 0)) == p:
            return True
    return False


def _windows_tcp_port_excluded(port):
    if os.name != "nt":
        return False
    try:
        target = int(str(port).strip())
    except Exception:
        return False
    if target < 1 or target > 65535:
        return True
    rc, out = run_capture(
        [
            "netsh",
            "interface",
            "ipv4",
            "show",
            "excludedportrange",
            "protocol=tcp",
        ],
        timeout=20,
    )
    if rc != 0 or not out:
        return False
    for line in out.splitlines():
        m = re.match(r"^\s*(\d+)\s+(\d+)\s*$", line.strip())
        if not m:
            continue
        start = int(m.group(1))
        end = int(m.group(2))
        if start <= target <= end:
            return True
    return False


def _is_windows_tcp_port_usable(port):
    if _windows_tcp_port_excluded(port):
        return False, "reserved by Windows"
    if is_local_tcp_port_listening(port):
        return False, "already in use"
    return True, ""


def _windows_locals3_iis_owns_port(port):
    if os.name != "nt":
        return False
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Import-Module WebAdministration; "
                "$site='LocalS3'; "
                "if (Test-Path \"IIS:\\Sites\\$site\") { "
                "Get-WebBinding -Name $site -Protocol https | "
                "ForEach-Object { $_.bindingInformation } }"
            ),
        ]
        rc, out = run_capture(cmd, timeout=20)
        if rc != 0 or not out:
            return False
        for line in out.splitlines():
            parts = line.strip().split(":")
            if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == int(port):
                return True
    except Exception:
        return False


def _windows_locals3_docker_owns_port(port):
    if os.name != "nt" or not command_exists("docker"):
        return False
    try:
        target = int(str(port).strip())
    except Exception:
        return False
    for name in ("minio", "nginx", "console"):
        details = _get_docker_container_details(name)
        labels = details.get("labels", {}) or {}
        if labels.get("com.locals3.installer") != "true" and not _is_locals3_name(name):
            continue
        for item in details.get("ports", []):
            if int(item.get("port", 0)) == target:
                return True
    return False


def _windows_locals3_native_owns_port(port):
    if os.name != "nt":
        return False
    try:
        target = int(str(port).strip())
    except Exception:
        return False
    ps = rf"""
$ErrorActionPreference='SilentlyContinue'
$conns = Get-NetTCPConnection -State Listen -LocalPort {target} -ErrorAction SilentlyContinue
foreach($conn in $conns) {{
  $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
  if(-not $proc) {{ continue }}
  $procName = [string]$proc.ProcessName
  $procPath = ''
  try {{ $procPath = [string]$proc.Path }} catch {{}}
  $cmdLine = ''
  try {{
    $cmdLine = [string]((Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine)
  }} catch {{}}
  $isManaged = $false
  if($procName -ieq 'minio' -and (($procPath -match 'LocalS3') -or ($cmdLine -match 'LocalS3|run-minio\.cmd'))) {{
    $isManaged = $true
  }}
  if($isManaged) {{
    [PSCustomObject]@{{ managed = $true }} | ConvertTo-Json -Compress
    exit 0
  }}
}}
"""
    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        timeout=20,
    )
    if rc != 0 or not out:
        return False
    try:
        data = json.loads(out)
        return bool(data.get("managed"))
    except Exception:
        return False


def _windows_locals3_owns_port(port):
    return (
        _windows_locals3_iis_owns_port(port)
        or _windows_locals3_docker_owns_port(port)
        or _windows_locals3_native_owns_port(port)
    )


def _windows_localmongo_owns_port(port):
    if os.name != "nt":
        return False
    try:
        target = int(str(port).strip())
    except Exception:
        return False

    details = _get_docker_container_details("localmongo-https")
    for item in details.get("ports", []):
        if int(item.get("port", 0)) == target:
            return True
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Import-Module WebAdministration -ErrorAction SilentlyContinue; "
                "$site='LocalMongoDB'; "
                "if (Test-Path \"IIS:\\Sites\\$site\") { "
                "Get-WebBinding -Name $site | ForEach-Object { $_.bindingInformation } }"
            ),
        ]
        rc, out = run_capture(cmd, timeout=20)
        if rc == 0 and out:
            for line in out.splitlines():
                if parse_port_from_addr(line) == target:
                    return True
    except Exception:
        return False
    return False


def _website_owns_port(port):
    try:
        target = int(str(port).strip())
    except Exception:
        return False
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return False
    site_names = []
    for payload in deployments.values():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "").strip()
        port_text = str(payload.get("port") or "").strip()
        runtime_target = str(payload.get("target") or "").strip().lower()
        if runtime_target == "iis" and os.name == "nt" and name:
            site_names.append(name)
        elif port_text.isdigit() and int(port_text) == target:
            return True
    for site_name in site_names:
        rc, out = run_capture(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "Import-Module WebAdministration -ErrorAction SilentlyContinue; "
                    f"Get-WebBinding -Name '{site_name}' -ErrorAction SilentlyContinue | "
                    "ForEach-Object { $_.bindingInformation }"
                ),
            ],
            timeout=20,
        )
        if rc == 0 and out:
            for line in out.splitlines():
                parsed = parse_port_from_addr(line)
                if parsed and str(parsed).isdigit() and int(parsed) == target:
                    return True
        payload = _website_state_payload(site_name)
        port_text = str(payload.get("port") or "").strip() if payload else ""
        if port_text.isdigit() and int(port_text) == target:
            return True
    return False


def pick_free_local_tcp_port(candidates):
    for p in candidates:
        try:
            port = int(str(p).strip())
        except Exception:
            continue
        if port < 1 or port > 65535:
            continue
        if not is_local_tcp_port_listening(port):
            return port
    return None


def _linux_locals3_nginx_owns_port(port):
    if os.name == "nt":
        return False
    try:
        p = int(str(port).strip())
    except Exception:
        return False
    conf = Path("/etc/nginx/conf.d/locals3.conf")
    if not conf.exists():
        return False
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return re.search(rf"\blisten\s+{p}\b", text) is not None


def _docker_locals3_owns_port(port):
    if os.name == "nt":
        return False
    if not command_exists("docker"):
        return False
    try:
        p = int(str(port).strip())
    except Exception:
        return False
    if p < 1 or p > 65535:
        return False
    rc, out = run_capture(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.locals3.installer=true",
            "--format",
            "{{.Names}}\t{{.Ports}}",
        ],
        timeout=15,
    )
    if rc != 0 or not out:
        return False
    marker = f":{p}->"
    for line in out.splitlines():
        parts = line.split("\t", 1)
        ports = parts[1] if len(parts) > 1 else ""
        if marker in ports:
            return True
    return False


def _docker_instance_owns_port(port, instance_name):
    """Returns True if containers of the given S3 instance already own this host port."""
    if os.name == "nt" or not command_exists("docker"):
        return False
    try:
        p = int(str(port).strip())
    except Exception:
        return False
    if p < 1 or p > 65535:
        return False
    rc, out = run_capture(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.locals3.instance={instance_name}",
            "--format",
            "{{.Names}}\t{{.Ports}}",
        ],
        timeout=15,
    )
    if rc != 0 or not out:
        return False
    marker = f":{p}->"
    for line in out.splitlines():
        parts = line.split("\t", 1)
        ports = parts[1] if len(parts) > 1 else ""
        if marker in ports:
            return True
    return False


def _linux_locals3_owns_port(port):
    return _linux_locals3_nginx_owns_port(port) or _docker_locals3_owns_port(port)


def _get_linux_minio_direct_ports():
    """Return port dicts for MinIO --address and --console-address ports from all systemd minio service files."""
    if os.name == "nt":
        return []
    svc_dir = Path("/etc/systemd/system")
    if not svc_dir.exists():
        return []
    ports = []
    seen_ports = set()
    try:
        for svc_file in svc_dir.glob("*-minio.service"):
            try:
                text = svc_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("ExecStart="):
                    continue
                for m in re.finditer(r"--(?:address|console-address)\s+:(\d+)", line):
                    port = int(m.group(1))
                    if port > 0 and port not in seen_ports:
                        seen_ports.add(port)
                        ports.append({"port": port, "protocol": "tcp"})
    except Exception:
        pass
    return ports


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


def start_live_job(title, runner):
    job_id = secrets.token_hex(12)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "title": title,
            "output": f"[{time.strftime('%H:%M:%S')}] Job accepted: {title}\n",
            "done": False,
            "exit_code": None,
            "created": time.time(),
        }

    def append_out(text):
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["output"] += text

    def heartbeat():
        last_len = -1
        unchanged_ticks = 0
        while True:
            time.sleep(5)
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return
                if job["done"]:
                    return
                current_len = len(job["output"])
                if current_len == last_len:
                    unchanged_ticks += 1
                    if unchanged_ticks >= 6:
                        job["output"] += f"[{time.strftime('%H:%M:%S')}] still running...\n"
                        unchanged_ticks = 0
                else:
                    unchanged_ticks = 0
                last_len = len(job["output"])

    def worker():
        try:
            code, output = runner(append_out)
            with JOBS_LOCK:
                if job_id in JOBS:
                    current_output = JOBS[job_id]["output"]
                    if output and not current_output.endswith(output):
                        JOBS[job_id]["output"] += output
                    JOBS[job_id]["exit_code"] = code
                    JOBS[job_id]["done"] = True
        except Exception as ex:
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["output"] += f"\nUnhandled error: {ex}\n"
                    JOBS[job_id]["exit_code"] = 1
                    JOBS[job_id]["done"] = True

    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    return job_id


def page_login(message=""):
    return render_login_page(message)


def page_dashboard_mui(message="", system_name=""):
    s3_docker = get_windows_s3_docker_support() if (system_name or platform.system()).lower() == "windows" else {"supported": True, "reason": ""}
    config = {
        "os": (system_name or platform.system()).lower(),
        "os_label": platform.system(),
        "message": message or "",
        "s3_windows_docker_supported": bool(s3_docker.get("supported", True)),
        "s3_windows_docker_reason": str(s3_docker.get("reason") or ""),
    }
    return render_dashboard_page(config, DASHBOARD_UI_SCRIPTS, dashboard_root=ROOT / "dashboard")


def page_dashboard(message=""):
    system_name = platform.system().lower()
    return page_dashboard_mui(message, system_name)


def page_output(title, output, code):
    return render_output_page(title, output, code)


def page_mongo_native_ui():
    info = get_windows_native_mongo_info() if os.name == "nt" else {}
    connection = str(info.get("connection") or "")
    version = str(info.get("version") or "")
    web_version = str(info.get("web_version") or "native-service")
    auth_enabled = bool(info.get("auth_enabled"))
    host = choose_service_host()
    port = str(info.get("port") or "27017")
    if not connection and port.isdigit():
        connection = f"mongodb://{host}:{int(port)}/"
    auth_text = "enabled" if auth_enabled else "not initialized"
    tls_text = "disabled"
    compass_uri = get_windows_native_mongo_uri(loopback=False) if os.name == "nt" else connection
    login_hint = (
        "Enter the MongoDB admin credentials to unlock the web manager."
        if auth_enabled else
        "Authentication is not initialized on this MongoDB service. You can continue without credentials, or enter credentials if you enabled auth manually."
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MongoDB Web</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0b1220;color:#e5eefc;padding:24px;margin:0}}
.card{{max-width:1280px;margin:0 auto;background:#111a2e;border:1px solid #243454;border-radius:16px;padding:24px}}
.muted{{color:#a9b9d5}}
.row{{margin:10px 0}}
.pill{{display:inline-block;padding:6px 10px;border-radius:999px;background:#1d4ed8;color:#fff;font-size:12px;margin-right:8px}}
a{{color:#93c5fd}}
code, pre{{background:#0a1020;padding:3px 6px;border-radius:6px;color:#dbeafe}}
.actions{{margin-top:18px;display:flex;gap:12px;flex-wrap:wrap}}
.btn{{display:inline-block;padding:10px 14px;border-radius:10px;text-decoration:none;background:#2563eb;color:#fff;border:0;cursor:pointer;font:inherit}}
.btn.secondary{{background:#334155}}
.btn.danger{{background:#b91c1c}}
.layout{{display:grid;grid-template-columns:260px 280px 1fr;gap:16px;margin-top:20px}}
.panel{{background:#0f172a;border:1px solid #22304a;border-radius:14px;padding:14px;min-height:420px}}
.panel h3{{margin:0 0 12px 0;font-size:16px}}
.list{{display:flex;flex-direction:column;gap:8px;max-height:420px;overflow:auto}}
.item{{padding:10px 12px;border-radius:10px;border:1px solid #243454;background:#111827;color:#e5eefc;cursor:pointer;text-align:left}}
.item.active{{border-color:#60a5fa;background:#13213c}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px 0}}
textarea{{width:100%;min-height:180px;background:#0a1020;color:#dbeafe;border:1px solid #22304a;border-radius:12px;padding:12px;font-family:Consolas,monospace}}
select,input{{background:#0a1020;color:#dbeafe;border:1px solid #22304a;border-radius:10px;padding:8px 10px}}
pre{{white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;padding:14px}}
.stack{{display:flex;flex-direction:column;gap:14px}}
.login-shell{{margin-top:20px;display:grid;grid-template-columns:minmax(320px,520px);justify-content:center}}
.login-panel{{min-height:auto}}
.hidden{{display:none}}
.status{{margin-top:10px;padding:10px 12px;border-radius:10px;border:1px solid #243454;background:#0a1020}}
.status.error{{border-color:#7f1d1d;color:#fecaca;background:#220c12}}
.status.ok{{border-color:#14532d;color:#bbf7d0;background:#0a1f17}}
.auth-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.auth-grid label{{display:flex;flex-direction:column;gap:6px}}
@media (max-width:1100px){{.layout{{grid-template-columns:1fr}}}}
@media (max-width:700px){{.auth-grid{{grid-template-columns:1fr}}}}
</style>
</head><body><div class="card">
<div class="pill">MongoDB</div><div class="pill">Windows Native</div><div class="pill">{html.escape(web_version)}</div>
<h2>MongoDB Web</h2>
<p class="muted">Windows native MongoDB management UI. Sign in on this page, then browse databases and collections, inspect documents, and run `mongosh` commands directly from the dashboard.</p>
<div class="row">Connection: <code>{html.escape(connection or "mongodb://localhost:27017/")}</code></div>
<div class="row">Compass URI: <code id="compassUri">{html.escape(compass_uri or "mongodb://admin:StrongPassword123@localhost:27017/admin?authSource=admin")}</code></div>
<div class="row">Version: <code>{html.escape(version or "unknown")}</code></div>
<div class="row">Authentication: <code>{html.escape(auth_text)}</code></div>
<div class="row">TLS/SSL: <code>{html.escape(tls_text)}</code></div>
<div class="actions">
<a class="btn" href="/">Back To Dashboard</a>
<a class="btn secondary" href="https://www.mongodb.com/try/download/compass" target="_blank" rel="noreferrer noopener">Download Compass</a>
<button class="btn secondary" id="copyCompass" type="button">Copy Compass URI</button>
<button class="btn secondary hidden" id="logoutMongo" type="button">Log Out</button>
</div>
<div class="login-shell" id="loginShell">
  <div class="panel login-panel">
    <h3>Login</h3>
    <p class="muted">{html.escape(login_hint)}</p>
    <div class="auth-grid">
      <label class="muted">Username
        <input id="mongoUser" type="text" autocomplete="username" value="admin">
      </label>
      <label class="muted">Password
        <input id="mongoPassword" type="password" autocomplete="current-password" value="StrongPassword123">
      </label>
    </div>
    <div class="toolbar">
      <button class="btn" id="loginMongo" type="button">Log In</button>
      <button class="btn secondary" id="continueMongo" type="button"{' style="display:none"' if auth_enabled else ''}>Continue Without Login</button>
    </div>
    <div class="status" id="loginStatus">{html.escape(login_hint)}</div>
  </div>
</div>
<div class="layout hidden" id="managerLayout">
  <div class="panel">
    <h3>Databases</h3>
    <div class="toolbar"><button class="btn secondary" id="refreshDbs" type="button">Refresh</button></div>
    <div class="list" id="dbList"><div class="muted">Loading...</div></div>
  </div>
  <div class="panel">
    <h3>Collections</h3>
    <div class="row muted" id="selectedDbLabel">Select a database.</div>
    <div class="list" id="collectionList"><div class="muted">No database selected.</div></div>
  </div>
  <div class="panel">
    <div class="stack">
      <div>
        <h3>Documents</h3>
        <div class="toolbar">
          <label class="muted">Limit <input id="docLimit" type="number" min="1" max="200" value="50"></label>
          <button class="btn secondary" id="refreshDocs" type="button">Load Documents</button>
        </div>
        <pre id="docOutput">Select a collection.</pre>
      </div>
      <div>
        <h3>Command Console</h3>
        <div class="toolbar">
          <label class="muted">Database <input id="commandDb" type="text" value="admin"></label>
          <button class="btn" id="runCommand" type="button">Run</button>
        </div>
        <textarea id="commandText">return db.runCommand({{ ping: 1 }});</textarea>
        <pre id="commandOutput">Run a command to manage MongoDB.</pre>
      </div>
    </div>
  </div>
</div>
<script>
const AUTH_STORAGE_KEY = 'mongo-native-auth-v1';
const state = {{ db: "", collection: "", auth: null }};
const dbList = document.getElementById("dbList");
const collectionList = document.getElementById("collectionList");
const selectedDbLabel = document.getElementById("selectedDbLabel");
const docOutput = document.getElementById("docOutput");
const commandOutput = document.getElementById("commandOutput");
const commandDb = document.getElementById("commandDb");
const commandText = document.getElementById("commandText");
const docLimit = document.getElementById("docLimit");
const loginShell = document.getElementById("loginShell");
const managerLayout = document.getElementById("managerLayout");
const loginStatus = document.getElementById("loginStatus");
const loginBtn = document.getElementById("loginMongo");
const continueBtn = document.getElementById("continueMongo");
const logoutBtn = document.getElementById("logoutMongo");
const mongoUser = document.getElementById("mongoUser");
const mongoPassword = document.getElementById("mongoPassword");
const authRequired = {str(auth_enabled).lower()};

function currentHeaders(extra) {{
  const headers = Object.assign({{ "X-Requested-With": "fetch" }}, extra || {{}});
  if (state.auth) {{
    headers["X-Mongo-User"] = state.auth.username || "";
    headers["X-Mongo-Password"] = state.auth.password || "";
  }}
  return headers;
}}

async function apiGet(url) {{
  const r = await fetch(url, {{ headers: currentHeaders() }});
  return await r.json();
}}
async function apiPost(url, body) {{
  const r = await fetch(url, {{
    method: "POST",
    headers: currentHeaders({{ "Content-Type": "application/x-www-form-urlencoded" }}),
    body: new URLSearchParams(body).toString()
  }});
  return await r.json();
}}
function pretty(value) {{
  return JSON.stringify(value, null, 2);
}}
function setLoginState(message, tone) {{
  loginStatus.textContent = message || '';
  loginStatus.className = 'status' + (tone === 'error' ? ' error' : (tone === 'ok' ? ' ok' : ''));
}}
function setLoggedIn(loggedIn) {{
  loginShell.classList.toggle('hidden', loggedIn);
  managerLayout.classList.toggle('hidden', !loggedIn);
  logoutBtn.classList.toggle('hidden', !loggedIn);
}}
function saveAuth() {{
  try {{
    if (state.auth) {{
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.auth));
    }} else {{
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
    }}
  }} catch (_err) {{}}
}}
function restoreAuth() {{
  try {{
    const raw = sessionStorage.getItem(AUTH_STORAGE_KEY) || '';
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return {{
      username: String(parsed.username || ''),
      password: String(parsed.password || '')
    }};
  }} catch (_err) {{
    return null;
  }}
}}
async function loadDatabases(initialPayload) {{
  dbList.innerHTML = '<div class="muted">Loading...</div>';
  const j = initialPayload || await apiGet('/api/mongo/native/overview');
  if (!j.ok) {{
    dbList.innerHTML = '<div class="muted">' + String(j.error || 'Failed to load databases.') + '</div>';
    return;
  }}
  const dbs = Array.isArray(j.databases) ? j.databases : [];
  if (!dbs.length) {{
    dbList.innerHTML = '<div class="muted">No databases found.</div>';
    return;
  }}
  dbList.innerHTML = '';
  dbs.forEach((item) => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'item' + (state.db === item.name ? ' active' : '');
    btn.textContent = item.name;
    btn.onclick = async () => {{
      state.db = item.name;
      state.collection = '';
      commandDb.value = item.name;
      await loadDatabases();
      await loadCollections();
    }};
    dbList.appendChild(btn);
  }});
}}
async function loadCollections() {{
  if (!state.db) {{
    selectedDbLabel.textContent = 'Select a database.';
    collectionList.innerHTML = '<div class="muted">No database selected.</div>';
    return;
  }}
  selectedDbLabel.textContent = 'Database: ' + state.db;
  collectionList.innerHTML = '<div class="muted">Loading...</div>';
  const j = await apiGet('/api/mongo/native/collections?db=' + encodeURIComponent(state.db));
  if (!j.ok) {{
    collectionList.innerHTML = '<div class="muted">' + String(j.error || 'Failed to load collections.') + '</div>';
    return;
  }}
  const cols = Array.isArray(j.collections) ? j.collections : [];
  if (!cols.length) {{
    collectionList.innerHTML = '<div class="muted">No collections found.</div>';
    return;
  }}
  collectionList.innerHTML = '';
  cols.forEach((item) => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'item' + (state.collection === item.name ? ' active' : '');
    btn.textContent = item.name;
    btn.onclick = async () => {{
      state.collection = item.name;
      await loadCollections();
      await loadDocuments();
    }};
    collectionList.appendChild(btn);
  }});
}}
async function loadDocuments() {{
  if (!state.db || !state.collection) {{
    docOutput.textContent = 'Select a collection.';
    return;
  }}
  docOutput.textContent = 'Loading...';
  const limit = Math.max(1, Math.min(200, Number(docLimit.value || 50)));
  const j = await apiGet('/api/mongo/native/documents?db=' + encodeURIComponent(state.db) + '&collection=' + encodeURIComponent(state.collection) + '&limit=' + encodeURIComponent(limit));
  if (!j.ok) {{
    docOutput.textContent = String(j.error || 'Failed to load documents.');
    return;
  }}
  docOutput.textContent = pretty(j.documents || []);
}}
async function runCommand() {{
  commandOutput.textContent = 'Running...';
  const j = await apiPost('/api/mongo/native/command', {{ db: commandDb.value || 'admin', script: commandText.value || '' }});
  if (!j.ok) {{
    commandOutput.textContent = String(j.error || 'Command failed.');
    return;
  }}
  commandOutput.textContent = pretty(j.result);
  await loadDatabases();
  if (state.db) await loadCollections();
}}
async function attemptLogin(username, password) {{
  state.auth = {{
    username: String(username || ''),
    password: String(password || '')
  }};
  setLoginState('Checking MongoDB credentials...', '');
  const j = await apiGet('/api/mongo/native/overview');
  if (!j.ok) {{
    state.auth = null;
    saveAuth();
    setLoggedIn(false);
    setLoginState(String(j.error || 'Login failed.'), 'error');
    return false;
  }}
  saveAuth();
  setLoggedIn(true);
  setLoginState(authRequired ? 'MongoDB login successful.' : 'Connected to MongoDB.', 'ok');
  await loadDatabases(j);
  return true;
}}
async function submitLogin() {{
  loginBtn.disabled = true;
  continueBtn.disabled = true;
  try {{
    await attemptLogin(mongoUser.value || '', mongoPassword.value || '');
  }} finally {{
    loginBtn.disabled = false;
    continueBtn.disabled = false;
  }}
}}
function logoutMongo() {{
  state.auth = null;
  state.db = '';
  state.collection = '';
  saveAuth();
  setLoggedIn(false);
  dbList.innerHTML = '<div class="muted">Log in to load databases.</div>';
  collectionList.innerHTML = '<div class="muted">No database selected.</div>';
  selectedDbLabel.textContent = 'Select a database.';
  docOutput.textContent = 'Select a collection.';
  commandOutput.textContent = 'Run a command to manage MongoDB.';
  setLoginState(authRequired ? 'Enter MongoDB credentials to continue.' : 'Continue without login or enter credentials.', '');
}}
document.getElementById('refreshDbs').onclick = loadDatabases;
document.getElementById('refreshDocs').onclick = loadDocuments;
document.getElementById('runCommand').onclick = runCommand;
loginBtn.onclick = submitLogin;
continueBtn.onclick = () => attemptLogin('', '');
logoutBtn.onclick = logoutMongo;
mongoPassword.addEventListener('keydown', (ev) => {{
  if (ev.key === 'Enter') {{
    ev.preventDefault();
    submitLogin();
  }}
}});
document.getElementById('copyCompass').onclick = async () => {{
  const text = document.getElementById('compassUri').textContent || '';
  try {{
    await navigator.clipboard.writeText(text);
  }} catch (_err) {{}}
}};
const savedAuth = restoreAuth();
if (savedAuth) {{
  mongoUser.value = savedAuth.username || mongoUser.value;
  mongoPassword.value = savedAuth.password || mongoPassword.value;
  attemptLogin(savedAuth.username || '', savedAuth.password || '');
}} else if (!authRequired) {{
  setLoginState('Authentication is optional here. Continue without login or enter credentials.', '');
}} else {{
  setLoginState('Enter MongoDB credentials to continue.', '');
}}
</script>
</div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def is_local_client(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except Exception:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def parse_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def get_mongo_native_credentials(self):
        username = (self.headers.get("X-Mongo-User", "") or "").strip()
        password = self.headers.get("X-Mongo-Password", "")
        return username, password

    def _handle_api_gateway_get(self):
        """Handle GET requests for the API gateway (S3, Mongo, Proxy, SAM3, Ollama)."""
        from api_gateway import (
            s3_list_buckets, s3_list_objects, s3_info, s3_health, s3_presign,
            mongo_list_databases, mongo_health,
            proxy_list_users, proxy_info, proxy_status, proxy_user_config, proxy_health,
            sam3_model_info, sam3_health,
            ollama_list_models, ollama_running_models, ollama_health,
        )
        path = self.path.split("?", 1)[0]
        query = {}
        if "?" in self.path:
            query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)

        # S3 routes
        if path == "/api/s3/buckets":
            return s3_list_buckets()
        if path == "/api/s3/objects":
            bucket = (query.get("bucket", [""])[0] or "").strip()
            prefix = (query.get("prefix", [""])[0] or "").strip()
            return s3_list_objects(bucket, prefix)
        if path == "/api/s3/info":
            return s3_info()
        if path == "/api/s3/health":
            return s3_health()

        # MongoDB routes
        if path == "/api/mongo/databases":
            username, password = self.get_mongo_native_credentials()
            return mongo_list_databases(username=username, password=password)
        if path == "/api/mongo/health":
            username, password = self.get_mongo_native_credentials()
            return mongo_health(username=username, password=password)

        # Proxy routes
        if path == "/api/proxy/users":
            return proxy_list_users()
        if path == "/api/proxy/info":
            return proxy_info()
        if path == "/api/proxy/status":
            return proxy_status()
        if path.startswith("/api/proxy/users/") and path.endswith("/config"):
            username = path[len("/api/proxy/users/"):-len("/config")]
            return proxy_user_config(unquote(username))
        if path == "/api/proxy/health":
            return proxy_health()

        # SAM3 routes
        if path == "/api/sam3/model-info":
            return sam3_model_info()
        if path == "/api/sam3/health":
            return sam3_health()

        # Ollama routes
        if path == "/api/ollama/tags" or path == "/api/ollama/models":
            return ollama_list_models()
        if path == "/api/ollama/ps":
            return ollama_running_models()
        if path == "/api/ollama/health":
            return ollama_health()

        return None  # Not handled

    def _handle_api_gateway_post(self):
        """Handle POST/PUT/DELETE requests for the API gateway."""
        from api_gateway import (
            s3_create_bucket, s3_delete_bucket, s3_delete_object, s3_presign,
            mongo_create_database, mongo_drop_database, mongo_create_collection,
            mongo_drop_collection, mongo_insert_documents, mongo_update_documents,
            mongo_delete_documents,
            proxy_add_user, proxy_delete_user, proxy_update_password,
            proxy_restart_service, proxy_switch_layer,
            sam3_detect,
            ollama_chat, ollama_generate, ollama_embeddings, ollama_pull_model,
            ollama_delete_model, ollama_show_model, ollama_copy_model, ollama_create_model,
        )
        path = self.path.split("?", 1)[0]
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length) if length > 0 else b""

        def _json_body():
            """Parse JSON body or fall back to form data."""
            if "json" in ctype and raw_body:
                try:
                    return json.loads(raw_body.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            # Fall back to URL-encoded form parsing
            if raw_body and "form" in ctype:
                try:
                    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True).items()}
                except Exception:
                    pass
            return {}

        # S3 routes
        if path == "/api/s3/buckets":
            body = _json_body()
            return s3_create_bucket(body.get("name", ""))
        if path.startswith("/api/s3/buckets/"):
            name = path[len("/api/s3/buckets/"):]
            return s3_delete_bucket(name)
        if path.startswith("/api/s3/objects/"):
            # DELETE /api/s3/objects/{bucket}/{key}
            rest = path[len("/api/s3/objects/"):]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                return s3_delete_object(parts[0], parts[1])
            return {"ok": False, "error": "Invalid path. Use /api/s3/objects/{bucket}/{key}"}
        if path == "/api/s3/presign":
            body = _json_body()
            return s3_presign(body.get("bucket", ""), body.get("key", ""), body.get("expires", 3600))

        # MongoDB routes
        if path == "/api/mongo/databases":
            body = _json_body()
            return mongo_create_database(body.get("name", ""))
        if path.startswith("/api/mongo/databases/"):
            name = path[len("/api/mongo/databases/"):]
            username, password = self.get_mongo_native_credentials()
            return mongo_drop_database(name, username=username, password=password)
        if path == "/api/mongo/collections":
            body = _json_body()
            username, password = self.get_mongo_native_credentials()
            return mongo_create_collection(body.get("db", ""), body.get("name", ""), username=username, password=password)
        if path.startswith("/api/mongo/collections/"):
            rest = path[len("/api/mongo/collections/"):]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                username, password = self.get_mongo_native_credentials()
                return mongo_drop_collection(parts[0], parts[1], username=username, password=password)
            return {"ok": False, "error": "Use /api/mongo/collections/{db}/{name}"}
        if path == "/api/mongo/documents":
            body = _json_body()
            username, password = self.get_mongo_native_credentials()
            db_name = body.get("db", "")
            col_name = body.get("collection", "")
            # Determine operation based on body content
            if "documents" in body:
                return mongo_insert_documents(db_name, col_name, body["documents"], username=username, password=password)
            if "update" in body:
                return mongo_update_documents(db_name, col_name, body.get("filter", {}), body["update"], username=username, password=password)
            if "filter" in body and "documents" not in body and "update" not in body:
                return mongo_delete_documents(db_name, col_name, body["filter"], username=username, password=password)
            return {"ok": False, "error": "Provide 'documents' to insert, 'update' to update, or 'filter' to delete."}

        # Proxy routes
        if path == "/api/proxy/users":
            body = _json_body()
            return proxy_add_user(body.get("username", ""), body.get("password"))
        if path.startswith("/api/proxy/users/") and path.endswith("/password"):
            username = path[len("/api/proxy/users/"):-len("/password")]
            body = _json_body()
            return proxy_update_password(unquote(username), body.get("password", ""))
        if path.startswith("/api/proxy/users/"):
            username = path[len("/api/proxy/users/"):]
            return proxy_delete_user(unquote(username))
        if path == "/api/proxy/service/restart":
            return proxy_restart_service()
        if path == "/api/proxy/layer/switch":
            body = _json_body()
            return proxy_switch_layer(body.get("layer", ""))

        # SAM3 routes
        if path == "/api/sam3/detect":
            try:
                parts = self._parse_multipart()
                image_data = b""
                prompt = ""
                threshold = 0.3
                content_type = "image/jpeg"
                for part in parts:
                    if part.get("name") == "image":
                        image_data = part.get("content", b"")
                        if part.get("filename", "").lower().endswith(".png"):
                            content_type = "image/png"
                    elif part.get("name") in ("prompt", "text_prompt"):
                        prompt = part.get("content", b"").decode("utf-8", errors="replace")
                    elif part.get("name") in ("threshold", "confidence"):
                        try:
                            threshold = float(part.get("content", b"0.3").decode())
                        except Exception:
                            pass
                if not image_data:
                    return {"ok": False, "error": "Image file is required."}
                return sam3_detect(image_data, prompt, threshold, content_type)
            except Exception as ex:
                return {"ok": False, "error": str(ex)}

        # Ollama routes
        if path == "/api/ollama/chat":
            body = _json_body()
            return ollama_chat(body.get("model", ""), body.get("messages", []))
        if path == "/api/ollama/generate":
            body = _json_body()
            return ollama_generate(body.get("model", ""), body.get("prompt", ""))
        if path == "/api/ollama/embeddings":
            body = _json_body()
            return ollama_embeddings(body.get("model", ""), body.get("prompt", ""))
        if path == "/api/ollama/pull":
            body = _json_body()
            return ollama_pull_model(body.get("name", ""))
        if path == "/api/ollama/delete":
            body = _json_body()
            return ollama_delete_model(body.get("name", ""))
        if path == "/api/ollama/show":
            body = _json_body()
            return ollama_show_model(body.get("name", ""))
        if path == "/api/ollama/copy":
            body = _json_body()
            return ollama_copy_model(body.get("source", ""), body.get("destination", ""))
        if path == "/api/ollama/create":
            body = _json_body()
            return ollama_create_model(body.get("name", ""), body.get("modelfile", ""))

        return None  # Not handled

    def _parse_multipart(self):
        ctype = self.headers.get("Content-Type", "") or ""
        m = re.search(r'boundary="?([^";]+)"?', ctype, flags=re.IGNORECASE)
        if not m:
            raise RuntimeError("Missing multipart boundary.")
        boundary = m.group(1).encode("utf-8")
        length = int(self.headers.get("Content-Length", "0") or "0")
        data = self.rfile.read(length)
        marker = b"--" + boundary
        parts = []
        for chunk in data.split(marker):
            if not chunk or chunk in (b"--\r\n", b"--", b"\r\n"):
                continue
            if chunk.startswith(b"\r\n"):
                chunk = chunk[2:]
            if chunk.endswith(b"--\r\n"):
                chunk = chunk[:-4]
            elif chunk.endswith(b"\r\n"):
                chunk = chunk[:-2]

            header_blob, sep, body = chunk.partition(b"\r\n\r\n")
            if not sep:
                continue
            headers = {}
            for line in header_blob.decode("utf-8", errors="replace").split("\r\n"):
                k, _, v = line.partition(":")
                if _:
                    headers[k.strip().lower()] = v.strip()
            cd = headers.get("content-disposition", "")
            if not cd:
                continue
            name_m = re.search(r'name="([^"]+)"', cd)
            file_m = re.search(r'filename="([^"]*)"', cd)
            if not name_m:
                continue
            parts.append({
                "name": name_m.group(1),
                "filename": file_m.group(1) if file_m else "",
                "content": body,
            })
        return parts

    def parse_request_form(self):
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        if ctype.startswith("multipart/form-data"):
            try:
                parts = self._parse_multipart()
            except Exception as ex:
                raise RuntimeError(f"Failed to parse multipart upload: {ex}") from ex
            result = {}
            if not parts:
                return result
            grouped = {}
            for p in parts:
                grouped.setdefault(p["name"], []).append(p)

            for key, items in grouped.items():
                folder_items = []
                for it in items:
                    filename = it.get("filename", "")
                    content = it.get("content", b"")
                    if filename:
                        fake_item = type("UploadItem", (), {})()
                        fake_item.filename = filename
                        fake_item.file = io.BytesIO(content)
                        if key in ("SourceFolder", "SOURCE_FOLDER", "SourceUpload"):
                            folder_items.append(fake_item)
                        else:
                            saved = save_uploaded_archive_or_file(fake_item)
                            result.setdefault(key, []).append(saved)
                    else:
                        value = content.decode("utf-8", errors="replace").strip()
                        result.setdefault(key, []).append(value)

                if folder_items:
                    if key == "SourceUpload":
                        if len(folder_items) == 1 and ("/" not in (folder_items[0].filename or "").replace("\\", "/")):
                            saved_single = save_uploaded_archive_or_file(folder_items[0])
                            result.setdefault(key, []).append(saved_single)
                        else:
                            saved_folder = save_uploaded_folder(folder_items)
                            result.setdefault(key, []).append(saved_folder)
                    else:
                        saved_folder = save_uploaded_folder(folder_items)
                        result.setdefault(key, []).append(saved_folder)
            return result
        return self.parse_form()

    def parse_upload_source(self):
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        if not ctype.startswith("multipart/form-data"):
            raise RuntimeError("Upload requires multipart/form-data.")

        parts = self._parse_multipart()
        if not parts:
            raise RuntimeError("Upload form is empty.")
        items = [p for p in parts if p.get("name") == "SourceUpload"]
        if not items:
            raise RuntimeError("No upload selected.")
        files = []
        for p in items:
            if p.get("filename"):
                fake_item = type("UploadItem", (), {})()
                fake_item.filename = p.get("filename", "")
                fake_item.file = io.BytesIO(p.get("content", b""))
                files.append(fake_item)

        valid_files = [it for it in files if getattr(it, "filename", None) and getattr(it, "file", None)]
        if not valid_files:
            raise RuntimeError("No upload selected.")

        looks_like_folder = (len(valid_files) > 1) or any(
            ("/" in (it.filename or "").replace("\\", "/")) for it in valid_files
        )
        if looks_like_folder:
            return save_uploaded_folder(valid_files)

        return save_uploaded_archive_or_file(valid_files[0])

    def set_cookie(self, sid):
        self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly")

    def clear_cookie(self):
        self.send_header("Set-Cookie", "sid=; Path=/; HttpOnly; Max-Age=0")

    def get_sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sid="):
                return part[4:]
        return ""

    def get_session(self):
        sid = self.get_sid()
        session = SESSIONS.get(sid)
        return session if isinstance(session, dict) else {}

    def is_auth(self):
        sid = self.get_sid()
        return bool(sid and sid in SESSIONS)

    def write_html(self, content, status=HTTPStatus.OK, cookie_sid=None, clear_sid=False):
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
            if clear_sid:
                self.clear_cookie()
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

    def _handle_ws_pty(self):
        """Handle /ws/pty WebSocket PTY upgrade in the threaded HTTP server."""
        import hashlib, base64, struct, threading
        from urllib.parse import urlparse, parse_qs as _pqs

        self.close_connection = True

        if (not self.is_local_client()) and (not self.is_auth()):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Dashboard"')
            self.end_headers()
            return

        parsed = urlparse(self.path)
        params = _pqs(parsed.query, keep_blank_values=True)
        cwd_val = (params.get("cwd", [""])[0] or "").strip() or None
        try:
            cols = max(10, min(512, int(params.get("cols", ["80"])[0] or 80)))
        except Exception:
            cols = 80
        try:
            rows = max(2, min(200, int(params.get("rows", ["24"])[0] or 24)))
        except Exception:
            rows = 24

        ws_key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(
            hashlib.sha1((ws_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()

        rfile = self.rfile
        wfile = self.wfile
        send_lock = threading.Lock()

        def _read_exact(n):
            if n == 0:
                return b""
            buf = b""
            while len(buf) < n:
                try:
                    chunk = rfile.read(n - len(buf))
                except Exception:
                    return None
                if not chunk:
                    return None
                buf += chunk
            return buf

        def ws_recv():
            try:
                h = _read_exact(2)
                if not h:
                    return None
                opcode = h[0] & 0x0F
                masked = bool(h[1] & 0x80)
                length = h[1] & 0x7F
                if length == 126:
                    e = _read_exact(2)
                    if not e:
                        return None
                    length = struct.unpack("!H", e)[0]
                elif length == 127:
                    e = _read_exact(8)
                    if not e:
                        return None
                    length = struct.unpack("!Q", e)[0]
                mask = _read_exact(4) if masked else b"\x00\x00\x00\x00"
                if mask is None:
                    return None
                raw = _read_exact(length)
                if raw is None:
                    return None
                payload = bytearray(raw)
                if masked:
                    for i in range(len(payload)):
                        payload[i] ^= mask[i % 4]
                return opcode, bytes(payload)
            except Exception:
                return None

        def ws_send(opcode, payload):
            if isinstance(payload, str):
                payload = payload.encode("utf-8", errors="replace")
            n = len(payload)
            hdr = bytearray([0x80 | opcode])
            if n < 126:
                hdr.append(n)
            elif n < 65536:
                hdr.append(126)
                hdr.extend(struct.pack("!H", n))
            else:
                hdr.append(127)
                hdr.extend(struct.pack("!Q", n))
            with send_lock:
                try:
                    wfile.write(bytes(hdr) + payload)
                    wfile.flush()
                    return True
                except Exception:
                    return False

        done = threading.Event()

        if os.name == "nt":
            try:
                import winpty as _winpty
            except ImportError:
                ws_send(0x1, "\r\nError: pywinpty not installed.\r\n")
                ws_send(0x8, b"")
                return
            shell = os.environ.get("COMSPEC", "cmd.exe")
            try:
                proc = _winpty.PtyProcess.spawn(shell, dimensions=(rows, cols), cwd=cwd_val)
            except Exception as ex:
                ws_send(0x1, f"\r\nFailed to start terminal: {ex}\r\n")
                ws_send(0x8, b"")
                return

            def _pty_read():
                try:
                    while not done.is_set():
                        try:
                            data = proc.read(4096)
                            if data:
                                ws_send(0x1, data)
                            elif not proc.isalive():
                                break
                        except EOFError:
                            break
                        except Exception:
                            break
                finally:
                    done.set()

            def _ws_read():
                nonlocal cols, rows
                try:
                    while not done.is_set():
                        frame = ws_recv()
                        if frame is None:
                            break
                        op, pl = frame
                        if op == 0x8:
                            break
                        if op == 0x9:
                            ws_send(0xA, pl)
                            continue
                        if op in (0x1, 0x2):
                            text = pl.decode("utf-8", errors="replace") if isinstance(pl, bytes) else pl
                            if text.startswith('{"type":"resize"'):
                                try:
                                    r = json.loads(text)
                                    proc.setwinsize(max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))))
                                except Exception:
                                    pass
                            else:
                                try:
                                    proc.write(text)
                                except Exception:
                                    break
                finally:
                    done.set()

            t1 = threading.Thread(target=_pty_read, daemon=True)
            t2 = threading.Thread(target=_ws_read, daemon=True)
            t1.start()
            t2.start()
            done.wait()
            try:
                proc.terminate()
            except Exception:
                pass
        else:
            try:
                import pty as _pty
                import termios as _termios
                import fcntl as _fcntl
            except ImportError as ex:
                ws_send(0x1, f"\r\nError: {ex}\r\n")
                ws_send(0x8, b"")
                return
            shell = os.environ.get("SHELL", "/bin/bash")
            master_fd = slave_fd = proc = None
            try:
                master_fd, slave_fd = _pty.openpty()
                try:
                    _fcntl.ioctl(slave_fd, _termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                except Exception:
                    pass
                env = {**os.environ, "TERM": "xterm-256color"}
                proc = subprocess.Popen(
                    [shell], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                    cwd=cwd_val, env=env, close_fds=True, start_new_session=True,
                )
                os.close(slave_fd)
                slave_fd = None
            except Exception as ex:
                for fd in [slave_fd, master_fd]:
                    if fd is not None:
                        try:
                            os.close(fd)
                        except Exception:
                            pass
                ws_send(0x1, f"\r\nFailed to start terminal: {ex}\r\n")
                ws_send(0x8, b"")
                return

            def _pty_read():
                try:
                    while not done.is_set():
                        try:
                            data = os.read(master_fd, 4096)
                            if data:
                                ws_send(0x2, data)
                            else:
                                break
                        except (OSError, IOError):
                            break
                finally:
                    done.set()

            def _ws_read():
                nonlocal cols, rows
                try:
                    while not done.is_set():
                        frame = ws_recv()
                        if frame is None:
                            break
                        op, pl = frame
                        if op == 0x8:
                            break
                        if op == 0x9:
                            ws_send(0xA, pl)
                            continue
                        if op in (0x1, 0x2):
                            if pl.startswith(b'{"type":"resize"'):
                                try:
                                    r = json.loads(pl.decode("utf-8", errors="replace"))
                                    if r.get("type") == "resize":
                                        _fcntl.ioctl(master_fd, _termios.TIOCSWINSZ,
                                                     struct.pack("HHHH", max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))), 0, 0))
                                except Exception:
                                    pass
                            else:
                                try:
                                    os.write(master_fd, pl)
                                except Exception:
                                    break
                finally:
                    done.set()

            t1 = threading.Thread(target=_pty_read, daemon=True)
            t2 = threading.Thread(target=_ws_read, daemon=True)
            t1.start()
            t2.start()
            done.wait()
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                os.close(master_fd)
            except Exception:
                pass

    def do_GET(self):
        if self.path == "/ws/pty" or self.path.startswith("/ws/pty?"):
            conn_hdr = self.headers.get("Connection", "")
            upg_hdr = self.headers.get("Upgrade", "")
            if "upgrade" in conn_hdr.lower() and upg_hdr.lower() == "websocket":
                self._handle_ws_pty()
                return
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
        if self.path == "/api/status":
            self.write_json({"ok": True}, HTTPStatus.OK)
            return
        if self.path == "/api/website/engines":
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                self.write_json({"ok": True, "engines": _detect_website_engines()}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/system/status"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                scope = (query.get("scope", ["all"])[0] or "all").strip().lower()
                payload = {"ok": True, "status": get_system_status(scope)}
                self.write_json(payload, HTTPStatus.OK)
            except Exception as ex:
                print(f"System status error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/system/services"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                scope = (query.get("scope", ["all"])[0] or "all").strip().lower()
                payload = {"ok": True, "services": filter_service_items(scope)}
                self.write_json(payload, HTTPStatus.OK)
            except Exception as ex:
                print(f"Service list error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/dashboard/version-check"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                installed_sha = _read_installed_commit()
                remote_sha = _fetch_remote_commit_sha(timeout=8)
                if not remote_sha:
                    # Network unavailable — can't determine; return null so button stays hidden
                    self.write_json({"ok": True, "update_available": None,
                                     "installed": installed_sha, "remote": ""}, HTTPStatus.OK)
                    return
                update_available = bool(not installed_sha or remote_sha != installed_sha)
                self.write_json({
                    "ok": True,
                    "update_available": update_available,
                    "installed": installed_sha[:12] if installed_sha else "",
                    "remote": remote_sha[:12],
                }, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/dashboard/cert"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                cfg_data = _dashboard_cert_config()
                mode = cfg_data.get("mode", "self-signed")
                name = cfg_data.get("name", "")
                # Determine which cert file is actually in use
                if mode == "managed" and name:
                    c, k = _get_managed_cert_paths(name)
                else:
                    c = str(DASHBOARD_SELFSIGNED_CERT) if DASHBOARD_SELFSIGNED_CERT.exists() else ""
                    k = str(DASHBOARD_SELFSIGNED_KEY) if DASHBOARD_SELFSIGNED_KEY.exists() else ""
                # Get cert info if available
                cert_info = {}
                if c and Path(c).exists():
                    try:
                        cert_info = ssl_cert_info(Path(c).read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass
                self.write_json({
                    "ok": True,
                    "mode": mode,
                    "name": name,
                    "cert_path": c,
                    "cert_info": cert_info,
                    "managed_certs": ssl_list_certs(),
                }, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/ssl/list"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                certs = ssl_list_certs()
                self.write_json({"ok": True, "certs": certs}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/files/list"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                payload = file_manager_list((query.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/files/download"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                normalized = _normalize_file_manager_path((query.get("path", [""])[0] or "").strip())
                if not normalized:
                    raise RuntimeError("File path is required.")
                path = Path(normalized)
                if not path.exists() or not path.is_file():
                    raise RuntimeError("File not found.")
                data = path.read_bytes()
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
                self.end_headers()
                self.wfile.write(data)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/mongo/native-ui":
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
                return
            self.write_html(page_mongo_native_ui())
            return
        if self.path.startswith("/api/mongo/native/overview"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_overview(username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        if self.path.startswith("/api/mongo/native/collections"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            db_name = (query.get("db", [""])[0] or "").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_collections(db_name, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        if self.path.startswith("/api/mongo/native/documents"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            db_name = (query.get("db", [""])[0] or "").strip()
            collection_name = (query.get("collection", [""])[0] or "").strip()
            limit = (query.get("limit", ["50"])[0] or "50").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_documents(db_name, collection_name, limit, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        # ── API Gateway GET routes ────────────────────────────────────────────
        if self.path.startswith("/api/s3/") or self.path.startswith("/api/mongo/") or self.path.startswith("/api/proxy/") or self.path.startswith("/api/sam3/") or self.path.startswith("/api/ollama/"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                result = self._handle_api_gateway_get()
                if result is not None:
                    status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                    self.write_json(result, status)
                    return
            except Exception as ex:
                print(f"API gateway GET error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if self.path == "/":
            if self.is_local_client() or self.is_auth():
                self.write_html(page_dashboard())
            else:
                self.write_html(page_login())
            return
        if self.path == "/logout":
            sid = self.get_sid()
            if sid in SESSIONS:
                SESSIONS.pop(sid, None)
            self.write_html(page_login(), clear_sid=True)
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
                SESSIONS[sid] = {"username": user, "password": password}
                self.write_html(page_dashboard(), cookie_sid=sid)
            else:
                self.write_html(page_login(error), HTTPStatus.UNAUTHORIZED)
            return

        if (not self.is_local_client()) and (not self.is_auth()):
            self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
            return

        if self.path == "/upload/source":
            try:
                saved_path = self.parse_upload_source()
            except Exception as ex:
                print(f"Upload error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
                return
            self.write_json({"ok": True, "path": saved_path})
            return

        if self.path == "/api/system/port":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            port = (form.get("port", [""])[0] or "").strip()
            protocol = (form.get("protocol", ["tcp"])[0] or "tcp").strip()
            ok, message = manage_firewall_port(action, port, protocol)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/system/port_check":
            form = self.parse_request_form()
            port = (form.get("port", [""])[0] or "").strip()
            protocol = (form.get("protocol", ["tcp"])[0] or "tcp").strip()
            result = get_port_usage(port, protocol)
            status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
            self.write_json(result, status)
            return
        if self.path == "/api/system/service":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            name = (form.get("name", [""])[0] or "").strip()
            kind = (form.get("kind", ["service"])[0] or "service").strip()
            detail = (form.get("detail", [""])[0] or "").strip()
            ports_json = (form.get("ports", [""])[0] or "").strip()
            # Collect ports to close BEFORE deletion (service may disappear after)
            ports_to_close = {}
            if action == "delete":
                try:
                    if ports_json:
                        for p in json.loads(ports_json):
                            port = p.get("port")
                            proto = str(p.get("protocol", "tcp") or "tcp").strip().lower()
                            if port and str(port).isdigit():
                                ports_to_close[(int(port), proto)] = True
                except Exception:
                    pass
                for p in _lookup_service_ports(name, kind):
                    port = p.get("port")
                    proto = str(p.get("protocol", "tcp") or "tcp").strip().lower()
                    if port and str(port).isdigit():
                        ports_to_close[(int(port), proto)] = True
            ok, message = manage_service(action, name, kind, detail)
            if ok and action == "delete":
                for (port, proto) in ports_to_close:
                    manage_firewall_port("close", str(port), proto)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/proxy/service":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            name = (form.get("name", [""])[0] or "").strip()
            ok, message = manage_proxy_service(action, name)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/files/read":
            form = self.parse_request_form()
            try:
                payload = file_manager_read_file((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/files/info"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                # Support both POST form data and GET query params
                info_form = self.parse_request_form()
                path_str = (info_form.get("path", [""])[0] or "").strip() if info_form else ""
                if not path_str:
                    query = {}
                    if "?" in self.path:
                        query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                    path_str = (query.get("path", [""])[0] or "").strip()
                if not path_str:
                    self.write_json({"ok": False, "error": "path is required"}, HTTPStatus.BAD_REQUEST)
                    return
                p = Path(path_str)
                if not p.exists():
                    self.write_json({"ok": False, "error": f"Path does not exist: {path_str}"}, HTTPStatus.NOT_FOUND)
                    return
                st = p.stat()
                is_dir = p.is_dir()
                # For directories count items (non-recursive) and compute recursive size
                item_count = None
                dir_size_bytes = None
                if is_dir:
                    try:
                        items = list(p.iterdir())
                        item_count = len(items)
                    except (PermissionError, OSError):
                        item_count = None
                    try:
                        dir_size_bytes = sum(
                            f.stat().st_size for f in p.rglob("*") if f.is_file()
                        )
                    except (PermissionError, OSError):
                        dir_size_bytes = None
                # Permissions string (rwxrwxrwx style)
                try:
                    import stat as _stat
                    mode = st.st_mode
                    perm_str = _stat.filemode(mode)
                except Exception:
                    perm_str = ""
                # Created time: Windows = st_ctime, Unix = birthtime if available else st_ctime
                created = None
                try:
                    created = int(st.st_birthtime)
                except AttributeError:
                    created = int(st.st_ctime)
                result = {
                    "ok": True,
                    "path": str(p),
                    "name": p.name,
                    "type": "folder" if is_dir else "file",
                    "size_bytes": st.st_size if not is_dir else (dir_size_bytes or 0),
                    "modified": int(st.st_mtime),
                    "created": created,
                    "permissions": perm_str,
                }
                if is_dir:
                    result["item_count"] = item_count
                    result["dir_size_bytes"] = dir_size_bytes
                else:
                    result["extension"] = p.suffix.lstrip(".")
                self.write_json(result, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path == "/api/files/write":
            form = self.parse_request_form()
            try:
                payload = file_manager_write_file(
                    (form.get("path", [""])[0] or "").strip(),
                    form.get("content", [""])[0] or "",
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/mkdir":
            form = self.parse_request_form()
            try:
                payload = file_manager_make_directory((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/delete":
            form = self.parse_request_form()
            try:
                payload = file_manager_delete_path((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/rename":
            form = self.parse_request_form()
            try:
                payload = file_manager_rename_path(
                    (form.get("source", [""])[0] or "").strip(),
                    (form.get("target", [""])[0] or "").strip(),
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/copy":
            form = self.parse_request_form()
            try:
                payload = file_manager_copy_path(
                    (form.get("source", [""])[0] or "").strip(),
                    (form.get("target_dir", [""])[0] or "").strip(),
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/upload":
            try:
                parts = self._parse_multipart()
                target_dir = ""
                upload_parts = []
                for part in parts:
                    if part.get("name") == "target":
                        target_dir = part.get("content", b"").decode("utf-8", errors="replace").strip()
                    elif part.get("name") == "files":
                        upload_parts.append(part)
                written = file_manager_save_uploads(upload_parts, target_dir)
                self.write_json({"ok": True, "written": written}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/mongo/native/command":
            form = self.parse_request_form()
            db_name = (form.get("db", ["admin"])[0] or "admin").strip()
            script_text = (form.get("script", [""])[0] or "").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_run_script(db_name, script_text, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok:
                self.write_json({"ok": True, "result": payload}, status)
            else:
                if not isinstance(payload, dict):
                    payload = {"error": str(payload)}
                self.write_json({"ok": False, **payload}, status)
            return
        # ── API Gateway POST routes ───────────────────────────────────────────
        if self.path.startswith("/api/s3/") or self.path.startswith("/api/mongo/") or self.path.startswith("/api/proxy/") or self.path.startswith("/api/sam3/") or self.path.startswith("/api/ollama/"):
            try:
                result = self._handle_api_gateway_post()
                if result is not None:
                    status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                    self.write_json(result, status)
                    return
            except Exception as ex:
                print(f"API gateway POST error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return

        try:
            form = self.parse_request_form()
        except Exception as ex:
            print(f"Form parse error: {ex}")
            traceback.print_exc()
            if self.is_fetch():
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            else:
                self.write_html(f"Invalid request: {html.escape(str(ex))}", HTTPStatus.BAD_REQUEST)
            return

        session = self.get_session()
        if session:
            session_user = str(session.get("username") or "").strip()
            session_password = str(session.get("password") or "")
            if session_user and "SYSTEM_USERNAME" not in form:
                form["SYSTEM_USERNAME"] = [session_user]
            if session_password and "SYSTEM_PASSWORD" not in form:
                form["SYSTEM_PASSWORD"] = [session_password]

        if self.path == "/run/s3_windows":
            title = "S3 Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_windows":
            title = "MongoDB Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_mongo_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_mongo_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_unix":
            title = "MongoDB Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_unix_mongo_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_unix_mongo_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_docker":
            title = "MongoDB Docker Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_mongo_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_mongo_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/proxy_windows":
            form["SERVER_INSTALLER_DASHBOARD_PORT"] = [str(getattr(self.server, "server_port", ""))]
            title = "Proxy Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_proxy_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_proxy_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/proxy_linux":
            form["SERVER_INSTALLER_DASHBOARD_PORT"] = [str(getattr(self.server, "server_port", ""))]
            title = "Proxy Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_proxy_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_proxy_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_install":
            title = f"Python Installer ({'Windows' if os.name == 'nt' else 'Linux/macOS'})"
            if self.is_fetch():
                runner = (lambda cb: run_windows_python_installer(form, live_cb=cb)) if os.name == "nt" else (lambda cb: run_unix_python_installer(form, live_cb=cb))
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                if os.name == "nt":
                    code, output = run_windows_python_installer(form)
                else:
                    code, output = run_unix_python_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_command":
            title = "Python CMD"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_command(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_command(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_service":
            title = "Python API OS Service"
            runner = (lambda cb: run_windows_python_api_service(form, live_cb=cb)) if os.name == "nt" else (lambda cb: run_unix_python_api_service(form, live_cb=cb))
            if self.is_fetch():
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = runner(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_docker":
            title = "Python API Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_api_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_api_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_update_source":
            title = "Update API Files"
            service_name = (form.get("service_name", [""])[0] or "").strip()
            source_path = (form.get("source_path", [""])[0] or "").strip()
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_api_update_source(service_name, source_path, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_api_update_source(service_name, source_path)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_iis":
            title = "Python API IIS"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_python_api_iis(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_python_api_iis(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_iis":
            title = "Website IIS"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_website_iis(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_website_iis(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_engine_install":
            engine_id = (form.get("ENGINE_ID", [""])[0] or "").strip().lower()
            if not engine_id:
                self.write_json({"ok": False, "error": "ENGINE_ID is required."}, HTTPStatus.BAD_REQUEST)
                return
            title = f"Install {engine_id}"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: _install_website_engine(engine_id, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = _install_website_engine(engine_id)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_deploy":
            target = (form.get("WEBSITE_TARGET", ["service"])[0] or "service").strip().lower()
            engine = (form.get("WEBSITE_ENGINE", [""])[0] or "").strip().lower()
            engine_label_map = {"docker": "Docker", "iis": "IIS", "nginx": "Nginx", "nodejs": "Node.js", "kubernetes": "Kubernetes", "pm2": "PM2", "service": "OS Service"}
            title = f"Website Deploy → {engine_label_map.get(engine or target, target)}"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_website_deploy(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_website_deploy(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_jupyter_start":
            title = "Start Jupyter"
            starter = lambda cb: start_python_jupyter(
                host=(form.get("PYTHON_HOST_IP", [""])[0] or "").strip(),
                port=(form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip(),
                notebook_dir=(form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip(),
                auth_username=(form.get("SYSTEM_USERNAME", [""])[0] or "").strip(),
                auth_password=(form.get("SYSTEM_PASSWORD", [""])[0] or ""),
                live_cb=cb,
            )
            if self.is_fetch():
                job_id = start_live_job(title, starter)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = starter(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_jupyter_stop":
            title = "Stop Jupyter"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: stop_python_jupyter(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = stop_python_jupyter()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_stop":
            title = "S3 Stop (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_iis":
            title = "S3 Installer (Windows IIS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb, mode="iis"))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form, mode="iis")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_docker":
            title = "S3 Installer (Windows Docker)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb, mode="docker"))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form, mode="docker")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_linux":
            selected_mode = (form.get("LOCALS3_MODE", ["os"])[0] or "os").strip().lower()
            if selected_mode == "docker":
                title = "Install S3 (Linux Docker)"
                runner = lambda cb, f=form: run_linux_s3_docker_installer(f, live_cb=cb)
            else:
                title = "S3 Installer (Linux/macOS)"
                runner = lambda cb, f=form: run_linux_s3_installer(f, live_cb=cb)
            if self.is_fetch():
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = runner(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_linux_stop":
            title = "S3 Stop (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_s3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_s3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/sam3_windows", "/run/sam3_windows_os", "/run/sam3_windows_iis"):
            mode = "iis" if self.path == "/run/sam3_windows_iis" else "os"
            form["SAM3_DEPLOY_MODE"] = [mode]
            title = f"SAM3 Installer (Windows {mode.upper()})"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_sam3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_sam3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/sam3_linux", "/run/sam3_linux_os"):
            form["SAM3_DEPLOY_MODE"] = ["os"]
            title = "SAM3 Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_unix_sam3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_unix_sam3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_download_model":
            title = "SAM3 Model Download"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_download_model(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_download_model(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_docker":
            title = "SAM3 Docker Deploy"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_stop":
            title = "SAM3 Stop"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_start":
            title = "SAM3 Start"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_start(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_start()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_delete":
            title = "SAM3 Delete"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_delete()
                self.respond_run_result(title, code, output)
            return
        # ── Ollama routes ─────────────────────────────────────────────────────
        if self.path in ("/run/ollama_windows_os", "/run/ollama_unix_os", "/run/ollama_windows_iis"):
            title = "Ollama Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ollama_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ollama_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ollama_docker":
            title = "Ollama Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ollama_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ollama_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ollama_pull_model":
            model_name = (form.get("OLLAMA_MODEL_NAME", [""])[0] or "").strip()
            title = "Ollama Pull: " + (model_name or "model")
            def _pull_model(cb):
                output = []
                def log(m):
                    output.append(m)
                    if cb: cb(m + "\n")
                log("=== Pulling Ollama model: " + model_name + " ===")
                # First check if ollama is running
                ollama_bin = shutil.which("ollama")
                if not ollama_bin:
                    log("ERROR: Ollama is not installed. Install it first using the Install card above.")
                    return 1, "\n".join(output)
                # Try to start Ollama if not running
                try:
                    import urllib.request
                    urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
                    log("Ollama server is running.")
                except Exception:
                    log("Ollama server not responding. Trying to start it...")
                    if os.name == "nt":
                        subprocess.Popen([ollama_bin, "serve"], creationflags=0x00000008)
                    else:
                        subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import time
                    for i in range(15):
                        time.sleep(2)
                        try:
                            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
                            log("Ollama server started.")
                            break
                        except Exception:
                            log("Waiting for Ollama to start... (" + str(i+1) + "/15)")
                    else:
                        log("ERROR: Could not start Ollama server. Please start it manually.")
                        return 1, "\n".join(output)
                # Pull the model using ollama CLI (shows progress)
                log("Downloading model: " + model_name)
                code = _run_install_cmd([ollama_bin, "pull", model_name], log, timeout=1800)
                if code == 0:
                    log("\nModel '" + model_name + "' pulled successfully!")
                else:
                    log("\nFailed to pull model '" + model_name + "'")
                return code, "\n".join(output)
            if self.is_fetch():
                job_id = start_live_job(title, _pull_model)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = _pull_model(None)
                self.respond_run_result(title, code, output)
            return
        # ── OpenClaw routes ───────────────────────────────────────────────────
        if self.path == "/run/openclaw_docker":
            title = "OpenClaw Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_openclaw_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_openclaw_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/openclaw_windows_os", "/run/openclaw_unix_os"):
            title = "OpenClaw Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_openclaw_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_openclaw_os_install(form)
                self.respond_run_result(title, code, output)
            return
        # ── LM Studio routes ──────────────────────────────────────────────────
        if self.path in ("/run/lmstudio_windows_os", "/run/lmstudio_unix_os"):
            title = "LM Studio Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_lmstudio_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_lmstudio_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/lmstudio_docker":
            title = "LM Studio Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_lmstudio_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_lmstudio_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Text Generation WebUI routes ──────────────────────────────────────
        if self.path in ("/run/tgwui_windows_os", "/run/tgwui_unix_os"):
            title = "Text Gen WebUI Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_tgwui_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_tgwui_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/tgwui_docker":
            title = "Text Gen WebUI Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_tgwui_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_tgwui_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── ComfyUI routes ────────────────────────────────────────────────────
        if self.path in ("/run/comfyui_windows_os", "/run/comfyui_unix_os", "/run/comfyui_windows_iis"):
            title = "ComfyUI Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_comfyui_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_comfyui_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/comfyui_docker":
            title = "ComfyUI Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_comfyui_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_comfyui_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Whisper routes ────────────────────────────────────────────────────
        if self.path in ("/run/whisper_windows_os", "/run/whisper_unix_os", "/run/whisper_windows_iis"):
            title = "Whisper STT Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_whisper_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_whisper_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/whisper_docker":
            title = "Whisper Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_whisper_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_whisper_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Piper TTS routes ──────────────────────────────────────────────────
        if self.path in ("/run/piper_windows_os", "/run/piper_unix_os", "/run/piper_windows_iis"):
            title = "Piper TTS Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_piper_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_piper_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/piper_docker":
            title = "Piper TTS Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_piper_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_piper_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Generic AI service install routes ─────────────────────────────────
        _ai_generic_map = {
            "vllm": ("vLLM", "vllm/vllm-openai:latest", "8000", "pip install vllm"),
            "llamacpp": ("llama.cpp", "ghcr.io/ggerganov/llama.cpp:server", "8080", "git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make -j"),
            "deepseek": ("DeepSeek", "ollama/ollama:latest", "11434", "ollama pull deepseek-coder-v2:lite"),
            "localai": ("LocalAI", "localai/localai:latest-aio-cpu", "8080", ""),
            "sdwebui": ("SD WebUI", "universonic/stable-diffusion-webui:latest", "7860", "git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui"),
            "fooocus": ("Fooocus", "ashleykza/fooocus:latest", "7865", "git clone https://github.com/lllyasviel/Fooocus"),
            "coqui": ("Coqui TTS", "ghcr.io/coqui-ai/tts:latest", "5002", "pip install coqui-tts"),
            "bark": ("Bark", "", "5005", "pip install git+https://github.com/suno-ai/bark.git"),
            "rvc": ("RVC", "alexta69/rvc-webui:latest", "7897", "git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI"),
            "openwebui": ("Open WebUI", "ghcr.io/open-webui/open-webui:main", "3000", "pip install open-webui"),
            "chromadb": ("ChromaDB", "chromadb/chroma:latest", "8000", "pip install chromadb"),
            "custom": ("Custom Model", "", "8080", ""),
            # OS Agents
            "openclaw": ("OpenClaw", "openclaw/openclaw:latest", "8080", "pip install openclaw"),
            "openinterpreter": ("Open Interpreter", "openinterpreter/open-interpreter:latest", "8080", "pip install open-interpreter"),
            "openhands": ("OpenHands", "ghcr.io/all-hands-ai/openhands:latest", "3000", ""),
            "autogpt": ("AutoGPT", "", "8000", "pip install autogpt-forge"),
            "crewai": ("CrewAI", "", "8080", "pip install crewai crewai-tools"),
            "metagpt": ("MetaGPT", "", "8080", "pip install metagpt"),
            "langchain": ("LangChain", "", "8000", "pip install langchain langchain-community langserve uvicorn"),
            "langgraph": ("LangGraph", "", "8123", "pip install langgraph langgraph-cli"),
            "llamaindex": ("LlamaIndex", "", "8000", "pip install llama-index"),
            "haystack": ("Haystack", "", "8000", "pip install haystack-ai"),
            "dify": ("Dify", "langgenius/dify-api:latest", "3000", ""),
            "flowise": ("Flowise", "flowiseai/flowise:latest", "3000", "npx flowise start"),
            "n8n": ("n8n", "n8nio/n8n:latest", "5678", "npx n8n start"),
            "activepieces": ("Activepieces", "activepieces/activepieces:latest", "8080", ""),
        }
        for _ai_key, (_ai_name, _ai_image, _ai_port, _ai_pip) in _ai_generic_map.items():
            if self.path in (f"/run/{_ai_key}_windows_os", f"/run/{_ai_key}_unix_os"):
                title = f"{_ai_name} Install"
                def _make_installer(_name, _pip, _port, _key, _form):
                    def _fn(cb):
                        output = []
                        def log(m):
                            output.append(m)
                            if cb: cb(m + "\n")
                        log(f"=== Installing {_name} ===")
                        host_ip = (_form.get(f"{_key.upper()}_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
                        port = (_form.get(f"{_key.upper()}_HTTP_PORT", [_port])[0] or _port).strip()
                        if _pip:
                            code = _run_install_cmd(_pip, log, timeout=600)
                        else:
                            log(f"No automated OS installer for {_name}. Use Docker instead.")
                            code = 1
                        if code == 0:
                            sdir = SERVER_INSTALLER_DATA / _key
                            sdir.mkdir(parents=True, exist_ok=True)
                            app_dir = sdir / "app"
                            app_dir.mkdir(parents=True, exist_ok=True)
                            display_host = host_ip if host_ip not in ("0.0.0.0", "*", "") else choose_service_host()
                            # Create a web wrapper so the service has an accessible URL
                            wrapper = app_dir / "server.py"
                            wrapper.write_text(
                                f'#!/usr/bin/env python3\n'
                                f'"""Auto-generated web wrapper for {_name}."""\n'
                                f'import os, sys, subprocess, json\n'
                                f'from http.server import HTTPServer, SimpleHTTPRequestHandler\n'
                                f'PORT = int(os.environ.get("PORT", "{port}"))\n'
                                f'HOST = os.environ.get("HOST", "0.0.0.0")\n'
                                f'SERVICE = "{_name}"\n'
                                f'KEY = "{_key}"\n\n'
                                f'class Handler(SimpleHTTPRequestHandler):\n'
                                f'    def do_GET(self):\n'
                                f'        if self.path == "/api/health":\n'
                                f'            self.send_response(200)\n'
                                f'            self.send_header("Content-Type", "application/json")\n'
                                f'            self.end_headers()\n'
                                f'            self.wfile.write(json.dumps({{"ok": True, "service": SERVICE, "status": "running"}}).encode())\n'
                                f'            return\n'
                                f'        self.send_response(200)\n'
                                f'        self.send_header("Content-Type", "text/html")\n'
                                f'        self.end_headers()\n'
                                f'        html = f"""<!DOCTYPE html><html><head><meta charset=utf-8><title>{{SERVICE}}</title>\n'
                                f'        <style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}}\n'
                                f'        .card{{background:#1e293b;border-radius:16px;padding:48px;max-width:600px;text-align:center;border:1px solid #334155}}\n'
                                f'        h1{{font-size:32px;margin-bottom:16px;color:#60a5fa}}p{{color:#94a3b8;line-height:1.8;margin-bottom:24px}}\n'
                                f'        code{{background:#334155;padding:4px 12px;border-radius:6px;font-size:14px}}\n'
                                f'        a{{color:#60a5fa;text-decoration:none}}</style></head>\n'
                                f'        <body><div class=card><h1>{{SERVICE}}</h1>\n'
                                f'        <p>{{SERVICE}} is installed and running on this server.</p>\n'
                                f'        <p>Use the CLI: <code>{{KEY}}</code></p>\n'
                                f'        <p>API health: <a href=/api/health>/api/health</a></p>\n'
                                f'        </div></body></html>"""\n'
                                f'        self.wfile.write(html.encode())\n\n'
                                f'print(f"{{SERVICE}} web server on http://{{HOST}}:{{PORT}}")\n'
                                f'HTTPServer((HOST, PORT), Handler).serve_forever()\n',
                                encoding="utf-8",
                            )
                            log(f"Created web server wrapper at {wrapper}")
                            # Start the server as a background process
                            log(f"Starting {_name} web server on port {port}...")
                            python_cmd = sys.executable or "python"
                            try:
                                if os.name == "nt":
                                    subprocess.Popen(
                                        [python_cmd, str(wrapper)],
                                        cwd=str(app_dir),
                                        creationflags=0x00000008,  # DETACHED_PROCESS
                                        env={**os.environ, "PORT": port, "HOST": host_ip},
                                    )
                                else:
                                    subprocess.Popen(
                                        [python_cmd, str(wrapper)],
                                        cwd=str(app_dir),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        env={**os.environ, "PORT": port, "HOST": host_ip},
                                    )
                                log(f"{_name} server started.")
                            except Exception as ex:
                                log(f"WARNING: Could not auto-start server: {ex}")
                            # Save state
                            sfile = sdir / f"{_key}-state.json"
                            _write_json_file(sfile, {
                                "installed": True, "service_name": f"serverinstaller-{_key}",
                                "install_dir": str(app_dir), "host": host_ip,
                                "http_port": port, "http_url": f"http://{display_host}:{port}",
                                "deploy_mode": "os", "running": True,
                            })
                            manage_firewall_port("open", port, "tcp")
                            log(f"\n{_name} installed and running!")
                            log(f"URL: http://{display_host}:{port}")
                        return code, "\n".join(output)
                    return _fn
                installer = _make_installer(_ai_name, _ai_pip, _ai_port, _ai_key, form)
                if self.is_fetch():
                    job_id = start_live_job(title, installer)
                    self.write_json({"job_id": job_id, "title": title})
                else:
                    code, output = installer(None)
                    self.respond_run_result(title, code, output)
                return
            if self.path == f"/run/{_ai_key}_docker" and _ai_image:
                title = f"{_ai_name} Docker"
                def _make_docker(_name, _image, _port, _key, _form):
                    def _fn(cb):
                        return _run_ai_docker_generic(
                            _key, _image, _form, _port,
                            _port, _name,
                            SERVER_INSTALLER_DATA / _key / f"{_key}-state.json",
                            SERVER_INSTALLER_DATA / _key,
                            live_cb=cb,
                        )
                    return _fn
                docker_fn = _make_docker(_ai_name, _ai_image, _ai_port, _ai_key, form)
                if self.is_fetch():
                    job_id = start_live_job(title, docker_fn)
                    self.write_json({"job_id": job_id, "title": title})
                else:
                    code, output = docker_fn(None)
                    self.respond_run_result(title, code, output)
                return
        if self.path == "/run/dashboard_update":
            title = "Dashboard Update"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_dashboard_update(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_dashboard_update()
                self.respond_run_result(title, code, output)
            return

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
        if self.path == "/run/windows_docker_engine":
            title = "Windows Docker Engine Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_docker_setup_only(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_docker_setup_only()
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
        if self.path == "/run/linux_docker":
            title = "Linux Docker Deployment"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_docker_deploy(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_docker_deploy(form)
                self.respond_run_result(title, code, output)
            return

        # ── SSL / Certificate endpoints ────────────────────────────────────────
        if self.path == "/api/ssl/delete":
            name = (form.get("SSL_CERT_NAME", [""])[0] or "").strip()
            ok, msg = ssl_delete_cert(name)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": msg}, status)
            return
        if self.path == "/api/ssl/upload":
            # Multipart upload: cert_file, key_file, chain_file, pfx_file + form fields
            try:
                parts = self._parse_multipart()
                form_fields = {}
                file_parts = []
                for part in parts:
                    pname = part.get("name", "")
                    if pname in ("cert_file", "key_file", "chain_file", "pfx_file"):
                        file_parts.append(part)
                    else:
                        form_fields[pname] = [part.get("content", b"").decode("utf-8", errors="replace").strip()]
                # Merge with already-parsed form
                for k, v in form.items():
                    if k not in form_fields:
                        form_fields[k] = v
                code, msg = run_ssl_upload(form_fields, file_parts)
                ok = (code == 0)
                self.write_json({"ok": ok, "message": msg}, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
            except Exception as ex:
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path == "/run/ssl_letsencrypt":
            title = "Let's Encrypt Certificate"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_letsencrypt(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_letsencrypt(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ssl_renew":
            title = "Renew SSL Certificates"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_renew_all(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_renew_all(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ssl_assign":
            title = "Assign Certificate to Service"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_assign(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_assign(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/dashboard_apply_cert":
            title = "Apply Dashboard Certificate"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_dashboard_apply_cert(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_dashboard_apply_cert(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/system_restart":
            title = "Restart System"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_system_power("restart", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_system_power("restart")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/system_shutdown":
            title = "Shut Down System"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_system_power("shutdown", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_system_power("shutdown")
                self.respond_run_result(title, code, output)
            return

        self.write_html("Not found", HTTPStatus.NOT_FOUND)


def run_system_power(action, live_cb=None):
    """action: 'restart' or 'shutdown'"""
    def emit(msg):
        if live_cb:
            live_cb(msg if msg.endswith("\n") else msg + "\n")

    if action not in ("restart", "shutdown"):
        return 1, f"Unknown action: {action}"

    label = "Restart" if action == "restart" else "Shut Down"
    emit(f"[INFO] {label} requested...")

    if os.name == "nt":
        # Use PowerShell Restart-Computer/Stop-Computer — more reliable than
        # shutdown.exe when called from a Python subprocess or Windows service context.
        ps_cmd = "Restart-Computer -Force" if action == "restart" else "Stop-Computer -Force"
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
    else:
        flag = "-r" if action == "restart" else "-h"
        cmd = ["shutdown", flag, "now"]
        if os.geteuid() != 0 and subprocess.run(
            ["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            cmd = ["sudo"] + cmd

    emit(f"[INFO] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()
            emit(f"[ERROR] {msg}")
            return 1, msg
        emit(f"[INFO] {label} command sent. System will {action} shortly.")
        return 0, f"{label} command sent."
    except Exception as ex:
        emit(f"[ERROR] {ex}")
        return 1, str(ex)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--cert", default="")
    parser.add_argument("--key", default="")
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

    # Resolve certificate: explicit args → managed cert config → auto self-signed
    cert_path, key_path = _resolve_dashboard_cert(args.cert, args.key)
    scheme = "http"
    if cert_path and key_path:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            scheme = "https"
            print(f"[dashboard] HTTPS enabled with certificate: {cert_path}")
        except Exception as ex:
            print(f"[dashboard] Failed to load certificate ({ex}), retrying with fresh self-signed...")
            # Force-regenerate and try once more
            cert_path, key_path = _generate_dashboard_selfsigned()
            if cert_path and key_path:
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                    server.socket = ctx.wrap_socket(server.socket, server_side=True)
                    scheme = "https"
                    print(f"[dashboard] HTTPS enabled with new self-signed certificate: {cert_path}")
                except Exception as ex2:
                    print(f"[dashboard] HTTPS setup failed ({ex2}). Running without TLS.")
            else:
                print("[dashboard] Could not generate self-signed cert. Running without TLS.")
    else:
        print("[dashboard] No certificate available. Running without TLS (HTTP only).")

    urls = [f"{scheme}://127.0.0.1:{args.port}"]
    if args.host not in ("127.0.0.1", "localhost", "0.0.0.0", ""):
        explicit = f"{scheme}://{args.host}:{args.port}"
        if explicit not in urls:
            urls.append(explicit)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and (not primary_ip.startswith("127.")):
            candidate = f"{scheme}://{primary_ip}:{args.port}"
            if candidate not in urls:
                urls.append(candidate)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
