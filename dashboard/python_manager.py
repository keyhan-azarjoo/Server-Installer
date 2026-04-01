import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from constants import (
    JUPYTER_SYSTEMD_SERVICE,
    PYTHON_API_HOST_TEMPLATE,
    PYTHON_API_STATE_FILE,
    PYTHON_IGNORED_FILE,
    PYTHON_JUPYTER_STATE_FILE,
    PYTHON_STATE_DIR,
    PYTHON_STATE_FILE,
    PYTHON_WINDOWS_INSTALLER,
    PYTHON_UNIX_INSTALLER,
    SERVER_INSTALLER_DATA,
)
from utils import (
    _read_json_file,
    _read_json_list,
    _write_json_file,
    _write_json_list,
    command_exists,
    run_capture,
    run_process,
    upload_root_dir,
)

def resolve_windows_python():
    env_override = os.environ.get("SERVER_INSTALLER_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        return env_override
    state = _read_json_file(PYTHON_STATE_FILE)
    managed = str(state.get("python_executable") or "").strip()
    if managed and Path(managed).exists():
        return managed
    embedded = SERVER_INSTALLER_DATA / "python" / "python.exe"
    if embedded.exists():
        return str(embedded)
    return sys.executable

def _normalize_python_version(version_text):
    raw = str(version_text or "").strip()
    if not raw:
        return ""
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
    if not match:
        return raw
    return match.group(1)


def _python_version_key(version_text):
    normalized = _normalize_python_version(version_text)
    parts = normalized.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else normalized


def _python_scripts_dir(python_exe):
    exe_path = Path(str(python_exe or "").strip())
    if not exe_path.exists():
        return ""
    scripts_dir = exe_path.parent / "Scripts"
    if scripts_dir.exists():
        return str(scripts_dir)
    bin_dir = exe_path.parent / "bin"
    if bin_dir.exists():
        return str(bin_dir)
    return ""


def _default_python_notebook_dir():
    if os.name == "nt":
        preferred = Path(os.environ.get("SystemDrive", "C:")) / "ServerInstaller-Notebooks"
    elif hasattr(os, "geteuid") and os.geteuid() == 0:
        preferred = Path("/root") / "notebooks"
    else:
        preferred = Path.home() / "notebooks"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return str(preferred)
    except Exception:
        return str(ROOT)


def _resolve_python_notebook_dir(value=""):
    raw = str(value or "").strip()
    if not raw:
        raw = _default_python_notebook_dir()
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(path)


def _resolve_python_from_launcher(version_hint=""):
    version_key = _python_version_key(version_hint)
    if os.name == "nt" and command_exists("py"):
        cmd = ["py"]
        if version_key:
            cmd.append(f"-{version_key}")
        cmd += ["-c", "import sys; print(sys.executable); print(sys.version.split()[0])"]
        rc, out = run_capture(cmd, timeout=20)
        if rc == 0 and out:
            lines = [x.strip() for x in out.splitlines() if x.strip()]
            if lines and Path(lines[0]).exists():
                return {
                    "python_executable": lines[0],
                    "python_version": lines[1] if len(lines) > 1 else "",
                }
    return {}


def _resolve_any_python():
    state = _read_json_file(PYTHON_STATE_FILE)
    managed = str(state.get("python_executable") or "").strip()
    if managed and Path(managed).exists():
        return {
            "python_executable": managed,
            "python_version": str(state.get("python_version") or "").strip(),
        }
    launcher = _resolve_python_from_launcher("")
    if launcher:
        return launcher
    current = resolve_windows_python() if os.name == "nt" else sys.executable
    if current and Path(current).exists():
        rc, out = run_capture([current, "--version"], timeout=10)
        return {
            "python_executable": current,
            "python_version": _normalize_python_version(out or ""),
        }
    return {}


def _python_env(python_executable):
    env = os.environ.copy()
    exe = str(python_executable or "").strip()
    if not exe:
        return env
    parts = []
    exe_dir = str(Path(exe).parent)
    if exe_dir:
        parts.append(exe_dir)
    scripts_dir = _python_scripts_dir(exe)
    if scripts_dir:
        parts.append(scripts_dir)
    if parts:
        env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
    env["SERVER_INSTALLER_PYTHON"] = exe
    return env


def _python_run_capture(args, timeout=30):
    resolved = _resolve_any_python()
    python_exe = str(resolved.get("python_executable") or "").strip()
    if not python_exe:
        return 1, "Managed Python is not installed."
    return run_capture([python_exe] + list(args), timeout=timeout)


def _hash_jupyter_password(python_executable, password_text):
    python_exe = str(python_executable or "").strip()
    password_value = str(password_text or "")
    if not python_exe or not password_value:
        return ""
    rc, out = run_capture(
        [
            python_exe,
            "-c",
            (
                "from jupyter_server.auth import passwd; "
                f"print(passwd({password_value!r}))"
            ),
        ],
        timeout=30,
    )
    if rc != 0:
        return ""
    return str(out or "").strip().splitlines()[-1].strip()


def _ensure_windows_jupyter_https_assets(python_executable, host):
    python_exe = str(python_executable or "").strip()
    host_value = str(host or "").strip() or "localhost"
    if os.name != "nt" or not python_exe:
        return "", ""
    https_dir = PYTHON_STATE_DIR / "https"
    cert_path = https_dir / "jupyter-cert.pem"
    key_path = https_dir / "jupyter-key.pem"
    try:
        https_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "", ""
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    rc_import, _ = run_capture([python_exe, "-c", "import trustme"], timeout=20)
    if rc_import != 0:
        rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "trustme"], timeout=180)
        if rc_install != 0:
            return "", ""

    script = (
        "from pathlib import Path\n"
        "import trustme\n"
        f"cert_path = Path(r'''{str(cert_path)}''')\n"
        f"key_path = Path(r'''{str(key_path)}''')\n"
        f"host = {host_value!r}\n"
        "ca = trustme.CA()\n"
        "server_cert = ca.issue_cert(host, 'localhost', '127.0.0.1')\n"
        "server_cert.cert_chain_pems[0].write_to_path(cert_path)\n"
        "server_cert.private_key_pem.write_to_path(key_path)\n"
        "print(cert_path)\n"
        "print(key_path)\n"
    )
    rc, out = run_capture([python_exe, "-c", script], timeout=60)
    if rc != 0 or not cert_path.exists() or not key_path.exists():
        return "", ""
    return str(cert_path), str(key_path)


