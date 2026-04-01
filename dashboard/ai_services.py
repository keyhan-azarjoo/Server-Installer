import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

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
from system_info import choose_service_host
from python_manager import _linux_systemd_unit_status
from port_manager import is_local_tcp_port_listening, manage_firewall_port
from website_manager import _docker_add_macos_path, _install_engine_docker, _run_install_cmd

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


def run_openclaw_docker(form=None, live_cb=None):
    """Deploy real OpenClaw gateway as a Docker container with Node.js."""
    form = form or {}
    http_port_raw = (form.get("OPENCLAW_HTTP_PORT", [""])[0] or "").strip()
    https_port_raw = (form.get("OPENCLAW_HTTPS_PORT", [""])[0] or "").strip()
    # Use HTTPS port as the exposed port if set; fall back to HTTP port or default
    if https_port_raw and https_port_raw.isdigit() and int(https_port_raw) > 0:
        http_port = https_port_raw  # Docker container serves HTTPS on this port via nginx
    elif http_port_raw and http_port_raw.isdigit() and int(http_port_raw) > 0:
        http_port = http_port_raw
    else:
        http_port = "18789"
    https_port = ""  # Docker always serves HTTPS on http_port via nginx
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
    # Remove old volume to clear stale config (e.g. anthropic defaults)
    run_capture(["docker", "volume", "rm", "openclaw-data"], timeout=15)

    # Build real OpenClaw container with Node.js
    log("Building OpenClaw container (Node.js + real OpenClaw gateway)...")
    build_dir = str(OPENCLAW_STATE_DIR / "docker-build")
    Path(build_dir).mkdir(parents=True, exist_ok=True)

    gw_internal_port = str(int(http_port) + 1)

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
        f'echo "=== OpenClaw Docker Container (port {http_port}) ==="',
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
        "# Pre-start config (before gateway generates its own token)",
        "echo 'Configuring OpenClaw gateway...'",
        "openclaw config set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true 2>/dev/null || true",
        "# Build allowedOrigins safely (prefer IPv4; avoid invalid unbracketed IPv6 URLs)",
        "DOCKER_HOST_IP=$(getent ahostsv4 host.docker.internal 2>/dev/null | awk '{print $1}' | head -1)",
        'if [ -z "$DOCKER_HOST_IP" ]; then',
        "  DOCKER_HOST_IP=$(hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i ~ /^[0-9]+\\./){print $i; exit}}}')",
        "fi",
        'if [ -z "$DOCKER_HOST_IP" ]; then',
        "  DOCKER_HOST_IP='127.0.0.1'",
        "fi",
        f'echo "Setting allowedOrigins for host IP: $DOCKER_HOST_IP port {http_port}"',
        f"ALLOWED_ORIGINS_JSON=$(python3 - << 'PYEOF'",
        "import json, os",
        f"port = '{http_port}'",
        "host_ip = (os.environ.get('DOCKER_HOST_IP') or '').strip()",
        "configured_host = (os.environ.get('OPENCLAW_HOST_IP') or '').strip()",
        "origins = [",
        "    f'https://127.0.0.1:{port}',",
        "    f'https://localhost:{port}',",
        "    f'http://127.0.0.1:{port}',",
        "    f'http://localhost:{port}',",
        "]",
        "if host_ip and host_ip != '127.0.0.1':",
        "    origins.extend([f'https://{host_ip}:{port}', f'http://{host_ip}:{port}'])",
        "if configured_host and configured_host not in ('0.0.0.0', '*', '127.0.0.1', 'localhost'):",
        "    origins.extend([f'https://{configured_host}:{port}', f'http://{configured_host}:{port}'])",
        "dedup = []",
        "for o in origins:",
        "    if o not in dedup:",
        "        dedup.append(o)",
        "print(json.dumps(dedup, separators=(',', ':')))",
        "PYEOF",
        ")",
        'echo "allowedOrigins JSON: $ALLOWED_ORIGINS_JSON"',
        'openclaw config set gateway.controlUi.allowedOrigins "$ALLOWED_ORIGINS_JSON" 2>/dev/null || true',
        'echo "Configured allowedOrigins: $(openclaw config get gateway.controlUi.allowedOrigins 2>/dev/null || echo unavailable)"',
        'openclaw config set gateway.trustedProxies \'["127.0.0.1","::1"]\' 2>/dev/null || true',
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
        f"export DESIRED_OLLAMA_MODEL='{llm_model}'",
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
        "models = []",
        "for m in (data.get('models') or []):",
        "  name = m.get('model') or m.get('name')",
        "  if name:",
        "    models.append(name)",
        "def norm(s: str) -> str:",
        "  s = s.lower()",
        "  s = re.sub(r'[^a-z0-9:]+', '', s)",
        "  return s",
        "desired = os.environ.get('OPENCLAW_MODEL') or os.environ.get('DESIRED_OLLAMA_MODEL') or ''",
        "desired_n = norm(desired)",
        "chosen = None",
        "if models:",
        "  for cand in models:",
        "    if cand == desired:",
        "      chosen = cand; break",
        "  if not chosen:",
        "    for cand in models:",
        "      if cand.lower() == desired.lower():",
        "        chosen = cand; break",
        "  if not chosen and desired_n:",
        "    for cand in models:",
        "      if norm(cand) == desired_n:",
        "        chosen = cand; break",
        "  if not chosen:",
        "    chosen = models[0]",
        "with open('/tmp/ollama-default-model.txt', 'w', encoding='utf-8') as f:",
        "  f.write(chosen or '')",
        "print('Ollama models discovered:', len(models))",
        "print('Ollama desired model:', desired)",
        "print('Ollama chosen model:', chosen)",
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
        "profiles = {}",
        "last_good = {}",
        "ollama_key = os.environ.get('OLLAMA_API_KEY')",
        "if ollama_key:",
        "  profiles['ollama:local'] = {'type': 'api_key', 'provider': 'ollama', 'key': ollama_key}",
        "  last_good['ollama'] = 'ollama:local'",
        "anthropic_key = os.environ.get('ANTHROPIC_API_KEY')",
        "if anthropic_key:",
        "  profiles['anthropic:default'] = {'type': 'api_key', 'provider': 'anthropic', 'key': anthropic_key}",
        "  last_good['anthropic'] = 'anthropic:default'",
        "data = {'version': 1, 'profiles': profiles, 'lastGood': last_good}",
        "(agent_dir / 'auth-profiles.json').write_text(json.dumps(data, indent=2), encoding='utf-8')",
        "enabled = ', '.join(sorted(profiles.keys())) if profiles else '(none)'",
        "print('Auth profiles enabled:', enabled)",
        "PYEOF",
        "",
        "# Gateway auth / Control UI access (set pre-start; avoids restart loops)",
        "openclaw config set gateway.auth.mode token 2>/dev/null || true",
        "openclaw config set gateway.auth.token serverinstaller 2>/dev/null || true",
        "openclaw config set gateway.controlUi.dangerouslyDisableDeviceAuth true 2>/dev/null || true",
        "openclaw config set gateway.controlUi.allowInsecureAuth true 2>/dev/null || true",
        "",
        "# NOTE: Do not set agents.defaults.models here.",
        "# New OpenClaw expects this key to be a record, not an array. Writing an array",
        "# causes config validation errors and can break Control UI with HTTP 500.",
        "",
        "# If no Claude key is provided, force default model to a VALID Ollama model to avoid auth failures",
        "if [ -z \"$ANTHROPIC_API_KEY\" ]; then",
        "  OLLAMA_DEFAULT=$(cat /tmp/ollama-default-model.txt 2>/dev/null || true)",
        "  if [ -n \"$OLLAMA_DEFAULT\" ]; then",
        "    echo \"No ANTHROPIC_API_KEY; defaulting agent model to ollama/$OLLAMA_DEFAULT\"",
        "    openclaw config set agents.defaults.model \"ollama/$OLLAMA_DEFAULT\" 2>/dev/null || true",
        "  else",
        "    echo 'No ANTHROPIC_API_KEY and no Ollama model detected; leaving default model unchanged'",
        "  fi",
        "fi",
        "",
        "# Check env from entrypoint perspective",
        "echo 'Checking env vars visible to openclaw:'",
        "openclaw doctor 2>&1 | head -20 || true",
        "",
        "# Generate SSL cert",
        "mkdir -p /root/.openclaw/certs",
        'openssl req -x509 -nodes -newkey rsa:2048 -keyout /root/.openclaw/certs/key.pem -out /root/.openclaw/certs/cert.pem -days 3650 -subj "/CN=openclaw/O=ServerInstaller" 2>/dev/null',
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
        "",
        "# Configure agent to use local Ollama as default AI",
        f"echo 'Configuring agent to use Ollama model: {llm_model}'",
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
        "# Clean invalid keys from previous installs",
        "OC_CFG=/root/.openclaw/openclaw.json",
        "if [ -f $OC_CFG ]; then",
        "  python3 << 'PYEOF'",
        "import json",
        "p = '/root/.openclaw/openclaw.json'",
        "try: c = json.load(open(p))",
        "except: c = {}",
        "for k in ['agent','defaultModel','defaultProvider']:",
        "  c.pop(k, None)",
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
        "json.dump(c, open(p,'w'), indent=2)",
        "PYEOF",
        "fi",
        "",
        "# Get gateway auth token and print dashboard URL",
        "GATEWAY_TOKEN=$(openclaw config get gateway.auth.token 2>/dev/null || echo 'serverinstaller')",
        f'echo "============================================="',
        f'echo "DASHBOARD URL: https://YOUR_IP:{http_port}/#token=$GATEWAY_TOKEN"',
        f'echo "Ollama API: $OLLAMA_API_URL"',
        f'echo "Select your model in OpenClaw dashboard: Settings > AI & Agents"',
        f'echo "============================================="',
        "",
        "# Test direct gateway access (no proxy) to diagnose 500 errors",
        f'echo "=== Direct gateway test on port {gw_internal_port} (no proxy) ==="',
        f"GW_HTTP_CODE=$(curl -s -o /tmp/gw-root-body.txt -w '%{{http_code}}' http://127.0.0.1:{gw_internal_port}/ 2>/tmp/gw-root-curl.err || echo '000')",
        'echo "Direct gateway status: $GW_HTTP_CODE"',
        'if [ "$GW_HTTP_CODE" != "200" ]; then',
        "  echo '--- Direct gateway body (first 80 lines) ---'",
        "  head -80 /tmp/gw-root-body.txt 2>/dev/null || true",
        "  echo '--- Direct gateway curl stderr ---'",
        "  head -40 /tmp/gw-root-curl.err 2>/dev/null || true",
        "  echo '--- Recent OpenClaw gateway log ---'",
        "  tail -120 /tmp/openclaw/openclaw-$(date +%F).log 2>/dev/null || true",
        "fi",
        f'echo "=== Direct gateway response headers ==="',
        f"curl -sI http://127.0.0.1:{gw_internal_port}/ 2>&1 | head -15 || echo 'Direct headers test failed'",
        "",
        "# Stop default nginx if running (not used, socat handles SSL)",
        "nginx -s stop 2>/dev/null || true",
        "",
        "# Use socat for SSL termination (pure TCP proxy, no HTTP header manipulation)",
        "# This avoids nginx rewriting Host/Origin headers which can break OpenClaw's validation",
        f'echo "Starting socat SSL proxy on port {http_port} -> 127.0.0.1:{gw_internal_port}..."',
        f"socat OPENSSL-LISTEN:{http_port},cert=/root/.openclaw/certs/cert.pem,key=/root/.openclaw/certs/key.pem,verify=0,reuseaddr,fork TCP:127.0.0.1:{gw_internal_port} &",
        "SOCAT_PID=$!",
        "sleep 2",
        f"echo 'Testing SSL port {http_port}...'",
        f"curl -sk https://127.0.0.1:{http_port}/ 2>&1 | head -5 || echo 'SSL curl test failed'",
        "",
        "wait $GW_PID",
    ]
    Path(build_dir, "entrypoint.sh").write_text("\n".join(entrypoint_lines) + "\n", encoding="utf-8")

    dockerfile = f"""FROM node:22-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y curl python3 build-essential socat openssl nginx zstd && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally
RUN npm install -g openclaw@latest @aws-sdk/client-bedrock @aws-sdk/client-bedrock-runtime

# Pre-create config dir
RUN mkdir -p /root/.openclaw

# Gateway port and Ollama provider
ENV OPENCLAW_PORT={http_port}
ENV OLLAMA_API_KEY=ollama-local
EXPOSE {http_port}

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
    # Pass channel tokens, LLM config, and Ollama API key as env vars
    env_map = {
        "OLLAMA_API_KEY": "ollama-local",
        "OPENCLAW_HOST_IP": host,
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
    # The Docker container serves HTTPS on the http_port (via nginx)
    https_url = f"https://{display_host}:{http_port}"
    state = _read_json_file(OPENCLAW_STATE_FILE)
    state.update({
        "installed": True, "service_name": container_name,
        "deploy_mode": "docker", "host": host,
        "http_port": http_port, "https_port": http_port,
        "http_url": f"https://{display_host}:{http_port}/#token=serverinstaller",
        "https_url": f"https://{display_host}:{http_port}/#token=serverinstaller",
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
    log(f" Dashboard:      https://{display_host}:{http_port}/")
    log(f" NOTE: Use HTTPS (not HTTP)! Accept the self-signed cert warning.")
    log(f"")
    # Try to get the gateway token from container
    gateway_token = ""
    try:
        import time as _t
        _t.sleep(2)
        rc, tok = run_capture(["docker", "exec", container_name, "openclaw", "config", "get", "gateway.auth.token"], timeout=10)
        if rc == 0 and tok.strip():
            gateway_token = tok.strip()
    except Exception:
        pass
    if gateway_token:
        log(f" Dashboard URL with token:")
        log(f"   https://{display_host}:{http_port}/#token={gateway_token}")
        log(f"")
        log(f" Gateway Token:  {gateway_token}")
    else:
        # Use the known token we set
        log(f" Dashboard URL:")
        log(f"   https://{display_host}:{http_port}/#token=serverinstaller")
        log(f"")
        log(f" Gateway Token:  serverinstaller")
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

    # Docker cleanup
    if command_exists("docker"):
        run_capture(["docker", "stop", cname], timeout=30)
        rc, _ = run_capture(["docker", "rm", "-f", cname], timeout=30)
        if rc == 0: log(f"Removed Docker container: {cname}")

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
    for subdir in ["app", "certs", "venv"]:
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
