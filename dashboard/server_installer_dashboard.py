#!/usr/bin/env python3
import argparse
import ctypes
import html
import io
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
import traceback
import re
import getpass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

warnings.filterwarnings("ignore", category=DeprecationWarning)


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INSTALLER = ROOT / "DotNet" / "windows" / "install-windows-dotnet-host.ps1"
LINUX_INSTALLER = ROOT / "DotNet" / "linux" / "install-linux-dotnet-runner.sh"
S3_WINDOWS_INSTALLER = ROOT / "S3" / "windows" / "setup-storage.ps1"
S3_LINUX_INSTALLER = ROOT / "S3" / "linux-macos" / "setup-storage.sh"
REPO_RAW_BASE = os.environ.get(
    "SERVER_INSTALLER_REPO_BASE",
    "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main",
)

WINDOWS_SETUP_MODULES = [
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
]

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

SESSIONS = set()
JOBS = {}
JOBS_LOCK = threading.Lock()


def command_exists(name):
    return shutil.which(name) is not None


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
    info = {"installed": False, "version": "", "server_version": "", "running": False}
    rc, out = run_capture(["docker", "--version"])
    if rc == 0 and out:
        info["installed"] = True
        info["version"] = out.splitlines()[0].strip()
        rc2, out2 = run_capture(["docker", "version", "--format", "{{.Server.Version}}"])
        if rc2 == 0 and out2:
            info["server_version"] = out2.strip()
            info["running"] = True
    return info


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


def parse_port_from_addr(addr):
    text = (addr or "").strip()
    if not text:
        return None
    if text.startswith("[") and "]:" in text:
        return text.rsplit("]:", 1)[1]
    if ":" in text:
        return text.rsplit(":", 1)[1]
    return None


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
            for line in out.splitlines():
                parts = [p for p in line.split() if p]
                if len(parts) < 5:
                    continue
                proto = parts[0]
                local_addr = parts[4]
                proc = parts[6] if len(parts) > 6 else ""
                port = parse_port_from_addr(local_addr)
                if not (port and port.isdigit()):
                    continue
                ports.append({"proto": proto, "port": int(port), "process": proc, "state": parts[1]})

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


def manage_firewall_port(action, port, protocol):
    action = (action or "").strip().lower()
    protocol = (protocol or "").strip().lower()
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
            cmd = prefix + ["ufw", "--force", "allow", f"{port_num}/{protocol}"]
        else:
            cmd = prefix + ["ufw", "--force", "delete", "allow", f"{port_num}/{protocol}"]
        rc, out = run_capture(cmd, timeout=30)
        return rc == 0, (out or f"ufw {action} completed.")

    return False, "No supported firewall manager found (ufw on Linux, Windows Firewall on Windows)."


def _safe_service_name(name):
    value = (name or "").strip()
    if not value:
        return ""
    if not re.match(r"^[A-Za-z0-9_.@-]+$", value):
        return ""
    return value