def _ensure_windows_jupyter_proxy_support(python_executable):
    python_exe = str(python_executable or "").strip()
    if os.name != "nt" or not python_exe:
        return False
    rc_import, _ = run_capture([python_exe, "-c", "import aiohttp"], timeout=20)
    if rc_import == 0:
        return True
    rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "aiohttp"], timeout=240)
    return rc_install == 0


def _ensure_windows_jupyter_proxy_script():
    script_path = PYTHON_STATE_DIR / "serverinstaller_jupyter_proxy.py"
    script_text = r'''import argparse
import asyncio
import base64
import ssl
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


def _unauthorized():
    response = web.Response(status=401, text="Unauthorized")
    response.headers["WWW-Authenticate"] = 'Basic realm="Restricted Jupyter"'
    return response


def _authorized(request, username, password):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except Exception:
        return False
    provided_user, _, provided_pass = decoded.partition(":")
    return provided_user == username and provided_pass == password


def _request_headers(request, backend_host, backend_port):
    headers = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in {"host", "authorization", "connection", "upgrade", "proxy-connection", "keep-alive", "transfer-encoding"}:
            continue
        headers[key] = value
    headers["Host"] = request.host
    headers["X-Forwarded-For"] = request.remote or ""
    headers["X-Forwarded-Proto"] = "https"
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Port"] = str(request.url.port or 443)
    headers["X-Real-IP"] = request.remote or ""
    return headers


def _response_headers(headers):
    result = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"content-length", "transfer-encoding", "connection", "keep-alive", "content-encoding"}:
            continue
        result[key] = value
    return result


async def _proxy_http(request, session, backend_base, backend_host, backend_port, username, password):
    if not _authorized(request, username, password):
        return _unauthorized()
    target_url = f"{backend_base}{request.rel_url}"
    body = await request.read()
    async with session.request(
        request.method,
        target_url,
        headers=_request_headers(request, backend_host, backend_port),
        data=body if body else None,
        allow_redirects=False,
    ) as upstream:
        payload = await upstream.read()
        return web.Response(
            status=upstream.status,
            headers=_response_headers(upstream.headers),
            body=payload,
        )


async def _pump_client_to_upstream(ws_client, ws_upstream):
    async for msg in ws_client:
        if msg.type == WSMsgType.TEXT:
            await ws_upstream.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            await ws_upstream.send_bytes(msg.data)
        elif msg.type == WSMsgType.PING:
            await ws_upstream.ping()
        elif msg.type == WSMsgType.PONG:
            await ws_upstream.pong()
        elif msg.type == WSMsgType.CLOSE:
            await ws_upstream.close()
            break


async def _pump_upstream_to_client(ws_client, ws_upstream):
    async for msg in ws_upstream:
        if msg.type == WSMsgType.TEXT:
            await ws_client.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            await ws_client.send_bytes(msg.data)
        elif msg.type == WSMsgType.PING:
            await ws_client.ping()
        elif msg.type == WSMsgType.PONG:
            await ws_client.pong()
        elif msg.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            await ws_client.close()
            break


async def _proxy_ws(request, session, backend_ws_base, backend_host, backend_port, username, password):
    if not _authorized(request, username, password):
        return _unauthorized()
    ws_client = web.WebSocketResponse(autoping=True, autoclose=True, max_msg_size=0)
    await ws_client.prepare(request)
    target_url = f"{backend_ws_base}{request.rel_url}"
    async with session.ws_connect(
        target_url,
        headers=_request_headers(request, backend_host, backend_port),
        autoclose=True,
        autoping=True,
        max_msg_size=0,
    ) as ws_upstream:
        await asyncio.gather(
            _pump_client_to_upstream(ws_client, ws_upstream),
            _pump_upstream_to_client(ws_client, ws_upstream),
        )
    return ws_client


async def _handle(request):
    app = request.app
    connection_header = request.headers.get("Connection", "")
    upgrade_header = request.headers.get("Upgrade", "")
    wants_ws = "upgrade" in connection_header.lower() and upgrade_header.lower() == "websocket"
    if wants_ws and request.path == "/ws/pty":
        return await _handle_pty_ws(request, app["username"], app["password"])
    if wants_ws:
        return await _proxy_ws(
            request,
            app["session"],
            app["backend_ws_base"],
            app["backend_host"],
            app["backend_port"],
            app["username"],
            app["password"],
        )
    return await _proxy_http(
        request,
        app["session"],
        app["backend_base"],
        app["backend_host"],
        app["backend_port"],
        app["username"],
        app["password"],
    )


async def _handle_pty_ws(request, username, password):
    """Spawn a real shell PTY and proxy I/O over WebSocket."""
    if not _authorized(request, username, password):
        return web.Response(status=401, text="Unauthorized")
    cwd = (request.query.get("cwd", "") or "").strip() or None
    cols = max(10, min(512, int(request.query.get("cols", 80) or 80)))
    rows = max(2, min(200, int(request.query.get("rows", 24) or 24)))
    ws = web.WebSocketResponse(autoping=False, autoclose=False, max_msg_size=0)
    await ws.prepare(request)
    loop = asyncio.get_event_loop()
    if os.name == "nt":
        try:
            import winpty as _winpty
        except ImportError:
            await ws.send_str("\r\nError: pywinpty not installed.\r\n")
            await ws.close()
            return ws
        shell = os.environ.get("COMSPEC", "cmd.exe")
        try:
            proc = _winpty.PtyProcess.spawn(shell, dimensions=(rows, cols), cwd=cwd)
        except Exception as ex:
            await ws.send_str(f"\r\nFailed to start terminal: {ex}\r\n")
            await ws.close()
            return ws

        async def _pty_read():
            try:
                while not ws.closed:
                    try:
                        data = await loop.run_in_executor(None, lambda: proc.read(4096))
                        if data:
                            await ws.send_str(data)
                        elif not proc.isalive():
                            break
                    except EOFError:
                        break
                    except Exception:
                        break
            except Exception:
                pass
            if not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def _pty_write():
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        d = msg.data
                        if d.startswith('{"type":"resize"'):
                            try:
                                r = json.loads(d)
                                if r.get("type") == "resize":
                                    proc.setwinsize(max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))))
                            except Exception:
                                pass
                        else:
                            try:
                                proc.write(d)
                            except Exception:
                                break
                    elif msg.type == WSMsgType.BINARY:
                        try:
                            proc.write(msg.data.decode("utf-8", errors="replace"))
                        except Exception:
                            break
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                        break
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

        await asyncio.gather(_pty_read(), _pty_write(), return_exceptions=True)
        try:
            proc.terminate()
        except Exception:
            pass
    else:
        try:
            import pty as _pty
            import termios as _termios
            import fcntl as _fcntl
            import struct as _struct
        except ImportError as ex:
            await ws.send_str(f"\r\nError: {ex}\r\n")
            await ws.close()
            return ws
        shell = os.environ.get("SHELL", "/bin/bash")
        master_fd = None
        slave_fd = None
        proc = None
        try:
            master_fd, slave_fd = _pty.openpty()
            try:
                _fcntl.ioctl(slave_fd, _termios.TIOCSWINSZ, _struct.pack("HHHH", rows, cols, 0, 0))
            except Exception:
                pass
            env = {**os.environ, "TERM": "xterm-256color"}
            proc = subprocess.Popen(
                [shell], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                cwd=cwd, env=env, close_fds=True, start_new_session=True,
            )
            os.close(slave_fd)
            slave_fd = None
        except Exception as ex:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except Exception:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except Exception:
                    pass
            await ws.send_str(f"\r\nFailed to start terminal: {ex}\r\n")
            await ws.close()
            return ws

        async def _pty_read():
            try:
                while not ws.closed:
                    try:
                        data = await loop.run_in_executor(None, lambda fd=master_fd: os.read(fd, 4096))
                        if data:
                            await ws.send_bytes(data)
                    except (OSError, IOError):
                        break
            except Exception:
                pass
            if not ws.closed:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def _pty_write():
            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        d = msg.data
                        if d.startswith('{"type":"resize"'):
                            try:
                                r = json.loads(d)
                                if r.get("type") == "resize":
                                    _fcntl.ioctl(master_fd, _termios.TIOCSWINSZ,
                                                 _struct.pack("HHHH", max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))), 0, 0))
                            except Exception:
                                pass
                        else:
                            try:
                                os.write(master_fd, d.encode())
                            except Exception:
                                break
                    elif msg.type == WSMsgType.BINARY:
                        try:
                            os.write(master_fd, msg.data)
                        except Exception:
                            break
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                        break
            except Exception:
                pass
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                os.close(master_fd)
            except Exception:
                pass

        await asyncio.gather(_pty_read(), _pty_write(), return_exceptions=True)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            os.close(master_fd)
        except Exception:
            pass
    return ws


async def _create_app(args):
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    app = web.Application(client_max_size=1024**3)
    app["username"] = args.username
    app["password"] = args.password
    app["backend_host"] = args.backend_host
    app["backend_port"] = args.backend_port
    app["backend_base"] = f"http://{args.backend_host}:{args.backend_port}"
    app["backend_ws_base"] = f"ws://{args.backend_host}:{args.backend_port}"
    app["session"] = ClientSession(timeout=timeout)
    app.router.add_route("*", "/{path_info:.*}", _handle)

    async def _cleanup(_app):
        await _app["session"].close()

    app.on_cleanup.append(_cleanup)
    return app


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--backend-host", required=True)
    parser.add_argument("--backend-port", type=int, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    args = parser.parse_args()

    app = await _create_app(args)
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(args.certfile, args.keyfile)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.listen_host, args.listen_port, ssl_context=ssl_context)
    await site.start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(_main())
'''
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_text, encoding="utf-8")
    return str(script_path)


