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
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


REPO = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
DASHBOARD_HTTPS = os.environ.get("DASHBOARD_HTTPS", "").strip().lower() in ("1", "true", "yes", "y", "on")
DASHBOARD_CERT = os.environ.get("DASHBOARD_CERT", "").strip()
DASHBOARD_KEY = os.environ.get("DASHBOARD_KEY", "").strip()
SYNC_DASHBOARD_FILES = [
    "dashboard/start-server-dashboard.py",
    "dashboard/server_installer_dashboard.py",
    "dashboard/windows_dashboard_service.py",
    "dashboard/file_manager.py",
    "dashboard/ui_assets.py",
    "dashboard/ui/core.js",
    "dashboard/ui/utils.js",
    "dashboard/ui/actions.js",
    "dashboard/ui/components.js",
    "dashboard/ui/app.js",
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
    for rel in sync_files_for_current_os():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
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
    if os.geteuid() != 0:
        print("Linux service installation requires root. Re-run with sudo.", file=sys.stderr)
        return 1

    script_path = (root / "dashboard" / "start-server-dashboard.py").resolve()
    app_path = (root / "dashboard" / "server_installer_dashboard.py").resolve()
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
    unit_path = Path("/etc/systemd/system") / LINUX_SERVICE_NAME
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
    print(f"OS detected: {platform.system()}")
    print(f"Service: {LINUX_SERVICE_NAME} (enabled, restarted)")
    print(f"Verified local URL: {primary_url}")
    if extra_urls:
        print(f"Network URLs: {', '.join(extra_urls)}")
    print(f"Firewall: {'updated' if fw_ok else 'not changed'} ({fw_note})")
    if ok:
        print(f"Local HTTP check: PASS (HTTP {detail})")
    else:
        print(f"Local HTTP check: FAIL ({detail})")
        print(f"Inspect logs: journalctl -u {LINUX_SERVICE_NAME} -n 120 --no-pager")
    if extra_urls:
        print("Remote URLs require firewall/security-group access to the selected port.")
    print("Re-running this same command will update files and restart the service.")
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

    if rc == 0:
        rc, out = run_capture([python_exe, str(service_script), "restart"], timeout=60)
        if rc != 0:
            rc, out = run_capture([python_exe, str(service_script), "start"], timeout=60)
    if rc != 0:
        print(f"Windows dashboard service registration failed:\n{out}", file=sys.stderr)
        return 1

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
            ok, detail = wait_for_local_http(selected_port, seconds=12, use_https=use_https)
        except Exception as ex:
            detail = f"Fallback launch failed: {ex}"

    print(f"OS detected: {platform.system()}")
    print(f"Service: {service_name}")
    urls = [f"https://127.0.0.1:{selected_port}"]
    for ip in get_local_ipv4_addresses():
        candidate = f"https://{ip}:{selected_port}"
        if candidate not in urls:
            urls.append(candidate)
    if display_host and display_host not in ("127.0.0.1", "localhost"):
        candidate = f"https://{display_host}:{selected_port}"
        if candidate not in urls:
            urls.insert(0, candidate)
    print("Dashboard URLs:")
    for url in urls:
        print(f"- {url}")
    print(f"Log file: {log_path}")
    if ok:
        print(f"Local HTTP check: PASS (HTTP {detail})")
    else:
        print(f"Local HTTP check: FAIL ({detail})")
        print(f"Inspect log: {log_path}")
    print("")
    print(f"Dashboard ready: https://{display_host}:{selected_port}")
    print(f"Service name in Windows Services: {service_name}")
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
    parser.add_argument("--run-server", action="store_true", help="Internal mode: run dashboard process in foreground.")
    parser.add_argument("--https", action="store_true", help="Ignored for compatibility; dashboard startup is HTTPS-only.")
    parser.add_argument("--cert", default="", help="Path to PEM certificate file.")
    parser.add_argument("--key", default="", help="Path to PEM private key file.")
    args = parser.parse_args()

    os.environ["DASHBOARD_HTTPS"] = "1"
    if args.cert:
        os.environ["DASHBOARD_CERT"] = args.cert
    if args.key:
        os.environ["DASHBOARD_KEY"] = args.key

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
