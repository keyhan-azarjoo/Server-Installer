import ipaddress
import os
import re
import socket
import subprocess
from pathlib import Path

from constants import (
    PYTHON_JUPYTER_STATE_FILE,
    WEBSITE_STATE_FILE,
    WINDOWS_LOCALS3_STATE,
)
from utils import command_exists, run_capture, run_process, _read_json_file, _sudo_prefix
from system_info import get_listening_ports

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