def _python_process_running(pid):
    try:
        pid_num = int(pid)
    except Exception:
        return False
    if pid_num <= 0:
        return False
    if os.name == "nt":
        rc, out = run_capture(["tasklist", "/FI", f"PID eq {pid_num}"], timeout=15)
        return rc == 0 and str(pid_num) in str(out or "")
    try:
        os.kill(pid_num, 0)
        return True
    except Exception:
        return False


def _windows_process_cmdline(pid):
    if os.name != "nt":
        return ""
    try:
        pid_num = int(pid)
    except Exception:
        return ""
    if pid_num <= 0:
        return ""
    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid_num}\").CommandLine",
        ],
        timeout=20,
    )
    return str(out or "").strip() if rc == 0 else ""


def _windows_process_matches_managed_jupyter(pid, port=None):
    if os.name != "nt":
        return False
    cmdline = _windows_process_cmdline(pid)
    if not cmdline:
        return False
    cmdline_lower = cmdline.lower()
    if "serverinstaller_jupyter_proxy.py" in cmdline_lower:
        target_port = str(port or _read_json_file(PYTHON_JUPYTER_STATE_FILE).get("port") or "").strip()
        if target_port.isdigit():
            return f"--listen-port {target_port}" in cmdline_lower or f"--listen-port={target_port}" in cmdline_lower
        return True
    if "jupyter" not in cmdline_lower or "lab" not in cmdline_lower:
        return False

    python_state = _read_json_file(PYTHON_STATE_FILE)
    python_executable = str(python_state.get("python_executable") or "").strip().lower()
    jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    state_port = str(jupyter_state.get("port") or python_state.get("jupyter_port") or "").strip()
    target_port = str(port or state_port or "").strip()

    if python_executable:
        normalized_cmd = cmdline_lower.replace("/", "\\")
        normalized_python = python_executable.replace("/", "\\")
        if normalized_python not in normalized_cmd:
            return False

    if target_port.isdigit():
        port_flag = f"--serverapp.port={target_port}"
        if port_flag not in cmdline_lower and f":{target_port}" not in cmdline_lower:
            return False

    return True


