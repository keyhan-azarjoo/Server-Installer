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
from urllib.parse import parse_qs

warnings.filterwarnings("ignore", category=DeprecationWarning)

BUILD_ID = "s3-fix-2026-03-09-1416"

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INSTALLER = ROOT / "DotNet" / "windows" / "install-windows-dotnet-host.ps1"
LINUX_INSTALLER = ROOT / "DotNet" / "linux" / "install-linux-dotnet-runner.sh"
S3_WINDOWS_INSTALLER = ROOT / "S3" / "windows" / "setup-storage.ps1"
S3_LINUX_INSTALLER = ROOT / "S3" / "linux-macos" / "setup-storage.sh"
MONGO_WINDOWS_INSTALLER = ROOT / "Mongo" / "windows" / "setup-mongodb.ps1"
REPO_RAW_BASE = os.environ.get(
    "SERVER_INSTALLER_REPO_BASE",
    "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main",
)
LOCAL_REPO_ROOT = os.environ.get("SERVER_INSTALLER_LOCAL_ROOT", "").strip()
LOCAL_REPO_REQUIRED = os.environ.get("SERVER_INSTALLER_USE_LOCAL", "").strip() in ("1", "true", "yes", "on")

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

MONGO_WINDOWS_FILES = [
    "Mongo/windows/setup-mongodb.ps1",
]

MONGO_UNIX_FILES = [
    "Mongo/linux-macos/setup-mongodb.sh",
]

SESSIONS = set()
JOBS = {}
JOBS_LOCK = threading.Lock()


def command_exists(name):
    return shutil.which(name) is not None


