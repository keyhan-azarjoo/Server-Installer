#!/usr/bin/env python3
import argparse
import ctypes
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path


REPO = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
REQUIRED_FILES = [
    "dashboard/server_installer_dashboard.py",
    "dashboard/server_dashboard_ui.js",
    "DotNet/windows/install-windows-dotnet-host.ps1",
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
    "DotNet/linux/install-linux-dotnet-runner.sh",
]


def is_repo_layout(root: Path) -> bool:
    return (root / "dashboard" / "server_installer_dashboard.py").exists()


def cache_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("ProgramData", "C:/ProgramData"))
        return base / "Server-Installer"
    return Path.home() / ".server-installer"


def ensure_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel in REQUIRED_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"{REPO}/{rel}"
        tmp_target = target.with_suffix(target.suffix + ".download")
        try:
            print(f"Syncing required file: {rel}")
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
    args = parser.parse_args()

    if relaunch_as_admin_if_needed():
        return 0

    cwd_root = Path.cwd()
    if is_repo_layout(cwd_root):
        root = cwd_root
    else:
        root = cache_root()
        ensure_files(root)

    app = root / "dashboard" / "server_installer_dashboard.py"
    if not app.exists():
        print(f"Dashboard script not found: {app}", file=sys.stderr)
        return 1

    host = preferred_host(args.host)
    print(f"OS detected: {platform.system()}")
    print(f"Dashboard URL: http://{host}:{args.port}")
    print(f"Local URL: http://127.0.0.1:{args.port}")

    cmd = [sys.executable, str(app), "--host", host, "--port", str(args.port)]
    return subprocess.call(cmd, cwd=str(root))


if __name__ == "__main__":
    raise SystemExit(main())