def _linux_systemd_unit_status(unit_name):
    unit = str(unit_name or "").strip()
    if not unit or os.name == "nt" or not command_exists("systemctl"):
        return {}
    rc_active, out_active = run_capture(["systemctl", "is-active", unit], timeout=15)
    rc_enabled, out_enabled = run_capture(["systemctl", "is-enabled", unit], timeout=15)
    active = str(out_active or "").strip()
    enabled = str(out_enabled or "").strip()
    return {
        "active": active,
        "enabled": enabled,
        "running": rc_active == 0 and active == "active",
        "autostart": enabled in ("enabled", "static", "indirect"),
    }


def _detect_python_versions():
    versions = []
    seen = set()
    ignored = {str(item).strip() for item in _read_json_list(PYTHON_IGNORED_FILE) if str(item).strip()}

    def add_candidate(cmd, managed=False):
        rc, out = run_capture(cmd, timeout=20)
        if rc != 0 or not out:
            return
        lines = [line.strip() for line in str(out).splitlines() if line.strip()]
        if len(lines) < 2:
            return
        exe = lines[0]
        version = _normalize_python_version(lines[1])
        if not exe or not version:
            return
        if exe in ignored:
            return
        key = (exe.lower(), version)
        if key in seen:
            return
        seen.add(key)
        versions.append({
            "version": version,
            "python_executable": exe,
            "managed": bool(managed),
        })

    state = _read_json_file(PYTHON_STATE_FILE)
    managed_exe = str(state.get("python_executable") or "").strip()
    managed_ver = str(state.get("python_version") or "").strip()
    if managed_exe and Path(managed_exe).exists():
        add_candidate([managed_exe, "-c", "import sys; print(sys.executable); print(sys.version.split()[0])"], managed=True)
    if os.name == "nt" and command_exists("py"):
        for version in ("3.13", "3.12", "3.11", "3.10", ""):
            cmd = ["py"]
            if version:
                cmd.append(f"-{version}")
            cmd += ["-c", "import sys; print(sys.executable); print(sys.version.split()[0])"]
            add_candidate(cmd, managed=(managed_ver and _python_version_key(version) == _python_version_key(managed_ver)))
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
            resolved = shutil.which(name)
            if not resolved:
                continue
            add_candidate([resolved, "-c", "import sys; print(sys.executable); print(sys.version.split()[0])"], managed=(managed_exe and str(Path(resolved)) == managed_exe))
    versions.sort(key=lambda item: tuple(int(part) if part.isdigit() else 0 for part in (_normalize_python_version(item.get("version") or "").split("."))), reverse=True)
    return versions


def _python_state_service_item(info):
    items = []
    if info.get("installed"):
        for runtime in info.get("python_versions") or []:
            is_managed = bool(runtime.get("managed"))
            items.append({
                "kind": "python_installation" if is_managed else "python_version",
                "name": f"python-{runtime.get('version') or 'unknown'}",
                "display_name": "Managed Python" if is_managed else "Detected Python",
                "status": "installed",
                "sub_status": runtime.get("python_executable") or "",
                "detail": runtime.get("python_executable") or "",
                "autostart": False,
                "platform": "windows" if os.name == "nt" else "linux",
                "urls": [],
                "ports": [],
                "manageable": False,
                "deletable": True,
            })
    if info.get("jupyter_running"):
        port_text = str(info.get("jupyter_port") or "").strip()
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        service_kind = "service" if os.name != "nt" and info.get("service_mode") else "python_runtime"
        service_name = JUPYTER_SYSTEMD_SERVICE if service_kind == "service" else "serverinstaller-python-jupyter"
        items.append({
            "kind": service_kind,
            "name": service_name,
            "display_name": "Managed Jupyter Lab",
            "status": "running",
            "sub_status": str(info.get("service_sub_status") or "running"),
            "autostart": bool(info.get("service_autostart")),
            "platform": "windows" if os.name == "nt" else "linux",
            "urls": [info.get("jupyter_url")] if info.get("jupyter_url") else [],
            "ports": ports,
            "manageable": True,
            "deletable": True,
        })
    items.extend(_python_api_service_items())
    return items


def _cleanup_managed_jupyter():
    jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    python_state = _read_json_file(PYTHON_STATE_FILE)
    python_executable = str(python_state.get("python_executable") or "").strip()
    jupyter_port = str(jupyter_state.get("port") or python_state.get("jupyter_port") or "").strip()
    stop_python_jupyter()
    if os.name != "nt":
        if command_exists("systemctl"):
            run_capture(["systemctl", "stop", JUPYTER_SYSTEMD_SERVICE], timeout=30)
            run_capture(["systemctl", "disable", JUPYTER_SYSTEMD_SERVICE], timeout=30)
        for path in (
            Path("/etc/systemd/system") / JUPYTER_SYSTEMD_SERVICE,
            Path("/etc/nginx/conf.d") / "serverinstaller-jupyter.conf",
        ):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        cert_dir = Path("/etc/nginx/ssl/serverinstaller-jupyter")
        try:
            if cert_dir.exists():
                shutil.rmtree(cert_dir, ignore_errors=True)
        except Exception:
            pass
        if command_exists("systemctl"):
            run_capture(["systemctl", "daemon-reload"], timeout=30)
            run_capture(["systemctl", "reload", "nginx"], timeout=30)
    elif jupyter_port.isdigit():
        try:
            manage_firewall_port("close", jupyter_port, "tcp")
        except Exception:
            pass
        if python_executable and Path(python_executable).exists():
            uninstall_packages = [
                "jupyterlab",
                "notebook",
                "ipykernel",
                "jupyter-server",
                "jupyterlab-server",
                "jupyter-lsp",
                "jupyter-server-terminals",
                "notebook-shim",
                "jupyter-client",
                "jupyter-core",
                "jupyter-events",
                "nbconvert",
                "nbformat",
                "nbclient",
                "pywinpty",
                "terminado",
            ]
            run_capture(
                [python_executable, "-m", "pip", "uninstall", "-y"] + uninstall_packages,
                timeout=180,
            )
            kernelspec_dir = Path(python_executable).parent / "share" / "jupyter" / "kernels" / "python3"
            try:
                if kernelspec_dir.exists():
                    shutil.rmtree(kernelspec_dir, ignore_errors=True)
            except Exception:
                pass
    for path in (
        PYTHON_JUPYTER_STATE_FILE,
        Path("/etc/nginx/auth/serverinstaller-jupyter.htpasswd"),
        PYTHON_STATE_DIR / "jupyter.log",
    ):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
    for path in (
        PYTHON_STATE_DIR / "jupyter-config",
        PYTHON_STATE_DIR / "jupyter-data",
        PYTHON_STATE_DIR / "jupyter-runtime",
        PYTHON_STATE_DIR / "ipython",
    ):
        try:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
    state = _read_json_file(PYTHON_STATE_FILE)
    for key in (
        "jupyter_installed",
        "jupyter_running",
        "jupyter_url",
        "jupyter_port",
        "jupyter_internal_port",
        "jupyter_username",
        "jupyter_password_hash",
        "jupyter_auth_enabled",
        "jupyter_https_enabled",
        "service_mode",
    ):
        state.pop(key, None)
    _write_json_file(PYTHON_STATE_FILE, state)
    return True, "Managed Jupyter removed."