def resolve_windows_python():
    env_override = os.environ.get("SERVER_INSTALLER_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    program_data = Path(os.environ.get("ProgramData", "C:/ProgramData"))
    embedded = program_data / "Server-Installer" / "python" / "python.exe"
    if embedded.exists():
        return str(embedded)
    return sys.executable


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
    return choose_s3_host("")


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


def get_mongo_info():
    info = {
        "installed": False,
        "server_version": "",
        "web_version": "",
        "https_url": "",
        "connection_string": "",
        "auth_enabled": False,
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
        if connection:
            info["connection_string"] = connection
        elif port.isdigit():
            info["connection_string"] = f"mongodb://{preferred_host}:{int(port)}/"
        if native.get("mode") == "native":
            info["web_version"] = str(native.get("web_version") or "native")
        info["auth_enabled"] = bool(native.get("auth_enabled"))

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
            if os.name == "nt" and _windows_localmongo_owns_port(p):
                managed_owner = True
                owner_hint = "localmongo-managed"
            elif _linux_locals3_owns_port(p):
                managed_owner = True
                owner_hint = "locals3-managed"
        except Exception:
            pass
    return {"ok": True, "busy": len(listeners) > 0, "listeners": listeners, "managed_owner": managed_owner, "owner_hint": owner_hint}


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
        "$root=Join-Path $env:ProgramData 'LocalMongoDB'; "
        "$meta=Join-Path $root 'install-info.json'; "
        "$cfg=Join-Path $root 'config\\mongod.cfg'; "
        "$svc=Get-Service -Name 'LocalMongoDB' -ErrorAction SilentlyContinue; "
        "$obj=[ordered]@{installed=$false;version='';connection='';port='';mode='';web_version='';auth_enabled=$false}; "
        "if($svc){$obj.installed=$true}; "
        "if(Test-Path $meta){ "
        "  try { "
        "    $m=Get-Content -LiteralPath $meta -Raw | ConvertFrom-Json; "
        "    if($m.version){$obj.version=[string]$m.version}; "
        "    if($m.connection_string){$obj.connection=[string]$m.connection_string}; "
        "    if($m.mongo_port){$obj.port=[string]$m.mongo_port}; "
        "    if($m.mode){$obj.mode=[string]$m.mode}; "
        "    if($m.web_version){$obj.web_version=[string]$m.web_version}; "
        "    if($null -ne $m.auth_enabled){$obj.auth_enabled=[bool]$m.auth_enabled}; "
        "    $obj.installed=$true; "
        "  } catch {} "
        "} "
        "if((-not $obj.port) -and (Test-Path $cfg)){ "
        "  $match=Select-String -Path $cfg -Pattern '^\\s*port\\s*:\\s*(\\d+)' -AllMatches -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "  if($match){$obj.port=[string]$match.Matches[0].Groups[1].Value} "
        "} "
        "if((-not $obj.version) -and (Test-Path (Join-Path $root 'mongodb\\bin\\mongod.exe'))){ "
        "  try { "
        "    $ver=& (Join-Path $root 'mongodb\\bin\\mongod.exe') --version 2>$null | Out-String; "
        "    if($ver -match 'db version v([0-9A-Za-z\\.\\-]+)'){ $obj.version=$matches[1] } "
        "  } catch {} "
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


def get_service_items():
    items = []
    managed_patterns = re.compile(
        r"(locals3|minio|dotnet-app|dotnet|aspnet|kestrel|dotnetapp|localmongo|mongodb|mongo-express|mongod)",
        re.IGNORECASE,
    )
    preferred_host = choose_service_host()
    native_mongo = get_windows_native_mongo_info() if os.name == "nt" else {}

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
                    display_name = str(row.get("DisplayName", "")).strip()
                    if not managed_patterns.search(f"{name} {display_name}"):
                        continue
                    items.append(
                        {
                            "kind": "service",
                            "name": name,
                            "display_name": display_name,
                            "status": str(row.get("Status", "")).strip(),
                            "start_type": str(row.get("StartType", "")).strip(),
                            "platform": "windows",
                            "urls": [],
                            "ports": ([{"port": int(native_mongo.get("port")), "protocol": "tcp"}] if _is_mongo_name(name) and str(native_mongo.get("port", "")).isdigit() else []),
                        }
                    )
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
                            for b in binds:
                                proto = str(b.get("protocol", "http") or "http").lower()
                                bind = str(b.get("bindingInformation", "") or "")
                                port = parse_port_from_addr(bind)
                                if port and str(port).isdigit():
                                    task_ports.append({"port": int(port), "protocol": "tcp"})
                                    scheme = "https" if proto == "https" else "http"
                                    host = preferred_host
                                    if int(port) in (80, 443):
                                        task_urls.append(f"{scheme}://{host}")
                                    else:
                                        task_urls.append(f"{scheme}://{host}:{port}")
                        except Exception:
                            pass
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

        # Include managed IIS websites.
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
                    if not managed_patterns.search(name):
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
                                    host = preferred_host
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
                    urls, ports = _urls_from_nginx_conf("/etc/nginx/conf.d/locals3.conf", preferred_host=preferred_host)
                    if not urls:
                        urls, ports = _urls_from_nginx_conf("/opt/locals3/nginx/nginx-standalone.conf", preferred_host=preferred_host)
                else:
                    urls, ports = _urls_from_nginx_conf(f"/etc/nginx/conf.d/{base_name}.conf", preferred_host=preferred_host)
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
                ports = details.get("ports", [])
                urls = []
                for p in ports:
                    scheme = "https" if (
                        p.get("port") == 443 or
                        details.get("labels", {}).get("com.localmongo.role") == "https"
                    ) else "http"
                    host = preferred_host
                    if details.get("labels", {}).get("com.localmongo.role") == "mongodb":
                        continue
                    if p.get("port") in (80, 443):
                        urls.append(f"{scheme}://{host}")
                    else:
                        urls.append(f"{scheme}://{host}:{p.get('port')}")
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

    items.sort(key=lambda x: (x.get("kind", ""), x.get("name", "").lower()))
    return items


def _is_locals3_name(name):
    return bool(re.search(r"locals3|minio", str(name or ""), re.IGNORECASE))


def _is_dotnet_name(name):
    return bool(re.search(r"dotnet|aspnet|kestrel|dotnetapp", str(name or ""), re.IGNORECASE))


def _is_mongo_name(name):
    return bool(re.search(r"localmongo|mongodb|mongo-express|mongod", str(name or ""), re.IGNORECASE))


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
    return ""


def _windows_cleanup_localmongo():
    if not is_windows_admin():
        return False, "Administrator is required."
    ps = r"""
$ErrorActionPreference='SilentlyContinue'
Import-Module WebAdministration -ErrorAction SilentlyContinue
if (Test-Path "IIS:\Sites\LocalMongoDB") {
  Stop-Website -Name 'LocalMongoDB' | Out-Null
  Remove-Website -Name 'LocalMongoDB' | Out-Null
}
$svc = Get-CimInstance Win32_Service -Filter "Name='LocalMongoDB'" -ErrorAction SilentlyContinue
if($svc){
  Stop-Service -Name 'LocalMongoDB' -Force -ErrorAction SilentlyContinue
  sc.exe delete "LocalMongoDB" | Out-Null
}
$bindings = @('0.0.0.0:9445','127.0.0.1:9445')
foreach($binding in $bindings){
  netsh http delete sslcert ipport=$binding 1>$null 2>$null | Out-Null
}
if(Get-Command docker -ErrorAction SilentlyContinue){
  docker rm -f localmongo-https localmongo-web localmongo-mongodb 1>$null 2>$null | Out-Null
  docker network rm localmongo-net 1>$null 2>$null | Out-Null
  docker volume rm -f localmongo-data 1>$null 2>$null | Out-Null
}
schtasks /End /TN "LocalMongoDB-Autostart" 1>$null 2>$null | Out-Null
schtasks /Delete /TN "LocalMongoDB-Autostart" /F 1>$null 2>$null | Out-Null
$root = Join-Path $env:ProgramData 'LocalMongoDB'
if(Test-Path $root){ Remove-Item -Recurse -Force -Path $root -ErrorAction SilentlyContinue }
Get-NetFirewallRule -DisplayName 'ServerInstaller-Managed-TCP-27017' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
try {
  $cert = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -match 'CN=Caddy Local Authority' -or $_.FriendlyName -match 'Caddy' }
  foreach($item in $cert){ Remove-Item -Path $item.PSPath -Force -ErrorAction SilentlyContinue }
} catch {}
"""
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=150)
    return rc == 0, (out or "LocalMongoDB managed files cleaned.")


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
        return _windows_cleanup_localmongo()
    ps = (
        "Import-Module WebAdministration -ErrorAction SilentlyContinue; "
        f"$s=Get-Website -Name '{site_name}' -ErrorAction SilentlyContinue; "
        "if($s){ $p=$s.physicalPath; Stop-Website -Name $s.Name -ErrorAction SilentlyContinue | Out-Null; "
        "Remove-Website -Name $s.Name -ErrorAction SilentlyContinue | Out-Null; "
        "if($p -and (Test-Path $p)){ Remove-Item -Recurse -Force -Path $p -ErrorAction SilentlyContinue } }"
    )
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=60)
    return rc == 0, (out or f"IIS site '{site_name}' and files removed.")