def get_service_items():
    items = []

    if os.name == "nt":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Get-Service | Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Depth 2",
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
                    items.append(
                        {
                            "kind": "service",
                            "name": name,
                            "display_name": str(row.get("DisplayName", "")).strip(),
                            "status": str(row.get("Status", "")).strip(),
                            "start_type": str(row.get("StartType", "")).strip(),
                            "platform": "windows",
                        }
                    )
            except Exception:
                pass
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
                items.append(
                    {
                        "kind": "service",
                        "name": name,
                        "display_name": desc,
                        "status": active,
                        "sub_status": sub,
                        "load": load,
                        "platform": "linux",
                    }
                )

    if command_exists("docker"):
        rc, out = run_capture(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"], timeout=30)
        if rc == 0 and out:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                name = parts[0].strip()
                status = parts[1].strip()
                image = parts[2].strip()
                if not name:
                    continue
                items.append(
                    {
                        "kind": "docker",
                        "name": name,
                        "display_name": image,
                        "status": status,
                        "platform": "docker",
                    }
                )

    items.sort(key=lambda x: (x.get("kind", ""), x.get("name", "").lower()))
    return items


def manage_service(action, name, kind):
    action = (action or "").strip().lower()
    kind = (kind or "service").strip().lower()
    svc_name = _safe_service_name(name)
    if action != "stop":
        return False, "Only 'stop' action is supported."
    if not svc_name:
        return False, "Invalid service name."

    if kind == "docker":
        if not command_exists("docker"):
            return False, "Docker is not available."
        rc, out = run_capture(["docker", "stop", svc_name], timeout=60)
        return rc == 0, (out or f"Docker container '{svc_name}' stop attempted.")

    if os.name == "nt":
        if not is_windows_admin():
            return False, "Stopping services on Windows requires Administrator."
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"Stop-Service -Name '{svc_name}' -Force -ErrorAction Stop; Write-Output 'Stopped {svc_name}'",
        ]
        rc, out = run_capture(cmd, timeout=60)
        return rc == 0, (out or f"Stop requested for {svc_name}.")

    prefix = _sudo_prefix()
    if command_exists("systemctl"):
        cmd = prefix + ["systemctl", "stop", svc_name]
        rc, out = run_capture(cmd, timeout=60)
        return rc == 0, (out or f"Stop requested for {svc_name}.")

    return False, "No supported service manager found."


def get_system_status():
    load = None
    try:
        if hasattr(os, "getloadavg"):
            la = os.getloadavg()
            load = {"1m": la[0], "5m": la[1], "15m": la[2]}
    except Exception:
        load = None

    status = {
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
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
        "listening_ports": get_listening_ports(),
        "software": {
            "dotnet": get_dotnet_info(),
            "docker": get_docker_info(),
            "iis": get_iis_info(),
        },
    }
    return status


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


def run_windows_s3_installer(form, live_cb=None, mode="iis"):
    if os.name != "nt":
        return 1, "Windows S3 installer can only run on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(S3_WINDOWS_FILES, live_cb=live_cb)

    selected_mode = (form.get("S3_MODE", [mode])[0] or mode or "iis").strip().lower()
    if selected_mode not in ("iis", "docker"):
        selected_mode = "iis"
    mode_choice = "2\n" if selected_mode == "docker" else "1\n"
    requested_https = (form.get("LOCALS3_HTTPS_PORT", [""])[0] or "").strip()
    if requested_https:
        if not requested_https.isdigit():
            return 1, "LOCALS3_HTTPS_PORT must be numeric."
        if is_local_tcp_port_listening(requested_https):
            return 1, f"Requested HTTPS port {requested_https} is already in use. Choose another port."
    # Script is interactive; feed defaults for remaining prompts.
    scripted_input = mode_choice + ("\n" * 200)
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
        "LOCALS3_ENABLE_LAN",
        "LOCALS3_HTTPS_PORT",
        "LOCALS3_API_PORT",
        "LOCALS3_UI_PORT",
        "LOCALS3_CONSOLE_PORT",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
    env["LOCALS3_MODE"] = selected_mode
    return run_process(cmd, env=env, live_cb=live_cb, input_text=scripted_input)