def _cleanup_managed_python():
    state = _read_json_file(PYTHON_STATE_FILE)
    managed_exe = str(state.get("python_executable") or "").strip()
    managed_root = str(state.get("python_root") or "").strip()
    managed_install = bool(state.get("managed_install"))
    install_method = str(state.get("install_method") or "").strip().lower()
    install_package_id = str(state.get("install_package_id") or "").strip()
    _cleanup_managed_jupyter()
    if os.name == "nt" and managed_install and install_method == "winget" and install_package_id:
        run_capture(
            [
                "winget.exe",
                "uninstall",
                "--id",
                install_package_id,
                "--exact",
                "--silent",
                "--accept-source-agreements",
            ],
            timeout=240,
        )
    if os.name == "nt" and managed_install and managed_root:
        try:
            root_path = Path(managed_root)
            if root_path.exists():
                shutil.rmtree(root_path, ignore_errors=True)
        except Exception:
            pass
    if managed_exe and not managed_install:
        current = _read_json_list(PYTHON_IGNORED_FILE)
        if managed_exe not in current:
            current.append(managed_exe)
        _write_json_list(PYTHON_IGNORED_FILE, current)
    elif managed_exe:
        current = [item for item in _read_json_list(PYTHON_IGNORED_FILE) if str(item).strip() and str(item).strip() != managed_exe]
        _write_json_list(PYTHON_IGNORED_FILE, current)
    try:
        if PYTHON_STATE_DIR.exists():
            shutil.rmtree(PYTHON_STATE_DIR, ignore_errors=True)
    except Exception:
        pass
    return True, "Managed Python removed."


def _hide_detected_python(python_executable):
    path_value = str(python_executable or "").strip()
    if not path_value:
        return False, "A Python executable path is required."
    current = _read_json_list(PYTHON_IGNORED_FILE)
    if path_value not in current:
        current.append(path_value)
        _write_json_list(PYTHON_IGNORED_FILE, current)
    return True, f"Detected Python hidden: {path_value}"


