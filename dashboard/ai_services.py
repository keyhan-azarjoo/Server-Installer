import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

from ai_catalog import get_generic_ai_service, is_generic_ai_service, list_generic_ai_service_ids
from constants import (
    COMFYUI_STATE_DIR,
    COMFYUI_STATE_FILE,
    COMFYUI_SYSTEMD_SERVICE,
    LMSTUDIO_LINUX_INSTALLER,
    LMSTUDIO_STATE_DIR,
    LMSTUDIO_STATE_FILE,
    LMSTUDIO_SYSTEMD_SERVICE,
    LMSTUDIO_UNIX_FILES,
    LMSTUDIO_WINDOWS_FILES,
    LMSTUDIO_WINDOWS_INSTALLER,
    OLLAMA_LINUX_INSTALLER,
    OLLAMA_STATE_DIR,
    OLLAMA_STATE_FILE,
    OLLAMA_SYSTEMD_SERVICE,
    OLLAMA_UNIX_FILES,
    OLLAMA_WINDOWS_FILES,
    OLLAMA_WINDOWS_INSTALLER,
    OPENCLAW_LINUX_INSTALLER,
    OPENCLAW_STATE_DIR,
    OPENCLAW_STATE_FILE,
    OPENCLAW_SYSTEMD_SERVICE,
    OPENCLAW_UNIX_FILES,
    OPENCLAW_WINDOWS_FILES,
    OPENCLAW_WINDOWS_INSTALLER,
    PIPER_STATE_DIR,
    PIPER_STATE_FILE,
    PIPER_SYSTEMD_SERVICE,
    ROOT,
    SERVER_INSTALLER_DATA,
    TGWUI_STATE_DIR,
    TGWUI_STATE_FILE,
    TGWUI_SYSTEMD_SERVICE,
    WHISPER_STATE_DIR,
    WHISPER_STATE_FILE,
    WHISPER_SYSTEMD_SERVICE,
    _interactive_sessions,
    _interactive_sessions_lock,
)
from utils import _read_json_file, _write_json_file, command_exists, ensure_repo_files, run_capture, run_process, _sudo_prefix
from system_info import choose_service_host, get_memory_info
from python_manager import _linux_systemd_unit_status
from port_manager import is_local_tcp_port_listening, manage_firewall_port
from website_manager import _docker_add_macos_path, _docker_wait_macos, _install_engine_docker, _run_install_cmd

OPENCLAW_MANAGED_PROVIDERS = ("ollama", "lmstudio", "openai", "anthropic")

def _ensure_docker_ready(log):
    if sys.platform == "darwin":
        _docker_add_macos_path()
    if not command_exists("docker"):
        log("Docker not found. Installing Docker first...")
        _install_engine_docker(log)
        if sys.platform == "darwin":
            _docker_add_macos_path()
    if not command_exists("docker"):
        return 1, "Docker is not available. Install Docker Desktop manually."

    rc, out = run_capture(["docker", "info"], timeout=15)
    if rc == 0:
        return 0, ""

    if sys.platform == "darwin":
        docker_app = Path("/Applications/Docker.app")
        if docker_app.exists():
            log("Docker Desktop is installed but not running. Opening Docker Desktop...")
            _run_install_cmd(["open", str(docker_app)], log, timeout=10)
            return _docker_wait_macos(log)
        return 1, "Docker Desktop is installed but the daemon is not running."

    if os.name != "nt":
        daemon_output = str(out or "")
        if "Cannot connect to the Docker daemon" in daemon_output and command_exists("systemctl"):
            log("Docker is installed but the daemon is not running. Starting docker.service...")
            start_cmd = _sudo_prefix() + ["systemctl", "start", "docker"]
            start_code = _run_install_cmd(start_cmd, log, timeout=60)
            if start_code == 0:
                rc, out = run_capture(["docker", "info"], timeout=15)
                if rc == 0:
                    return 0, ""
        return 1, "Docker is installed but the daemon is not running. Start Docker and retry."

    return 1, "Docker is installed but the daemon is not running."


def _friendly_docker_image_error(image, raw_output):
    text = str(raw_output or "").strip()
    low = text.lower()
    arch = platform.machine().lower()
    if "no matching manifest" in low and ("arm64" in low or arch in ("arm64", "aarch64")):
        return (
            f"The Docker image '{image}' does not publish a Linux ARM64 variant. "
            f"This host is '{platform.machine()}'. "
            "Use the OS/native installer for this service on Apple Silicon or ARM, "
            "or run an amd64 image manually with Docker emulation if you accept slower performance."
        )
    if "not found" in low and ("failed to resolve reference" in low or "pull access denied" in low):
        return (
            f"The Docker image '{image}' could not be pulled. "
            "The configured image/tag may no longer exist or may be private."
        )
    return text


def _docker_image_platform_supported(image):
    if not image:
        return True, ""
    target_os = "linux"
    target_arch = platform.machine().lower()
    arch_aliases = {
        "x86_64": {"x86_64", "amd64"},
        "amd64": {"x86_64", "amd64"},
        "arm64": {"arm64", "aarch64"},
        "aarch64": {"arm64", "aarch64"},
    }
    expected_arches = arch_aliases.get(target_arch, {target_arch})
    rc, out = run_capture(["docker", "manifest", "inspect", image], timeout=120)
    if rc != 0 or not out:
        return False, _friendly_docker_image_error(image, out or f"Unable to inspect manifest for {image}.")
    try:
        data = json.loads(out)
    except Exception:
        return False, _friendly_docker_image_error(image, out)
    manifests = data.get("manifests")
    if isinstance(manifests, list) and manifests:
        for manifest in manifests:
            platform_info = manifest.get("platform") or {}
            os_name = str(platform_info.get("os") or "").lower()
            arch_name = str(platform_info.get("architecture") or "").lower()
            if os_name == target_os and arch_name in expected_arches:
                return True, ""
        return False, (
            f"The Docker image '{image}' does not publish a {target_os}/{platform.machine()} manifest. "
            "Choose the OS/native installer or a different image for this host."
        )
    os_name = str((data.get("os") or "")).lower()
    arch_name = str((data.get("architecture") or "")).lower()
    if os_name == target_os and arch_name in expected_arches:
        return True, ""
    if os_name or arch_name:
        return False, (
            f"The Docker image '{image}' targets {os_name or 'unknown'}/{arch_name or 'unknown'}, "
            f"not {target_os}/{platform.machine()}."
        )
    return True, ""


def _generic_ai_state_paths(service_id):
    sid = str(service_id or "").strip().lower()
    state_dir = SERVER_INSTALLER_DATA / sid
    return state_dir / f"{sid}-state.json", state_dir


def _managed_ai_state_paths(service_id):
    sid = str(service_id or "").strip().lower()
    builtins = {
        "ollama": (OLLAMA_STATE_FILE, OLLAMA_STATE_DIR),
        "lmstudio": (LMSTUDIO_STATE_FILE, LMSTUDIO_STATE_DIR),
        "openclaw": (OPENCLAW_STATE_FILE, OPENCLAW_STATE_DIR),
        "tgwui": (TGWUI_STATE_FILE, TGWUI_STATE_DIR),
        "comfyui": (COMFYUI_STATE_FILE, COMFYUI_STATE_DIR),
        "whisper": (WHISPER_STATE_FILE, WHISPER_STATE_DIR),
        "piper": (PIPER_STATE_FILE, PIPER_STATE_DIR),
    }
    if sid in builtins:
        return builtins[sid]
    if is_generic_ai_service(sid):
        return _generic_ai_state_paths(sid)
    raise KeyError(f"Unknown AI service id: {service_id}")

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
        "gateway_token": str(state.get("gateway_token") or "").strip(),
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
    info = _get_ai_service_info(OLLAMA_STATE_FILE, OLLAMA_STATE_DIR, OLLAMA_SYSTEMD_SERVICE, "Ollama LLM Service", "11434")
    api_base = str(info.get("http_url") or info.get("https_url") or "").strip()
    info["api_url"] = api_base
    info["api_tags_url"] = (api_base.rstrip("/") + "/api/tags") if api_base else ""
    return info


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


def _openclaw_internal_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _openclaw_load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    except Exception:
        return {}


def _openclaw_read_env_file(home_dir):
    env_path = Path(home_dir) / ".openclaw" / ".env"
    data = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def _openclaw_normalize_base_url(url, suffix=""):
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    if suffix == "/v1":
        if base.endswith("/v1"):
            return base
        if base.endswith("/models"):
            return base[:-len("/models")]
        return base + "/v1"
    return base


