#!/usr/bin/env python3
import json
import os
import shutil
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
        # Register as a DLL directory so Windows can find pywintypes*.dll
        # even when running as a service with a restricted system PATH.
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(path)
            except Exception:
                pass


_bootstrap_pywin32()

import servicemanager
import win32event
import win32service
import win32serviceutil


SERVICE_NAME = "ServerInstallerDashboard"
SERVICE_DISPLAY_NAME = "Server Installer Dashboard"
SERVICE_DESCRIPTION = "Runs the Server Installer dashboard continuously."
SERVICE_MODULE = "windows_dashboard_service"


def data_root() -> Path:
    override = os.environ.get("SERVER_INSTALLER_DATA_DIR", "").strip()
    if override:
        return Path(override)
    sibling_root = Path(__file__).resolve().parents[1]
    if (sibling_root / "dashboard" / "start-server-dashboard.py").exists():
        return sibling_root
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


def resolve_pythonservice_exe() -> str:
    exe_dir = Path(sys.executable).resolve().parent
    candidate = exe_dir / "pythonservice.exe"
    if candidate.exists():
        return str(candidate)

    # Best-effort: locate and copy pythonservice.exe from pywin32 if installed.
    try:
        try:
            import site

            search_roots = [Path(p) for p in site.getsitepackages()]
        except Exception:
            search_roots = []
        search_roots.append(exe_dir / "Lib" / "site-packages")
        for root in search_roots:
            for rel in (("pywin32_system32", "pythonservice.exe"), ("win32", "pythonservice.exe")):
                src = root.joinpath(*rel)
                if not src.exists():
                    continue
                try:
                    shutil.copyfile(src, candidate)
                    return str(candidate)
                except Exception:
                    return str(exe_dir / "python.exe")
    except Exception:
        pass

    return str(exe_dir / "python.exe")


def resolve_system_site_packages() -> Path:
    return Path(sys.executable).resolve().parent / "Lib" / "site-packages"


def ensure_service_module_copy() -> Path:
    target = resolve_system_site_packages() / f"{SERVICE_MODULE}.py"
    source = Path(__file__).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target:
        shutil.copyfile(source, target)
    return target


def ensure_system_pywin32_pth() -> None:
    """Create pywin32.pth in the system site-packages so pythonservice.exe (running
    as SYSTEM with no user profile) can locate win32/ and servicemanager.pyd.
    pywin32 is often installed per-user, leaving system site-packages without
    the .pth file that adds win32/ to sys.path. Without it, pythonservice.exe
    fails with ModuleNotFoundError: No module named 'servicemanager'."""
    site_packages = resolve_system_site_packages()
    win32_dir = site_packages / "win32"
    if not win32_dir.exists():
        return
    pth_path = site_packages / "pywin32.pth"
    if pth_path.exists():
        return
    pth_content = (
        "# .pth file for the PyWin32 extensions\n"
        "win32\n"
        "win32\\lib\n"
        "Pythonwin\n"
        "import pywin32_bootstrap\n"
    )
    try:
        pth_path.write_text(pth_content, encoding="utf-8")
    except Exception:
        pass


def python_class_string() -> str:
    return f"{SERVICE_MODULE}.ServerInstallerDashboardService"


def install_or_update_service() -> None:
    ensure_service_module_copy()
    ensure_system_pywin32_pth()
    exe_name = resolve_pythonservice_exe()
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        win32serviceutil.ChangeServiceConfig(
            python_class_string(),
            SERVICE_NAME,
            startType=win32service.SERVICE_AUTO_START,
            exeName=exe_name,
            displayName=SERVICE_DISPLAY_NAME,
            description=SERVICE_DESCRIPTION,
        )
    except Exception:
        win32serviceutil.InstallService(
            python_class_string(),
            SERVICE_NAME,
            SERVICE_DISPLAY_NAME,
            startType=win32service.SERVICE_AUTO_START,
            exeName=exe_name,
            description=SERVICE_DESCRIPTION,
        )


def start_service() -> None:
    win32serviceutil.StartService(SERVICE_NAME)


def stop_service() -> None:
    try:
        win32serviceutil.StopService(SERVICE_NAME)
    except Exception:
        pass


def restart_service() -> None:
    stop_service()
    time.sleep(2)
    start_service()


def remove_service() -> None:
    try:
        stop_service()
        time.sleep(1)
    except Exception:
        pass
    win32serviceutil.RemoveService(SERVICE_NAME)


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
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
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
        try:
            log_fp = open(log_path, "a", encoding="utf-8", buffering=1)
        except Exception:
            log_fp = None
        creationflags = 0x08000000
        popen_kwargs = {"cwd": str(root), "creationflags": creationflags}
        if log_fp is not None:
            popen_kwargs["stdout"] = log_fp
            popen_kwargs["stderr"] = log_fp
        else:
            popen_kwargs["stdout"] = subprocess.DEVNULL
            popen_kwargs["stderr"] = subprocess.DEVNULL
        self.process = subprocess.Popen(args, **popen_kwargs)
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
    args = [arg.lower() for arg in sys.argv[1:]]
    if "install" in args or "update" in args:
        install_or_update_service()
    elif "restart" in args:
        restart_service()
    elif "start" in args:
        start_service()
    elif "stop" in args:
        stop_service()
    elif "remove" in args:
        remove_service()
    else:
        win32serviceutil.HandleCommandLine(ServerInstallerDashboardService)