def get_python_info():
    state = _read_json_file(PYTHON_STATE_FILE)
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or state.get("python_executable") or "").strip()
    python_version = str(resolved.get("python_version") or state.get("python_version") or "").strip()
    default_notebook_dir = _resolve_python_notebook_dir(
        state.get("default_notebook_dir") or state.get("notebook_dir") or ""
    )
    info = {
        "installed": bool(python_executable and Path(python_executable).exists()),
        "python_executable": python_executable,
        "python_version": _normalize_python_version(python_version),
        "python_versions": _detect_python_versions(),
        "requested_version": str(state.get("requested_version") or "").strip(),
        "jupyter_installed": False,
        "jupyter_running": False,
        "jupyter_url": "",
        "jupyter_port": str(state.get("jupyter_port") or "").strip(),
        "jupyter_username": str(state.get("jupyter_username") or "").strip(),
        "jupyter_auth_enabled": bool(state.get("jupyter_auth_enabled")),
        "jupyter_https_enabled": bool(state.get("jupyter_https_enabled")),
        "host": str(state.get("host") or "").strip(),
        "scripts_dir": _python_scripts_dir(python_executable),
        "default_notebook_dir": default_notebook_dir,
        "notebook_dir": default_notebook_dir,
        "service_mode": bool(state.get("service_mode")),
        "service_sub_status": "",
        "service_autostart": False,
        "services": [],
    }
    if info["installed"]:
        env = _python_env(python_executable)
        rc_ver, out_ver = run_capture([python_executable, "--version"], timeout=10)
        if rc_ver == 0 and out_ver:
            info["python_version"] = _normalize_python_version(out_ver)
        rc_j, out_j = run_capture([python_executable, "-m", "jupyter", "--version"], timeout=20)
        info["jupyter_installed"] = rc_j == 0 and bool(out_j)
        if out_j:
            info["jupyter_version"] = out_j.splitlines()[0].strip()
        jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
        if os.name != "nt" and (info["service_mode"] or jupyter_state.get("service_name") == JUPYTER_SYSTEMD_SERVICE):
            service_status = _linux_systemd_unit_status(JUPYTER_SYSTEMD_SERVICE)
            info["service_mode"] = True
            info["service_sub_status"] = str(service_status.get("active") or "")
            info["service_autostart"] = bool(service_status.get("autostart"))
            info["jupyter_running"] = bool(service_status.get("running"))
            info["jupyter_port"] = str(jupyter_state.get("port") or state.get("jupyter_port") or info["jupyter_port"] or "").strip()
            info["host"] = str(jupyter_state.get("host") or state.get("host") or info["host"] or "").strip()
            info["jupyter_url"] = str(jupyter_state.get("url") or state.get("jupyter_url") or "").strip()
            info["notebook_dir"] = _resolve_python_notebook_dir(
                jupyter_state.get("notebook_dir") or state.get("notebook_dir") or info["default_notebook_dir"]
            )
            info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
            info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
            info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
            if info["jupyter_installed"] and not info["jupyter_url"] and info["jupyter_port"].isdigit():
                host = info["host"] or choose_service_host()
                info["jupyter_url"] = f"https://{host}:{info['jupyter_port']}/lab"
        else:
            pid = jupyter_state.get("pid")
            if pid and _python_process_running(pid):
                info["jupyter_running"] = True
                info["jupyter_port"] = str(jupyter_state.get("port") or info["jupyter_port"] or "").strip()
                info["host"] = str(jupyter_state.get("host") or info["host"] or "").strip()
                info["jupyter_url"] = str(jupyter_state.get("url") or "").strip()
                info["notebook_dir"] = _resolve_python_notebook_dir(
                    jupyter_state.get("notebook_dir") or info["default_notebook_dir"]
                )
                info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
                info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
                info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
                info["jupyter_pid"] = pid
            elif os.name == "nt":
                port = str(jupyter_state.get("port") or info["jupyter_port"] or "").strip()
                listeners = []
                if port.isdigit():
                    for item in get_listening_ports(limit=5000):
                        proto = str(item.get("proto", "")).lower()
                        if proto.startswith("tcp") and int(item.get("port", 0)) == int(port):
                            listeners.append(item)
                if port.isdigit() and _windows_managed_python_owns_port(port, listeners):
                    info["jupyter_running"] = True
                    info["jupyter_port"] = port
                    info["host"] = str(jupyter_state.get("host") or info["host"] or choose_service_host()).strip()
                    scheme = "https" if (jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled")) else "http"
                    info["jupyter_url"] = str(jupyter_state.get("url") or f"{scheme}://{info['host']}:{port}/lab").strip()
                    info["notebook_dir"] = _resolve_python_notebook_dir(
                        jupyter_state.get("notebook_dir") or info["default_notebook_dir"]
                    )
                    info["jupyter_username"] = str(jupyter_state.get("username") or state.get("jupyter_username") or info["jupyter_username"] or "").strip()
                    info["jupyter_auth_enabled"] = bool(jupyter_state.get("auth_enabled") or state.get("jupyter_auth_enabled"))
                    info["jupyter_https_enabled"] = bool(jupyter_state.get("https_enabled") or state.get("jupyter_https_enabled"))
                    for item in listeners:
                        try:
                            listener_pid = int(str(item.get("pid") or "0"))
                        except Exception:
                            continue
                        if listener_pid > 0 and _windows_process_matches_managed_jupyter(listener_pid, port):
                            jupyter_state["pid"] = listener_pid
                            jupyter_state["running"] = True
                            _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
                            info["jupyter_pid"] = listener_pid
                            break
            else:
                if jupyter_state:
                    jupyter_state["pid"] = None
                    jupyter_state["running"] = False
                    _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
                info["jupyter_url"] = ""
                info["notebook_dir"] = _resolve_python_notebook_dir(
                    jupyter_state.get("notebook_dir") if jupyter_state else info["default_notebook_dir"]
                )
    info["services"] = _python_state_service_item(info)
    return info

def _safe_python_api_name(value, default_name="python-api"):
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._").lower()
    return raw or default_name


def _python_api_source_candidates(source_root):
    root = Path(source_root)
    if not root.exists():
        return []
    blocked = {"__pycache__", ".git", ".venv", "venv", "node_modules", "site-packages"}
    result = []
    for path in root.rglob("*.py"):
        parts = {part.lower() for part in path.parts}
        if blocked & parts:
            continue
        if path.name.lower().startswith("serverinstaller_"):
            continue
        result.append(path)
    return result


def _resolve_python_api_source(source_value, entry_hint="", live_cb=None):
    src = str(source_value or "").strip()
    if not src:
        raise RuntimeError("Source path/URL, uploaded file, or uploaded folder is required.")

    source_path = Path(src)
    if src.lower().startswith(("http://", "https://")):
        source_root = prepare_source_dir(src, live_cb=live_cb)
        source_path = Path(source_root)
    elif source_path.is_dir():
        pass
    elif source_path.is_file():
        pass
    else:
        source_root = prepare_source_dir(src, live_cb=live_cb)
        source_path = Path(source_root)

    if source_path.is_file():
        if source_path.suffix.lower() != ".py":
            raise RuntimeError("Direct file input must point to a Python .py file.")
        return source_path, source_path, source_path.name

    candidates = _python_api_source_candidates(source_path)
    if not candidates:
        raise RuntimeError("No Python .py files were found in the selected source.")

    if entry_hint:
        normalized = entry_hint.replace("\\", "/").strip().lstrip("/")
        if "/" not in normalized:
            by_name = [path for path in candidates if path.name.lower() == normalized.lower()]
            if by_name:
                by_name.sort(key=lambda p: (len(p.parts), str(p).lower()))
                preferred = by_name[0]
                return source_path, preferred, preferred.relative_to(source_path).as_posix()
        preferred = (source_path / normalized).resolve()
        try:
            preferred.relative_to(source_path.resolve())
        except Exception:
            raise RuntimeError("Main file must stay inside the selected source folder.")
        if not preferred.exists() or not preferred.is_file():
            raise RuntimeError(f"Main file was not found: {normalized}")
        return source_path, preferred, preferred.relative_to(source_path).as_posix()

    preferred_names = ["main.py", "app.py", "server.py", "api.py", "run.py", "wsgi.py", "asgi.py"]
    candidates.sort(key=lambda p: (preferred_names.index(p.name.lower()) if p.name.lower() in preferred_names else 999, len(p.parts), str(p).lower()))
    chosen = candidates[0]
    return source_path, chosen, chosen.relative_to(source_path).as_posix()


def _copy_python_api_source(source_root, entry_file, deploy_root):
    source_root = Path(source_root)
    entry_file = Path(entry_file)
    deploy_root = Path(deploy_root)
    app_root = deploy_root / "app"
    if app_root.exists():
        shutil.rmtree(app_root, ignore_errors=True)
    app_root.mkdir(parents=True, exist_ok=True)

    if source_root.is_file():
        target_file = app_root / entry_file.name
        shutil.copy2(source_root, target_file)
        return target_file, entry_file.name

    if entry_file.parent == source_root and len(list(source_root.iterdir())) == 1 and entry_file.is_file():
        target_file = app_root / entry_file.name
        shutil.copy2(entry_file, target_file)
        return target_file, entry_file.name

    for item in source_root.iterdir():
        target = app_root / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    copied_entry = app_root / entry_file.relative_to(source_root)
    return copied_entry, copied_entry.relative_to(app_root).as_posix()


def _ensure_python_api_runtime_deps(python_executable, app_root, extra_packages=None, live_cb=None):
    python_exe = str(python_executable or "").strip()
    if not python_exe:
        return 1, "Install Python first."
    env = _python_env(python_exe)
    req_file = Path(app_root) / "requirements.txt"
    if req_file.exists():
        if live_cb:
            live_cb(f"Installing Python app requirements from {req_file}...\n")
        code, output = run_process([python_exe, "-m", "pip", "install", "-r", str(req_file)], env=env, live_cb=live_cb)
        if code != 0:
            return code, output or "Failed to install requirements.txt."
    packages = [pkg for pkg in (extra_packages or []) if str(pkg or "").strip()]
    if packages:
        if live_cb:
            live_cb(f"Installing deployment runtime packages: {', '.join(packages)}\n")
        code, output = run_process([python_exe, "-m", "pip", "install", "--upgrade"] + packages, env=env, live_cb=live_cb)
        if code != 0:
            return code, output or "Failed to install Python deployment runtime packages."
    return 0, ""


def _python_api_venv_python(venv_dir):
    base = Path(venv_dir)
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def _create_python_api_venv(deploy_root, python_executable, app_root, extra_packages=None, live_cb=None):
    deploy_root = Path(deploy_root)
    app_root = Path(app_root)
    python_exe = str(python_executable or "").strip()
    if not python_exe:
        return "", 1, "Install Python first."
    venv_dir = deploy_root / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    if live_cb:
        live_cb(f"Creating virtual environment at {venv_dir}...\n")
    code, output = run_process([python_exe, "-m", "venv", str(venv_dir)], live_cb=live_cb)
    if code != 0:
        return "", code, output or "Failed to create Python virtual environment."
    venv_python = _python_api_venv_python(venv_dir)
    if not venv_python.exists():
        return "", 1, f"Virtual environment Python was not created: {venv_python}"
    code, output = run_process([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], live_cb=live_cb)
    if code != 0:
        return "", code, output or "Failed to bootstrap pip inside the virtual environment."
    req_file = app_root / "requirements.txt"
    if req_file.exists():
        if live_cb:
            live_cb(f"Installing Python app requirements from {req_file} into the virtual environment...\n")
        code, output = run_process([str(venv_python), "-m", "pip", "install", "-r", str(req_file)], live_cb=live_cb)
        if code != 0:
            return "", code, output or "Failed to install requirements.txt into the virtual environment."
    packages = [pkg for pkg in (extra_packages or []) if str(pkg or "").strip()]
    if packages:
        if live_cb:
            live_cb(f"Installing deployment runtime packages into the virtual environment: {', '.join(packages)}\n")
        code, output = run_process([str(venv_python), "-m", "pip", "install", "--upgrade"] + packages, live_cb=live_cb)
        if code != 0:
            return "", code, output or "Failed to install deployment runtime packages into the virtual environment."
    return str(venv_python), 0, ""


def _ensure_python_api_https_assets(python_executable, host, deploy_name):
    python_exe = str(python_executable or "").strip()
    host_value = str(host or "").strip() or "localhost"
    name = _safe_python_api_name(deploy_name, "python-api")
    cert_dir = PYTHON_STATE_DIR / "api-certs" / name
    cert_path = cert_dir / "tls-cert.pem"
    key_path = cert_dir / "tls-key.pem"
    cert_dir.mkdir(parents=True, exist_ok=True)
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)
    rc_import, _ = run_capture([python_exe, "-c", "import trustme"], timeout=20)
    if rc_import != 0:
        rc_install, _ = run_capture([python_exe, "-m", "pip", "install", "--upgrade", "trustme"], timeout=240)
        if rc_install != 0:
            return "", ""
    script = (
        "from pathlib import Path\n"
        "import trustme\n"
        f"cert_path = Path(r'''{str(cert_path)}''')\n"
        f"key_path = Path(r'''{str(key_path)}''')\n"
        f"host = {host_value!r}\n"
        "ca = trustme.CA()\n"
        "server_cert = ca.issue_cert(host, 'localhost', '127.0.0.1')\n"
        "server_cert.cert_chain_pems[0].write_to_path(cert_path)\n"
        "server_cert.private_key_pem.write_to_path(key_path)\n"
    )
    rc, _ = run_capture([python_exe, "-c", script], timeout=60)
    if rc != 0 or not cert_path.exists() or not key_path.exists():
        return "", ""
    return str(cert_path), str(key_path)


