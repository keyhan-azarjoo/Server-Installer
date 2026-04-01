import ctypes
import ipaddress
import json
import os
import platform
import re
import socket
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

from constants import WINDOWS_LOCALS3_STATE
from utils import command_exists, run_capture, _read_json_file

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
