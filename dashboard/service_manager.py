import getpass
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from constants import (
    PROXY_NATIVE_STATE,
    PROXY_ROOT,
    PROXY_WINDOWS_STATE,
    SAM3_STATE_DIR,
    SAM3_STATE_FILE,
    SAM3_SYSTEMD_SERVICE,
    SERVER_INSTALLER_DATA,
    WEBSITE_STATE_FILE,
    WINDOWS_LOCALS3_STATE,
    PYTHON_STATE_FILE,
    PYTHON_API_STATE_FILE,
    PYTHON_JUPYTER_STATE_FILE,
)
from utils import _read_json_file, _write_json_file, command_exists, run_capture, run_process, _sudo_prefix
from system_info import (
    choose_service_host,
    get_cpu_usage_percent,
    get_docker_info,
    get_dotnet_info,
    get_iis_info,
    get_ip_addresses,
    get_listening_ports,
    get_memory_info,
    get_mongo_info,
    get_network_totals,
    get_public_ipv4,
    get_uptime_seconds,
    get_windows_locals3_host,
    _get_docker_container_details,
    _urls_from_windows_locals3_log,
)
from python_manager import _linux_systemd_unit_status, _python_state_service_item, get_python_info
from website_manager import get_website_info, _website_state_payload, _website_service_items
from mongo_manager import get_windows_native_mongo_info
from ai_services import (
    _get_ai_service_info,
    _is_ollama_name,
    _is_tgwui_name,
    _is_comfyui_name,
    _is_whisper_name,
    _is_piper_name,
    get_ollama_info,
    get_openclaw_info,
    get_lmstudio_info,
    get_tgwui_info,
    get_comfyui_info,
    get_whisper_info,
    get_piper_info,
)

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

    # Generic AI services — route delete to dedicated cleanup functions
    if _is_tgwui_name(svc_name) and action == "delete":
        code, out = run_tgwui_delete(); return code == 0, out
    if _is_comfyui_name(svc_name) and action == "delete":
        code, out = run_comfyui_delete(); return code == 0, out
    if _is_whisper_name(svc_name) and action == "delete":
        code, out = run_whisper_delete(); return code == 0, out
    if _is_piper_name(svc_name) and action == "delete":
        code, out = run_piper_delete(); return code == 0, out

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