def _write_python_api_runtime_files(deploy_root, app_entry_rel, app_object, host, port, certfile="", keyfile=""):
    deploy_root = Path(deploy_root)
    runtime_dir = deploy_root / ".serverinstaller"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    host_script = runtime_dir / "serverinstaller_python_api_host.py"
    shutil.copy2(PYTHON_API_HOST_TEMPLATE, host_script)
    runner_script = runtime_dir / "run_api.py"
    runner_script.write_text(
        "\n".join([
            "import os",
            "import runpy",
            f"os.environ['SERVER_INSTALLER_APP_FILE'] = r'''{str((deploy_root / 'app' / app_entry_rel).resolve())}'''",
            f"os.environ['SERVER_INSTALLER_APP_OBJECT'] = r'''{str(app_object or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_HOST'] = r'''{str(host or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_PORT'] = r'''{str(port or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_CERTFILE'] = r'''{str(certfile or '').strip()}'''",
            f"os.environ['SERVER_INSTALLER_KEYFILE'] = r'''{str(keyfile or '').strip()}'''",
            f"runpy.run_path(r'''{str(host_script.resolve())}''', run_name='__main__')",
            "",
        ]),
        encoding="utf-8",
    )
    return runtime_dir, runner_script


def _prepare_python_api_deployment(form, deployment_name, live_cb=None):
    source_value = resolve_source_value(form, "PYTHON_API_SOURCE", "PYTHON_API_SOURCE_FILE", "PYTHON_API_SOURCE_FOLDER")
    if not source_value:
        raise RuntimeError("Source path/URL, uploaded file, or uploaded folder is required.")
    source_root, entry_file, entry_rel = _resolve_python_api_source(
        source_value,
        entry_hint=((form.get("PYTHON_API_MAIN_FILE", [""])[0] or "").strip() or (form.get("PYTHON_API_ENTRY_FILE", [""])[0] or "").strip()),
        live_cb=live_cb,
    )
    python_info = get_python_info()
    python_executable = str(python_info.get("python_executable") or "").strip()
    if not python_executable:
        raise RuntimeError("Install Python first on the main Python page.")
    host = (form.get("PYTHON_API_HOST_IP", [""])[0] or "").strip() or choose_service_host()
    https_port = (form.get("PYTHON_API_PORT", ["8443"])[0] or "8443").strip()
    if not https_port.isdigit():
        raise RuntimeError("HTTPS port must be numeric.")
    http_port = (form.get("PYTHON_API_HTTP_PORT", [""])[0] or "").strip()
    if http_port and not http_port.isdigit():
        raise RuntimeError("HTTP port must be numeric.")
    app_object = (form.get("PYTHON_API_APP_OBJECT", [""])[0] or "").strip()
    deploy_key = _safe_python_api_name(deployment_name)
    deploy_root = PYTHON_STATE_DIR / "api" / deploy_key
    deploy_root.mkdir(parents=True, exist_ok=True)
    copied_entry, copied_entry_rel = _copy_python_api_source(source_root, entry_file, deploy_root)
    return {
        "python_executable": python_executable,
        "host": host,
        "http_port": http_port,
        "https_port": https_port,
        "app_object": app_object,
        "deploy_key": deploy_key,
        "deploy_root": deploy_root,
        "entry_path": copied_entry,
        "entry_rel": copied_entry_rel,
    }