def _windows_remove_service_and_files(svc_name):
    if not is_windows_admin():
        return False, "Administrator is required."
    if _is_mongo_name(svc_name):
        return _windows_cleanup_localmongo()
    ps = (
        f"$s=Get-CimInstance Win32_Service -Filter \"Name='{svc_name}'\" -ErrorAction SilentlyContinue; "
        "$bin=''; if($s){$bin=$s.PathName}; "
        f"Stop-Service -Name '{svc_name}' -Force -ErrorAction SilentlyContinue; "
        f"sc.exe delete \"{svc_name}\" | Out-Null; "
        "$exe=''; if($bin){ if($bin.StartsWith('\"')){$exe=($bin -split '\"')[1]} else {$exe=($bin -split ' ')[0]} }; "
        "$dir=''; if($exe){$dir=Split-Path -Parent $exe}; "
        "if($dir -and (Test-Path $dir)){ "
        "$d=$dir.ToLowerInvariant(); "
        "if($d.Contains('locals3') -or $d.Contains('dotnet') -or $d.Contains('aspnet') -or $d.Contains('kestrel')){ "
        "Remove-Item -Recurse -Force -Path $dir -ErrorAction SilentlyContinue } }"
    )
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=90)
    return rc == 0, (out or f"Service '{svc_name}' and managed files removed.")


