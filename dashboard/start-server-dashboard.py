#!/usr/bin/env python3
import argparse
import ctypes
import json
import re
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


REPO = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
DASHBOARD_LOCAL_ROOT = os.environ.get("SERVER_INSTALLER_LOCAL_ROOT", "").strip()
DASHBOARD_FILES = [
    "dashboard/start-server-dashboard.py",
    "dashboard/server_installer_dashboard.py",
    "dashboard/ui/components.js",
    "dashboard/ui/app.js",
]
LINUX_SERVICE_NAME = "server-installer-dashboard.service"


def is_repo_layout(root: Path) -> bool:
    return (root / "dashboard" / "server_installer_dashboard.py").exists()


def cache_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("ProgramData", "C:/ProgramData"))
        return base / "Server-Installer"
    return Path.home() / ".server-installer"


def ensure_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    local_root = Path(DASHBOARD_LOCAL_ROOT) if DASHBOARD_LOCAL_ROOT else None
    use_local = bool(local_root and is_repo_layout(local_root))
    for rel in DASHBOARD_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = target.with_suffix(target.suffix + ".download")
        try:
            print(f"Syncing required file: {rel}")
            if use_local:
                src = local_root / rel
                if not src.exists():
                    raise RuntimeError(f"Missing local file: {src}")
                tmp_target.parent.mkdir(parents=True, exist_ok=True)
                if tmp_target.exists():
                    tmp_target.unlink(missing_ok=True)
                tmp_target.write_bytes(src.read_bytes())
                os.replace(tmp_target, target)
            else:
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


def can_bind(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
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


def check_local_http(port: int, attempts: int = 8, delay: float = 0.5):
    url = f"http://127.0.0.1:{port}/"
    last_error = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return True, f"{resp.status}"
        except Exception as ex:
            last_error = ex
            time.sleep(delay)
    return False, str(last_error) if last_error else "Unknown error"


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


def resolve_root() -> Path:
    if DASHBOARD_LOCAL_ROOT:
        local_root = Path(DASHBOARD_LOCAL_ROOT)
        if is_repo_layout(local_root):
            return local_root
    cwd_root = Path.cwd()
    script_root = Path(__file__).resolve().parents[1]
    if is_repo_layout(script_root):
        return script_root
    if is_repo_layout(cwd_root):
        return cwd_root
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
    proc = subprocess.Popen(cmd, cwd=str(root))

    ok, detail = check_local_http(selected_port)
    print("Startup diagnostics:")
    print(f"- Bind host: {bind_host}")
    print(f"- Selected port: {selected_port}")
    print(f"- Dashboard URL: http://{display_host}:{selected_port}")
    print(f"- Local URL: http://127.0.0.1:{selected_port}")
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
    print(f"Dashboard ready: http://{display_host}:{selected_port}")
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

    unit_path = Path("/etc/systemd/system") / LINUX_SERVICE_NAME
    unit_text = f"""[Unit]
Description=Server Installer Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart={sys.executable} {script_path} --run-server --host {bind_host} --port {selected_port}
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

    ok, detail = check_local_http(selected_port)
    print(f"OS detected: {platform.system()}")
    print(f"Service: {LINUX_SERVICE_NAME} (enabled, restarted)")
    print(f"Dashboard URL: http://{display_host}:{selected_port}")
    print(f"Local URL: http://127.0.0.1:{selected_port}")
    if ok:
        print(f"Local HTTP check: PASS (HTTP {detail})")
    else:
        print(f"Local HTTP check: FAIL ({detail})")
        print(f"Inspect logs: journalctl -u {LINUX_SERVICE_NAME} -n 120 --no-pager")
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

    python_exe = sys.executable
    task_name = "ServerInstallerDashboard"
    task_cmd = f"\"{python_exe}\" \"{script_path}\" --run-server --host {bind_host} --port {selected_port}"
    rc, out = run_capture(
        [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/SC",
            "ONSTART",
            "/RL",
            "HIGHEST",
            "/RU",
            "SYSTEM",
            "/TR",
            task_cmd,
            "/F",
        ],
        timeout=30,
    )
    if rc != 0:
        print(f"schtasks /Create failed:\n{out}", file=sys.stderr)
        return 1
    run_capture(["schtasks", "/Run", "/TN", task_name], timeout=20)

    state_file = root / "dashboard" / "service-state.json"
    state_file.write_text(
        json.dumps(
            {
                "service": task_name,
                "root": str(root),
                "host": bind_host,
                "port": selected_port,
                "updated_at": int(time.time()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"OS detected: {platform.system()}")
    print(f"Service: {task_name} (scheduled task, enabled)")
    print(f"Dashboard URL: http://{display_host}:{selected_port}")
    print(f"Local URL: http://127.0.0.1:{selected_port}")
    print("")
    print(f"Dashboard ready: http://{display_host}:{selected_port}")
    print("Re-running this same command will update files and restart the service.")
    return 0


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
    args = parser.parse_args()

    if relaunch_as_admin_if_needed():
        return 0

    display_host = preferred_host(args.host)
    bind_host = args.host
    if (not bind_host) or bind_host in ("auto", "0.0.0.0"):
        bind_host = "0.0.0.0"

    root = resolve_root()
    if args.run_server:
        return run_dashboard_foreground(root, bind_host, args.port, display_host, preclean=False)

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