def run_linux_s3_installer(form=None, live_cb=None):
    if os.name == "nt":
        return 1, "Linux S3 installer can only run on Linux/macOS hosts."
    ensure_repo_files(S3_LINUX_FILES, live_cb=live_cb)

    cmd = ["bash", str(S3_LINUX_INSTALLER)]
    requested_https = (form.get("LOCALS3_HTTPS_PORT", [""])[0] or "").strip()
    if requested_https and (not requested_https.isdigit()):
        return 1, "LOCALS3_HTTPS_PORT must be numeric."
    if requested_https and is_local_tcp_port_listening(requested_https):
        auto_port = pick_free_local_tcp_port([9443, 10443, 11443, 12443, 13443, 8443, 15443, 16443])
        if auto_port:
            if live_cb:
                live_cb(f"Requested HTTPS port {requested_https} is busy. Auto-selected free port {auto_port}.\n")
            form["LOCALS3_HTTPS_PORT"] = [str(auto_port)]
            requested_https = str(auto_port)
        else:
            return 1, f"Requested HTTPS port {requested_https} is already in use and no fallback port was found."

    requested_host = (form.get("LOCALS3_HOST", [""])[0] or "").strip()
    requested_lan = (form.get("LOCALS3_ENABLE_LAN", [""])[0] or "").strip().lower()
    host_line = requested_host if requested_host else ""
    lan_line = "y" if requested_lan in ("1", "true", "yes", "y", "on") else "n"

    # Keep compatibility with older interactive scripts:
    # 1) host prompt
    # 2) LAN prompt
    # 3) use 443 prompt -> default to No
    # 4) choose HTTPS option / custom port
    if requested_https:
        if requested_https == "443":
            https_flow = "y"
        else:
            https_flow = f"n\n2\n{requested_https}"
    else:
        https_flow = "n\n1"

    scripted_input = f"{host_line}\n{lan_line}\n{https_flow}\n" + ("\n" * 200)
    env = os.environ.copy()
    form = form or {}
    forwarded_env = {}
    for key in [
        "LOCALS3_HOST",
        "LOCALS3_ENABLE_LAN",
        "LOCALS3_HTTPS_PORT",
        "LOCALS3_API_PORT",
        "LOCALS3_UI_PORT",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value
            forwarded_env[key] = value

    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "env"]
        for k, v in forwarded_env.items():
            cmd.append(f"{k}={v}")
        cmd += ["bash", str(S3_LINUX_INSTALLER)]

    return run_process(cmd, env=env, live_cb=live_cb, input_text=scripted_input)


def run_linux_s3_stop(live_cb=None):
    if os.name == "nt":
        return 1, "Linux S3 stop can only run on Linux/macOS hosts."

    script = r"""
set -euo pipefail
echo "[INFO] Stopping LocalS3 services..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl stop locals3-minio >/dev/null 2>&1 || true
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
if [ -f /Library/LaunchDaemons/com.locals3.minio.plist ]; then
  launchctl bootout system /Library/LaunchDaemons/com.locals3.minio.plist >/dev/null 2>&1 || true
fi
if command -v brew >/dev/null 2>&1; then
  brew services stop nginx >/dev/null 2>&1 || true
fi
echo "[INFO] LocalS3 API/Console services stopped."
"""
    cmd = ["sh", "-c", script]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "sh", "-c", script]
    return run_process(cmd, env=os.environ.copy(), live_cb=live_cb)


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

    threading.Thread(target=heartbeat, daemon=True).start()
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
        if self.path.startswith("/api/system/status"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = {"ok": True, "status": get_system_status()}
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
                payload = {"ok": True, "services": get_service_items()}
                self.write_json(payload, HTTPStatus.OK)
            except Exception as ex:
                print(f"Service list error: {ex}")
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
                SESSIONS.discard(sid)
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
                SESSIONS.add(sid)
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
            form = self.parse_form()
            action = (form.get("action", [""])[0] or "").strip()
            port = (form.get("port", [""])[0] or "").strip()
            protocol = (form.get("protocol", ["tcp"])[0] or "tcp").strip()
            ok, message = manage_firewall_port(action, port, protocol)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/system/service":
            form = self.parse_form()
            action = (form.get("action", [""])[0] or "").strip()
            name = (form.get("name", [""])[0] or "").strip()
            kind = (form.get("kind", ["service"])[0] or "service").strip()
            ok, message = manage_service(action, name, kind)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
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

        if self.path == "/run/s3_windows":
            title = "S3 Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form)
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
            title = "S3 Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_s3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_s3_installer(form)
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
        if self.path == "/run/linux_docker":
            title = "Linux Docker Deployment"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_docker_deploy(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_docker_deploy(form)
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