def manage_service(action, name, kind):
    action = (action or "").strip().lower()
    kind = (kind or "service").strip().lower()
    svc_name = _safe_service_name(name)
    if action not in ("start", "stop", "restart", "delete", "autostart_on", "autostart_off"):
        return False, "Supported actions: start, stop, restart, delete, autostart_on, autostart_off."
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
        if action == "delete":
            rc, out = run_capture(["docker", "rm", "-f", svc_name], timeout=60)
            if _is_locals3_name(svc_name):
                if os.name == "nt":
                    _windows_cleanup_locals3()
                else:
                    _linux_cleanup_locals3(_sudo_prefix())
            if _is_mongo_name(svc_name) and os.name == "nt":
                _windows_cleanup_localmongo()
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
                return _windows_cleanup_localmongo()
            return _windows_remove_iis_site_and_path(svc_name)
        if action in ("autostart_on", "autostart_off"):
            val = "$true" if action == "autostart_on" else "$false"
            rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Import-Module WebAdministration; Set-ItemProperty \"IIS:\\Sites\\{svc_name}\" -Name serverAutoStart -Value {val}"], timeout=30)
            return rc == 0, (out or f"IIS site '{svc_name}' auto-start updated.")
        return False, "Unsupported IIS action."

    if os.name == "nt":
        if not is_windows_admin():
            return False, "Stopping services on Windows requires Administrator."
        if action == "delete":
            if _is_locals3_name(svc_name):
                return _windows_cleanup_locals3()
            if _is_mongo_name(svc_name):
                return _windows_cleanup_localmongo()
            return _windows_remove_service_and_files(svc_name)
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
            if action == "delete":
                if unit.startswith("/") or ".." in unit:
                    return False, "Invalid unit name for delete."
                if _is_locals3_name(unit):
                    return _linux_cleanup_locals3(prefix)
                if _is_dotnet_name(unit):
                    return _linux_cleanup_dotnet_service(prefix, unit)
                run_capture(prefix + ["systemctl", "stop", unit], timeout=30)
                run_capture(prefix + ["systemctl", "disable", unit], timeout=30)
                unit_file = f"/etc/systemd/system/{unit}"
                rc, out = run_capture(prefix + ["rm", "-f", unit_file], timeout=30)
                run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
                if rc == 0:
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
        "public_ip": get_public_ipv4(),
        "listening_ports": get_listening_ports(),
        "software": {
            "dotnet": get_dotnet_info(),
            "docker": get_docker_info(),
            "iis": get_iis_info(),
            "mongo": get_mongo_info(),
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


def _download_file_with_timeout(url, target_path, timeout_sec=30):
    with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
        data = resp.read()
    with open(target_path, "wb") as fh:
        fh.write(data)


def ensure_repo_files(relative_paths, live_cb=None, refresh=True, retries=2):
    local_root = Path(LOCAL_REPO_ROOT) if LOCAL_REPO_ROOT else None
    local_root_ok = bool(local_root and local_root.exists())
    for rel in relative_paths:
        rel_path = Path(rel)
        target = ROOT / rel_path
        local_source = None
        bundled_source = (ROOT / rel_path).resolve()
        if bundled_source.exists():
            local_source = bundled_source
        if local_root_ok:
            candidate = (local_root / rel_path).resolve()
            if candidate.exists():
                local_source = candidate
        exists_before = target.exists()
        if local_source is not None:
            if live_cb:
                live_cb(f"Using local file: {rel_path.as_posix()}\n")
            else:
                print(f"Using local file: {rel_path.as_posix()}")
            if local_source != target.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_source, target)
            continue
        if exists_before and (not refresh):
            continue
        if LOCAL_REPO_REQUIRED and (local_source is None):
            raise RuntimeError(
                f"Local repo required but missing file: {rel_path.as_posix()} (SERVER_INSTALLER_LOCAL_ROOT={LOCAL_REPO_ROOT})"
            )
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