def _update_python_api_state(name, payload):
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        deployments = {}
    deployments[_safe_python_api_name(name)] = payload
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)


def _cleanup_python_api_state_entry(service_name, kind=""):
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return
    remove_keys = []
    for key, payload in deployments.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("name") or "").strip() != str(service_name or "").strip():
            continue
        if kind and str(payload.get("kind") or "").strip() != str(kind or "").strip():
            continue
        deploy_root = Path(str(payload.get("deploy_root") or "").strip())
        try:
            if deploy_root.exists():
                shutil.rmtree(deploy_root, ignore_errors=True)
        except Exception:
            pass
        remove_keys.append(key)
    for key in remove_keys:
        deployments.pop(key, None)
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)


def _python_api_service_items():
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return []
    items = []
    for _, payload in deployments.items():
        if not isinstance(payload, dict):
            continue
        kind = str(payload.get("kind") or "").strip().lower()
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        url = str(payload.get("url") or "").strip()
        port_text = str(payload.get("port") or "").strip()
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        running = False
        autostart = False
        sub_status = ""
        if kind == "service":
            if os.name == "nt":
                rc, out = run_capture(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        f"$svc=Get-CimInstance Win32_Service -Filter \"Name='{name}'\" -ErrorAction SilentlyContinue; if($svc){{Write-Output ($svc.State + '|' + $svc.StartMode)}}",
                    ],
                    timeout=20,
                )
                if rc == 0 and out:
                    parts = str(out).strip().split("|", 1)
                    sub_status = parts[0] if parts else ""
                    running = sub_status.lower() == "running"
                    autostart = len(parts) > 1 and parts[1].strip().lower() == "auto"
            else:
                svc = _linux_systemd_unit_status(name)
                sub_status = str(svc.get("active") or "")
                running = bool(svc.get("running"))
                autostart = bool(svc.get("autostart"))
        elif kind == "docker":
            details = _get_docker_container_details(name)
            sub_status = str(details.get("state") or "")
            running = sub_status == "running"
            autostart = str(details.get("restart_policy") or "") in ("always", "unless-stopped")
        elif kind == "iis_site" and os.name == "nt":
            rc, out = run_capture(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Import-Module WebAdministration; $site=Get-Website -Name '{name}' -ErrorAction SilentlyContinue; if($site){{Write-Output ($site.State + '|' + [string]$site.serverAutoStart)}}",
                ],
                timeout=20,
            )
            if rc == 0 and out:
                parts = str(out).strip().split("|", 1)
                sub_status = parts[0] if parts else ""
                running = sub_status.lower() == "started"
                autostart = len(parts) > 1 and parts[1].strip().lower() == "true"
        items.append({
            "kind": kind or "service",
            "name": name,
            "display_name": "Python API",
            "status": "running" if running else "stopped",
            "sub_status": sub_status or ("running" if running else "stopped"),
            "autostart": autostart,
            "platform": "windows" if os.name == "nt" else "linux",
            "urls": [url] if url else [],
            "ports": ports,
            "manageable": True,
            "deletable": True,
            "detail": str(payload.get("entry_file") or ""),
            "python_api": True,
            "target_page": "python-system" if kind == "service" else ("python-docker" if kind == "docker" else ("python-iis" if kind == "iis_site" else "python-api")),
            "deployment_key": str(payload.get("deployment_key") or ""),
            "form_name": str(payload.get("form_name") or name),
            "project_path": str(payload.get("project_path") or ""),
            "deploy_root": str(payload.get("deploy_root") or ""),
            "main_file": str(payload.get("entry_file") or ""),
            "host": str(payload.get("host") or ""),
            "port_value": str(payload.get("port") or ""),
            "service_log": str(payload.get("service_log") or ""),
        })
    return items
