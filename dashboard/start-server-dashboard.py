#!/usr/bin/env python3
import argparse
import ctypes
import json
import re
import os
import platform
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# ── Fix SSL certificate verification (macOS / minimal systems) ────────────────
# Python on macOS doesn't trust system certs by default. We MUST fix this
# before ANY urllib HTTPS call or it will fail with CERTIFICATE_VERIFY_FAILED.
if sys.platform == "darwin":
    # macOS: always try to install certs, then force unverified if still broken
    _ssl_fixed = False
    for _pyver in [f"{sys.version_info.major}.{sys.version_info.minor}", "3.13", "3.12", "3.11", "3.10"]:
        _cert_cmd = f"/Applications/Python {_pyver}/Install Certificates.command"
        if os.path.exists(_cert_cmd):
            try:
                subprocess.run(["bash", _cert_cmd], capture_output=True, timeout=30)
                _ssl_fixed = True
                break
            except Exception:
                pass
    if not _ssl_fixed:
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
            os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        except ImportError:
            pass
    # Always set unverified as fallback — macOS cert issues are too common
    ssl._create_default_https_context = ssl._create_unverified_context

REPO = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
DASHBOARD_HTTPS = os.environ.get("DASHBOARD_HTTPS", "").strip().lower() in ("1", "true", "yes", "y", "on")
DASHBOARD_CERT = os.environ.get("DASHBOARD_CERT", "").strip()
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "").strip()
SYNC_DASHBOARD_FILES = [
    "dashboard/start-server-dashboard.py",
    "dashboard/server_installer_dashboard.py",
    "dashboard/windows_dashboard_service.py",
    "dashboard/file_manager.py",
    "dashboard/ssl_manager.py",
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
    "dashboard/ui/pages/ai/lmstudio.js",
    "dashboard/ui/pages/agents/openclaw.js",
    "dashboard/ui/pages/ai/tgwui.js",
    "dashboard/ui/pages/ai/comfyui.js",
    "dashboard/ui/pages/ai/whisper.js",
    "dashboard/ui/pages/ai/piper.js",
    "dashboard/ui/pages/ai/ai-all.js",
    "dashboard/ui/pages/api/api-docs.js",
    "dashboard/ui/pages/agents/agents-all.js",
    "dashboard/ui/pages/ssl/ssl.js",
    "dashboard/ui/pages/files/files.js",
    "dashboard/ui/app.js",
    "dashboard/api_gateway.py",
]
SYNC_WINDOWS_FILES = [
    "Python/windows/setup-python.ps1",
    "Mongo/windows/setup-mongodb.ps1",
    "DotNet/windows/install-windows-dotnet-host.ps1",
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
    "S3/windows/setup-storage.ps1",
    "S3/windows/modules/common.ps1",
    "S3/windows/modules/minio.ps1",
    "S3/windows/modules/cleanup.ps1",
    "S3/windows/modules/iis.ps1",
    "S3/windows/modules/docker.ps1",
    "S3/windows/modules/main.ps1",
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
SYNC_UNIX_FILES = [
    "Python/linux-macos/setup-python.sh",
    "Mongo/linux-macos/setup-mongodb.sh",
    "DotNet/linux/install-linux-dotnet-runner.sh",
    "S3/linux-macos/setup-storage.sh",
    "S3/linux-macos/modules/core.sh",
    "S3/linux-macos/modules/cleanup.sh",
    "S3/linux-macos/modules/platform.sh",
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
    "Proxy/linux-macos/setup-proxy.sh",
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
LINUX_SERVICE_NAME = "server-installer-dashboard.service"


def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sync_files_for_current_os():
    files = list(SYNC_DASHBOARD_FILES)
    if os.name == "nt":
        files.extend(SYNC_WINDOWS_FILES)
    else:
        files.extend(SYNC_UNIX_FILES)
    return files


def cache_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("ProgramData", "C:/ProgramData"))
        return base / "Server-Installer"
    return Path.home() / ".server-installer"


def ensure_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    local_root_str = os.environ.get("SERVER_INSTALLER_LOCAL_ROOT", "").strip()
    local_root = Path(local_root_str) if local_root_str else None
    for rel in sync_files_for_current_os():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Try local copy first (when running from the repo directory)
        if local_root:
            local_src = local_root / rel
            if local_src.exists():
                if not target.exists() or local_src.stat().st_mtime > target.stat().st_mtime:
                    import shutil
                    shutil.copy2(str(local_src), str(target))
                continue
        tmp_target = target.with_suffix(target.suffix + ".download")
        try:
            print(f"Syncing required file: {rel}")
            url = f"{REPO}/{rel}"
            urllib.request.urlretrieve(url, tmp_target)
            os.replace(tmp_target, target)
        except Exception as ex:
            if tmp_target.exists():
                tmp_target.unlink(missing_ok=True)
            if not target.exists():
                raise RuntimeError(f"Failed to download required file '{rel}': {ex}") from ex
            print(f"Warning: using cached file for {rel} ({ex})")


def preferred_host(arg_host: str) -> str:
    if arg_host and arg_host not in ("auto", "0.0.0.0"):
        return arg_host
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        if ip:
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def can_bind(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return True, None
    except OSError as ex:
        return False, ex
    finally:
        sock.close()


def find_listener_pids_linux(port: int):
    try:
        out = subprocess.check_output(
            ["ss", "-ltnp", f"sport = :{port}"],
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        return set()

    pids = set()
    for line in out.splitlines():
        if "users:((" not in line:
            continue
        marker = "pid="
        idx = line.find(marker)
        if idx == -1:
            continue
        idx += len(marker)
        end = idx
        while end < len(line) and line[end].isdigit():
            end += 1
        if end > idx:
            try:
                pids.add(int(line[idx:end]))
            except ValueError:
                continue
    return pids


def find_listener_pids_windows(port: int):
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return set()

    pids = set()
    pat = re.compile(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE)
    for line in out.splitlines():
        m = pat.match(line)
        if not m:
            continue
        lp = int(m.group(1))
        pid = int(m.group(2))
        if lp == port:
            pids.add(pid)
    return pids


def process_cmdline(pid: int):
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
                ],
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return out.strip()
        except Exception:
            return ""
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except Exception:
        return ""
    return data.replace(b"\x00", b" ").decode("utf-8", errors="ignore")


def is_dashboard_process(pid: int):
    cmd = process_cmdline(pid)
    if not cmd:
        return False
    indicators = [
        "start-server-dashboard.py",
        "server_installer_dashboard.py",
    ]
    return any(ind in cmd for ind in indicators)


def stop_process(pid: int, timeout_sec: float = 3.0):
    if os.name == "nt":
        try:
            subprocess.check_call(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception:
        return False

    started = time.time()
    while time.time() - started < timeout_sec:
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            return True
        except Exception:
            break

    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass

    time.sleep(0.2)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except Exception:
        return False


def stop_existing_dashboard_on_port(port: int):
    pids = find_listener_pids_windows(port) if os.name == "nt" else find_listener_pids_linux(port)
    if not pids:
        return False, "no listener"

    own_pids = [pid for pid in pids if is_dashboard_process(pid)]
    foreign_pids = [pid for pid in pids if pid not in own_pids]

    stopped_any = False
    failed = []
    for pid in own_pids:
        if stop_process(pid):
            stopped_any = True
        else:
            failed.append(pid)

    parts = []
    if stopped_any:
        parts.append(f"stopped previous dashboard process(es): {', '.join(map(str, own_pids))}")
    if failed:
        parts.append(f"failed to stop dashboard pid(s): {', '.join(map(str, failed))}")
    if foreign_pids:
        parts.append(f"port owned by different process(es): {', '.join(map(str, foreign_pids))}")
    if not parts:
        parts.append("no dashboard process found on listener")

    return stopped_any, "; ".join(parts)


def choose_port(bind_host: str, preferred_port: int):
    candidates = []
    for p in [preferred_port, 80, 443]:
        if p and p not in candidates:
            candidates.append(p)

    diagnostics = []
    for port in candidates:
        ok, err = can_bind(bind_host, port)
        diagnostics.append((port, ok, err))
        if ok:
            return port, diagnostics
    return None, diagnostics


def check_local_http(port: int, attempts: int = 8, delay: float = 0.5, use_https: bool = False):
    scheme = "https" if use_https else "http"
    url = f"{scheme}://127.0.0.1:{port}/"
    last_error = None
    for _ in range(attempts):
        try:
            ctx = None
            if use_https:
                import ssl
                ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(url, timeout=2, context=ctx) as resp:
                return True, f"{resp.status}"
        except Exception as ex:
            last_error = ex
            time.sleep(delay)
    return False, str(last_error) if last_error else "Unknown error"


def wait_for_local_http(port: int, seconds: int, use_https: bool = False):
    last_detail = "Unknown error"
    for _ in range(max(1, seconds)):
        ok, detail = check_local_http(port, attempts=1, delay=0.25, use_https=use_https)
        last_detail = detail
        if ok:
            return True, detail
        time.sleep(1)
    return False, last_detail


def run_capture(cmd, timeout=30):
    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
        return 0, out
    except subprocess.CalledProcessError as ex:
        return ex.returncode, ex.output or ""
    except Exception as ex:
        return 1, str(ex)


def try_open_append_log(*paths):
    for path in paths:
        try:
            return open(path, "a", encoding="utf-8")
        except Exception:
            continue
    return None


def powershell_single_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def powershell_list(items) -> str:
    return "@(" + ",".join(powershell_single_quote(item) for item in items) + ")"


def resolve_root() -> Path:
    root = cache_root()
    ensure_files(root)
    # If a newer version of this script was just downloaded to the cache and
    # the user ran an older copy, re-exec with the fresh cached version so that
    # any changes (e.g. an updated SYNC_DASHBOARD_FILES list) take effect.
    cached_self = root / "dashboard" / "start-server-dashboard.py"
    current_self = Path(__file__).resolve()
    if cached_self.exists() and cached_self.resolve() != current_self:
        try:
            if cached_self.read_bytes() != current_self.read_bytes():
                os.execv(sys.executable, [sys.executable, str(cached_self)] + sys.argv[1:])
        except Exception:
            pass
    return root


def port_owner_state(port: int):
    pids = find_listener_pids_windows(port) if os.name == "nt" else find_listener_pids_linux(port)
    if not pids:
        return "free", set(), set()
    own = {pid for pid in pids if is_dashboard_process(pid)}
    foreign = set(pids) - own
    if own and not foreign:
        return "dashboard", own, foreign
    return "foreign", own, foreign


def choose_port_allowing_dashboard_owner(bind_host: str, preferred_port: int):
    candidates = []
    for p in [preferred_port, 80, 443]:
        if p and p not in candidates:
            candidates.append(p)

    diagnostics = []
    for port in candidates:
        ok, err = can_bind(bind_host, port)
        if ok:
            diagnostics.append((port, "free", "available for local bind"))
            return port, diagnostics
        owner_state, own, foreign = port_owner_state(port)
        if owner_state == "dashboard":
            diagnostics.append((port, "dashboard", f"already owned by dashboard process(es): {', '.join(map(str, sorted(own)))}"))
            return port, diagnostics
        diagnostics.append((port, "foreign", f"unavailable ({err}); owner pid(s): {', '.join(map(str, sorted(foreign)))}"))
    return None, diagnostics


def run_dashboard_foreground(root: Path, bind_host: str, selected_port: int, display_host: str, preclean: bool = True) -> int:
    app = root / "dashboard" / "server_installer_dashboard.py"
    if not app.exists():
        print(f"Dashboard script not found: {app}", file=sys.stderr)
        return 1

    if preclean:
        preclean_ports = []
        for p in [selected_port, 80, 443]:
            if p and p not in preclean_ports:
                preclean_ports.append(p)
        print("Pre-run checks:")
        for p in preclean_ports:
            changed, note = stop_existing_dashboard_on_port(p)
            if changed:
                print(f"- Port {p}: {note}")
            elif note != "no listener":
                print(f"- Port {p}: {note}")

    cmd = [sys.executable, str(app), "--host", bind_host, "--port", str(selected_port)]
    use_https, cert_path, key_path = resolve_https_config()
    cmd += ["--https", "--cert", cert_path, "--key", key_path]
    proc = subprocess.Popen(cmd, cwd=str(root))

    ok, detail = check_local_http(selected_port, use_https=use_https)
    primary_url, extra_urls = build_dashboard_urls(bind_host, selected_port)
    print("Startup diagnostics:")
    print(f"- Bind host: {bind_host}")
    print(f"- Selected port: {selected_port}")
    print(f"- Verified local URL: {primary_url}")
    if extra_urls:
        print(f"- Network URLs: {', '.join(extra_urls)}")
    if ok:
        print(f"- Local HTTP check: PASS (HTTP {detail})")
    else:
        if proc.poll() is not None:
            print(f"- Local HTTP check: FAIL ({detail})")
            print(f"- Dashboard process exited early with code {proc.returncode}.")
        else:
            print(f"- Local HTTP check: FAIL ({detail})")
            print("- Process is running but localhost is not responding yet.")
    print("")
    print(f"Dashboard ready: {primary_url}")
    if extra_urls:
        print("Remote URLs require firewall/security-group access to the selected port.")
    return proc.wait()


def install_or_update_linux_service(root: Path, bind_host: str, selected_port: int, display_host: str) -> int:
    if os.name == "nt":
        return 1

    script_path = (root / "dashboard" / "start-server-dashboard.py").resolve()
    if not script_path.exists():
        script_path = Path(os.path.abspath(__file__))
    app_path = (root / "dashboard" / "server_installer_dashboard.py").resolve()

    if os.geteuid() != 0:
        # Not root — show URLs and instructions, then try to re-run with sudo
        use_https, _, _ = resolve_https_config()
        primary_url, extra_urls = build_dashboard_urls(bind_host, selected_port)
        hostname = socket.gethostname()
        # Build .local name (avoid double .local suffix)
        local_suffix = hostname if hostname.endswith(".local") else hostname + ".local"
        print("")
        print("=" * 60)
        print("  Server Installer Dashboard")
        print("=" * 60)
        print(f"  URL:  {primary_url}")
        if extra_urls:
            for u in extra_urls:
                print(f"        {u}")
        print(f"        http://{local_suffix}:{selected_port}")
        print(f"  Port: {selected_port}")
        print("=" * 60)
        print("")
        print("Service installation requires root. Re-running with sudo...")
        print("")
        # Try to re-launch with sudo
        try:
            cmd = ["sudo", sys.executable, str(script_path)] + sys.argv[1:]
            os.execvp("sudo", cmd)
        except Exception:
            print("Could not re-launch with sudo. Run manually:")
            print(f"  sudo python3 {script_path} --host {bind_host} --port {selected_port}")
            return 1
    if not script_path.exists() or not app_path.exists():
        print("Required dashboard files are missing after sync.", file=sys.stderr)
        return 1

    owner_state, own, foreign = port_owner_state(selected_port)
    if owner_state == "foreign":
        print(
            f"Port {selected_port} is owned by another process ({', '.join(map(str, sorted(foreign)))}). "
            "Choose another port.",
            file=sys.stderr,
        )
        return 1
    if owner_state == "dashboard":
        stop_existing_dashboard_on_port(selected_port)

    use_https, cert_path, key_path = resolve_https_config()

    # ── macOS: use launchd instead of systemd ────────────────────────────
    if sys.platform == "darwin":
        plist_label = "com.serverinstaller.dashboard"
        plist_path = Path("/Library/LaunchDaemons") / f"{plist_label}.plist"
        if not plist_path.parent.exists():
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"{plist_label}.plist"
            plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_text = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{plist_label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
    <string>--run-server</string>
    <string>--host</string><string>{bind_host}</string>
    <string>--port</string><string>{selected_port}</string>
    <string>--https</string>
    <string>--cert</string><string>{cert_path}</string>
    <string>--key</string><string>{key_path}</string>
  </array>
  <key>WorkingDirectory</key><string>{root}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{root}/dashboard/dashboard.log</string>
  <key>StandardErrorPath</key><string>{root}/dashboard/dashboard.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>DASHBOARD_HTTPS</key><string>1</string>
  </dict>
</dict>
</plist>
"""
        plist_path.write_text(plist_text, encoding="utf-8")
        # Unload old, load new
        run_capture(["launchctl", "bootout", "system", str(plist_path)], timeout=15)
        rc, out = run_capture(["launchctl", "bootstrap", "system", str(plist_path)], timeout=30)
        if rc != 0:
            # Try user-level launchctl
            run_capture(["launchctl", "unload", str(plist_path)], timeout=15)
            rc, out = run_capture(["launchctl", "load", "-w", str(plist_path)], timeout=30)
        if rc != 0:
            print(f"launchctl load failed, starting directly...", file=sys.stderr)
            # Fallback: just run in foreground
            return run_dashboard_foreground(root, bind_host, selected_port, display_host, preclean=True)
        # Wait for startup
        time.sleep(3)
        state_file = root / "dashboard" / "service-state.json"
        state_file.write_text(json.dumps({"service": plist_label, "root": str(root), "host": bind_host, "port": selected_port, "updated_at": int(time.time())}, indent=2), encoding="utf-8")
        ok, detail = check_local_http(selected_port, use_https=use_https)
        hostname = socket.gethostname()
        local_suffix = hostname if hostname.endswith(".local") else hostname + ".local"
        primary_url, extra_urls = build_dashboard_urls(bind_host, selected_port)
        print("")
        print("=" * 60)
        print("  Server Installer Dashboard — Running!")
        print("=" * 60)
        print(f"  URL:      {primary_url}")
        if extra_urls:
            for u in extra_urls:
                print(f"            {u}")
        print(f"            http://{local_suffix}:{selected_port}")
        print(f"  Service:  {plist_label} (launchd)")
        print(f"  Port:     {selected_port}")
        if ok:
            print(f"  Status:   RUNNING (HTTP {detail})")
        else:
            print(f"  Status:   STARTING (check: {root}/dashboard/dashboard.log)")
        print("=" * 60)
        print("")
        return 0

    # ── Linux: use systemd ───────────────────────────────────────────────
    unit_path = Path("/etc/systemd/system") / LINUX_SERVICE_NAME
    if not unit_path.parent.exists():
        print(f"systemd not available ({unit_path.parent} does not exist).", file=sys.stderr)
        print("Starting dashboard in foreground instead...", file=sys.stderr)
        return run_dashboard_foreground(root, bind_host, selected_port, display_host, preclean=True)

    unit_text = f"""[Unit]
Description=Server Installer Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart={sys.executable} {script_path} --run-server --host {bind_host} --port {selected_port} --https --cert {cert_path} --key {key_path}
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

    unit_path.write_text(unit_text, encoding="utf-8")
    rc, out = run_capture(["systemctl", "daemon-reload"], timeout=30)
    if rc != 0:
        print(f"systemctl daemon-reload failed:\n{out}", file=sys.stderr)
        return 1
    rc, out = run_capture(["systemctl", "enable", LINUX_SERVICE_NAME], timeout=30)
    if rc != 0 and "Created symlink" not in out and "already enabled" not in out.lower():
        print(f"systemctl enable failed:\n{out}", file=sys.stderr)
        return 1
    rc, out = run_capture(["systemctl", "restart", LINUX_SERVICE_NAME], timeout=40)
    if rc != 0:
        print(f"systemctl restart failed:\n{out}", file=sys.stderr)
        run_capture(["systemctl", "status", LINUX_SERVICE_NAME, "--no-pager", "-l"], timeout=30)
        return 1

    state_file = root / "dashboard" / "service-state.json"
    state_file.write_text(
        json.dumps(
            {
                "service": LINUX_SERVICE_NAME,
                "root": str(root),
                "host": bind_host,
                "port": selected_port,
                "updated_at": int(time.time()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    ok, detail = check_local_http(selected_port, use_https=use_https)
    fw_ok, fw_note = ensure_linux_firewall_port(selected_port)
    primary_url, extra_urls = build_dashboard_urls(bind_host, selected_port)
    hostname = socket.gethostname()
    print("")
    print("=" * 60)
    print("  Server Installer Dashboard — Running!")
    print("=" * 60)
    print(f"  URL:      {primary_url}")
    if extra_urls:
        for u in extra_urls:
            print(f"            {u}")
    try:
        _ls = hostname if hostname.endswith(".local") else hostname + ".local"
        local_name = f"http://{_ls}:{selected_port}"
        print(f"            {local_name}")
    except Exception:
        pass
    print(f"  Service:  {LINUX_SERVICE_NAME}")
    print(f"  Port:     {selected_port}")
    print(f"  Firewall: {'updated' if fw_ok else 'not changed'} ({fw_note})")
    if ok:
        print(f"  Status:   RUNNING (HTTP {detail})")
    else:
        print(f"  Status:   STARTING (check: journalctl -u {LINUX_SERVICE_NAME} -n 50)")
    print("=" * 60)
    print("")
    if not ok:
        print(f"Inspect logs: journalctl -u {LINUX_SERVICE_NAME} -n 120 --no-pager")
    if extra_urls:
        print("Remote access requires firewall/security-group to allow the port.")
    print("Re-running this command will update files and restart the service.")
    return 0


def install_or_update_windows_task(root: Path, bind_host: str, selected_port: int, display_host: str) -> int:
    if os.name != "nt":
        return 1
    if not is_windows_admin():
        print("Windows service installation requires Administrator. Re-run as admin.", file=sys.stderr)
        return 1

    script_path = (root / "dashboard" / "start-server-dashboard.py").resolve()
    if not script_path.exists():
        print("Required dashboard files are missing after sync.", file=sys.stderr)
        return 1

    owner_state, own, foreign = port_owner_state(selected_port)
    if owner_state == "foreign":
        print(
            f"Port {selected_port} is owned by another process ({', '.join(map(str, sorted(foreign)))}). "
            "Choose another port.",
            file=sys.stderr,
        )
        return 1
    if owner_state == "dashboard":
        stop_existing_dashboard_on_port(selected_port)

    python_exe = resolve_windows_python()
    service_name = "ServerInstallerDashboard"
    program_data = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer"
    log_dir = program_data / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server-installer-dashboard.log"
    service_script = (root / "dashboard" / "windows_dashboard_service.py").resolve()
    use_https, cert_path, key_path = resolve_https_config()
    if not service_script.exists():
        print("Windows dashboard service script is missing after sync.", file=sys.stderr)
        return 1

    state_file = root / "dashboard" / "service-state.json"
    state_file.write_text(
        json.dumps(
            {
                "service": service_name,
                "root": str(root),
                "host": bind_host,
                "port": selected_port,
                "updated_at": int(time.time()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rc, out = run_capture(["sc.exe", "stop", service_name], timeout=30)
    if rc != 0 and "1060" not in out and "1062" not in out:
        out = out.strip()

    rc, out = run_capture(["sc.exe", "query", service_name], timeout=20)
    if rc != 0:
        rc, out = run_capture(
            [python_exe, str(service_script), "--startup", "auto", "install"],
            timeout=60,
        )
    else:
        rc, out = run_capture([python_exe, str(service_script), "update"], timeout=60)

    _service_start_ok = False
    if rc == 0:
        rc, out = run_capture([python_exe, str(service_script), "restart"], timeout=60)
        if rc != 0:
            rc, out = run_capture([python_exe, str(service_script), "start"], timeout=60)
        _service_start_ok = rc == 0
    if not _service_start_ok:
        print(f"[WARN] Windows service start failed (falling back to direct process):\n{out.strip()}", file=sys.stderr)

    ok, detail = wait_for_local_http(selected_port, seconds=8, use_https=use_https)

    if not ok:
        try:
            fallback_log_path = log_dir / "server-installer-dashboard-fallback.log"
            log_fp = try_open_append_log(log_path, fallback_log_path)
            creation_flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            detached_cmd = [
                python_exe,
                str(script_path),
                "--run-server",
                "--host",
                bind_host,
                "--port",
                str(selected_port),
            ]
            detached_cmd += ["--https", "--cert", cert_path, "--key", key_path]
            popen_kwargs = {
                "cwd": str(root),
                "creationflags": creation_flags,
            }
            if log_fp is not None:
                popen_kwargs["stdout"] = log_fp
                popen_kwargs["stderr"] = log_fp
            else:
                popen_kwargs["stdout"] = subprocess.DEVNULL
                popen_kwargs["stderr"] = subprocess.DEVNULL
            try:
                subprocess.Popen(detached_cmd, **popen_kwargs)
            finally:
                if log_fp is not None:
                    log_fp.close()
            # If Windows service failed, register a Task Scheduler task for reboot persistence.
            if not _service_start_ok:
                try:
                    pythonw = Path(python_exe).with_name("pythonw.exe")
                    if not pythonw.exists():
                        pythonw = Path(python_exe)
                    tr_cmd = (
                        f'"{pythonw}" "{script_path}" --run-server'
                        f" --host {bind_host} --port {selected_port}"
                        f' --https --cert "{cert_path}" --key "{key_path}"'
                    )
                    run_capture(
                        [
                            "schtasks", "/Create", "/F",
                            "/TN", service_name,
                            "/SC", "ONSTART",
                            "/DELAY", "0000:30",
                            "/TR", tr_cmd,
                            "/RU", "SYSTEM",
                            "/RL", "HIGHEST",
                        ],
                        timeout=30,
                    )
                    print("[INFO] Registered startup task via Task Scheduler (service fallback).")
                except Exception:
                    pass
            ok, detail = wait_for_local_http(selected_port, seconds=12, use_https=use_https)
        except Exception as ex:
            detail = f"Fallback launch failed: {ex}"

    urls = [f"https://127.0.0.1:{selected_port}"]
    for ip in get_local_ipv4_addresses():
        candidate = f"https://{ip}:{selected_port}"
        if candidate not in urls:
            urls.append(candidate)
    if display_host and display_host not in ("127.0.0.1", "localhost"):
        candidate = f"https://{display_host}:{selected_port}"
        if candidate not in urls:
            urls.insert(0, candidate)
    hostname = socket.gethostname()
    try:
        local_name = f"https://{hostname}:{selected_port}"
        if local_name not in urls:
            urls.append(local_name)
    except Exception:
        pass
    print("")
    print("=" * 60)
    print("  Server Installer Dashboard — Running!")
    print("=" * 60)
    for url in urls:
        print(f"  URL:      {url}")
    print(f"  Service:  {service_name}")
    print(f"  Port:     {selected_port}")
    if ok:
        print(f"  Status:   RUNNING (HTTP {detail})")
    else:
        print(f"  Status:   STARTING (check log: {log_path})")
    print("=" * 60)
    print("")
    print("Re-running this same command will update files and restart the service.")
    return 0


def resolve_windows_python() -> str:
    env_override = os.environ.get("SERVER_INSTALLER_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    program_data = Path(os.environ.get("ProgramData", "C:/ProgramData"))
    embedded = program_data / "Server-Installer" / "python" / "python.exe"
    if embedded.exists():
        return str(embedded)
    python_state_file = cache_root() / "python" / "python-state.json"
    state = _read_json_file(python_state_file)
    managed = str(state.get("python_executable") or "").strip()
    if managed and Path(managed).exists():
        return managed
    return sys.executable


def get_local_ipv4_addresses():
    ips = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 53))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.append(ip)
    except Exception:
        pass
    return ips


def ensure_linux_firewall_port(port: int):
    if os.name == "nt":
        return False, "not applicable on Windows"
    if os.geteuid() != 0:
        return False, "requires root to update Linux firewall"

    if command_exists("firewall-cmd"):
        rc_state, _ = run_capture(["firewall-cmd", "--state"], timeout=15)
        if rc_state == 0:
            run_capture(["firewall-cmd", "--quiet", "--add-port", f"{port}/tcp"], timeout=20)
            run_capture(["firewall-cmd", "--quiet", "--permanent", "--add-port", f"{port}/tcp"], timeout=20)
            rc_reload, out_reload = run_capture(["firewall-cmd", "--quiet", "--reload"], timeout=20)
            if rc_reload == 0:
                return True, f"firewalld opened TCP {port}"
            return False, (out_reload or f"firewalld reload failed after opening TCP {port}").strip()

    if command_exists("ufw"):
        rc_status, out_status = run_capture(["ufw", "status"], timeout=20)
        status_text = (out_status or "").lower()
        if rc_status == 0 and "inactive" not in status_text:
            rc_allow, out_allow = run_capture(["ufw", "allow", f"{port}/tcp"], timeout=20)
            if rc_allow == 0:
                return True, f"ufw opened TCP {port}"
            return False, (out_allow or f"ufw failed to open TCP {port}").strip()

    return False, "no active supported Linux firewall manager detected"


def build_dashboard_urls(bind_host: str, selected_port: int):
    scheme = "https"
    primary = f"{scheme}://127.0.0.1:{selected_port}"
    extras = []

    def add(url: str):
        if url != primary and url not in extras:
            extras.append(url)

    add(f"{scheme}://localhost:{selected_port}")

    if bind_host and bind_host not in ("auto", "0.0.0.0", "127.0.0.1", "localhost"):
        add(f"{scheme}://{bind_host}:{selected_port}")

    for ip in get_local_ipv4_addresses():
        add(f"{scheme}://{ip}:{selected_port}")

    preferred = preferred_host(bind_host)
    if preferred not in ("127.0.0.1", "localhost"):
        add(f"{scheme}://{preferred}:{selected_port}")

    return primary, extras


def ensure_unix_https_material(cert_path: Path, key_path: Path) -> None:
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    names = ["localhost", socket.gethostname()]
    san_entries = ["DNS:localhost", "IP:127.0.0.1"]
    for name in names:
        if name and name not in ("localhost",) and f"DNS:{name}" not in san_entries:
            san_entries.append(f"DNS:{name}")
    for ip in get_local_ipv4_addresses():
        entry = f"IP:{ip}"
        if entry not in san_entries:
            san_entries.append(entry)

    config_text = (
        "[req]\n"
        "default_bits = 2048\n"
        "prompt = no\n"
        "default_md = sha256\n"
        "x509_extensions = v3_req\n"
        "distinguished_name = dn\n"
        "\n"
        "[dn]\n"
        "CN = localhost\n"
        "\n"
        "[v3_req]\n"
        "subjectAltName = " + ", ".join(san_entries) + "\n"
        "basicConstraints = CA:true\n"
        "keyUsage = critical, digitalSignature, keyEncipherment, keyCertSign\n"
        "extendedKeyUsage = serverAuth\n"
    )

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".cnf") as tmp:
        tmp.write(config_text)
        config_path = tmp.name

    try:
        cmd = [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "825",
            "-config",
            config_path,
            "-extensions",
            "v3_req",
        ]
        rc, out = run_capture(cmd, timeout=60)
        if rc != 0:
            raise RuntimeError((out or "openssl failed").strip())
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass


def resolve_https_config():
    use_https = True
    cert_dir = cache_root() / "certs"
    cert_path = (Path(DASHBOARD_CERT) if DASHBOARD_CERT else (cert_dir / "dashboard.crt")).resolve()
    key_path = (Path(DASHBOARD_KEY) if DASHBOARD_KEY else (cert_dir / "dashboard.key")).resolve()
    if (not cert_path.exists()) or (not key_path.exists()):
        if os.name == "nt":
            raise RuntimeError(
                f"HTTPS certificate files are missing: {cert_path} and {key_path}. "
                "Start the dashboard through start-dashboard.ps1 so the Windows CA/self-signed certificate is generated."
            )
        if not shutil.which("openssl"):
            raise RuntimeError(
                "HTTPS is required, but OpenSSL is not installed. Install openssl and rerun start-dashboard.sh."
            )
        ensure_unix_https_material(cert_path, key_path)
    return True, str(cert_path), str(key_path)


def is_windows_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin_if_needed() -> bool:
    if os.name != "nt":
        return False
    if is_windows_admin():
        return False

    params = subprocess.list2cmdline(sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )
    if rc <= 32:
        raise RuntimeError("Administrator elevation was required but could not be started.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="auto")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--user", default="", help="Set a custom dashboard login username.")
    parser.add_argument("--password", default="", help="Set a custom dashboard login password.")
    parser.add_argument("--run-server", action="store_true", help="Internal mode: run dashboard process in foreground.")
    parser.add_argument("--https", action="store_true", help="Ignored for compatibility; dashboard startup is HTTPS-only.")
    parser.add_argument("--cert", default="", help="Path to PEM certificate file.")
    parser.add_argument("--key", default="", help="Path to PEM private key file.")
    # Also accept positional args: python3 start.py <username> <password>
    parser.add_argument("positional_user", nargs="?", default="", help=argparse.SUPPRESS)
    parser.add_argument("positional_pass", nargs="?", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # Resolve credentials: --user/--password take priority, then positional args
    dash_user = args.user or args.positional_user or ""
    dash_pass = args.password or args.positional_pass or ""

    # macOS: default to admin/admin if no credentials provided and none saved
    if sys.platform == "darwin" and not dash_user and not dash_pass:
        creds_check = cache_root() / "dashboard-credentials.json"
        if not creds_check.exists():
            dash_user = "admin"
            dash_pass = "admin"
            print("[INFO] macOS: default credentials set (admin / admin)")

    os.environ["DASHBOARD_HTTPS"] = "1"
    if args.cert:
        os.environ["DASHBOARD_CERT"] = args.cert
    if args.key:
        os.environ["DASHBOARD_KEY"] = args.key

    # Save custom credentials if provided — write to ALL possible locations
    if dash_user and dash_pass:
        import hashlib
        hashed = hashlib.sha256(dash_pass.encode()).hexdigest()
        creds_data = json.dumps({"username": dash_user, "password_hash": hashed}, indent=2)
        # Write to multiple locations so the dashboard finds it regardless of which user runs it
        creds_paths = [
            cache_root() / "dashboard-credentials.json",  # current user
        ]
        # Also write to the real user's home (in case running with sudo)
        real_home = os.environ.get("SUDO_USER", "")
        if real_home:
            creds_paths.append(Path("/Users") / real_home / ".server-installer" / "dashboard-credentials.json")
            creds_paths.append(Path("/home") / real_home / ".server-installer" / "dashboard-credentials.json")
        # Also write to root's location
        if os.name != "nt":
            creds_paths.append(Path("/var/root/.server-installer/dashboard-credentials.json"))
            creds_paths.append(Path("/root/.server-installer/dashboard-credentials.json"))
        for creds_file in creds_paths:
            try:
                creds_file.parent.mkdir(parents=True, exist_ok=True)
                creds_file.write_text(creds_data, encoding="utf-8")
                os.chmod(str(creds_file), 0o644)
            except Exception:
                pass
        print(f"[INFO] Dashboard credentials set: user={dash_user}")
        os.environ["DASHBOARD_CUSTOM_USER"] = dash_user
        os.environ["DASHBOARD_CUSTOM_PASS_HASH"] = hashed

    if relaunch_as_admin_if_needed():
        return 0

    display_host = preferred_host(args.host)
    bind_host = args.host
    if (not bind_host) or bind_host in ("auto", "0.0.0.0"):
        bind_host = "0.0.0.0"

    root = resolve_root()
    if args.run_server:
        return run_dashboard_foreground(root, bind_host, args.port, display_host, preclean=True)

    selected_port, diagnostics = choose_port_allowing_dashboard_owner(bind_host, args.port)
    if selected_port is None:
        print("No usable port found for dashboard startup.", file=sys.stderr)
        for port, state, note in diagnostics:
            print(f"- Port {port}: {state} -> {note}", file=sys.stderr)
        print("Port checks validate local bind only. For remote access, firewall/security-group must also allow the port.", file=sys.stderr)
        return 1

    print("Port checks:")
    for port, state, note in diagnostics:
        if state == "free":
            print(f"- Port {port}: available for local bind")
        elif state == "dashboard":
            print(f"- Port {port}: owned by existing dashboard (will be replaced)")
        else:
            print(f"- Port {port}: {note}")

    if selected_port != args.port:
        print(f"Requested port {args.port} is unavailable. Falling back to {selected_port}.")

    if os.name != "nt":
        return install_or_update_linux_service(root, bind_host, selected_port, display_host)

    return install_or_update_windows_task(root, bind_host, selected_port, display_host)


if __name__ == "__main__":
    raise SystemExit(main())