def _linux_locals3_owns_port(port):
    return _linux_locals3_nginx_owns_port(port) or _docker_locals3_owns_port(port)


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
    ensure_repo_files(S3_WINDOWS_FILES, live_cb=live_cb, refresh=True)

    selected_mode = (form.get("S3_MODE", [mode])[0] or mode or "iis").strip().lower()
    if selected_mode not in ("iis", "docker"):
        selected_mode = "iis"
    mode_choice = "2\n" if selected_mode == "docker" else "1\n"
    requested_host = (form.get("LOCALS3_HOST", [""])[0] or "").strip()
    requested_mode = (form.get("LOCALS3_HOST_MODE", [""])[0] or "").strip().lower()
    requested_ip = (form.get("LOCALS3_HOST_IP", [""])[0] or "").strip()
    if (requested_mode in ("", "lan")) and requested_ip:
        form["LOCALS3_HOST"] = [requested_ip]
    elif requested_mode == "custom" and requested_host:
        form["LOCALS3_HOST"] = [requested_host]
    elif requested_mode == "public":
        if not requested_host or requested_host in ("localhost", "127.0.0.1"):
            resolved_host = choose_s3_host(requested_host)
            form["LOCALS3_HOST"] = [resolved_host]
    elif not requested_host or requested_host in ("localhost", "127.0.0.1"):
        resolved_host = choose_s3_host(requested_host)
        form["LOCALS3_HOST"] = [resolved_host]
    requested_https = (form.get("LOCALS3_HTTPS_PORT", [""])[0] or "").strip()
    if requested_https:
        if not requested_https.isdigit():
            return 1, "LOCALS3_HTTPS_PORT must be numeric."
        if is_local_tcp_port_listening(requested_https):
            if _windows_locals3_iis_owns_port(requested_https):
                # Allow reuse when the existing LocalS3 IIS binding owns the port (update/reinstall).
                pass
            else:
                return 1, f"Requested HTTPS port {requested_https} is already in use. Choose another port."
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
        "LOCALMONGO_HTTPS_PORT",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_WEB_PORT",
        "LOCALMONGO_ADMIN_USER",
        "LOCALMONGO_ADMIN_PASSWORD",
        "LOCALMONGO_UI_USER",
        "LOCALMONGO_UI_PASSWORD",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    requested_host = env.get("LOCALMONGO_HOST", "").strip()
    requested_ip = env.get("LOCALMONGO_HOST_IP", "").strip()
    if (not requested_host) and requested_ip:
        env["LOCALMONGO_HOST"] = requested_ip
    elif not requested_host:
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
        "LOCALMONGO_HTTPS_PORT",
        "LOCALMONGO_MONGO_PORT",
        "LOCALMONGO_WEB_PORT",
        "LOCALMONGO_ADMIN_USER",
        "LOCALMONGO_ADMIN_PASSWORD",
        "LOCALMONGO_UI_USER",
        "LOCALMONGO_UI_PASSWORD",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    requested_host = env.get("LOCALMONGO_HOST", "").strip()
    requested_ip = env.get("LOCALMONGO_HOST_IP", "").strip()
    if (not requested_host) and requested_ip:
        env["LOCALMONGO_HOST"] = requested_ip
    elif not requested_host:
        env["LOCALMONGO_HOST"] = choose_service_host()

    for port_key in ("LOCALMONGO_HTTPS_PORT", "LOCALMONGO_MONGO_PORT", "LOCALMONGO_WEB_PORT"):
        port_value = env.get(port_key, "").strip()
        if port_value and (not port_value.isdigit()):
            return 1, f"{port_key} must be numeric."

    for port_key in ("LOCALMONGO_HTTPS_PORT", "LOCALMONGO_MONGO_PORT", "LOCALMONGO_WEB_PORT"):
        port_value = env.get(port_key, "").strip()
        if port_value and is_local_tcp_port_listening(port_value):
            usage = get_port_usage(port_value, "tcp")
            if not usage.get("managed_owner"):
                return 1, f"Requested port {port_value} for {port_key} is already in use. Choose another port."

    cmd = ["bash", str(ROOT / "Mongo" / "linux-macos" / "setup-mongodb.sh")]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        cmd = ["sudo", "env"]
        for key in [
            "LOCALMONGO_HOST",
            "LOCALMONGO_HOST_IP",
            "LOCALMONGO_HTTPS_PORT",
            "LOCALMONGO_MONGO_PORT",
            "LOCALMONGO_WEB_PORT",
            "LOCALMONGO_ADMIN_USER",
            "LOCALMONGO_ADMIN_PASSWORD",
            "LOCALMONGO_UI_USER",
            "LOCALMONGO_UI_PASSWORD",
        ]:
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(ROOT / "Mongo" / "linux-macos" / "setup-mongodb.sh")]

    return run_process(cmd, env=env, live_cb=live_cb)


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
    if not requested_host or requested_host in ("localhost", "127.0.0.1"):
        resolved_host = choose_s3_host(requested_host)
        form["LOCALS3_HOST"] = [resolved_host]
        requested_host = resolved_host
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
    forwarded_env = {}
    for key in [
        "LOCALS3_HOST",
        "LOCALS3_ENABLE_LAN",
        "LOCALS3_HTTPS_PORT",
        "LOCALS3_API_PORT",
        "LOCALS3_UI_PORT",
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
        'local root="/opt/locals3"; '
        '[ "$(detect_os)" = "macos" ] && root="/usr/local/locals3"; '
        'if has_cmd systemctl; then '
        '  systemctl stop locals3-minio >/dev/null 2>&1 || true; '
        '  systemctl stop locals3-nginx >/dev/null 2>&1 || true; '
        'fi; '
        'if [ -f /opt/locals3/nginx/nginx.pid ]; then '
        '  kill "$(cat /opt/locals3/nginx/nginx.pid)" >/dev/null 2>&1 || true; '
        '  rm -f /opt/locals3/nginx/nginx.pid || true; '
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
  local bin="/usr/local/bin/minio"
  local data="${root}/data"
  local envf="/etc/default/locals3-minio"
  mkdir -p "$root" "$data"

  install_minio_binary "$bin"

  cat > "$envf" <<EOF
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=StrongPassword123
MINIO_SERVER_URL=${public_url}
MINIO_BROWSER_REDIRECT_URL=${console_browser_url}
EOF

  cat > /etc/systemd/system/locals3-minio.service <<EOF
[Unit]
Description=Local S3 MinIO
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
  systemctl enable --now locals3-minio
}

