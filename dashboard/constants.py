import os
import platform
import re
import threading
from pathlib import Path

BUILD_ID = "python-jupyter-service-2026-03-13-1048"


def _server_installer_data_dir():
    override = os.environ.get("SERVER_INSTALLER_DATA_DIR", "").strip()
    if override:
        return Path(override)
    sibling_root = Path(__file__).resolve().parents[1]
    if (sibling_root / "dashboard" / "start-server-dashboard.py").exists():
        return sibling_root
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

INSTALLED_COMMIT_FILE = Path(__file__).parent / "installed-commit.txt"

WINDOWS_SETUP_MODULES = [
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
]

# Dashboard certificate config
DASHBOARD_CERT_CONFIG_FILE = SERVER_INSTALLER_DATA / "dashboard-cert.json"
DASHBOARD_SELFSIGNED_CERT = SERVER_INSTALLER_DATA / "certs" / "dashboard.crt"
DASHBOARD_SELFSIGNED_KEY = SERVER_INSTALLER_DATA / "certs" / "dashboard.key"

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

# Interactive terminal sessions for openclaw configure
_interactive_sessions = {}
_interactive_sessions_lock = threading.Lock()