def _openclaw_ollama_api_root(url):
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    for suffix in ("/api/tags", "/api", "/v1"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    return base.rstrip("/")


def _openclaw_safe_json(url, headers=None, timeout=8):
    try:
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        ctx = _openclaw_internal_ssl_ctx() if url.startswith("https://") else None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _openclaw_make_model_entry(item):
    mid = str((item or {}).get("id") or (item or {}).get("name") or "").strip()
    name = str((item or {}).get("name") or mid).strip()
    context_window = int((item or {}).get("contextWindow") or 128000)
    max_tokens = int((item or {}).get("maxTokens") or max(2048, min(8192, context_window // 4)))
    return {
        "id": mid,
        "name": name,
        "reasoning": False,
        "input": ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": context_window,
        "maxTokens": max_tokens,
    }


def _openclaw_filter_text_model_id(provider, model_id):
    mid = str(model_id or "").strip().lower()
    if not mid:
        return False
    excluded_parts = (
        "embedding", "image", "audio", "transcribe", "tts", "realtime",
        "search", "moderation", "whisper", "sora",
    )
    if any(part in mid for part in excluded_parts):
        return False
    if provider == "openai":
        return mid.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))
    if provider == "anthropic":
        return mid.startswith("claude")
    return True


def _discover_openclaw_provider_models(form=None, home_dir=None):
    form = form or {}
    home_dir = str(home_dir or os.path.expanduser("~"))
    env_keys = _openclaw_read_env_file(home_dir)
    providers = {}

    ollama_url = (form.get("OPENCLAW_OLLAMA_URL", [""])[0] if form.get("OPENCLAW_OLLAMA_URL") else "") or ""
    ollama_url = str(ollama_url).strip() or str((get_ollama_info() or {}).get("api_url") or "").strip()
    if ollama_url:
        ollama_root = _openclaw_ollama_api_root(ollama_url)
        tags_url = ollama_root.rstrip("/") + "/api/tags"
        result = _openclaw_safe_json(tags_url)
        models = []
        for item in result.get("models") or []:
            mid = str(item.get("name") or item.get("model") or "").strip()
            if mid:
                models.append({
                    "id": mid,
                    "name": mid,
                    "contextWindow": int(item.get("context_length") or 16384),
                    "maxTokens": 4096,
                })
        if models:
            providers["ollama"] = {
                "label": "Ollama",
                "baseUrl": ollama_root.rstrip("/") + "/v1",
                "api": "openai-completions",
                "apiKey": env_keys.get("OLLAMA_API_KEY") or "ollama-local",
                "models": models,
                "reachable": True,
                "sourceUrl": ollama_url,
            }

    lmstudio_url = (form.get("OPENCLAW_LMSTUDIO_URL", [""])[0] if form.get("OPENCLAW_LMSTUDIO_URL") else "") or ""
    lmstudio_url = str(lmstudio_url).strip() or str((get_lmstudio_info() or {}).get("api_url") or "").strip()
    if lmstudio_url:
        lmstudio_base = _openclaw_normalize_base_url(lmstudio_url, "/v1")
        headers = {}
        lmstudio_key = env_keys.get("LMSTUDIO_API_KEY") or "lmstudio-local"
        if lmstudio_key:
            headers["Authorization"] = f"Bearer {lmstudio_key}"
        result = _openclaw_safe_json(lmstudio_base.rstrip("/") + "/models", headers=headers)
        models = []
        for item in result.get("data") or []:
            mid = str(item.get("id") or "").strip()
            if mid:
                models.append({"id": mid, "name": mid, "contextWindow": 16384, "maxTokens": 4096})
        if models:
            providers["lmstudio"] = {
                "label": "LM Studio",
                "baseUrl": lmstudio_base,
                "api": "openai-responses",
                "apiKey": lmstudio_key,
                "models": models,
                "reachable": True,
                "sourceUrl": lmstudio_url,
            }

    openai_key = (form.get("OPENCLAW_OPENAI_KEY", [""])[0] if form.get("OPENCLAW_OPENAI_KEY") else "") or ""
    openai_key = str(openai_key).strip() or env_keys.get("OPENAI_API_KEY") or ""
    if openai_key:
        result = _openclaw_safe_json(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {openai_key}"},
        )
        models = []
        for item in result.get("data") or []:
            mid = str(item.get("id") or "").strip()
            if _openclaw_filter_text_model_id("openai", mid):
                models.append({"id": mid, "name": mid, "contextWindow": 128000, "maxTokens": 16384})
        models.sort(key=lambda item: str(item.get("id") or "").lower())
        if models:
            providers["openai"] = {
                "label": "OpenAI",
                "baseUrl": "https://api.openai.com/v1",
                "apiKey": openai_key,
                "models": models,
                "reachable": True,
                "sourceUrl": "https://api.openai.com/v1",
            }

    anthropic_key = (form.get("OPENCLAW_ANTHROPIC_KEY", [""])[0] if form.get("OPENCLAW_ANTHROPIC_KEY") else "") or ""
    anthropic_key = str(anthropic_key).strip() or env_keys.get("ANTHROPIC_API_KEY") or ""
    if anthropic_key:
        result = _openclaw_safe_json(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
        )
        models = []
        for item in result.get("data") or []:
            mid = str(item.get("id") or "").strip()
            name = str(item.get("display_name") or mid).strip()
            if _openclaw_filter_text_model_id("anthropic", mid):
                models.append({"id": mid, "name": name, "contextWindow": 200000, "maxTokens": 16384})
        models.sort(key=lambda item: str(item.get("id") or "").lower())
        if models:
            providers["anthropic"] = {
                "label": "Anthropic",
                "baseUrl": "https://api.anthropic.com/v1",
                "apiKey": anthropic_key,
                "models": models,
                "reachable": True,
                "sourceUrl": "https://api.anthropic.com/v1",
            }

    return providers


def sync_openclaw_provider_catalog(form=None, home_dir=None, live_cb=None):
    home_dir = str(home_dir or os.path.expanduser("~"))
    agent_dir = Path(home_dir) / ".openclaw" / "agents" / "main" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    auth_path = agent_dir / "auth-profiles.json"
    settings_path = agent_dir / "settings.json"
    cfg_path = Path(home_dir) / ".openclaw" / "openclaw.json"

    providers = _discover_openclaw_provider_models(form=form, home_dir=home_dir)
    auth = _openclaw_load_json(auth_path)
    settings = _openclaw_load_json(settings_path)
    cfg = _openclaw_load_json(cfg_path)

    profiles = auth.get("profiles") if isinstance(auth.get("profiles"), dict) else {}
    last_good = auth.get("lastGood") if isinstance(auth.get("lastGood"), dict) else {}
    accessible_providers = set(providers.keys())
    for key in list(profiles.keys()):
        provider_name = str((profiles.get(key) or {}).get("provider") or "").strip().lower()
        if not provider_name or provider_name not in accessible_providers:
            profiles.pop(key, None)
    for provider in list(last_good.keys()):
        if str(provider).strip().lower() not in accessible_providers:
            last_good.pop(provider, None)
    for provider, info in providers.items():
        profile_name = f"{provider}:local" if provider in ("ollama", "lmstudio") else f"{provider}:default"
        profiles[profile_name] = {"type": "api_key", "provider": provider, "key": str(info.get("apiKey") or "")}
        last_good[provider] = profile_name
    auth = {"version": 1, "profiles": profiles, "lastGood": last_good}
    auth_path.write_text(json.dumps(auth, indent=2), encoding="utf-8")

    agents = cfg.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    model_cfg = defaults.setdefault("model", {})
    catalog_cfg = defaults.setdefault("models", {})
    if not isinstance(catalog_cfg, dict):
        catalog_cfg = {}
        defaults["models"] = catalog_cfg
    models_cfg = cfg.setdefault("models", {})
    models_cfg["mode"] = "merge"
    providers_cfg = models_cfg.setdefault("providers", {})
    if not isinstance(providers_cfg, dict):
        providers_cfg = {}
        models_cfg["providers"] = providers_cfg

    for provider in list(providers_cfg.keys()):
        if str(provider).strip().lower() not in accessible_providers:
            providers_cfg.pop(provider, None)
    for key in list(catalog_cfg.keys()):
        provider_name = str(key).split("/", 1)[0].strip().lower()
        if provider_name not in accessible_providers:
            catalog_cfg.pop(key, None)

    ordered_models = []
    for provider in ("ollama", "lmstudio", "openai", "anthropic"):
        info = providers.get(provider)
        if not info:
            continue
        providers_cfg[provider] = {
            "baseUrl": str(info.get("baseUrl") or "").strip(),
            "apiKey": str(info.get("apiKey") or "").strip(),
            "models": [_openclaw_make_model_entry(item) for item in info.get("models") or []],
        }
        if info.get("api"):
            providers_cfg[provider]["api"] = info["api"]
        for item in info.get("models") or []:
            mid = str(item.get("id") or "").strip()
            if not mid:
                continue
            ordered_models.append(f"{provider}/{mid}")
            catalog_cfg[f"{provider}/{mid.lower()}"] = {"alias": str(item.get("name") or mid)}

    primary = str(model_cfg.get("primary") or "").strip()
    if primary not in ordered_models:
        primary = ordered_models[0] if ordered_models else ""
    if primary:
        provider, _, model = primary.partition("/")
        model_cfg["primary"] = primary
        settings["provider"] = provider
        settings["model"] = primary
    else:
        model_cfg.pop("primary", None)
        settings.pop("provider", None)
        settings.pop("model", None)
    if not providers_cfg:
        models_cfg.pop("providers", None)
    if not catalog_cfg:
        defaults.pop("models", None)

    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    result = {
        "ok": True,
        "providers": [
            {
                "id": provider,
                "label": providers[provider]["label"],
                "base_url": providers[provider]["sourceUrl"],
                "model_count": len(providers[provider].get("models") or []),
                "models": [str(item.get("id") or "").strip() for item in (providers[provider].get("models") or []) if str(item.get("id") or "").strip()],
            }
            for provider in ("ollama", "lmstudio", "openai", "anthropic")
            if provider in providers
        ],
        "primary_model": primary,
    }
    if live_cb:
        for item in result["providers"]:
            live_cb(f"Provider models synced: {item['label']} ({item['model_count']})\n")
        if primary:
            live_cb(f"OpenClaw primary model: {primary}\n")
    return result


def get_lmstudio_info():
    info = _get_ai_service_info(LMSTUDIO_STATE_FILE, LMSTUDIO_STATE_DIR, LMSTUDIO_SYSTEMD_SERVICE, "LM Studio", "1234")
    api_base = str(info.get("http_url") or info.get("https_url") or "").strip().rstrip("/")
    if api_base and not api_base.endswith("/v1"):
        api_base += "/v1"
    info["api_url"] = api_base
    info["models_url"] = (api_base + "/models") if api_base else ""
    return info


def get_tgwui_info():
    return _get_ai_service_info(TGWUI_STATE_FILE, TGWUI_STATE_DIR, TGWUI_SYSTEMD_SERVICE, "Text Generation WebUI", "7860")


def get_comfyui_info():
    return _get_ai_service_info(COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, COMFYUI_SYSTEMD_SERVICE, "ComfyUI", "8188")


def get_whisper_info():
    return _get_ai_service_info(WHISPER_STATE_FILE, WHISPER_STATE_DIR, WHISPER_SYSTEMD_SERVICE, "Whisper STT Service", "9000")


def get_piper_info():
    return _get_ai_service_info(PIPER_STATE_FILE, PIPER_STATE_DIR, PIPER_SYSTEMD_SERVICE, "Piper TTS Service", "5500")


def _docker_password_hash(password):
    password = str(password or "")
    if not password:
        return ""
    ok, message = _docker_image_platform_supported("caddy:2-alpine")
    if not ok:
        raise RuntimeError(message)
    cmd = ["docker", "run", "--rm", "caddy:2-alpine", "caddy", "hash-password", "--plaintext", password]
    rc, out = run_capture(cmd, timeout=120)
    if rc != 0:
        raise RuntimeError(out or "Failed to generate password hash with Caddy.")
    return str(out or "").strip().splitlines()[-1].strip()


def _write_ai_proxy_caddyfile(proxy_dir, upstream_name, upstream_port, http_enabled, https_enabled, username="", password_hash=""):
    proxy_dir.mkdir(parents=True, exist_ok=True)
    auth_block = ""
    if username and password_hash:
        auth_block = (
            "    basicauth {\n"
            f"        {username} {password_hash}\n"
            "    }\n"
        )
    blocks = []
    if http_enabled:
        blocks.append(
            ":80 {\n"
            f"{auth_block}"
            f"    reverse_proxy {upstream_name}:{upstream_port}\n"
            "}\n"
        )
    if https_enabled:
        blocks.append(
            ":443 {\n"
            "    tls internal\n"
            f"{auth_block}"
            f"    reverse_proxy {upstream_name}:{upstream_port}\n"
            "}\n"
        )
    if not blocks:
        raise RuntimeError("At least one of HTTP or HTTPS must be enabled.")
    caddyfile = proxy_dir / "Caddyfile"
    caddyfile.write_text("\n".join(blocks), encoding="utf-8")
    return caddyfile


def _remove_ai_docker_artifacts(service_id):
    sid = str(service_id or "").strip().lower()
    container_name = f"serverinstaller-{sid}"
    proxy_name = f"{container_name}-proxy"
    network_name = f"{container_name}-net"
    if command_exists("docker"):
        run_capture(["docker", "rm", "-f", proxy_name], timeout=30)
        run_capture(["docker", "rm", "-f", container_name], timeout=30)
        run_capture(["docker", "network", "rm", network_name], timeout=30)


def _run_managed_ai_docker_action(service_id, action, live_cb=None):
    sid = str(service_id or "").strip().lower()
    state_file, _state_dir = _managed_ai_state_paths(sid)
    state = _read_json_file(state_file)
    if not state:
        return 1, f"No saved state for {sid}."
    container_name = str(state.get("service_name") or f"serverinstaller-{sid}").strip()
    proxy_name = str(state.get("proxy_service_name") or f"{container_name}-proxy").strip()
    targets = [container_name]
    if state.get("proxy_enabled"):
        targets.append(proxy_name)
    output = []
    def log(message):
        output.append(message)
        if live_cb:
            live_cb(message + "\n")
    if not command_exists("docker"):
        return 1, "Docker is not available."
    if action == "delete":
        _remove_ai_docker_artifacts(sid)
        state.update({"running": False, "installed": False})
        _write_json_file(state_file, state)
        return 0, f"{sid} Docker deployment removed."
    cmd_name = {"start": "start", "stop": "stop", "restart": "restart"}.get(action)
    if not cmd_name:
        return 1, f"Unsupported action: {action}"
    for target in targets:
        rc, out = run_capture(["docker", cmd_name, target], timeout=120)
        if rc != 0 and cmd_name != "stop":
            log(out or f"Failed to {cmd_name} {target}.")
            return rc, "\n".join(output)
        if out:
            log(out.strip())
    state["running"] = action != "stop"
    _write_json_file(state_file, state)
    return 0, "\n".join(output) or f"{action} completed."


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
import os, tempfile
from flask import Flask, request, jsonify
app = Flask(__name__)
model = None
MODEL_SIZE = "{model_size}"

def get_model():
    global model
    if model is None:
        try:
            from faster_whisper import WhisperModel
            model = ("faster_whisper", WhisperModel(MODEL_SIZE, device="auto", compute_type="auto"))
        except Exception:
            import whisper
            model = ("openai_whisper", whisper.load_model(MODEL_SIZE))
    return model

def _transcribe_file(tmp_path, task="transcribe"):
    backend, m = get_model()
    if backend == "faster_whisper":
        segments, info = m.transcribe(tmp_path, task=task)
        seg_list = []
        texts = []
        for seg in segments:
            seg_list.append({{"start": float(seg.start), "end": float(seg.end), "text": str(seg.text).strip()}})
            texts.append(str(seg.text).strip())
        return {{"text": " ".join([t for t in texts if t]).strip(), "language": getattr(info, "language", ""), "segments": seg_list}}
    result = m.transcribe(tmp_path, task=task)
    seg_list = []
    for seg in result.get("segments") or []:
        seg_list.append({{"start": float(seg.get("start", 0.0)), "end": float(seg.get("end", 0.0)), "text": str(seg.get("text", "")).strip()}})
    return {{"text": str(result.get("text", "")).strip(), "language": result.get("language", ""), "segments": seg_list}}

def _handle_transcription():
    audio = request.files.get("audio") or request.files.get("file")
    if not audio:
        return jsonify({{"error": "No audio file provided"}}), 400
    response_format = (request.form.get("response_format") or "json").strip().lower()
    task = (request.form.get("task") or "transcribe").strip().lower()
    suffix = os.path.splitext(audio.filename or "audio.bin")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio.save(tmp.name)
        tmp_path = tmp.name
    try:
        payload = _transcribe_file(tmp_path, task=task)
        if response_format == "verbose_json":
            return jsonify(payload)
        return jsonify({{"ok": True, "text": payload.get("text", ""), "language": payload.get("language", "")}})
    except Exception as e:
        return jsonify({{"ok": False, "error": str(e)}}), 500
    finally:
        os.unlink(tmp_path)

@app.route("/", methods=["GET"])
def index():
    return jsonify({{"service": "whisper", "model": MODEL_SIZE, "status": "running"}})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    return _handle_transcription()

@app.route("/v1/audio/transcriptions", methods=["POST"])
def openai_transcriptions():
    return _handle_transcription()

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
    """Completely delete Ollama — Docker containers, images, volumes, OS service, data, certs."""
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Deleting Ollama ===")

    # Read state to get ports for firewall cleanup
    state = _read_json_file(OLLAMA_STATE_FILE)
    deploy_mode = state.get("deploy_mode", "")
    http_port = str(state.get("http_port") or "").strip()
    https_port = str(state.get("https_port") or "").strip()

    # Stop first
    run_ollama_stop(live_cb=live_cb)

    # Docker cleanup
    if command_exists("docker"):
        for cname in ["serverinstaller-ollama-webui", "serverinstaller-ollama"]:
            run_capture(["docker", "stop", cname], timeout=30)
            rc, _ = run_capture(["docker", "rm", "-f", cname], timeout=30)
            if rc == 0: log(f"Removed Docker container: {cname}")
        # Remove images
        for img in ["serverinstaller/ollama-webui:latest", "ollama/ollama:latest"]:
            rc, _ = run_capture(["docker", "rmi", img], timeout=30)
            if rc == 0: log(f"Removed Docker image: {img}")
        # Remove volume
        rc, _ = run_capture(["docker", "volume", "rm", "ollama-data"], timeout=30)
        if rc == 0: log("Removed Docker volume: ollama-data")

    # Systemd cleanup (Linux/macOS)
    if os.name != "nt" and command_exists("systemctl"):
        for svc in [f"{OLLAMA_SYSTEMD_SERVICE}-webui", OLLAMA_SYSTEMD_SERVICE]:
            run_capture(["systemctl", "disable", svc], timeout=15)
            run_capture(["systemctl", "stop", svc], timeout=15)
            svc_file = Path(f"/etc/systemd/system/{svc}.service")
            if svc_file.exists():
                svc_file.unlink()
                log(f"Removed systemd unit: {svc}")
        run_capture(["systemctl", "daemon-reload"], timeout=15)
        # Remove nginx config
        nginx_conf = Path(f"/etc/nginx/conf.d/ollama.conf")
        if nginx_conf.exists():
            nginx_conf.unlink()
            run_capture(["nginx", "-s", "reload"], timeout=15)
            log("Removed nginx config")
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-Ollama", "/F"], timeout=15)
            log("Removed scheduled task")
        except Exception:
            pass

    # Clean up all data directories
    for subdir in ["app", "docker-webui", "certs", "venv"]:
        d = OLLAMA_STATE_DIR / subdir
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            log(f"Removed directory: {subdir}")
    if OLLAMA_STATE_FILE.exists():
        OLLAMA_STATE_FILE.unlink()
        log("Removed state file")

    # Firewall cleanup
    for port in [http_port, https_port]:
        if port:
            manage_firewall_port("close", port, "tcp")

    log("=== Ollama completely removed ===")
    return 0, "\n".join(output)


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
    """Completely delete LM Studio — Docker containers, images, OS service, data, certs."""
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Deleting LM Studio ===")

    state = _read_json_file(LMSTUDIO_STATE_FILE)
    http_port = str(state.get("http_port") or "").strip()
    https_port = str(state.get("https_port") or "").strip()

    run_lmstudio_stop(live_cb=live_cb)

    # Docker cleanup
    if command_exists("docker"):
        for cname in ["serverinstaller-lmstudio-webui"]:
            run_capture(["docker", "stop", cname], timeout=30)
            rc, _ = run_capture(["docker", "rm", "-f", cname], timeout=30)
            if rc == 0: log(f"Removed Docker container: {cname}")
        rc, _ = run_capture(["docker", "rmi", "serverinstaller/lmstudio-webui:latest"], timeout=30)
        if rc == 0: log("Removed Docker image: serverinstaller/lmstudio-webui")

    # Systemd cleanup
    if os.name != "nt" and command_exists("systemctl"):
        for svc in [f"{LMSTUDIO_SYSTEMD_SERVICE}-webui", LMSTUDIO_SYSTEMD_SERVICE]:
            run_capture(["systemctl", "disable", svc], timeout=15)
            run_capture(["systemctl", "stop", svc], timeout=15)
            svc_file = Path(f"/etc/systemd/system/{svc}.service")
            if svc_file.exists():
                svc_file.unlink()
                log(f"Removed systemd unit: {svc}")
        run_capture(["systemctl", "daemon-reload"], timeout=15)
        nginx_conf = Path(f"/etc/nginx/conf.d/lmstudio.conf")
        if nginx_conf.exists():
            nginx_conf.unlink()
            run_capture(["nginx", "-s", "reload"], timeout=15)
            log("Removed nginx config")
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-LMStudio", "/F"], timeout=15)
            log("Removed scheduled task")
        except Exception: pass

    # Clean up data
    for subdir in ["app", "docker-webui", "certs", "venv"]:
        d = LMSTUDIO_STATE_DIR / subdir
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            log(f"Removed directory: {subdir}")
    if LMSTUDIO_STATE_FILE.exists():
        LMSTUDIO_STATE_FILE.unlink()
        log("Removed state file")

    for port in [http_port, https_port]:
        if port: manage_firewall_port("close", port, "tcp")

    log("=== LM Studio completely removed ===")
    return 0, "\n".join(output)


# ── OpenClaw install/start/stop/delete ────────────────────────────────────────
def run_openclaw_os_install(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        ensure_repo_files(OPENCLAW_WINDOWS_FILES, live_cb=live_cb, refresh=True)
        env = os.environ.copy()
        all_keys = ["OPENCLAW_HOST_IP", "OPENCLAW_HTTP_PORT", "OPENCLAW_HTTPS_PORT", "OPENCLAW_DOMAIN",
                    "OPENCLAW_USERNAME", "OPENCLAW_PASSWORD",
                    "OPENCLAW_TELEGRAM_TOKEN", "OPENCLAW_DISCORD_TOKEN", "OPENCLAW_SLACK_TOKEN", "OPENCLAW_WHATSAPP_PHONE",
                    "OPENCLAW_LLM_PROVIDER", "OPENCLAW_LLM_MODEL", "OPENCLAW_OLLAMA_URL", "OPENCLAW_LMSTUDIO_URL", "OPENCLAW_OPENAI_KEY", "OPENCLAW_ANTHROPIC_KEY"]
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
                    "OPENCLAW_LLM_PROVIDER", "OPENCLAW_LLM_MODEL", "OPENCLAW_OLLAMA_URL", "OPENCLAW_LMSTUDIO_URL", "OPENCLAW_OPENAI_KEY", "OPENCLAW_ANTHROPIC_KEY"]
        for key in env_keys:
            val = (form.get(key, [""])[0] or "").strip()
            if val: env[key] = val
        env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
        # Ensure common Node.js install locations are in PATH (may exist from previous installs)
        extra_paths = [
            str(OPENCLAW_STATE_DIR / "node" / "bin"),
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/opt/homebrew/opt/node@22/bin",
        ]
        current_path = env.get("PATH", os.environ.get("PATH", ""))
        for ep in extra_paths:
            if ep not in current_path:
                current_path = ep + os.pathsep + current_path
        env["PATH"] = current_path
        # Pre-write channel tokens to ~/.openclaw/.env before bash runs
        # (the cached bash script may have a bash 3.x incompatible declare -A)
        home_dir = os.path.expanduser("~")
        oc_env_dir = Path(home_dir) / ".openclaw"
        oc_env_dir.mkdir(parents=True, exist_ok=True)
        oc_env_file = oc_env_dir / ".env"
        env_data = {}
        if oc_env_file.exists():
            for line in oc_env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    env_data[k.strip()] = v.strip()
        token_map = {
            "OPENCLAW_TELEGRAM_TOKEN": "TELEGRAM_BOT_TOKEN",
            "OPENCLAW_DISCORD_TOKEN": "DISCORD_TOKEN",
            "OPENCLAW_SLACK_TOKEN": "SLACK_BOT_TOKEN",
            "OPENCLAW_WHATSAPP_PHONE": "WHATSAPP_PHONE",
            "OPENCLAW_OPENAI_KEY": "OPENAI_API_KEY",
            "OPENCLAW_ANTHROPIC_KEY": "ANTHROPIC_API_KEY",
        }
        for form_key, env_key in token_map.items():
            val = (form.get(form_key, [""])[0] or "").strip()
            if val:
                env_data[env_key] = val
        env_data.setdefault("OLLAMA_API_KEY", "ollama-local")
        oc_env_file.write_text(
            "\n".join(f"{k}={v}" for k, v in sorted(env_data.items())) + "\n",
            encoding="utf-8",
        )
        # Patch the bash script to remove declare -A if present (bash 3.x compat)
        installer_path = str(OPENCLAW_LINUX_INSTALLER)
        try:
            script_text = Path(installer_path).read_text(encoding="utf-8")
            if "declare -A" in script_text:
                # Remove everything from "declare -A" line to the next step marker
                import re
                script_text = re.sub(
                    r'declare -A ENV_DATA.*?(?=# ── Step 3d)',
                    '# (env file written by ai_services.py)\n',
                    script_text,
                    flags=re.DOTALL,
                )
                Path(installer_path).write_text(script_text, encoding="utf-8")
        except Exception:
            pass
        cmd = ["bash", str(OPENCLAW_LINUX_INSTALLER)]
        if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
            cmd = ["sudo", "env"] + [f"{k}={env.get(k, '')}" for k in env_keys + ["SERVER_INSTALLER_DATA_DIR"] if env.get(k)] + ["bash", str(OPENCLAW_LINUX_INSTALLER)]
        code, out = run_process(cmd, env=env, live_cb=live_cb)
        # Always ensure deps and config (even if bash script partially failed)
        _ensure_openclaw_channel_deps(live_cb)
        _ensure_openclaw_os_config(form, live_cb)
        _ensure_openclaw_https_proxy(form, live_cb)
        if code != 0 and os.name != "nt" and not command_exists("systemctl"):
            recovered = _ensure_openclaw_macos_gateway_running(form=form, live_cb=live_cb)
            if recovered:
                code = 0
        return code, out


def _ensure_openclaw_channel_deps(live_cb=None):
    """Install optional peer dependencies for OpenClaw channels (Telegram, Discord, Slack)."""
    state = _read_json_file(OPENCLAW_STATE_FILE)
    if str(state.get("deploy_mode") or "").strip().lower() == "docker":
        return
    oc_bin = str(state.get("openclaw_bin") or "").strip()
    if not oc_bin:
        return
    pkg_dir = str(Path(oc_bin).resolve().parent.parent / "lib" / "node_modules" / "openclaw")
    if not os.path.isdir(pkg_dir):
        # Try common location
        for try_dir in [
            str(OPENCLAW_STATE_DIR / ".npm-global" / "lib" / "node_modules" / "openclaw"),
            "/usr/local/lib/node_modules/openclaw",
        ]:
            if os.path.isdir(try_dir):
                pkg_dir = try_dir
                break
    if not os.path.isdir(pkg_dir):
        return
    def _log(m):
        if live_cb:
            live_cb(m + "\n")
    required_runtime_deps = ["@buape/carbon", "@larksuiteoapi/node-sdk", "@slack/web-api"]
    missing_runtime_deps = [
        dep for dep in required_runtime_deps
        if not os.path.isdir(os.path.join(pkg_dir, "node_modules", *dep.split("/")))
    ]
    if not missing_runtime_deps:
        return
    _log(f"[OpenClaw] Installing required OpenClaw runtime dependencies: {', '.join(missing_runtime_deps)}")
    npm_bin = "npm"
    for try_npm in [str(Path(oc_bin).parent / "npm"), str(OPENCLAW_STATE_DIR / "node" / "bin" / "npm"), "/usr/local/bin/npm"]:
        if os.path.isfile(try_npm):
            npm_bin = try_npm
            break
    npm_env = dict(os.environ)
    # Ensure node is in PATH for npm to work
    for extra in [str(Path(oc_bin).parent), str(OPENCLAW_STATE_DIR / "node" / "bin"), "/usr/local/bin"]:
        if extra not in npm_env.get("PATH", ""):
            npm_env["PATH"] = extra + os.pathsep + npm_env.get("PATH", "")
    _log(f"[OpenClaw] Using npm: {npm_bin}, pkg_dir: {pkg_dir}")
    try:
        proc = subprocess.run(
            [npm_bin, "install", "--no-save", "--ignore-scripts", *missing_runtime_deps],
            cwd=pkg_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=120, env=npm_env,
        )
        if proc.returncode == 0:
            _log("[OpenClaw] Required OpenClaw runtime dependencies installed.")
        else:
            _log(f"[OpenClaw] WARNING: npm install failed: {(proc.stdout or '')[:400]}")
    except Exception as e:
        _log(f"[OpenClaw] WARNING: Could not install required OpenClaw runtime dependencies: {e}")


def _ensure_openclaw_macos_gateway_running(form=None, live_cb=None):
    form = form or {}
    state = _read_json_file(OPENCLAW_STATE_FILE)
    oc_bin = str(state.get("openclaw_bin") or "").strip()
    if not oc_bin or not os.path.isfile(oc_bin):
        return False
    http_port = str(state.get("http_port") or (form.get("OPENCLAW_HTTP_PORT", ["18800"])[0] or "").strip() or "18800").strip()
    host_ip = str(state.get("host") or (form.get("OPENCLAW_HOST_IP", ["0.0.0.0"])[0] or "").strip() or "0.0.0.0").strip()
    bind_arg = "lan" if host_ip in ("", "0.0.0.0", "*") else "lan"
    log_file = OPENCLAW_STATE_DIR / "openclaw.log"

    def _log(m):
        if live_cb:
            live_cb(m + "\n")

    try:
        run_capture(["pkill", "-f", "openclaw gateway"], timeout=10)
    except Exception:
        pass

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([
        str(Path(oc_bin).parent),
        str(OPENCLAW_STATE_DIR / "node" / "bin"),
        env.get("PATH", ""),
    ])
    env["HOME"] = str(OPENCLAW_STATE_DIR)

    oc_env_file = Path(env["HOME"]) / ".openclaw" / ".env"
    if oc_env_file.exists():
        for line in oc_env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    try:
        log_file.write_text("", encoding="utf-8")
    except Exception:
        pass

    _log(f"[OpenClaw] Retrying gateway after backend dependency repair on port {http_port}...")
    try:
        proc = subprocess.Popen(
            [oc_bin, "gateway", "--bind", bind_arg, "--allow-unconfigured", "--port", http_port, "--verbose"],
            stdout=open(log_file, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            env=env,
        )
    except Exception as e:
        _log(f"[OpenClaw] WARNING: Could not restart gateway after repair: {e}")
        return False

    time.sleep(5)
    if proc.poll() is None:
        state["running"] = True
        _write_json_file(OPENCLAW_STATE_FILE, state)
        _log("[OpenClaw] Gateway recovered after backend dependency repair.")
        return True

    try:
        tail = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:]
        for line in tail:
            _log(f"[OpenClaw]   {line}")
    except Exception:
        pass
    return False


def _ensure_openclaw_os_config(form=None, live_cb=None):
    """Apply full-access config settings for OS-mode OpenClaw installs."""
    form = form or {}
    state = _read_json_file(OPENCLAW_STATE_FILE)
    if str(state.get("deploy_mode") or "").strip().lower() == "docker":
        return
    oc_bin = str(state.get("openclaw_bin") or "").strip()
    if not oc_bin or not os.path.isfile(oc_bin):
        return
    def _log(m):
        if live_cb:
            live_cb(m + "\n")
    config_cmds = [
        [oc_bin, "config", "set", "commands.native", "auto"],
        [oc_bin, "config", "set", "commands.nativeSkills", "auto"],
        [oc_bin, "config", "set", "agents.defaults.maxConcurrent", "4"],
        [oc_bin, "config", "set", "agents.defaults.subagents.maxConcurrent", "8"],
        [oc_bin, "config", "set", "gateway.controlUi.dangerouslyDisableDeviceAuth", "true"],
        [oc_bin, "config", "set", "gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback", "true"],
    ]
    for cmd in config_cmds:
        try:
            run_capture(cmd, timeout=10)
        except Exception:
            pass

    # Write channel tokens and API keys to .env file
    home_dir = os.path.expanduser("~")
    oc_env_file = Path(home_dir) / ".openclaw" / ".env"
    oc_env_file.parent.mkdir(parents=True, exist_ok=True)
    env_data = {}
    if oc_env_file.exists():
        for line in oc_env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env_data[k.strip()] = v.strip()
    token_map = {
        "OPENCLAW_TELEGRAM_TOKEN": "TELEGRAM_BOT_TOKEN",
        "OPENCLAW_DISCORD_TOKEN": "DISCORD_TOKEN",
        "OPENCLAW_SLACK_TOKEN": "SLACK_BOT_TOKEN",
        "OPENCLAW_WHATSAPP_PHONE": "WHATSAPP_PHONE",
        "OPENCLAW_OPENAI_KEY": "OPENAI_API_KEY",
        "OPENCLAW_ANTHROPIC_KEY": "ANTHROPIC_API_KEY",
    }
    for form_key, env_key in token_map.items():
        val = (form.get(form_key, [""])[0] or "").strip()
        if val:
            env_data[env_key] = val
    env_data.setdefault("OLLAMA_API_KEY", "ollama-local")
    oc_env_file.write_text(
        "\n".join(f"{k}={v}" for k, v in sorted(env_data.items())) + "\n",
        encoding="utf-8",
    )

    def _build_openclaw_path_instructions():
        desktop_path = Path(home_dir) / "Desktop"
        documents_path = Path(home_dir) / "Documents"
        downloads_path = Path(home_dir) / "Downloads"
        if sys.platform == "darwin":
            try:
                console_user = subprocess.run(
                    ["stat", "-f%Su", "/dev/console"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                ).stdout.strip()
                if console_user and console_user not in {"root", "loginwindow"}:
                    dscl = subprocess.run(
                        ["dscl", ".", "-read", f"/Users/{console_user}", "NFSHomeDirectory"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=5,
                    ).stdout.strip()
                    parts = dscl.split()
                    if parts:
                        real_home = Path(parts[-1])
                        desktop_path = real_home / "Desktop"
                        documents_path = real_home / "Documents"
                        downloads_path = real_home / "Downloads"
            except Exception:
                pass
        return (
            "You have full access to the entire filesystem. "
            "You can read, write, and execute files anywhere on this computer. "
            f"When the user asks for the desktop, use the real desktop path '{desktop_path}'. "
            f"When the user asks for Documents, use '{documents_path}'. "
            f"When the user asks for Downloads, use '{downloads_path}'. "
            "Do not create relative folders named Desktop, Documents, or Downloads inside the current working directory. "
            "Use absolute paths for user folders."
        )

    # Write agent settings with full filesystem/tool access
    agent_dir = Path(home_dir) / ".openclaw" / "agents" / "main" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    settings_file = agent_dir / "settings.json"
    try:
        import json as _json2
        settings = {}
        if settings_file.exists():
            try:
                settings = _json2.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                settings = {}
        settings["customInstructions"] = _build_openclaw_path_instructions()
        settings_file.write_text(_json2.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Update openclaw.json to allow tools and full filesystem access
    oc_config_path = Path(home_dir) / ".openclaw" / "openclaw.json"
    try:
        import json as _json3
        oc_cfg = {}
        if oc_config_path.exists():
            try:
                oc_cfg = _json3.loads(oc_config_path.read_text(encoding="utf-8"))
            except Exception:
                oc_cfg = {}
        agents = oc_cfg.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        defaults.setdefault("compaction", {})["mode"] = "safeguard"
        oc_config_path.write_text(_json3.dumps(oc_cfg, indent=2), encoding="utf-8")
    except Exception:
        pass

    try:
        sync_openclaw_provider_catalog(form=form, home_dir=home_dir, live_cb=live_cb)
    except Exception:
        pass

    # Retrieve gateway token directly from openclaw.json (CLI redacts it)
    gateway_token = ""
    oc_config_path = Path(home_dir) / ".openclaw" / "openclaw.json"
    try:
        import json as _json
        oc_cfg = _json.loads(oc_config_path.read_text(encoding="utf-8"))
        gateway_token = str(oc_cfg.get("gateway", {}).get("auth", {}).get("token", "")).strip()
    except Exception:
        pass
    # Fallback: try CLI (may return redacted)
    if not gateway_token or "REDACTED" in gateway_token.upper():
        rc, token_out = run_capture([oc_bin, "config", "get", "gateway.auth.token"], timeout=10)
        tok = token_out.strip() if rc == 0 else ""
        if tok and "REDACTED" not in tok.upper():
            gateway_token = tok
    if gateway_token:
        state["gateway_token"] = gateway_token
        # Build dashboard URL with token
        host = str(state.get("host") or "0.0.0.0").strip()
        if host in ("0.0.0.0", "", "*"):
            try:
                import socket as _s
                host = _s.gethostbyname(_s.gethostname())
            except Exception:
                host = "127.0.0.1"
        https_port = str(state.get("https_port") or "18801").strip()
        http_port = str(state.get("http_port") or "18800").strip()
        if https_port:
            state["dashboard_url"] = f"https://{host}:{https_port}/#token={gateway_token}"
            state["https_url"] = f"https://{host}:{https_port}"
        else:
            state["dashboard_url"] = f"http://{host}:{http_port}/#token={gateway_token}"
        state["http_url"] = f"http://{host}:{http_port}"
        _write_json_file(OPENCLAW_STATE_FILE, state)
        _log(f"[OpenClaw] Gateway token saved. Dashboard URL includes token.")
    _log("[OpenClaw] Full computer access configured (native commands, filesystem).")


def _ensure_openclaw_https_proxy(form=None, live_cb=None):
    """Start an HTTPS TLS proxy for OS-mode OpenClaw installs."""
    form = form or {}
    import subprocess as _sp
    state = _read_json_file(OPENCLAW_STATE_FILE)
    if str(state.get("deploy_mode") or "").strip().lower() == "docker":
        return  # Docker handles its own HTTPS via nginx
    http_port = str(state.get("http_port") or (form.get("OPENCLAW_HTTP_PORT", ["18800"])[0] or "").strip() or "18800").strip()
    https_port = str(state.get("https_port") or (form.get("OPENCLAW_HTTPS_PORT", ["18801"])[0] or "").strip() or "18801").strip()
    if not https_port:
        return
    install_dir = str(state.get("install_dir") or "").strip()
    cert_dir = OPENCLAW_STATE_DIR / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    def _log(m):
        if live_cb:
            live_cb(m + "\n")

    # Generate self-signed cert if missing
    if not cert_file.exists() or not key_file.exists():
        host_ip = str(state.get("host") or "0.0.0.0").strip()
        if host_ip in ("0.0.0.0", "", "*"):
            try:
                import socket as _sock
                host_ip = _sock.gethostbyname(_sock.gethostname())
            except Exception:
                host_ip = "127.0.0.1"
        cnf = cert_dir / "cert.cnf"
        cnf.write_text(
            "[req]\ndistinguished_name = req_dn\nx509_extensions = v3\nprompt = no\n"
            "[req_dn]\nCN = openclaw\nO = ServerInstaller\n"
            f"[v3]\nsubjectAltName = DNS:localhost,DNS:openclaw,IP:127.0.0.1,IP:{host_ip}\n",
            encoding="utf-8",
        )
        rc, _ = run_capture([
            "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-keyout", str(key_file), "-out", str(cert_file),
            "-days", "3650", "-config", str(cnf), "-extensions", "v3",
        ], timeout=30)
        cnf.unlink(missing_ok=True)
        if rc == 0:
            _log("[OpenClaw] SSL certificate generated.")
        else:
            _log("[OpenClaw] WARNING: Failed to generate SSL certificate.")
            return

    # Run TLS proxy as an in-process background thread
    import socket as _socket
    import ssl as _ssl
    import threading as _threading

    _https_port = int(https_port)
    _http_port = int(http_port)

    def _tls_pipe(src, dst):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try: src.close()
            except: pass
            try: dst.close()
            except: pass

    def _tls_handle(raw_client, ssl_ctx, backend_port):
        ssl_client = None
        try:
            ssl_client = ssl_ctx.wrap_socket(raw_client, server_side=True)
            backend = _socket.create_connection(("127.0.0.1", backend_port), timeout=10)
            t1 = _threading.Thread(target=_tls_pipe, args=(ssl_client, backend), daemon=True)
            t2 = _threading.Thread(target=_tls_pipe, args=(backend, ssl_client), daemon=True)
            t1.start(); t2.start()
            t1.join(); t2.join()
        except Exception:
            pass
        finally:
            if ssl_client:
                try: ssl_client.close()
                except: pass
            try: raw_client.close()
            except: pass

    def _run_tls_proxy(cert, key, listen_port, backend_port):
        try:
            ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert), str(key))
            srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", listen_port))
            srv.listen(128)
            while True:
                try:
                    client, addr = srv.accept()
                    _threading.Thread(target=_tls_handle, args=(client, ctx, backend_port), daemon=True).start()
                except Exception:
                    pass
        except Exception as e:
            import traceback
            traceback.print_exc()

    # Kill any existing process holding the HTTPS port
    try:
        run_capture(["pkill", "-f", "https-proxy"], timeout=5)
    except Exception:
        pass
    # Also kill by port using lsof (macOS/Linux)
    try:
        rc, lsof_out = run_capture(["lsof", "-ti", f":{_https_port}"], timeout=5)
        if rc == 0 and lsof_out.strip():
            for pid in lsof_out.strip().split():
                try:
                    os.kill(int(pid), 9)
                except Exception:
                    pass
            time.sleep(1)
    except Exception:
        pass

    proxy_thread = _threading.Thread(
        target=_run_tls_proxy,
        args=(cert_file, key_file, _https_port, _http_port),
        daemon=True,
    )
    proxy_thread.start()
    time.sleep(1)
    if proxy_thread.is_alive():
        _log(f"[OpenClaw] HTTPS proxy running on port {https_port} (in-process thread).")
    else:
        _log(f"[OpenClaw] WARNING: HTTPS proxy thread exited unexpectedly.")


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
    """Completely delete OpenClaw — Docker containers, images, OS service, data."""
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Deleting OpenClaw ===")

    state = _read_json_file(OPENCLAW_STATE_FILE)
    http_port = str(state.get("http_port") or "").strip()
    https_port = str(state.get("https_port") or "").strip()

    run_openclaw_stop(live_cb=live_cb)

    # Docker cleanup
    if command_exists("docker"):
        for cname in ["serverinstaller-openclaw"]:
            run_capture(["docker", "stop", cname], timeout=30)
            rc, _ = run_capture(["docker", "rm", "-f", cname], timeout=30)
            if rc == 0: log(f"Removed Docker container: {cname}")

    # Systemd cleanup
    if os.name != "nt" and command_exists("systemctl"):
        for svc in [OPENCLAW_SYSTEMD_SERVICE, "clawdbot-gateway"]:
            run_capture(["systemctl", "disable", svc], timeout=15)
            run_capture(["systemctl", "stop", svc], timeout=15)
            svc_file = Path(f"/etc/systemd/system/{svc}.service")
            if svc_file.exists():
                svc_file.unlink()
                log(f"Removed systemd unit: {svc}")
        run_capture(["systemctl", "daemon-reload"], timeout=15)
    elif os.name == "nt":
        try:
            run_capture(["schtasks", "/Delete", "/TN", "ServerInstaller-OpenClaw", "/F"], timeout=15)
            log("Removed scheduled task")
        except Exception: pass

    for subdir in ["app", "certs"]:
        d = OPENCLAW_STATE_DIR / subdir
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            log(f"Removed directory: {subdir}")
    if OPENCLAW_STATE_FILE.exists():
        OPENCLAW_STATE_FILE.unlink()
        log("Removed state file")

    for port in [http_port, https_port]:
        if port: manage_firewall_port("close", port, "tcp")

    log("=== OpenClaw completely removed ===")
    return 0, "\n".join(output)


def run_openclaw_refresh_models(live_cb=None):
    """Refresh OpenClaw model discovery by restarting the active service/container."""
    output = []
    def log(m):
        output.append(m)
        if live_cb:
            live_cb(m + "\n")

    state = _read_json_file(OPENCLAW_STATE_FILE)
    if not state.get("installed"):
        return 1, "OpenClaw is not installed."

    deploy_mode = str(state.get("deploy_mode") or "").strip().lower()
    log("=== Refreshing OpenClaw model list ===")
    log("OpenClaw refresh re-syncs reachable provider models, then restarts the service.")

    if deploy_mode != "docker":
        try:
            sync_openclaw_provider_catalog(live_cb=live_cb)
        except Exception as ex:
            log(f"Warning: provider model sync failed before restart: {ex}")

    if deploy_mode == "docker" and command_exists("docker"):
        container_name = str(state.get("service_name") or "serverinstaller-openclaw").strip() or "serverinstaller-openclaw"
        rc, out = run_capture(["docker", "restart", container_name], timeout=120)
        if out:
            log(out.strip())
        if rc != 0:
            return rc or 1, "\n".join(output)
        time.sleep(5)
        rc, logs = run_capture(["docker", "logs", "--tail", "60", container_name], timeout=20)
        if logs:
            log(logs.strip())
        state["running"] = True
        _write_json_file(OPENCLAW_STATE_FILE, state)
        log("Refresh complete. Re-open OpenClaw Settings > AI & Agents in a few seconds.")
        return 0, "\n".join(output)

    code, stop_out = run_openclaw_stop(live_cb=None)
    if stop_out:
        log(stop_out.strip())
    if code != 0:
        return code or 1, "\n".join(output)
    time.sleep(2)
    code, start_out = run_openclaw_start(live_cb=None)
    if start_out:
        log(start_out.strip())
    if code != 0:
        return code or 1, "\n".join(output)
    log("Refresh complete. Re-open OpenClaw Settings > AI & Agents in a few seconds.")
    return 0, "\n".join(output)


def run_openclaw_docker(form=None, live_cb=None):
    """Deploy real OpenClaw gateway as a Docker container with Node.js."""
    form = form or {}
    http_port_raw = (form.get("OPENCLAW_HTTP_PORT", [""])[0] or "").strip()
    https_port_raw = (form.get("OPENCLAW_HTTPS_PORT", [""])[0] or "").strip()
    http_port = http_port_raw if (http_port_raw.isdigit() and int(http_port_raw) > 0) else "18789"
    https_port = https_port_raw if (https_port_raw.isdigit() and int(https_port_raw) > 0) else ""
    adjusted_https_port = False
    if https_port and https_port == http_port:
        https_port = str(int(http_port) + 1)
        adjusted_https_port = True
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
    llm_model = (form.get("OPENCLAW_LLM_MODEL", ["ministral:3b"])[0] or "ministral:3b").strip()
    llm_model_custom = (form.get("OPENCLAW_LLM_MODEL_CUSTOM", [""])[0] or "").strip()
    if llm_model == "custom" and llm_model_custom:
        llm_model = llm_model_custom
    ollama_url = (form.get("OPENCLAW_OLLAMA_URL", [""])[0] or "").strip()
    # If OpenClaw Ollama URL is not explicitly provided, inherit it from the
    # installed Ollama service info so dashboard pages stay aligned.
    inherited_ollama_url = ""
    if not ollama_url:
        try:
            oinfo = get_ollama_info() or {}
            preferred = (
                str(oinfo.get("api_url") or "").strip()
                or str(oinfo.get("http_url") or "").strip()
                or str(oinfo.get("https_url") or "").strip()
                or ""
            )
            if preferred:
                ollama_url = preferred
                inherited_ollama_url = preferred
        except Exception:
            pass
    lmstudio_url = (form.get("OPENCLAW_LMSTUDIO_URL", [""])[0] or "").strip()
    inherited_lmstudio_url = ""
    if not lmstudio_url:
        try:
            linfo = get_lmstudio_info() or {}
            preferred = (
                str(linfo.get("api_url") or "").strip()
                or str(linfo.get("http_url") or "").strip()
                or str(linfo.get("https_url") or "").strip()
                or ""
            )
            if preferred:
                lmstudio_url = preferred
                inherited_lmstudio_url = preferred
        except Exception:
            pass
    openai_key = (form.get("OPENCLAW_OPENAI_KEY", [""])[0] or "").strip()
    anthropic_key = (form.get("OPENCLAW_ANTHROPIC_KEY", [""])[0] or "").strip()
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    host_memory = {}
    try:
        host_memory = get_memory_info() or {}
    except Exception:
        host_memory = {}
    host_available_bytes = int(host_memory.get("available_bytes") or 0)
    host_total_bytes = int(host_memory.get("total_bytes") or 0)
    log("=== Installing OpenClaw via Docker ===")
    if host_available_bytes:
        log(
            "Detected host memory: "
            f"{host_available_bytes / (1024 ** 3):.1f} GiB available"
            + (
                f" of {host_total_bytes / (1024 ** 3):.1f} GiB total"
                if host_total_bytes else ""
            )
        )
    if inherited_ollama_url:
        log(f"Using Ollama API URL from Ollama service: {inherited_ollama_url}")
    elif ollama_url:
        log(f"Using Ollama API URL for OpenClaw: {ollama_url}")
    if inherited_lmstudio_url:
        log(f"Using LM Studio API URL from LM Studio service: {inherited_lmstudio_url}")
    elif lmstudio_url:
        log(f"Using LM Studio API URL for OpenClaw: {lmstudio_url}")
    if adjusted_https_port:
        log(f"HTTPS port matched HTTP port; adjusted HTTPS to {https_port} to keep protocols separate.")

    docker_code, docker_message = _ensure_docker_ready(log)
    if docker_code != 0:
        log(docker_message)
        return docker_code, "\n".join(output)

    container_name = "serverinstaller-openclaw"
    run_capture(["docker", "stop", container_name], timeout=15)
    run_capture(["docker", "rm", container_name], timeout=15)

    # Build real OpenClaw container with Node.js
    log("Building OpenClaw container (Node.js + real OpenClaw gateway)...")
    build_dir = str(OPENCLAW_STATE_DIR / "docker-build")
    Path(build_dir).mkdir(parents=True, exist_ok=True)

    gw_internal_port = str(max(int(http_port), int(https_port) if https_port else 0) + 1)

    # Write nginx config as a separate file (no shell escaping issues)
    nginx_conf = f"""daemon off;
worker_processes 1;
error_log /dev/stderr info;
pid /tmp/nginx.pid;
events {{ worker_connections 1024; }}
http {{
    access_log /dev/stdout;
    server {{
        listen {http_port} ssl;
        ssl_certificate /root/.openclaw/certs/cert.pem;
        ssl_certificate_key /root/.openclaw/certs/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        location / {{
            proxy_pass http://127.0.0.1:{gw_internal_port};
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
        }}
    }}
}}
"""
    Path(build_dir, "nginx.conf").write_text(nginx_conf, encoding="utf-8")

    # Simple entrypoint — no escaping issues
    entrypoint_lines = [
        "#!/bin/bash",
        f'echo "=== OpenClaw Docker Container (http {http_port}{", https " + https_port if https_port else ""}) ==="',
        "",
        "# Install and start Ollama for local LLM",
        f'OLLAMA_REMOTE="{ollama_url}"',
        'if [ -z "$OLLAMA_REMOTE" ]; then',
        "  # Prefer host Ollama if present (Windows/macOS Docker)",
        "  if curl -sf http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then",
        "    OLLAMA_REMOTE='http://host.docker.internal:11434'",
        "    echo \"Using host Ollama at: $OLLAMA_REMOTE\"",
        "  fi",
        "fi",
        "",
        'if [ -z "$OLLAMA_REMOTE" ]; then',
        "  echo 'Setting up local Ollama (inside container)...'",
        "  if ! command -v ollama &>/dev/null; then",
        "    echo 'Installing Ollama...'",
        "    curl -fsSL https://ollama.com/install.sh | sh 2>&1 || echo 'Ollama install failed'",
        "  fi",
        "  if command -v ollama &>/dev/null; then",
        "    echo 'Starting Ollama server...'",
        "    ollama serve &>/dev/null &",
        "    sleep 5",
        f"    echo 'Pulling model ({llm_model})...'",
        f"    ollama pull {llm_model} 2>&1 || echo 'Model pull skipped'",
        "    echo 'Ollama ready on 127.0.0.1:11434'",
        "  fi",
        "else",
        '  echo "Using remote Ollama at: $OLLAMA_REMOTE"',
        "fi",
        "",
        "# Clean old agent config and sessions",
        "rm -f /root/.openclaw/agents/main/agent/settings.json 2>/dev/null || true",
        "rm -f /root/.openclaw/agents/main/agent/auth-profiles.json 2>/dev/null || true",
        "rm -rf /root/.openclaw/agents/main/sessions 2>/dev/null || true",
        "rm -rf /root/.openclaw/sessions 2>/dev/null || true",
        "# Fix corrupted openclaw.json from previous bad installs",
        "if [ -f /root/.openclaw/openclaw.json ]; then",
        "  python3 -c \"",
        "import json",
        "p='/root/.openclaw/openclaw.json'",
        "try: c=json.load(open(p))",
        "except: c={}",
        "bad=['agent','defaultModel','defaultProvider']",
        "for k in bad:",
        "  c.pop(k,None)",
        "if isinstance(c.get('agents'), dict) and isinstance(c['agents'].get('defaults'), dict):",
        "  if 'models' in c['agents']['defaults']:",
        "    c['agents']['defaults'].pop('models', None)",
        "  if not c['agents']['defaults']:",
        "    c['agents'].pop('defaults', None)",
        "  if not c['agents']:",
        "    c.pop('agents', None)",
        "if 'models' in c and 'ollama' in c.get('models',{}):",
        "  del c['models']['ollama']",
        "  if not c['models']: c.pop('models',None)",
        "json.dump(c,open(p,'w'),indent=2)",
        "\" 2>/dev/null || true",
        "fi",
        "",
        "# Pre-start config (keep this minimal; newer OpenClaw releases reject",
        "# legacy control-ui keys and require gateway.mode to be set explicitly).",
        "echo 'Configuring OpenClaw gateway...'",
        "mkdir -p /root/.openclaw /root/.openclaw/agents/main/agent /root/.openclaw/agents/main/sessions /root/.openclaw/credentials /root/.openclaw/canvas",
        "chmod 700 /root/.openclaw /root/.openclaw/agents /root/.openclaw/agents/main /root/.openclaw/agents/main/agent /root/.openclaw/agents/main/sessions /root/.openclaw/credentials /root/.openclaw/canvas 2>/dev/null || true",
        "openclaw config set gateway.mode local 2>/dev/null || true",
        "EXISTING_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null || true)",
        "if [ -n \"$EXISTING_TOKEN\" ]; then",
        "  OPENCLAW_GATEWAY_TOKEN=\"$EXISTING_TOKEN\"",
        "  echo \"Reusing existing gateway token (browser cache remains valid)\"",
        "else",
        "  OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 24 2>/dev/null || echo openclaw-local-token)",
        "fi",
        "export OPENCLAW_GATEWAY_TOKEN",
        "openclaw config set gateway.auth.token \"$OPENCLAW_GATEWAY_TOKEN\" 2>/dev/null || true",
        "openclaw config set gateway.remote.token \"$OPENCLAW_GATEWAY_TOKEN\" 2>/dev/null || true",
        "openclaw config set gateway.trustedProxies '[\"127.0.0.1\",\"::1\"]' 2>/dev/null || true",
        "# This managed deployment exposes the Control UI to remote browsers behind",
        "# the installer's reverse proxy. Disable OpenClaw device pairing so LAN users",
        "# can connect immediately with the gateway token instead of a manual approval step.",
        "openclaw config set gateway.controlUi.dangerouslyDisableDeviceAuth true 2>/dev/null || true",
        "# Build the gateway.controlUi.allowedOrigins list so the browser can connect.",
        "# We collect every IPv4 address the user might browse to:",
        "#  1. $OPENCLAW_HOST_IP env var (set from the install form — the most reliable source)",
        "#  2. All IPv4 addresses on the container's network interfaces",
        "#  3. The docker host gateway (host.docker.internal, IPv4 only)",
        f'OC_ORIGINS=\'["http://localhost:{http_port}","http://127.0.0.1:{http_port}"\'',
        *(
            [f'OC_ORIGINS="$OC_ORIGINS,\\"https://localhost:{https_port}\\",\\"https://127.0.0.1:{https_port}\\""']
            if https_port else []
        ),
        "# Add OPENCLAW_HOST_IP if it is a real (non-wildcard) address",
        'if [ -n "$OPENCLAW_HOST_IP" ] && [ "$OPENCLAW_HOST_IP" != "0.0.0.0" ] && [ "$OPENCLAW_HOST_IP" != "*" ]; then',
        f'  OC_ORIGINS="$OC_ORIGINS,\\"http://$OPENCLAW_HOST_IP:{http_port}\\""',
        *(
            [f'  OC_ORIGINS="$OC_ORIGINS,\\"https://$OPENCLAW_HOST_IP:{https_port}\\""']
            if https_port else []
        ),
        "fi",
        "# Add every IPv4 address found on the host's network interfaces (IPv4 only)",
        "for IP4 in $(hostname -I 2>/dev/null | tr ' ' '\\n' | grep -E '^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$' || true); do",
        f'  OC_ORIGINS="$OC_ORIGINS,\\"http://$IP4:{http_port}\\""',
        *(
            [f'  OC_ORIGINS="$OC_ORIGINS,\\"https://$IP4:{https_port}\\""']
            if https_port else []
        ),
        "done",
        "# Add the docker host gateway IPv4 (resolves to the host machine on Docker Desktop)",
        "DOCKER_HOST_IP4=$(getent ahosts host.docker.internal 2>/dev/null | awk '$2==\"STREAM\" && $1 !~ /:/{print $1}' | head -1 || echo '')",
        'if [ -n "$DOCKER_HOST_IP4" ]; then',
        f'  OC_ORIGINS="$OC_ORIGINS,\\"http://$DOCKER_HOST_IP4:{http_port}\\""',
        *(
            [f'  OC_ORIGINS="$OC_ORIGINS,\\"https://$DOCKER_HOST_IP4:{https_port}\\""']
            if https_port else []
        ),
        "fi",
        'OC_ORIGINS="$OC_ORIGINS]"',
        "openclaw config set gateway.controlUi.allowedOrigins \"$OC_ORIGINS\" 2>/dev/null || true",
        "",
        "# Set Ollama API key — enables Ollama provider in OpenClaw",
        "# Only OLLAMA_API_KEY is set by default. OpenAI/Anthropic keys",
        "# are set by the user via the API Tokens panel (no placeholders).",
        "export OLLAMA_API_KEY='ollama-local'",
        f"export OLLAMA_HOST='{ollama_url or 'http://127.0.0.1:11434'}'",
        "",
        "# OpenClaw auto-discovers Ollama at http://127.0.0.1:11434 ONLY.",
        "# The user's Ollama URL can be anything: http, https, any host, any port.",
        "# We use nginx as a local reverse proxy on port 11434 to handle all cases.",
        "",
        "# Find the working Ollama URL (try user URL, then common fallbacks)",
        "OLLAMA_PROXY_URL=''",
        "for TRY_URL in \"$OLLAMA_HOST\" http://host.docker.internal:11434 http://127.0.0.1:11434; do",
        "  if [ -n \"$TRY_URL\" ] && curl -skf \"${TRY_URL}/api/tags\" >/dev/null 2>&1; then",
        "    OLLAMA_PROXY_URL=$TRY_URL",
        "    break",
        "  fi",
        "done",
        "",
        "if [ -n \"$OLLAMA_PROXY_URL\" ] && [ \"$OLLAMA_PROXY_URL\" != 'http://127.0.0.1:11434' ]; then",
        "  echo \"Ollama found at: $OLLAMA_PROXY_URL\"",
        "  echo 'Starting nginx proxy on 127.0.0.1:11434 -> '$OLLAMA_PROXY_URL",
        "  # Determine if target is HTTPS",
        "  OLLAMA_IS_HTTPS=$(echo \"$OLLAMA_PROXY_URL\" | grep -c '^https://' || true)",
        "  cat > /tmp/ollama-proxy.conf << OLLAMAEOF",
        "worker_processes 1;",
        "error_log /dev/null;",
        "pid /tmp/ollama-proxy.pid;",
        "events { worker_connections 256; }",
        "http {",
        "  server {",
        "    listen 11434;",
        "    location / {",
        "      proxy_pass $OLLAMA_PROXY_URL;",
        "      proxy_http_version 1.1;",
        "      proxy_set_header Host \\$host;",
        "      proxy_set_header Connection \\\"\\\";",
        "      proxy_read_timeout 600;",
        "      proxy_ssl_verify off;",
        "    }",
        "  }",
        "}",
        "OLLAMAEOF",
        "  nginx -c /tmp/ollama-proxy.conf &",
        "  sleep 1",
        "  # Verify proxy works",
        "  if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then",
        "    echo 'Ollama proxy OK — models available at 127.0.0.1:11434'",
        "  else",
        "    echo 'WARNING: Ollama proxy started but not responding'",
        "  fi",
        "elif [ -n \"$OLLAMA_PROXY_URL\" ]; then",
        "  echo 'Ollama already at 127.0.0.1:11434 — no proxy needed'",
        "else",
        "  echo 'WARNING: Ollama not reachable. Tried: '$OLLAMA_HOST', host.docker.internal:11434, 127.0.0.1:11434'",
        "fi",
        "",
        "# Verify Ollama is reachable and show models",
        "echo 'Testing Ollama API at 127.0.0.1:11434...'",
        "curl -sf http://127.0.0.1:11434/api/tags 2>&1 | head -3 || echo 'Ollama API not responding'",
        "",
        "# Force OpenClaw to use the local proxy URL (avoids TLS/self-signed issues with remote Ollama URLs)",
        "export OLLAMA_HOST='http://127.0.0.1:11434'",
        "export OLLAMA_BASE_URL='http://127.0.0.1:11434'",
        f"export LMSTUDIO_HOST='{lmstudio_url}'",
        "if [ -n \"$LMSTUDIO_HOST\" ] && ! echo \"$LMSTUDIO_HOST\" | grep -q '/v1'; then",
        "  export LMSTUDIO_API_BASE=\"${LMSTUDIO_HOST%/}/v1\"",
        "else",
        "  export LMSTUDIO_API_BASE=\"$LMSTUDIO_HOST\"",
        "fi",
        "export LMSTUDIO_API_KEY='lmstudio-local'",
        f"export DESIRED_OLLAMA_MODEL='{llm_model}'",
        f"export DESIRED_LLM_PROVIDER='{llm_provider}'",
        "",
        "# Sync OpenClaw model picker with Ollama (/api/tags) and pick a valid default model",
        "python3 - << 'PYEOF'",
        "import json, os, re, sys, urllib.request",
        "url = 'http://127.0.0.1:11434/api/tags'",
        "try:",
        "  with urllib.request.urlopen(url, timeout=5) as r:",
        "    data = json.load(r)",
        "except Exception as e:",
        "  print('WARN: could not query Ollama tags:', e, file=sys.stderr)",
        "  data = {}",
        "available_bytes = int(os.environ.get('OPENCLAW_HOST_AVAILABLE_BYTES') or '0')",
        "records = []",
        "for m in (data.get('models') or []):",
        "  name = (m.get('model') or m.get('name') or '').strip()",
        "  if not name:",
        "    continue",
        "  details = m.get('details') or {}",
        "  families = [str(x).strip().lower() for x in (details.get('families') or []) if str(x).strip()]",
        "  family = str(details.get('family') or '').strip().lower()",
        "  if family and family not in families:",
        "    families.append(family)",
        "  records.append({",
        "    'name': name,",
        "    'size': int(m.get('size') or 0),",
        "    'families': families,",
        "    'parameter_size': str(details.get('parameter_size') or '').strip(),",
        "    'tool_capable': False,",
        "    'required_bytes': 0,",
        "    'fits_memory': True,",
        "    'context_window': 16384,",
        "    'max_tokens': 4096,",
        "  })",
        "def norm(s: str) -> str:",
        "  s = (s or '').lower().strip()",
        "  s = re.sub(r'[^a-z0-9:]+', '', s)",
        "  return s",
        "def size_to_billions(s: str) -> float:",
        "  s = (s or '').strip().upper()",
        "  if not s:",
        "    return 0.0",
        "  m = re.match(r'([0-9]+(?:\\.[0-9]+)?)\\s*([BM])', s)",
        "  if not m:",
        "    return 0.0",
        "  val = float(m.group(1))",
        "  unit = m.group(2)",
        "  return val / 1000.0 if unit == 'M' else val",
        "def estimate_required_bytes(rec):",
        "  on_disk = int(rec.get('size') or 0)",
        "  params_b = size_to_billions(rec.get('parameter_size') or '')",
        "  disk_estimate = int(on_disk * 1.10) if on_disk else 0",
        "  param_estimate = int(params_b * 1.7 * (1024 ** 3)) if params_b else 0",
        "  return max(disk_estimate, param_estimate, on_disk)",
        "def _extract_context_window(info: dict) -> int:",
        "  for scope in (info.get('model_info') or {}, info.get('details') or {}, info):",
        "    if not isinstance(scope, dict):",
        "      continue",
        "    for key, value in scope.items():",
        "      key_s = str(key).strip().lower()",
        "      if 'context_length' in key_s or key_s.endswith('num_ctx') or key_s == 'context_window':",
        "        try:",
        "          parsed = int(value)",
        "        except Exception:",
        "          continue",
        "        if parsed > 0:",
        "          # Keep OpenClaw prompts above Ollama's 4096 default without",
        "          # allocating arbitrarily huge KV caches on larger models.",
        "          return max(16384, min(parsed, 32768))",
        "  return 16384",
        "def show_model_info(name: str):",
        "  try:",
        "    payload = json.dumps({'model': name}).encode('utf-8')",
        "    req = urllib.request.Request(",
        "      'http://127.0.0.1:11434/api/show',",
        "      data=payload,",
        "      headers={'Content-Type': 'application/json'},",
        "      method='POST'",
        "    )",
        "    with urllib.request.urlopen(req, timeout=8) as r:",
        "      return json.load(r)",
        "  except Exception as e:",
        "    print(f'WARN: could not inspect Ollama model {name}: {e}', file=sys.stderr)",
        "    return {}",
        "for rec in records:",
        "  info = show_model_info(rec['name'])",
        "  caps = [str(x).strip().lower() for x in (info.get('capabilities') or []) if str(x).strip()]",
        "  families = [str(x).strip().lower() for x in (info.get('details', {}).get('families') or []) if str(x).strip()]",
        "  family = str(info.get('details', {}).get('family') or '').strip().lower()",
        "  for fam in families + ([family] if family else []):",
        "    if fam and fam not in rec['families']:",
        "      rec['families'].append(fam)",
        "  if info.get('details', {}).get('parameter_size'):",
        "    rec['parameter_size'] = str(info.get('details', {}).get('parameter_size') or '').strip()",
        "  rec['context_window'] = _extract_context_window(info)",
        "  rec['max_tokens'] = max(2048, min(8192, rec['context_window'] // 4))",
        "  rec['tool_capable'] = ('tools' in caps) or ('tool' in caps)",
        "  rec['required_bytes'] = estimate_required_bytes(rec)",
        "  rec['fits_memory'] = (not available_bytes) or (rec['required_bytes'] <= available_bytes)",
        "visible_records = [rec for rec in records if rec['fits_memory']]",
        "models = [",
        "  {",
        "    'id': r['name'],",
        "    'name': r['name'],",
        "    'contextWindow': int(r.get('context_window') or 16384),",
        "    'maxTokens': int(r.get('max_tokens') or 4096),",
        "  }",
        "  for r in visible_records",
        "]",
        "def split_model(s: str):",
        "  s = (s or '').strip()",
        "  if ':' in s:",
        "    fam, tag = s.split(':', 1)",
        "  else:",
        "    fam, tag = s, ''",
        "  fam_n = re.sub(r'[^a-z0-9]+', '', fam.lower())",
        "  tag_n = re.sub(r'[^a-z0-9]+', '', tag.lower())",
        "  return fam_n, tag_n",
        "desired = os.environ.get('OPENCLAW_MODEL') or os.environ.get('DESIRED_OLLAMA_MODEL') or ''",
        "desired_n = norm(desired)",
        "desired_fam, desired_tag = split_model(desired)",
        "chosen = None",
        "candidate_records = visible_records",
        "if candidate_records:",
        "  for rec in candidate_records:",
        "    cand = rec['name']",
        "    if cand == desired:",
        "      chosen = cand; break",
        "  if not chosen:",
        "    for rec in candidate_records:",
        "      cand = rec['name']",
        "      if cand.lower() == desired.lower():",
        "        chosen = cand; break",
        "  if not chosen and desired_n:",
        "    for rec in candidate_records:",
        "      cand = rec['name']",
        "      if norm(cand) == desired_n:",
        "        chosen = cand; break",
        "  if not chosen and desired_fam:",
        "    for rec in candidate_records:",
        "      cand = rec['name']",
        "      cfam, ctag = split_model(cand)",
        "      fam_match = (",
        "        cfam == desired_fam or",
        "        cfam.startswith(desired_fam) or",
        "        desired_fam.startswith(cfam) or",
        "        (desired_fam == 'ministral' and cfam.startswith('ministral3'))",
        "      )",
        "      tag_match = (not desired_tag) or (ctag == desired_tag)",
        "      if fam_match and tag_match:",
        "        chosen = cand; break",
        "  if not chosen:",
        "    preferred_tokens = [",
        "      'gptoss', 'llama33', 'qwen25coder', 'qwen3', 'deepseekr1', 'mistral', 'llama32'",
        "    ]",
        "    def rank(rec):",
        "      name_n = norm(rec['name'])",
        "      fam_blob = ''.join(rec['families'])",
        "      tool_rank = 1 if rec['tool_capable'] else 0",
        "      param_rank = size_to_billions(rec['parameter_size'])",
        "      size_rank = rec['size']",
        "      weak_penalty = 1 if param_rank and param_rank < 7.0 else 0",
        "      preferred_rank = 0",
        "      for idx, tok in enumerate(preferred_tokens):",
        "        if tok in name_n or tok in fam_blob:",
        "          preferred_rank = len(preferred_tokens) - idx",
        "          break",
        "      return (tool_rank, preferred_rank, 0 if weak_penalty else 1, param_rank, size_rank, name_n)",
        "    candidate_records.sort(key=rank, reverse=True)",
        "    chosen = candidate_records[0]['name']",
        "with open('/tmp/ollama-default-model.txt', 'w', encoding='utf-8') as f:",
        "  f.write(chosen or '')",
        "with open('/tmp/ollama-models.json', 'w', encoding='utf-8') as f:",
        "  json.dump(models, f)",
        "print('Ollama models discovered:', len(records))",
        "if records:",
        "  print('Ollama available models:', ', '.join(r['name'] for r in records))",
        "if available_bytes:",
        "  print('Ollama models that fit available memory:', ', '.join(models) if models else '(none)')",
        "for rec in records:",
        "  req_gib = (rec['required_bytes'] / (1024 ** 3)) if rec['required_bytes'] else 0",
        "  print('Ollama model probe:', rec['name'], 'tools=' + ('yes' if rec['tool_capable'] else 'no'), 'params=' + (rec['parameter_size'] or '?'), 'families=' + (','.join(rec['families']) or '-'), 'required~=' + (f'{req_gib:.1f}GiB' if req_gib else '?'), 'fits=' + ('yes' if rec['fits_memory'] else 'no'))",
        "if records and not visible_records and available_bytes:",
        "  print('WARN: no Ollama models fit the currently available host memory', file=sys.stderr)",
        "print('Ollama desired model:', desired)",
        "print('Ollama chosen model:', chosen)",
        "PYEOF",
        "",
        "# Discover LM Studio models when a compatible endpoint is configured",
        "python3 - << 'PYEOF'",
        "import json, os, sys, urllib.request",
        "base = (os.environ.get('LMSTUDIO_API_BASE') or '').strip().rstrip('/')",
        "chosen = ''",
        "models = []",
        "if base:",
        "  try:",
        "    req = urllib.request.Request(base + '/models', headers={'Authorization': 'Bearer ' + (os.environ.get('LMSTUDIO_API_KEY') or 'lmstudio-local')})",
        "    with urllib.request.urlopen(req, timeout=5) as r:",
        "      data = json.load(r)",
        "    for item in (data.get('data') or []):",
        "      mid = (item.get('id') or '').strip()",
        "      if mid:",
        "        models.append(mid)",
        "    if models:",
        "      chosen = models[0]",
        "  except Exception as e:",
        "    print('WARN: could not query LM Studio models:', e, file=sys.stderr)",
        "with open('/tmp/lmstudio-default-model.txt', 'w', encoding='utf-8') as f:",
        "  f.write(chosen)",
        "with open('/tmp/lmstudio-models.json', 'w', encoding='utf-8') as f:",
        "  json.dump(models, f)",
        "print('LM Studio models discovered:', len(models))",
        "if models:",
        "  print('LM Studio available models:', ', '.join(models))",
        "print('LM Studio chosen model:', chosen)",
        "PYEOF",
        "",
        "# Ensure OLLAMA_API_KEY is available everywhere",
        "echo 'OLLAMA_API_KEY='$OLLAMA_API_KEY",
        "# Write .env file in OpenClaw's directory (Node.js dotenv reads this)",
        "echo 'OLLAMA_API_KEY=ollama-local' > /root/.openclaw/.env",
        "# Also write to home dir and working dir for Node.js process",
        "echo 'OLLAMA_API_KEY=ollama-local' > /root/.env",
        "echo 'OLLAMA_API_KEY=ollama-local' > /.env",
        "# Write to /etc/environment for all processes",
        "echo 'OLLAMA_API_KEY=ollama-local' >> /etc/environment",
        "",
        "# Provider registration (no interactive configure)",
        "# Provider setup: OLLAMA_API_KEY + local OLLAMA_HOST, plus auth-profiles.json",
        "# Write agent auth profiles (Ollama + Claude if provided)",
        "AGENT_DIR=/root/.openclaw/agents/main/agent",
        "mkdir -p $AGENT_DIR",
        "python3 - << 'PYEOF'",
        "import json, os, pathlib",
        "agent_dir = pathlib.Path('/root/.openclaw/agents/main/agent')",
        "agent_dir.mkdir(parents=True, exist_ok=True)",
        "auth_path = agent_dir / 'auth-profiles.json'",
        "try:",
        "  existing = json.loads(auth_path.read_text(encoding='utf-8')) if auth_path.exists() else {}",
        "except Exception:",
        "  existing = {}",
        "profiles = existing.get('profiles') or {}",
        "last_good = existing.get('lastGood') or {}",
        "# Also read keys from .env files (set by the API Tokens panel)",
        "env_keys = {}",
        "for env_path in ['/root/.env', '/root/.openclaw/.env']:",
        "  try:",
        "    for line in pathlib.Path(env_path).read_text(encoding='utf-8', errors='ignore').splitlines():",
        "      if '=' in line and not line.lstrip().startswith('#'):",
        "        k, v = line.split('=', 1)",
        "        env_keys[k.strip()] = v.strip()",
        "  except Exception:",
        "    pass",
        "ollama_key = os.environ.get('OLLAMA_API_KEY') or env_keys.get('OLLAMA_API_KEY')",
        "if ollama_key:",
        "  profiles['ollama:local'] = {'type': 'api_key', 'provider': 'ollama', 'key': ollama_key}",
        "  last_good['ollama'] = 'ollama:local'",
        "lmstudio_key = os.environ.get('LMSTUDIO_API_KEY') or env_keys.get('LMSTUDIO_API_KEY')",
        "if lmstudio_key:",
        "  profiles['lmstudio:local'] = {'type': 'api_key', 'provider': 'lmstudio', 'key': lmstudio_key}",
        "  last_good['lmstudio'] = 'lmstudio:local'",
        "anthropic_key = os.environ.get('ANTHROPIC_API_KEY') or env_keys.get('ANTHROPIC_API_KEY')",
        "if anthropic_key:",
        "  profiles['anthropic:default'] = {'type': 'api_key', 'provider': 'anthropic', 'key': anthropic_key}",
        "  last_good['anthropic'] = 'anthropic:default'",
        "openai_key = os.environ.get('OPENAI_API_KEY') or env_keys.get('OPENAI_API_KEY')",
        "if openai_key:",
        "  profiles['openai:default'] = {'type': 'api_key', 'provider': 'openai', 'key': openai_key}",
        "  last_good['openai'] = 'openai:default'",
        "data = {'version': 1, 'profiles': profiles, 'lastGood': last_good}",
        "(agent_dir / 'auth-profiles.json').write_text(json.dumps(data, indent=2), encoding='utf-8')",
        "enabled = ', '.join(sorted(profiles.keys())) if profiles else '(none)'",
        "print('Auth profiles enabled:', enabled)",
        "PYEOF",
        "",
        "# Keep other gateway auth/controlUi options at OpenClaw defaults.",
        "# This version only needs gateway.mode plus a concrete token value.",
        "",
        "# NOTE: Do not set agents.defaults.models here.",
        "# New OpenClaw expects this key to be a record, not an array. Writing an array",
        "# causes config validation errors and can break Control UI with HTTP 500.",
        "",
        "# Always enforce a model that exists in Ollama /api/tags",
        "OLLAMA_DEFAULT=$(cat /tmp/ollama-default-model.txt 2>/dev/null || true)",
        "LMSTUDIO_DEFAULT=$(cat /tmp/lmstudio-default-model.txt 2>/dev/null || true)",
        "export OLLAMA_DEFAULT LMSTUDIO_DEFAULT",
        "export OLLAMA_API_BASE=\"$OLLAMA_PROXY_URL\"",
        "SELECTED_PROVIDER=$(printf '%s' \"$DESIRED_LLM_PROVIDER\" | tr '[:upper:]' '[:lower:]')",
        "if echo \"$SELECTED_PROVIDER\" | grep -q 'lm studio\\|lmstudio'; then",
        "  if [ -n \"$LMSTUDIO_DEFAULT\" ]; then",
        "    export OPENCLAW_PROVIDER='lmstudio'",
        "    export OPENCLAW_MODEL=\"$LMSTUDIO_DEFAULT\"",
        "    echo \"Using LM Studio model from /v1/models: $LMSTUDIO_DEFAULT\"",
        "  elif [ -n \"$OLLAMA_DEFAULT\" ]; then",
        "    export OPENCLAW_PROVIDER='ollama'",
        "    export OPENCLAW_MODEL=\"$OLLAMA_DEFAULT\"",
        "    echo \"LM Studio unavailable; falling back to Ollama model: $OLLAMA_DEFAULT\"",
        "  fi",
        "else",
        "  if [ -n \"$OLLAMA_DEFAULT\" ]; then",
        "    export OPENCLAW_PROVIDER='ollama'",
        "    export OPENCLAW_MODEL=\"$OLLAMA_DEFAULT\"",
        "    echo \"Using Ollama model from /api/tags: $OLLAMA_DEFAULT\"",
        "  elif [ -n \"$LMSTUDIO_DEFAULT\" ]; then",
        "    export OPENCLAW_PROVIDER='lmstudio'",
        "    export OPENCLAW_MODEL=\"$LMSTUDIO_DEFAULT\"",
        "    echo \"Ollama unavailable; falling back to LM Studio model: $LMSTUDIO_DEFAULT\"",
        "  fi",
        "fi",
        "# Source .env files so API keys set via the Tokens panel are visible",
        "if [ -f /root/.openclaw/.env ]; then set -a; . /root/.openclaw/.env; set +a; fi",
        "if [ -z \"$OPENCLAW_PROVIDER\" ] && [ -n \"$OPENAI_API_KEY\" ]; then",
        "  export OPENCLAW_PROVIDER='openai'",
        "  echo 'Using OpenAI provider (model selected in OpenClaw dashboard).'",
        "fi",
        "if [ -z \"$OPENCLAW_PROVIDER\" ] && [ -n \"$ANTHROPIC_API_KEY\" ]; then",
        "  export OPENCLAW_PROVIDER='anthropic'",
        "  echo 'Using Anthropic provider (model selected in OpenClaw dashboard).'",
        "fi",
        "# Write the default model to the agent settings file and global config.",
        "python3 - << 'PYEOF'",
        "import json, os, pathlib",
        "cfg_path = pathlib.Path('/root/.openclaw/openclaw.json')",
        "try:",
        "  cfg = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}",
        "except Exception:",
        "  cfg = {}",
        "agent_dir = pathlib.Path('/root/.openclaw/agents/main/agent')",
        "agent_dir.mkdir(parents=True, exist_ok=True)",
        "def _load_models(path):",
        "  try:",
        "    data = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))",
        "    if isinstance(data, list):",
        "      cleaned = []",
        "      for item in data:",
        "        if isinstance(item, dict):",
        "          mid = str(item.get('id') or item.get('name') or '').strip()",
        "          if not mid:",
        "            continue",
        "          cleaned.append({",
        "            'id': mid,",
        "            'name': str(item.get('name') or mid).strip(),",
        "            'contextWindow': int(item.get('contextWindow') or 16384),",
        "            'maxTokens': int(item.get('maxTokens') or 4096),",
        "          })",
        "        else:",
        "          mid = str(item).strip()",
        "          if mid:",
        "            cleaned.append({",
        "              'id': mid,",
        "              'name': mid,",
        "              'contextWindow': 16384,",
        "              'maxTokens': 4096,",
        "            })",
        "      return cleaned",
        "  except Exception:",
        "    pass",
        "  return []",
        "def _make_model_entry(item):",
        "  mid = str((item or {}).get('id') or (item or {}).get('name') or '').strip()",
        "  name = str((item or {}).get('name') or mid).strip()",
        "  context_window = int((item or {}).get('contextWindow') or 16384)",
        "  max_tokens = int((item or {}).get('maxTokens') or max(2048, min(8192, context_window // 4)))",
        "  return {",
        "    'id': mid,",
        "    'name': name,",
        "    'reasoning': False,",
        "    'input': ['text'],",
        "    'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},",
        "    'contextWindow': context_window,",
        "    'maxTokens': max_tokens,",
        "  }",
        "model = (os.environ.get('OPENCLAW_MODEL') or '').strip()",
        "provider = (os.environ.get('OPENCLAW_PROVIDER') or '').strip()",
        "settings = {'customInstructions': ''}",
        "agents = cfg.setdefault('agents', {})",
        "defaults = agents.setdefault('defaults', {})",
        "model_cfg = defaults.setdefault('model', {})",
        "catalog_cfg = defaults.setdefault('models', {})",
        "models_cfg = cfg.setdefault('models', {})",
        "models_cfg['mode'] = 'merge'",
        "providers_cfg = models_cfg.setdefault('providers', {})",
        "ollama_base = 'http://127.0.0.1:11434/v1'",
        "ollama_model = (os.environ.get('OLLAMA_DEFAULT') or '').strip()",
        "ollama_models = _load_models('/tmp/ollama-models.json')",
        "if ollama_model and all(str(item.get('id') or '').strip() != ollama_model for item in ollama_models):",
        "  ollama_models.append({'id': ollama_model, 'name': ollama_model, 'contextWindow': 16384, 'maxTokens': 4096})",
        "if ollama_models:",
        "  providers_cfg['ollama'] = {",
        "    'baseUrl': ollama_base,",
        "    'api': 'openai-completions',",
        "    'apiKey': os.environ.get('OLLAMA_API_KEY') or 'ollama-local',",
        "    'models': [_make_model_entry(item) for item in ollama_models],",
        "  }",
        "  for item in ollama_models:",
        "    mid = str(item.get('id') or '').strip()",
        "    if mid:",
        "      catalog_cfg[f'ollama/{mid.lower()}'] = {'alias': str(item.get('name') or mid)}",
        "else:",
        "  providers_cfg.pop('ollama', None)",
        "  for key in [k for k in list(catalog_cfg.keys()) if str(k).startswith('ollama/')]:",
        "    catalog_cfg.pop(key, None)",
        "lmstudio_base = (os.environ.get('LMSTUDIO_API_BASE') or '').strip()",
        "lmstudio_model = (os.environ.get('LMSTUDIO_DEFAULT') or '').strip()",
        "lmstudio_models = _load_models('/tmp/lmstudio-models.json')",
        "if lmstudio_model and all(str(item.get('id') or '').strip() != lmstudio_model for item in lmstudio_models):",
        "  lmstudio_models.append({'id': lmstudio_model, 'name': lmstudio_model, 'contextWindow': 16384, 'maxTokens': 4096})",
        "if lmstudio_base and lmstudio_models:",
        "  providers_cfg['lmstudio'] = {",
        "    'baseUrl': lmstudio_base,",
        "    'apiKey': os.environ.get('LMSTUDIO_API_KEY') or 'lmstudio-local',",
        "    'api': 'openai-responses',",
        "    'models': [_make_model_entry(mid) for mid in lmstudio_models],",
        "  }",
        "  for mid in lmstudio_models:",
        "    catalog_cfg[f'lmstudio/{mid.lower()}'] = {'alias': mid}",
        "else:",
        "  providers_cfg.pop('lmstudio', None)",
        "  for key in [k for k in list(catalog_cfg.keys()) if str(k).startswith('lmstudio/')]:",
        "    catalog_cfg.pop(key, None)",
        "# Repair any existing cloud provider entries missing baseUrl",
        "cloud_base_urls = {'openai': 'https://api.openai.com/v1', 'anthropic': 'https://api.anthropic.com/v1'}",
        "for pname, pconf in list(providers_cfg.items()):",
        "  if isinstance(pconf, dict) and not pconf.get('baseUrl') and pname in cloud_base_urls:",
        "    pconf['baseUrl'] = cloud_base_urls[pname]",
        "    print(f'Repaired missing baseUrl for {pname} provider')",
        "if not providers_cfg:",
        "  models_cfg.pop('providers', None)",
        "if not catalog_cfg:",
        "  defaults.pop('models', None)",
        "if model and provider in ('ollama', 'lmstudio'):",
        "  settings['model'] = f'{provider}/{model}'",
        "  settings['provider'] = provider",
        "  model_cfg['primary'] = f'{provider}/{model}'",
        "elif provider in ('openai', 'anthropic'):",
        "  settings['provider'] = provider",
        "  model_cfg['primary'] = defaults.get('model', {}).get('primary') or ''",
        "  if not model_cfg['primary'] and provider == 'openai':",
        "    model_cfg['primary'] = 'openai/gpt-4.1-mini'",
        "  if not model_cfg['primary'] and provider == 'anthropic':",
        "    model_cfg['primary'] = 'anthropic/claude-sonnet-4-5'",
        "(agent_dir / 'settings.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')",
        "cfg_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')",
        "print('Agent settings written:', settings.get('model', '(unchanged)'))",
        "print('Configured primary model:', model_cfg.get('primary', '(unset)'))",
        "PYEOF",
        "echo '--- OpenClaw config snapshot (before gateway start) ---'",
        "python3 - << 'PYEOF'",
        "import json, pathlib",
        "for path in [",
        "  pathlib.Path('/root/.openclaw/openclaw.json'),",
        "  pathlib.Path('/root/.openclaw/agents/main/agent/auth-profiles.json'),",
        "  pathlib.Path('/root/.openclaw/agents/main/agent/settings.json'),",
        "]:",
        "  print(f'FILE: {path}')",
        "  if path.exists():",
        "    try:",
        "      print(json.dumps(json.loads(path.read_text(encoding='utf-8')), indent=2))",
        "    except Exception as exc:",
        "      print(f'(unreadable json: {exc})')",
        "      print(path.read_text(encoding='utf-8', errors='ignore'))",
        "  else:",
        "    print('(missing)')",
        "PYEOF",
        "",
        "# Check env from entrypoint perspective",
        "echo 'Checking env vars visible to openclaw:'",
        "openclaw doctor 2>&1 | head -20 || true",
        "echo 'OpenClaw version:'",
        "openclaw --version 2>&1 || true",
        "",
        "# Generate SSL cert with SANs for localhost and the configured host IP.",
        "mkdir -p /root/.openclaw/certs",
        "CERT_HOST_IP=${OPENCLAW_HOST_IP:-127.0.0.1}",
        "cat > /tmp/openclaw-cert.cnf << CERTCONF",
        "[req]",
        "distinguished_name = req_distinguished_name",
        "x509_extensions = v3_req",
        "prompt = no",
        "[req_distinguished_name]",
        "CN = openclaw",
        "O = ServerInstaller",
        "[v3_req]",
        "subjectAltName = @alt_names",
        "[alt_names]",
        "DNS.1 = localhost",
        "DNS.2 = openclaw",
        "IP.1 = 127.0.0.1",
        "IP.2 = $CERT_HOST_IP",
        "CERTCONF",
        "openssl req -x509 -nodes -newkey rsa:2048 -keyout /root/.openclaw/certs/key.pem -out /root/.openclaw/certs/cert.pem -days 3650 -config /tmp/openclaw-cert.cnf -extensions v3_req 2>/dev/null",
        "echo '--- HTTPS certificate summary ---'",
        "openssl x509 -in /root/.openclaw/certs/cert.pem -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null || true",
        "",
        f"# Start gateway with OLLAMA_API_KEY",
        f"echo '{gw_internal_port}' > /tmp/gw_port",
        "# Use a Node.js wrapper to inject OLLAMA_API_KEY directly into process.env",
        "# This bypasses any env var inheritance issues",
        f"cat > /tmp/start-gw.js << 'NODEEOF'",
        "process.env.OLLAMA_API_KEY = 'ollama-local';",
        "console.log('Node.js OLLAMA_API_KEY:', process.env.OLLAMA_API_KEY);",
        "const { execFileSync, spawn } = require('child_process');",
        "// Find openclaw binary path",
        "const bin = execFileSync('which', ['openclaw']).toString().trim();",
        "console.log('OpenClaw binary:', bin);",
        "// Spawn gateway as child with env inherited",
        f"const child = spawn(bin, ['gateway', '--allow-unconfigured', '--port', '{gw_internal_port}', '--verbose'], {{",
        "  stdio: 'inherit',",
        "  env: { ...process.env, OLLAMA_API_KEY: 'ollama-local' }",
        "});",
        "child.on('exit', (code) => process.exit(code || 0));",
        "NODEEOF",
        "node /tmp/start-gw.js &",
        "GW_PID=$!",
        "sleep 5",
        "echo 'Gateway process list after startup:'",
        "if command -v ps >/dev/null 2>&1; then ps aux | grep -E 'openclaw|node /tmp/start-gw.js' | grep -v grep || true; else echo 'ps not installed in container'; fi",
        "",
        "# Configure agent to use local Ollama as default AI",
        "echo \"Configuring agent to use Ollama model: ${OPENCLAW_MODEL:-auto}\"",
        "",
        "# Resolve Ollama API URL for auth-profiles.json",
        "# OpenClaw needs the DIRECT Ollama API (port 11434), NOT the web UI proxy",
        "# From inside Docker, use host.docker.internal to reach Ollama on the host",
        "OLLAMA_API_URL=''",
        "# Test direct Ollama API via host.docker.internal first",
        "if curl -sf http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then",
        "  OLLAMA_API_URL='http://host.docker.internal:11434'",
        "  echo \"Ollama API found at: $OLLAMA_API_URL\"",
        "# Test localhost (Ollama installed inside this container)",
        "elif curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then",
        "  OLLAMA_API_URL='http://127.0.0.1:11434'",
        "  echo \"Ollama API found at: $OLLAMA_API_URL\"",
        "else",
        "  # Fall back to user-provided URL but try to extract the Ollama API port",
        "  OLLAMA_API_URL=${OLLAMA_HOST:-http://127.0.0.1:11434}",
        "  echo \"Using configured Ollama URL: $OLLAMA_API_URL (may be web UI, not direct API)\"",
        "fi",
        "",
        "# Keep remote.token aligned with auth.token so browser #token URLs work",
        "GATEWAY_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null || true)",
        "if [ -n \"$GATEWAY_TOKEN\" ]; then",
        "  openclaw config set gateway.remote.token \"$GATEWAY_TOKEN\" 2>/dev/null || true",
        "fi",
        "",
        "# Get gateway auth token and print dashboard URL with token",
        "GATEWAY_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null || true)",
        f'echo "============================================="',
        "if [ -n \"$GATEWAY_TOKEN\" ]; then",
        (
            f'  echo "DASHBOARD URL (https): https://YOUR_IP:{https_port}/?gatewayUrl=wss://YOUR_IP:{https_port}#token=$GATEWAY_TOKEN"'
            if https_port else
            '  echo "DASHBOARD URL (https): (disabled)"'
        ),
        f'  echo "DASHBOARD URL (http):  http://YOUR_IP:{http_port}/?gatewayUrl=ws://YOUR_IP:{http_port}#token=$GATEWAY_TOKEN"',
        "else",
        (
            f'  echo "DASHBOARD URL (https): https://YOUR_IP:{https_port}/"'
            if https_port else
            '  echo "DASHBOARD URL (https): (disabled)"'
        ),
        f'  echo "DASHBOARD URL (http):  http://YOUR_IP:{http_port}/"',
        "fi",
        (
            'echo "NOTE: For remote browsers, use the HTTPS dashboard URL. HTTP only works reliably on localhost because OpenClaw requires a secure browser context."'
            if https_port else
            'echo "NOTE: Remote HTTP dashboard access can be blocked by browser secure-context rules. Prefer localhost or enable HTTPS."'
        ),
        f'echo "Ollama API: $OLLAMA_API_URL"',
        f'echo "Select your model in OpenClaw dashboard: Settings > AI & Agents"',
        f'echo "============================================="',
        "",
        "# Test direct gateway access (no proxy) to diagnose 500 errors",
        f'echo "=== Direct gateway test on port {gw_internal_port} (no proxy) ==="',
        f"GW_HTTP_CODE=$(curl -s -o /tmp/gw-root-body.txt -w '%{{http_code}}' http://127.0.0.1:{gw_internal_port}/ 2>/tmp/gw-root-curl.err || echo '000')",
        'echo "Direct gateway status: $GW_HTTP_CODE"',
        'GW_HOST="${OPENCLAW_HOST_IP:-127.0.0.1}"',
        f'GW_HOST_TEST_CODE=$(curl -s -o /tmp/gw-host-body.txt -w \'%{{http_code}}\' -H "Host: $GW_HOST:{http_port}" http://127.0.0.1:{gw_internal_port}/ 2>/tmp/gw-host-curl.err || echo "000")',
        'echo "Direct gateway status with forwarded Host header: $GW_HOST_TEST_CODE"',
        f'GW_ORIGIN_TEST_CODE=$(curl -s -o /tmp/gw-origin-body.txt -w \'%{{http_code}}\' -H "Host: $GW_HOST:{http_port}" -H "Origin: http://$GW_HOST:{http_port}" http://127.0.0.1:{gw_internal_port}/ 2>/tmp/gw-origin-curl.err || echo "000")',
        'echo "Direct gateway status with forwarded Host + Origin headers: $GW_ORIGIN_TEST_CODE"',
        "if [ -f /tmp/gw-host-body.txt ]; then",
        "  echo '--- Direct gateway (forwarded Host) body (first 40 lines) ---'",
        "  head -40 /tmp/gw-host-body.txt 2>/dev/null || true",
        "fi",
        "if [ -f /tmp/gw-origin-body.txt ]; then",
        "  echo '--- Direct gateway (forwarded Host + Origin) body (first 40 lines) ---'",
        "  head -40 /tmp/gw-origin-body.txt 2>/dev/null || true",
        "fi",
        'if [ "$GW_HTTP_CODE" != "200" ]; then',
        "  echo '--- Direct gateway body (first 80 lines) ---'",
        "  head -80 /tmp/gw-root-body.txt 2>/dev/null || true",
        "  echo '--- Direct gateway curl stderr ---'",
        "  head -40 /tmp/gw-root-curl.err 2>/dev/null || true",
        "  echo '--- Direct gateway Host+Origin curl stderr ---'",
        "  head -40 /tmp/gw-origin-curl.err 2>/dev/null || true",
        "  echo '--- Recent OpenClaw gateway log ---'",
        "  tail -120 /tmp/openclaw/openclaw-$(date +%F).log 2>/dev/null || true",
        "fi",
        f'echo "=== Direct gateway response headers ==="',
        f"curl -sI http://127.0.0.1:{gw_internal_port}/ 2>&1 | head -15 || echo 'Direct headers test failed'",
        "",
        "# Public nginx wrapper: proxy the Control UI + WebSocket directly.",
        "# The browser gets gatewayUrl in the query string and token in #fragment,",
        "# matching the current OpenClaw Control UI docs.",
        "nginx -s stop 2>/dev/null || true",
        "cat > /tmp/openclaw-public-nginx.conf << 'NGINXEOF'",
        "worker_processes 1;",
        "events { worker_connections 1024; }",
        "http {",
        "  map $http_upgrade $connection_upgrade {",
        "    default upgrade;",
        "    '' close;",
        "  }",
        "  server {",
        f"    listen {http_port};",
        "    server_name _;",
        "    location / {",
        "      proxy_http_version 1.1;",
        "      proxy_set_header Host $host;",
        "      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "      proxy_set_header X-Real-IP $remote_addr;",
        "      proxy_set_header X-Forwarded-Proto $scheme;",
        "      proxy_set_header Upgrade $http_upgrade;",
        "      proxy_set_header Connection $connection_upgrade;",
        f"      proxy_pass http://127.0.0.1:{gw_internal_port}/;",
        "    }",
        "  }",
        f'  {"server { listen " + https_port + " ssl; server_name _; ssl_certificate /root/.openclaw/certs/cert.pem; ssl_certificate_key /root/.openclaw/certs/key.pem; location / { proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection $connection_upgrade; proxy_pass http://127.0.0.1:" + gw_internal_port + "/; } }" if https_port else ""}',
        "}",
        "NGINXEOF",
        'echo "Starting nginx public wrapper..."',
        "nginx -c /tmp/openclaw-public-nginx.conf &",
        "PUBLIC_NGINX_PID=$!",
        "sleep 2",
        f"echo 'Testing HTTP port {http_port}...'",
        f"curl -sI http://127.0.0.1:{http_port}/ 2>&1 | head -10 || echo 'HTTP curl test failed'",
        f'if [ -n "{https_port}" ]; then',
        f"  echo 'Testing HTTPS port {https_port}...'",
        f"  curl -skI https://127.0.0.1:{https_port}/ 2>&1 | head -10 || echo 'HTTPS curl test failed'",
        f"  echo 'HTTPS certificate presented on port {https_port}:'",
        f"  echo | openssl s_client -connect 127.0.0.1:{https_port} -servername localhost 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null || true",
        "fi",
        "",
        "wait $GW_PID",
    ]
    Path(build_dir, "entrypoint.sh").write_text("\n".join(entrypoint_lines) + "\n", encoding="utf-8")

    expose_lines = f"EXPOSE {http_port}\n"
    if https_port:
        expose_lines += f"EXPOSE {https_port}\n"

    dockerfile = f"""FROM node:24-bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl python3 build-essential socat openssl nginx zstd git && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally.
# Pin to a known-good release because newer builds have regressed Docker control UI startup.
RUN npm install -g openclaw@2026.2.3 @aws-sdk/client-bedrock @aws-sdk/client-bedrock-runtime

# Pre-create config dir
RUN mkdir -p /root/.openclaw

# Gateway port and Ollama provider
ENV OPENCLAW_PORT={http_port}
ENV OLLAMA_API_KEY=ollama-local
{expose_lines.rstrip()}

COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /app/nginx.conf
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
    if https_port:
        docker_cmd += ["-p", f"{https_port}:{https_port}"]
    # Pass channel tokens, LLM config, and Ollama API key as env vars
    env_map = {
        "OLLAMA_API_KEY": "ollama-local",
        "OPENCLAW_HOST_IP": host,
        "OPENCLAW_HOST_AVAILABLE_BYTES": str(host_available_bytes) if host_available_bytes else "",
        "OPENCLAW_LLM_PROVIDER": llm_provider,
        "OPENCLAW_OLLAMA_URL": ollama_url,
        "OPENCLAW_LMSTUDIO_URL": lmstudio_url,
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
        "http_url": http_url,
        "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "gateway_token": "",
        "running": code2 == 0,
    })
    _write_json_file(OPENCLAW_STATE_FILE, state)
    manage_firewall_port("open", http_port, "tcp")
    if https_port:
        manage_firewall_port("open", https_port, "tcp")

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

    # Also install the model on host Ollama if available
    if not ollama_url and command_exists("ollama"):
        log(f"\nInstalling model {llm_model} on host Ollama...")
        try:
            _run_install_cmd(["ollama", "pull", llm_model], log, timeout=600)
        except Exception:
            log("Model pull on host skipped.")

    log("\n" + "=" * 60)
    log(" OpenClaw Docker Deployment Complete!")
    log("=" * 60)
    if https_port:
        log(f" HTTPS Dashboard: https://{display_host}:{https_port}/")
        log(f" HTTP Dashboard:  http://{display_host}:{http_port}/")
        log(" NOTE: Use HTTPS for remote browser access. HTTP is only reliable on localhost because OpenClaw requires a secure browser context.")
        log(" NOTE: HTTPS uses a self-signed cert; browser warning is expected.")
    else:
        log(f" HTTP Dashboard:  http://{display_host}:{http_port}/")
    log(f"")
    # Try to get the gateway token from container (read JSON directly since CLI redacts)
    gateway_token = ""
    try:
        import time as _t
        _t.sleep(2)
        rc, tok = run_capture([
            "docker", "exec", container_name, "python3", "-c",
            "import json; c=json.load(open('/root/.openclaw/openclaw.json')); print(c.get('gateway',{}).get('auth',{}).get('token',''))"
        ], timeout=10)
        if rc == 0 and tok.strip() and "REDACTED" not in tok.upper():
            gateway_token = tok.strip()
    except Exception:
        pass
    if not gateway_token:
        try:
            rc, tok = run_capture(["docker", "exec", container_name, "openclaw", "config", "get", "gateway.auth.token"], timeout=10)
            if rc == 0 and tok.strip() and "REDACTED" not in tok.upper():
                gateway_token = tok.strip()
        except Exception:
            pass
    if gateway_token:
        state = _read_json_file(OPENCLAW_STATE_FILE)
        state["gateway_token"] = gateway_token
        _write_json_file(OPENCLAW_STATE_FILE, state)
        if https_port:
            log(f" Dashboard URL (open this in your browser):")
            log(f"   https://{display_host}:{https_port}/?gatewayUrl=wss://{display_host}:{https_port}#token={gateway_token}")
            log(f"   http://{display_host}:{http_port}/?gatewayUrl=ws://{display_host}:{http_port}#token={gateway_token}")
            log(" Use the HTTPS URL from another machine. HTTP will fail OpenClaw's secure-context check.")
            log(" Remote browsers may require one-time pairing approval: openclaw devices list && openclaw devices approve --latest")
        else:
            log(f" Dashboard URL (open this in your browser):")
            log(f"   http://{display_host}:{http_port}/?gatewayUrl=ws://{display_host}:{http_port}#token={gateway_token}")
        log(f"")
        log(f" Gateway Token:  {gateway_token}")
    else:
        # Gateway generated no token yet; print URLs without token hint
        log(f" Dashboard URL:")
        log(f"   http://{display_host}:{http_port}/")
        if https_port:
            log(f"   https://{display_host}:{https_port}/")
        log(f"")
        log(f" Gateway Token:  (auto-generated by OpenClaw when needed)")
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
    # If neither port specified, default HTTP to 11434
    if not http_port and not https_port:
        http_port = "11434"
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log("=== Installing Ollama via Docker ===")
    docker_code, docker_message = _ensure_docker_ready(log)
    if docker_code != 0:
        log(docker_message)
        return docker_code, "\n".join(output)
    ok, image_error = _docker_image_platform_supported("ollama/ollama:latest")
    if not ok:
        log(image_error)
        return 1, "\n".join(output)

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
    expose_list = []
    if http_port:
        expose_list.append(http_port)
    if https_port and https_port != http_port:
        expose_list.append(https_port)
    expose_ports = " ".join(expose_list) if expose_list else "11434"
    dockerfile = f"""FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir flask requests
ENV OLLAMA_API_BASE=http://{ollama_ip}:11434
ENV OLLAMA_DEPLOY_MODE=docker
ENV OLLAMA_HOST_OS={sys.platform}
ENV OLLAMA_WEBUI_PORT={http_port}
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
        fallback_port = http_port or https_port or "11434"
        cmd_fallback = ["docker", "run", "-d", "--name", "serverinstaller-ollama",
                        "-p", f"{fallback_port}:11434", "-v", "ollama-data:/root/.ollama",
                        "--restart", "unless-stopped", "ollama/ollama:latest"]
        _run_install_cmd(cmd_fallback, log, timeout=300)
    else:
        # Run web UI container linked to Ollama
        webui_cmd = ["docker", "run", "-d", "--name", "serverinstaller-ollama-webui",
                     "--link", "serverinstaller-ollama:ollama",
                     "-e", f"OLLAMA_API_BASE=http://serverinstaller-ollama:11434",
                     "-e", "OLLAMA_DEPLOY_MODE=docker",
                     "-e", f"OLLAMA_HOST_OS={sys.platform}",
                     "-e", f"OLLAMA_WEBUI_PORT={http_port}",
                     "-e", f"OLLAMA_HTTPS_PORT={https_port}",
                     "-e", f"OLLAMA_AUTH_USERNAME={username}",
                     "-e", f"OLLAMA_AUTH_PASSWORD={password}",
                     "--restart", "unless-stopped"]
        if http_port:
            webui_cmd += ["-p", f"{http_port}:{http_port}"]
        if https_port and https_port != http_port:
            webui_cmd += ["-p", f"{https_port}:{https_port}"]
        webui_cmd.append("serverinstaller/ollama-webui:latest")
        code3 = _run_install_cmd(webui_cmd, log, timeout=60)
        if code3 != 0:
            log("Web UI container failed to start.")

    # Save state
    OLLAMA_STATE_DIR.mkdir(parents=True, exist_ok=True)
    display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
    http_url = f"http://{display_host}:{http_port}" if http_port else ""
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    primary_port = http_port or https_port
    state = _read_json_file(OLLAMA_STATE_FILE)
    state.update({
        "installed": True, "service_name": "serverinstaller-ollama",
        "deploy_mode": "docker", "host": host,
        "http_port": http_port, "https_port": https_port,
        "http_url": http_url,
        "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "running": True,
    })
    _write_json_file(OLLAMA_STATE_FILE, state)
    if http_port:
        manage_firewall_port("open", http_port, "tcp")
    if https_port and https_port != http_port:
        manage_firewall_port("open", https_port, "tcp")

    # Show results
    log("\n" + "=" * 60)
    log(" Ollama Docker Deployment Complete!")
    log("=" * 60)
    if http_url:
        log(f" Web UI (HTTP):  {http_url}")
    if https_url:
        log(f" Web UI (HTTPS): {https_url}")
    if not http_url and not https_url:
        log(f" Web UI:         http://{display_host}:{primary_port}")
    if username:
        log(f" Auth:           {username} / ****")
    api_port = http_port or https_port
    api_proto = "http" if http_port else "https"
    log(f" Ollama API:     {api_proto}://{display_host}:{api_port}/api/tags")
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
    # If neither port specified, default HTTP to 1234 (LM Studio native default)
    if not http_port and not https_port:
        http_port = "1234"
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

    docker_code, docker_message = _ensure_docker_ready(log)
    if docker_code != 0:
        log(docker_message)
        return docker_code, "\n".join(output)

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
    expose_list = []
    if http_port:
        expose_list.append(http_port)
    if https_port and https_port != http_port:
        expose_list.append(https_port)
    expose_ports = " ".join(expose_list) if expose_list else "1234"
    dockerfile = f"""FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir flask requests
ENV LMSTUDIO_API_BASE={lms_api_base}
ENV LMSTUDIO_WEB_PORT={http_port}
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
                 "--add-host", "host.docker.internal:host-gateway",
                 "-e", f"LMSTUDIO_API_BASE={lms_api_base}",
                 "-e", f"LMSTUDIO_WEB_PORT={http_port}",
                 "-e", f"LMSTUDIO_HTTPS_PORT={https_port}",
                 "-e", f"LMSTUDIO_AUTH_USERNAME={username}",
                 "-e", f"LMSTUDIO_AUTH_PASSWORD={password}",
                 "--restart", "unless-stopped"]
    if http_port:
        webui_cmd += ["-p", f"{http_port}:{http_port}"]
    if https_port and https_port != http_port:
        webui_cmd += ["-p", f"{https_port}:{https_port}"]
    webui_cmd.append("serverinstaller/lmstudio-webui:latest")
    code2 = _run_install_cmd(webui_cmd, log, timeout=60)

    # Save state
    LMSTUDIO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    display_host = host if host not in ("0.0.0.0", "*", "") else choose_service_host()
    http_url = f"http://{display_host}:{http_port}" if http_port else ""
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    state = _read_json_file(LMSTUDIO_STATE_FILE)
    state.update({
        "installed": True, "service_name": "serverinstaller-lmstudio-webui",
        "deploy_mode": "docker", "host": host,
        "http_port": http_port, "https_port": https_port,
        "http_url": http_url, "https_url": https_url,
        "auth_enabled": bool(username), "auth_username": username,
        "running": code2 == 0,
    })
    _write_json_file(LMSTUDIO_STATE_FILE, state)
    if http_port:
        manage_firewall_port("open", http_port, "tcp")
    if https_port and https_port != http_port:
        manage_firewall_port("open", https_port, "tcp")

    log("\n" + "=" * 60)
    log(" LM Studio Web UI Docker Deployment Complete!")
    log("=" * 60)
    if http_url:
        log(f" Web UI (HTTP):  {http_url}")
    if https_url:
        log(f" Web UI (HTTPS): {https_url}")
    if not http_url and not https_url:
        log(f" Web UI:         http://{display_host}:{http_port or https_port}")
    log(f" LM Studio API:  http://localhost:1234 (on host)")
    if username:
        log(f" Auth:           {username} / ****")
    log(" Note: Start the local server in LM Studio desktop app")
    log("=" * 60)
    return code2, "\n".join(output)


def _run_ai_docker_generic(
    service_id,
    image,
    form,
    default_port,
    container_port,
    display_name,
    state_file,
    state_dir,
    live_cb=None,
    extra_args=None,
    extra_env=None,
    extra_volumes=None,
    extra_command=None,
    gpu_mode="auto",
    gpu_image="",
    post_start_exec=None,
):
    """Deploy an AI service behind a managed Caddy proxy with optional auth and HTTPS."""
    form = form or {}
    sid = str(service_id or "").strip().lower()
    http_port = (form.get(f"{sid.upper()}_HTTP_PORT", [default_port])[0] or "").strip()
    https_port = (form.get(f"{sid.upper()}_HTTPS_PORT", [""])[0] or "").strip()
    if not http_port and not https_port:
        http_port = str(default_port or "").strip()
    if not http_port and not https_port:
        return 1, "At least one of HTTP Port or HTTPS Port must be specified."
    host = (form.get(f"{sid.upper()}_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
    domain = (form.get(f"{sid.upper()}_DOMAIN", [""])[0] or "").strip()
    username = (form.get(f"{sid.upper()}_USERNAME", [""])[0] or "").strip()
    password = (form.get(f"{sid.upper()}_PASSWORD", [""])[0] or "").strip()
    output = []

    def log(message):
        output.append(message)
        if live_cb:
            live_cb(message + "\n")

    log(f"=== Installing {display_name} via Docker ===")
    docker_code, docker_message = _ensure_docker_ready(log)
    if docker_code != 0:
        log(docker_message)
        return docker_code, "\n".join(output)
    ok, image_error = _docker_image_platform_supported(image)
    if not ok:
        log(image_error)
        return 1, "\n".join(output)

    state_dir.mkdir(parents=True, exist_ok=True)
    proxy_dir = state_dir / "proxy"
    container_name = f"serverinstaller-{sid}"
    proxy_name = f"{container_name}-proxy"
    network_name = f"{container_name}-net"
    _remove_ai_docker_artifacts(sid)
    run_capture(["docker", "network", "create", network_name], timeout=30)

    runtime_cmd = ["docker", "run", "-d", "--name", container_name, "--network", network_name, "--restart", "unless-stopped"]
    runtime_cmd += ["--label", f"serverinstaller.scope={sid}"]

    runtime_supports_nvidia = False
    try:
        rc, out = run_capture(["docker", "info", "--format", "{{.Runtimes}}"], timeout=10)
        runtime_supports_nvidia = "nvidia" in str(out).lower()
    except Exception:
        runtime_supports_nvidia = False
    if gpu_mode in ("auto", "nvidia", "optional-nvidia") and runtime_supports_nvidia:
        runtime_cmd += ["--gpus", "all"]
        log("NVIDIA GPU runtime detected.")
    elif gpu_mode in ("nvidia",) and not runtime_supports_nvidia:
        log("NVIDIA GPU runtime not detected. Continuing without GPU passthrough.")
    effective_image = image
    if gpu_mode == "optional-nvidia" and runtime_supports_nvidia and gpu_image:
        effective_image = gpu_image

    for arg in extra_args or []:
        runtime_cmd.append(arg)
    for env_item in extra_env or []:
        runtime_cmd += ["-e", env_item]
    for volume in extra_volumes or []:
        runtime_cmd += ["-v", volume]
    runtime_cmd.append(effective_image)
    if extra_command:
        runtime_cmd += [str(x) for x in extra_command]
    log(f"Running service container: {' '.join(runtime_cmd)}")
    code = _run_install_cmd(runtime_cmd, log, timeout=1800)
    if code != 0:
        friendly = _friendly_docker_image_error(effective_image, "\n".join(output))
        if friendly and friendly not in "\n".join(output):
            log(friendly)
        _remove_ai_docker_artifacts(sid)
        return code, "\n".join(output)

    for exec_cmd in post_start_exec or []:
        resolved = [str(x) for x in exec_cmd]
        log(f"Post-start: docker exec {container_name} {' '.join(resolved)}")
        rc, out = run_capture(["docker", "exec", container_name] + resolved, timeout=1800)
        if rc != 0:
            log(out or "Post-start command failed.")
            _remove_ai_docker_artifacts(sid)
            return rc or 1, "\n".join(output)
        if out:
            log(out.strip())

    password_hash = ""
    if username and password:
        try:
            password_hash = _docker_password_hash(password)
        except Exception as ex:
            _remove_ai_docker_artifacts(sid)
            return 1, f"Failed to configure HTTP auth: {ex}"
    elif username or password:
        _remove_ai_docker_artifacts(sid)
        return 1, "Both username and password are required when enabling auth."

    _write_ai_proxy_caddyfile(
        proxy_dir=proxy_dir,
        upstream_name=container_name,
        upstream_port=str(container_port),
        http_enabled=bool(http_port),
        https_enabled=bool(https_port),
        username=username,
        password_hash=password_hash,
    )

    proxy_cmd = [
        "docker", "run", "-d",
        "--name", proxy_name,
        "--network", network_name,
        "--restart", "unless-stopped",
        "-v", f"{str((proxy_dir / 'Caddyfile').resolve())}:/etc/caddy/Caddyfile:ro",
        "-v", f"{str((proxy_dir / 'data').resolve())}:/data",
        "-v", f"{str((proxy_dir / 'config').resolve())}:/config",
        "--label", f"serverinstaller.scope={sid}",
    ]
    if http_port:
        proxy_cmd += ["-p", f"{http_port}:80"]
    if https_port:
        proxy_cmd += ["-p", f"{https_port}:443"]
    proxy_cmd.append("caddy:2-alpine")
    log(f"Running proxy container: {' '.join(proxy_cmd)}")
    code2 = _run_install_cmd(proxy_cmd, log, timeout=300)
    if code2 != 0:
        _remove_ai_docker_artifacts(sid)
        return code2, "\n".join(output)

    display_host = domain or (host if host not in ("0.0.0.0", "*", "") else choose_service_host())
    http_url = f"http://{display_host}:{http_port}" if http_port else ""
    https_url = f"https://{display_host}:{https_port}" if https_port else ""
    state = _read_json_file(state_file)
    state.update({
        "installed": True,
        "service_name": container_name,
        "proxy_service_name": proxy_name,
        "proxy_enabled": True,
        "deploy_mode": "docker",
        "host": host,
        "domain": domain,
        "http_port": http_port,
        "https_port": https_port,
        "http_url": http_url,
        "https_url": https_url,
        "auth_enabled": bool(username),
        "auth_username": username,
        "running": True,
        "container_port": str(container_port),
    })
    _write_json_file(state_file, state)
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=display_host)
    if https_port and https_port != http_port:
        manage_firewall_port("open", https_port, "tcp", host=display_host)

    log("\n" + "=" * 60)
    log(f" {display_name} Docker Deployment Complete!")
    log("=" * 60)
    if http_url:
        log(f" HTTP URL:   {http_url}")
    if https_url:
        log(f" HTTPS URL:  {https_url}")
        log(" HTTPS is provided by an internal Caddy certificate.")
    if username:
        log(f" Auth user:  {username}")
    log(f" Service:    {container_name}")
    log(f" Proxy:      {proxy_name}")
    log("=" * 60)
    return 0, "\n".join(output)


def run_tgwui_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("tgwui", "atinoda/text-generation-webui:default-nightly", form, "7860", "7860", "Text Generation WebUI", TGWUI_STATE_FILE, TGWUI_STATE_DIR, live_cb)

def run_comfyui_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("comfyui", "yanwk/comfyui-boot:latest", form, "8188", "8188", "ComfyUI", COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, live_cb)

def run_whisper_docker(form=None, live_cb=None):
    model = (form or {}).get("WHISPER_MODEL_SIZE", ["base"])
    model_size = model[0] if isinstance(model, list) else model
    return _run_ai_docker_generic("whisper", "onerahmet/openai-whisper-asr-webservice:latest", form, "9000", "9000", "Whisper STT",
        WHISPER_STATE_FILE, WHISPER_STATE_DIR, live_cb, extra_env=[f"ASR_MODEL={model_size}"])

def run_piper_docker(form=None, live_cb=None):
    return _run_ai_docker_generic("piper", "rhasspy/wyoming-piper:latest", form, "5500", "10200", "Piper TTS", PIPER_STATE_FILE, PIPER_STATE_DIR, live_cb,
        extra_volumes=["piper-data:/data"], extra_env=["PIPER_VOICE=en_US-lessac-medium"])


def get_generic_ai_info(service_id):
    cfg = get_generic_ai_service(service_id)
    state_file, state_dir = _generic_ai_state_paths(cfg["service_id"])
    info = _get_ai_service_info(
        state_file,
        state_dir,
        f"serverinstaller-{cfg['service_id']}",
        cfg["display_name"],
        cfg["default_port"],
    )
    model_field = cfg.get("model_field")
    state = _read_json_file(state_file)
    if model_field:
        info["model_name"] = str(state.get(model_field.lower()) or state.get("model_name") or cfg.get("default_model") or "").strip()
    return info


def run_generic_ai_docker(service_id, form=None, live_cb=None):
    cfg = get_generic_ai_service(service_id)
    if not cfg.get("image"):
        return 1, f"No supported Docker image is configured for {cfg['display_name']}."
    form = form or {}
    model_value = ""
    if cfg.get("model_field"):
        model_value = (form.get(cfg["model_field"], [cfg.get("default_model", "")])[0] or cfg.get("default_model", "")).strip()
    command = deepcopy(cfg.get("docker_command") or [])
    command = [str(item).replace("{model}", model_value) for item in command]
    post_start_exec = deepcopy(cfg.get("post_start_exec") or [])
    resolved_post_start = []
    for entry in post_start_exec:
        resolved_post_start.append([str(item).replace("{model}", model_value) for item in entry])
    state_file, state_dir = _generic_ai_state_paths(cfg["service_id"])
    code, output = _run_ai_docker_generic(
        service_id=cfg["service_id"],
        image=cfg["image"],
        form=form,
        default_port=cfg["default_port"],
        container_port=cfg["container_port"],
        display_name=cfg["display_name"],
        state_file=state_file,
        state_dir=state_dir,
        live_cb=live_cb,
        extra_args=cfg.get("docker_args"),
        extra_env=cfg.get("docker_env"),
        extra_volumes=cfg.get("docker_volumes"),
        extra_command=command,
        gpu_mode=cfg.get("gpu_runtime", "auto"),
        gpu_image=cfg.get("gpu_image", ""),
        post_start_exec=resolved_post_start,
    )
    if code == 0 and model_value:
        state = _read_json_file(state_file)
        state[cfg["model_field"].lower()] = model_value
        state["model_name"] = model_value
        _write_json_file(state_file, state)
    return code, output


def run_generic_ai_delete(service_id, live_cb=None):
    cfg = get_generic_ai_service(service_id)
    state_file, state_dir = _generic_ai_state_paths(cfg["service_id"])
    return _run_ai_service_delete(
        cfg["service_id"],
        cfg["display_name"],
        state_file,
        state_dir,
        f"serverinstaller-{cfg['service_id']}",
        live_cb=live_cb,
    )


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


def _run_ai_service_delete(service_id, display_name, state_file, state_dir, systemd_service, container_name=None, live_cb=None):
    """Generic complete delete for AI services (Docker + OS + data + firewall)."""
    output = []
    def log(m):
        output.append(m)
        if live_cb: live_cb(m + "\n")
    log(f"=== Deleting {display_name} ===")

    state = _read_json_file(state_file)
    http_port = str(state.get("http_port") or "").strip()
    https_port = str(state.get("https_port") or "").strip()
    cname = container_name or f"serverinstaller-{service_id}"
    proxy_name = str(state.get("proxy_service_name") or f"{cname}-proxy").strip()
    network_name = f"{cname}-net"

    # Docker cleanup
    if command_exists("docker"):
        run_capture(["docker", "stop", proxy_name], timeout=30)
        rc_proxy, _ = run_capture(["docker", "rm", "-f", proxy_name], timeout=30)
        if rc_proxy == 0:
            log(f"Removed Docker proxy container: {proxy_name}")
        run_capture(["docker", "stop", cname], timeout=30)
        rc, _ = run_capture(["docker", "rm", "-f", cname], timeout=30)
        if rc == 0: log(f"Removed Docker container: {cname}")
        run_capture(["docker", "network", "rm", network_name], timeout=30)

    # Systemd cleanup
    if os.name != "nt" and command_exists("systemctl"):
        run_capture(["systemctl", "disable", systemd_service], timeout=15)
        run_capture(["systemctl", "stop", systemd_service], timeout=15)
        svc_file = Path(f"/etc/systemd/system/{systemd_service}.service")
        if svc_file.exists():
            svc_file.unlink()
            log(f"Removed systemd unit: {systemd_service}")
        run_capture(["systemctl", "daemon-reload"], timeout=15)
    elif os.name == "nt":
        task_name = f"ServerInstaller-{display_name.replace(' ', '')}"
        try:
            run_capture(["schtasks", "/Delete", "/TN", task_name, "/F"], timeout=15)
        except Exception: pass

    # Clean up data
    for subdir in ["app", "certs", "venv", "proxy"]:
        d = state_dir / subdir
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            log(f"Removed directory: {subdir}")
    if state_file.exists():
        state_file.unlink()
        log("Removed state file")

    for port in [http_port, https_port]:
        if port: manage_firewall_port("close", port, "tcp")

    log(f"=== {display_name} completely removed ===")
    return 0, "\n".join(output)


def run_tgwui_delete(live_cb=None):
    return _run_ai_service_delete("tgwui", "Text Generation WebUI", TGWUI_STATE_FILE, TGWUI_STATE_DIR, TGWUI_SYSTEMD_SERVICE, live_cb=live_cb)

def run_comfyui_delete(live_cb=None):
    return _run_ai_service_delete("comfyui", "ComfyUI", COMFYUI_STATE_FILE, COMFYUI_STATE_DIR, COMFYUI_SYSTEMD_SERVICE, live_cb=live_cb)

def run_whisper_delete(live_cb=None):
    return _run_ai_service_delete("whisper", "Whisper STT", WHISPER_STATE_FILE, WHISPER_STATE_DIR, WHISPER_SYSTEMD_SERVICE, live_cb=live_cb)

def run_piper_delete(live_cb=None):
    return _run_ai_service_delete("piper", "Piper TTS", PIPER_STATE_FILE, PIPER_STATE_DIR, PIPER_SYSTEMD_SERVICE, live_cb=live_cb)


def run_managed_ai_action(service_id, action, live_cb=None):
    return _run_managed_ai_docker_action(service_id, action, live_cb=live_cb)