configure_minio_macos() {
  local root="$1" api_port="$2" ui_port="$3" public_url="$4" console_browser_url="$5"
  local bin="/usr/local/bin/minio"
  [ -d /opt/homebrew/bin ] && bin="/opt/homebrew/bin/minio"
  local data="${root}/data"
  local plist="/Library/LaunchDaemons/com.locals3.minio.plist"
  mkdir -p "$root" "$data"
  install_minio_binary "$bin"

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.locals3.minio</string>
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
  launchctl enable system/com.locals3.minio
  launchctl kickstart -k system/com.locals3.minio
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
  api_port="$(pick_port 9000 19000 29000)"
  ui_port="$(pick_port 9001 19001 29001)"
  [ -z "$api_port" ] && { err "No free API port."; exit 1; }
  [ -z "$ui_port" ] && { err "No free UI port."; exit 1; }
  console_https_port="$(pick_distinct_port "$https_port" 9443 10443 18443 8444)"
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

  root="/opt/locals3"
  [ "$os" = "macos" ] && root="/usr/local/locals3"
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
  cat > /etc/nginx/conf.d/locals3.conf <<EOF
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

  nginx -t || { err "Nginx config test failed."; exit 1; }

  if has_cmd systemctl; then
    systemctl unmask nginx >/dev/null 2>&1 || true
    if systemctl is-active --quiet nginx 2>/dev/null; then
      systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx >/dev/null 2>&1 || true
    else
      systemctl start nginx >/dev/null 2>&1 || true
    fi
    if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
      return
    fi
  elif has_cmd service; then
    service nginx reload >/dev/null 2>&1 || service nginx restart >/dev/null 2>&1 || true
    if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
      return
    fi
  fi

  warn "System nginx could not bind HTTPS ports ${api_https_port}/${console_https_port}. Trying isolated LocalS3 nginx..."
  local standalone_dir="/opt/locals3/nginx"
  local standalone_conf="${standalone_dir}/nginx-standalone.conf"
  local standalone_pid="${standalone_dir}/nginx.pid"
  mkdir -p "$standalone_dir"
  if [ -f "$standalone_pid" ]; then
    kill "$(cat "$standalone_pid")" >/dev/null 2>&1 || true
    rm -f "$standalone_pid" || true
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
    }
}
EOF
  nginx -t -c "$standalone_conf" || { err "Isolated nginx config test failed."; exit 1; }
  nginx -c "$standalone_conf" >/dev/null 2>&1 || true
  if ! port_free "$api_https_port" && ! port_free "$console_https_port"; then
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
    script_url = f"{REPO_RAW_BASE}/dashboard/start-server-dashboard.py"
    if live_cb:
        live_cb("[INFO] Updating dashboard files and restarting service...\n")
    if os.name == "nt":
        python_exe = resolve_windows_python().replace("'", "''")
        ps = (
            "$ProgressPreference='SilentlyContinue'; "
            f"Set-Location -Path '{(ROOT / 'dashboard')}' ; "
            f"Invoke-WebRequest -Uri '{script_url}' -OutFile './start-server-dashboard.py'; "
            "$log = Join-Path $env:TEMP 'server-installer-dashboard-update.log'; "
            f"Start-Process -FilePath '{python_exe}' -ArgumentList '.\\start-server-dashboard.py' "
            "-WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $log;"
            "Write-Host \"[INFO] Update launched in background. Log: $log\""
        )
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]
        rc, out = run_capture(cmd, timeout=30)
        return (0 if rc == 0 else 1), (out or "")

    python_bin = "python3" if command_exists("python3") else "python"
    log_path = "/tmp/server-installer-dashboard-update.log"
    shell_cmd = (
        f"cd '{(ROOT / 'dashboard')}' && "
        f"curl -fsSL '{script_url}' -o ./start-server-dashboard.py && "
        f"({python_bin} ./start-server-dashboard.py > '{log_path}' 2>&1 &)"
    )
    cmd = ["bash", "-lc", shell_cmd]
    rc, out = run_capture(cmd, timeout=30)
    if live_cb:
        live_cb(f"[INFO] Update launched in background. Log: {log_path}\n")
    return (0 if rc == 0 else 1), (out or "")

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
                    if output:
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
    msg = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Login</title>
