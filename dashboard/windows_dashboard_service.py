#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _bootstrap_pywin32() -> None:
    candidates = []
    try:
        import site

        for base in site.getsitepackages():
            candidates.append(Path(base))
    except Exception:
        pass
    candidates.append(Path(sys.executable).resolve().parent / "Lib" / "site-packages")

    extra_paths = []
    for base in candidates:
        for rel in ("pywin32_system32", "win32", "win32\\lib", "pythonwin"):
            path = base / rel
            if path.exists():
                extra_paths.append(str(path))

    for path in extra_paths:
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_pywin32()

import servicemanager
import win32event
import win32service
import win32serviceutil


SERVICE_NAME = "ServerInstallerDashboard"
SERVICE_DISPLAY_NAME = "Server Installer Dashboard"
SERVICE_DESCRIPTION = "Runs the Server Installer dashboard continuously."


def data_root() -> Path:
    return Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer"


def read_service_state() -> dict:
    state_path = data_root() / "dashboard" / "service-state.json"
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_python_exe() -> str:
    state = {}
    try:
        state = json.loads((data_root() / "python" / "python-state.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}

    python_exe = str(state.get("python_executable") or "").strip()
    if python_exe and Path(python_exe).exists():
        candidate = Path(python_exe).with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
        return python_exe

    exe_dir = Path(sys.executable).resolve().parent
    for name in ("pythonw.exe", "python.exe", "pythonservice.exe"):
        candidate = exe_dir / name
        if candidate.exists():
            return str(candidate)

    return sys.executable


class ServerInstallerDashboardService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def log(self, message: str) -> None:
        servicemanager.LogInfoMsg(f"{SERVICE_NAME}: {message}")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop_dashboard()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.main()

    def stop_dashboard(self) -> None:
        if not self.process:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=10)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        finally:
            self.process = None

    def start_dashboard(self) -> None:
        root = data_root()
        state = read_service_state()
        host = str(state.get("host") or "0.0.0.0")
        port = str(state.get("port") or "8090")
        script_path = root / "dashboard" / "start-server-dashboard.py"
        cert_path = root / "certs" / "dashboard.crt"
        key_path = root / "certs" / "dashboard.key"
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "server-installer-dashboard.log"
        python_exe = resolve_python_exe()
        args = [
            python_exe,
            str(script_path),
            "--run-server",
            "--host",
            host,
            "--port",
            port,
            "--https",
            "--cert",
            str(cert_path),
            "--key",
            str(key_path),
        ]
        log_fp = open(log_path, "a", encoding="utf-8", buffering=1)
        creationflags = 0x08000000
        self.process = subprocess.Popen(
            args,
            cwd=str(root),
            stdout=log_fp,
            stderr=log_fp,
            creationflags=creationflags,
        )
        self.log(f"Started dashboard pid={self.process.pid}")

    def main(self):
        while True:
            if self.process is None or self.process.poll() is not None:
                if self.process is not None:
                    self.log(f"Dashboard exited with code {self.process.returncode}; restarting.")
                self.start_dashboard()
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break
        self.stop_dashboard()


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(ServerInstallerDashboardService)