<style>
:root{{
  --bg:#f4f8fc;
  --panel:#ffffff;
  --ink:#0f172a;
  --muted:#475569;
  --line:#d9e4f2;
  --brand:#0f766e;
  --brand-deep:#115e59;
  --brand-soft:#dff7f3;
  --danger:#b42318;
  --danger-bg:#fff1f1;
}}
*{{box-sizing:border-box}}
body{{
  margin:0;
  min-height:100vh;
  font-family:"Segoe UI",Tahoma,Arial,sans-serif;
  color:var(--ink);
  background:
    radial-gradient(circle at top left, rgba(15,118,110,.18), transparent 28%),
    radial-gradient(circle at bottom right, rgba(37,99,235,.14), transparent 24%),
    linear-gradient(135deg, #eef5fb 0%, #f8fbff 45%, #eef7f5 100%);
}}
.shell{{
  min-height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:32px 20px;
}}
.frame{{
  width:min(1080px, 100%);
  display:grid;
  grid-template-columns:1.08fr .92fr;
  background:rgba(255,255,255,.78);
  border:1px solid rgba(217,228,242,.95);
  border-radius:28px;
  overflow:hidden;
  box-shadow:0 28px 80px rgba(15,23,42,.16);
  backdrop-filter:blur(14px);
}}
.hero{{
  position:relative;
  padding:56px 48px;
  background:
    linear-gradient(160deg, rgba(15,118,110,.94), rgba(14,89,118,.9)),
    linear-gradient(135deg, #0f766e, #1d4ed8);
  color:#fff;
}}
.hero::before,
.hero::after{{
  content:"";
  position:absolute;
  border-radius:999px;
  background:rgba(255,255,255,.09);
}}
.hero::before{{width:260px;height:260px;top:-80px;right:-60px}}
.hero::after{{width:220px;height:220px;bottom:-110px;left:-90px}}
.eyebrow{{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:7px 12px;
  border:1px solid rgba(255,255,255,.18);
  border-radius:999px;
  background:rgba(255,255,255,.08);
  font-size:12px;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.hero h1{{
  margin:18px 0 14px;
  font-size:40px;
  line-height:1.06;
}}
.hero p{{
  margin:0;
  max-width:520px;
  color:rgba(255,255,255,.84);
  font-size:16px;
  line-height:1.7;
}}
.points{{margin:32px 0 0;padding:0;list-style:none;display:grid;gap:14px}}
.points li{{
  padding:14px 16px;
  border-radius:16px;
  background:rgba(255,255,255,.1);
  border:1px solid rgba(255,255,255,.12);
  line-height:1.5;
}}
.points strong{{display:block;margin-bottom:4px;font-size:14px}}
.card{{
  padding:48px 42px;
  background:linear-gradient(180deg, rgba(255,255,255,.96), rgba(252,253,255,.92));
  display:flex;
  align-items:center;
}}
.card-inner{{width:min(420px, 100%);margin:0 auto}}
.kicker{{
  margin:0 0 10px;
  color:var(--brand);
  font-size:12px;
  font-weight:700;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.card h2{{margin:0 0 10px;font-size:32px;line-height:1.1}}
.lead{{margin:0 0 26px;color:var(--muted);line-height:1.65}}
.alert{{
  margin:0 0 18px;
  padding:12px 14px;
  border-radius:14px;
  border:1px solid rgba(180,35,24,.14);
  background:var(--danger-bg);
  color:var(--danger);
  font-size:14px;
}}
form{{display:grid;gap:16px}}
.field{{display:grid;gap:8px}}
label{{font-size:14px;font-weight:700;color:#1e293b}}
input{{
  width:100%;
  padding:14px 16px;
  border:1px solid var(--line);
  border-radius:14px;
  background:#fff;
  color:var(--ink);
  font-size:15px;
  outline:none;
  transition:border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}}
input:focus{{
  border-color:rgba(15,118,110,.55);
  box-shadow:0 0 0 4px rgba(15,118,110,.12);
  transform:translateY(-1px);
}}
input::placeholder{{color:#94a3b8}}
.password-wrap{{position:relative}}
.password-wrap input{{padding-right:84px}}
.password-toggle{{
  position:absolute;
  right:10px;
  top:50%;
  transform:translateY(-50%);
  min-width:62px;
  background:#fff;
  color:#0f172a;
  border:1px solid var(--line);
  padding:7px 10px;
  border-radius:10px;
  font-size:12px;
  font-weight:700;
  cursor:pointer;
}}
.password-toggle:hover{{background:#f8fafc}}
.submit{{
  margin-top:4px;
  padding:14px 18px;
  border:0;
  border-radius:14px;
  background:linear-gradient(135deg, var(--brand), var(--brand-deep));
  color:#fff;
  font-size:15px;
  font-weight:700;
  letter-spacing:.01em;
  cursor:pointer;
  box-shadow:0 14px 28px rgba(15,118,110,.22);
  transition:transform .18s ease, box-shadow .18s ease, filter .18s ease;
}}
.submit:hover{{transform:translateY(-1px);box-shadow:0 18px 34px rgba(15,118,110,.28);filter:saturate(1.05)}}
.footnote{{margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.6}}
.meta{{
  margin-top:16px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  flex-wrap:wrap;
}}
.credit{{
  margin:0;
  color:#64748b;
  font-size:12px;
  line-height:1.5;
}}
.github-link{{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:7px 10px;
  border-radius:999px;
  border:1px solid var(--line);
  background:#fff;
  color:#334155;
  font-size:12px;
  font-weight:700;
  text-decoration:none;
  transition:border-color .18s ease, background .18s ease, color .18s ease;
}}
.github-link:hover{{
  border-color:rgba(15,118,110,.35);
  background:#f8fffe;
  color:var(--brand-deep);
}}
@media (max-width: 900px) {{
  .frame{{grid-template-columns:1fr}}
  .hero{{padding:36px 28px}}
  .card{{padding:34px 24px 36px}}
  .hero h1{{font-size:32px}}
}}
</style></head>
<body><div class="shell"><div class="frame">
<section class="hero">
  <div class="eyebrow">Secure Remote Access</div>
  <h1>Server Installer Dashboard</h1>
  <p>Manage IIS, .NET hosting, S3 services, and Mongo deployments from one place with a cleaner, safer remote sign-in experience.</p>
  <ul class="points">
    <li><strong>System-backed authentication</strong>Use this machine's operating system account to access the dashboard remotely.</li>
    <li><strong>Operational visibility</strong>Track service state, resource usage, and installer output from a single control surface.</li>
    <li><strong>Built for administration</strong>Fast access to the tools you need without exposing a separate dashboard password store.</li>
  </ul>
</section>
<section class="card">
  <div class="card-inner">
    <p class="kicker">Administrator Sign In</p>
    <h2>Open the dashboard</h2>
    <p class="lead">Remote access requires the OS username and password for this computer.</p>
    {msg}
    <form method="post" action="/login" autocomplete="on">
      <div class="field">
        <label for="username">Server Username</label>
        <input id="username" name="username" placeholder="DOMAIN\\username or local account" autocomplete="username" required>
      </div>
      <div class="field">
        <label for="password">Server Password</label>
        <div class="password-wrap">
          <input id="password" type="password" name="password" autocomplete="current-password" placeholder="Enter your OS password" required>
          <button type="button" class="password-toggle" data-password-toggle>Show</button>
        </div>
      </div>
      <button type="submit" class="submit">Open Dashboard</button>
    </form>
    <p class="footnote">Localhost access does not require this sign-in screen. This login is only for remote dashboard access.</p>
    <div class="meta">
      <p class="credit">Created by Keyhan Azarjoo</p>
      <a class="github-link" href="https://github.com/keyhan-azarjoo/Server-Installer" target="_blank" rel="noopener noreferrer">Project GitHub</a>
    </div>
  </div>
</section>
</div></div>
<script>
document.querySelectorAll('[data-password-toggle]').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var wrap = btn.closest('.password-wrap');
    var input = wrap ? wrap.querySelector('input[type="password"], input[type="text"]') : null;
    if (!input) return;
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.textContent = show ? 'Hide' : 'Show';
  }});
}});
var firstInput = document.getElementById('username');
if (firstInput) firstInput.focus();
</script>
</body></html>"""


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
  <script crossorigin src="https://unpkg.com/@mui/icons-material@5.16.14/umd/material-ui-icons.production.min.js"></script>
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
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--cert", default="")
    parser.add_argument("--key", default="")
    args = parser.parse_args()

    if not args.https:
        print("Dashboard requires HTTPS. Start it with start-dashboard.ps1 or start-dashboard.sh.")
        return

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as ex:
        print(f"Failed to bind dashboard on {args.host}:{args.port} -> {ex}")
        if getattr(ex, "errno", None) in (13,):
            print("Hint: Port requires elevated privileges. Try a higher port (e.g. 8090) or run as root/admin.")
        if getattr(ex, "errno", None) in (98, 10048):
            print("Hint: Port is already in use by another process. Choose another port.")
        return

    use_https = args.https
    scheme = "https" if use_https else "http"

    if use_https:
        cert_path = args.cert
        key_path = args.key
        if not cert_path or not key_path:
            print("HTTPS enabled but cert/key not provided. Set --cert and --key.")
            return
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
        except Exception as ex:
            print(f"Failed to enable HTTPS: {ex}")
            return

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
