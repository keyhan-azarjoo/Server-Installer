import html
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

from constants import (
    PYTHON_API_HOST_TEMPLATE,
    PYTHON_API_STATE_FILE,
    PYTHON_STATE_DIR,
    PYTHON_STATE_FILE,
    PYTHON_JUPYTER_STATE_FILE,
    SERVER_INSTALLER_DATA,
    WEBSITE_STATE_DIR,
    WEBSITE_STATE_FILE,
    ROOT,
    JUPYTER_SYSTEMD_SERVICE,
)
from utils import (
    _read_json_file,
    _write_json_file,
    command_exists,
    prepare_source_dir,
    resolve_source_value,
    run_capture,
    run_process,
    upload_root_dir,
    _sudo_prefix,
    find_app_dll_dir,
)
from system_info import choose_service_host, get_listening_ports
from python_manager import _linux_systemd_unit_status, _python_process_running, _windows_process_matches_managed_jupyter
from port_manager import is_local_tcp_port_listening

def _safe_website_name(value, default_name="ServerInstallerWebsite"):
    text = re.sub(r"[^A-Za-z0-9 _.-]+", "", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._-")
    return text or default_name


def _safe_website_runtime_name(value, default_name="serverinstaller-website"):
    text = re.sub(r"[^A-Za-z0-9.-]+", "-", str(value or "").strip().lower()).strip("-.")
    return text or default_name


def _website_state_key(value):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return cleaned or "website"


def _update_website_state(name, payload):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        deployments = {}
    deployments[_website_state_key(name)] = payload
    state["deployments"] = deployments
    _write_json_file(WEBSITE_STATE_FILE, state)


def _cleanup_website_state_entry(site_name):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return
    remove_keys = []
    for key, payload in deployments.items():
        if not isinstance(payload, dict):
            remove_keys.append(key)
            continue
        if str(payload.get("name") or "").strip().lower() == str(site_name or "").strip().lower():
            remove_keys.append(key)
    for key in remove_keys:
        deployments.pop(key, None)
    state["deployments"] = deployments
    _write_json_file(WEBSITE_STATE_FILE, state)


def _website_state_payload(site_name):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return {}
    target = str(site_name or "").strip().lower()
    for payload in deployments.values():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("name") or "").strip().lower() == target:
            return payload
    return {}


def _website_state_payload_by_key(site_key):
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return {}
    payload = deployments.get(str(site_key or "").strip())
    return payload if isinstance(payload, dict) else {}


def _cleanup_existing_website_runtime(payload):
    if not isinstance(payload, dict):
        return
    name = str(payload.get("name") or "").strip()
    target = str(payload.get("target") or "").strip().lower()
    if not name:
        return
    if target == "docker" and command_exists("docker"):
        run_capture(["docker", "rm", "-f", name], timeout=60)
        image_name = str(payload.get("image_name") or "").strip()
        if image_name:
            run_capture(["docker", "rmi", "-f", image_name], timeout=30)
        return
    if target == "iis" and os.name == "nt":
        ps = "\n".join([
            "Import-Module WebAdministration",
            f"$siteName = {_ps_single_quote(name)}",
            "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
            f"if (Test-Path ('IIS:\\AppPools\\{name}')) {{ Stop-WebAppPool -Name '{name}' -ErrorAction SilentlyContinue | Out-Null; Remove-WebAppPool -Name '{name}' -ErrorAction SilentlyContinue | Out-Null }}",
        ])
        run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=90)
        return
    if target == "service" and os.name == "nt":
        run_capture(["sc.exe", "stop", name], timeout=30)
        run_capture(["sc.exe", "delete", name], timeout=30)
        return
    if target == "service" and platform.system() == "Darwin":
        plist_name = str(payload.get("plist_name") or f"com.serverinstaller.website.{_safe_website_runtime_name(name)}").strip()
        plist_path = f"/Library/LaunchDaemons/{plist_name}.plist"
        prefix = _sudo_prefix()
        run_capture(prefix + ["launchctl", "bootout", "system", plist_path], timeout=30)
        run_capture(prefix + ["rm", "-f", plist_path], timeout=30)
        return
    if target == "service":
        unit_name = name if name.endswith(".service") else f"{name}.service"
        prefix = _sudo_prefix()
        run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
        run_capture(prefix + ["systemctl", "disable", unit_name], timeout=30)
        run_capture(prefix + ["rm", "-f", f"/etc/systemd/system/{unit_name}"], timeout=30)
        run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)


def _detect_static_website_root(source_root: Path, website_kind="auto"):
    root = Path(source_root).resolve()
    kind = str(website_kind or "auto").strip().lower()
    candidate_dirs = []

    def add_candidate(path_obj):
        try:
            candidate = Path(path_obj).resolve()
        except Exception:
            return
        if not candidate.exists() or not candidate.is_dir():
            return
        if candidate not in candidate_dirs:
            candidate_dirs.append(candidate)

    if kind == "flutter":
        add_candidate(root / "build" / "web")
    elif kind in ("static", "web", "next-export"):
        add_candidate(root / "out")
        add_candidate(root / "dist")
        add_candidate(root / "build")

    for rel in (
        "build/web",
        "out",
        "dist",
        "build",
        "public",
        ".next/static",
        "",
    ):
        add_candidate(root / rel if rel else root)

    for candidate in list(candidate_dirs):
        index_file = candidate / "index.html"
        if index_file.exists():
            return candidate, str(candidate.relative_to(root)) if candidate != root else "."

    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        if (candidate / "index.html").exists():
            return candidate, str(candidate.relative_to(root))

    # No index.html found anywhere — use the source root as-is so the
    # web server can serve whatever files were uploaded.
    return root, "."


def _read_text_if_exists(path_value):
    path_obj = Path(path_value)
    if not path_obj.exists() or not path_obj.is_file():
        return ""
    try:
        return path_obj.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _find_php_public_root(source_root: Path):
    root = Path(source_root).resolve()
    for rel in ("public", "web", ""):
        candidate = root / rel if rel else root
        if candidate.is_dir() and any((candidate / name).exists() for name in ("index.php", "router.php")):
            return candidate, (str(candidate.relative_to(root)) if candidate != root else ".")
    for candidate in root.rglob("*"):
        if candidate.is_dir() and (candidate / "index.php").exists():
            return candidate, str(candidate.relative_to(root))
    raise RuntimeError("Could not find a PHP web root. Expected index.php in the project root or a public/ folder.")


def _detect_website_stack(source_root: Path):
    root = Path(source_root).resolve()
    package_json = root / "package.json"
    pubspec = root / "pubspec.yaml"
    composer_json = root / "composer.json"
    next_config = any((root / name).exists() for name in ("next.config.js", "next.config.mjs", "next.config.ts"))
    next_dir = (root / ".next").exists()
    out_dir = (root / "out" / "index.html").exists()
    dist_dir = (root / "dist" / "index.html").exists()
    flutter_build = (root / "build" / "web" / "index.html").exists()
    php_index = any((root / rel).exists() for rel in ("index.php", "public/index.php", "web/index.php"))

    package_data = {}
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            package_data = {}
    deps = {}
    if isinstance(package_data, dict):
        deps = {
            **(package_data.get("dependencies") if isinstance(package_data.get("dependencies"), dict) else {}),
            **(package_data.get("devDependencies") if isinstance(package_data.get("devDependencies"), dict) else {}),
        }
    scripts = package_data.get("scripts") if isinstance(package_data.get("scripts"), dict) else {}
    is_next = ("next" in deps) or next_config or next_dir
    is_next_export = is_next and (
        out_dir or
        "export" in scripts or
        "next export" in json.dumps(scripts)
    )
    if is_next_export and out_dir:
        return {"kind": "next-export", "runtime": "static", "stack_label": "Next Export / Static Website"}
    if is_next:
        return {"kind": "nextjs", "runtime": "node", "stack_label": "Next.js Website"}
    pubspec_text = _read_text_if_exists(pubspec)
    if pubspec.exists() and ("flutter:" in pubspec_text.lower() or flutter_build):
        return {"kind": "flutter", "runtime": "static", "stack_label": "Flutter Web Website"}
    if composer_json.exists() or php_index:
        return {"kind": "php", "runtime": "php", "stack_label": "PHP Website"}
    if out_dir:
        return {"kind": "next-export", "runtime": "static", "stack_label": "Next Export / Static Website"}
    if dist_dir or flutter_build or (root / "index.html").exists():
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Check for index.html in common subdirectories
    for sub in ("public", "www", "wwwroot", "html", "htdocs", "web", "static"):
        if (root / sub / "index.html").exists():
            return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Check for any .html file at root level
    if any(f.suffix.lower() == ".html" for f in root.iterdir() if f.is_file()):
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    # Default to static for any directory with files — let the web server serve whatever is there
    if any(root.iterdir()):
        return {"kind": "static", "runtime": "static", "stack_label": "Static Website"}
    raise RuntimeError("Source folder is empty. Upload or point to a folder with your website files.")


def _copy_website_source(source_root: Path, deploy_root: Path):
    if deploy_root.exists():
        shutil.rmtree(deploy_root, ignore_errors=True)
    blocked = {".git", "__pycache__", ".venv", "venv", "node_modules", ".next/cache", "vendor/.cache"}

    def ignore_func(_dir, names):
        ignored = []
        for name in names:
            normalized = name.replace("\\", "/")
            if name in blocked or normalized in blocked:
                ignored.append(name)
        return ignored

    shutil.copytree(source_root, deploy_root, ignore=ignore_func)


def _choose_website_target(requested_target, detected_runtime):
    target = str(requested_target or "auto").strip().lower()
    runtime = str(detected_runtime or "static").strip().lower()
    valid_targets = ("service", "docker", "iis", "nginx", "nodejs", "kubernetes", "pm2")
    if target == "auto":
        if runtime == "static":
            if os.name == "nt" and get_iis_info().get("installed"):
                return "iis"
            if command_exists("docker"):
                return "docker"
            if command_exists("nginx"):
                return "nginx"
            return "service"
        if runtime == "node":
            if command_exists("docker"):
                return "docker"
            if command_exists("pm2"):
                return "pm2"
            if command_exists("node"):
                return "nodejs"
            return "service"
        if runtime == "php":
            if command_exists("docker"):
                return "docker"
            if command_exists("nginx"):
                return "nginx"
            return "service"
    return target if target in valid_targets else "service"


def _validate_website_target(stack_kind, runtime, target):
    stack = str(stack_kind or "").strip().lower()
    selected = str(target or "").strip().lower()
    runtime_value = str(runtime or "").strip().lower()
    if selected == "iis":
        if os.name != "nt":
            raise RuntimeError("IIS target is only available on Windows.")
        if runtime_value != "static":
            raise RuntimeError(f"{stack or 'This'} website cannot run directly on IIS from this dashboard. Use Docker or OS service.")
    if selected == "docker":
        if sys.platform == "darwin":
            _docker_add_macos_path()
        if not command_exists("docker"):
            # Auto-install Docker
            _install_website_engine("docker")
            if sys.platform == "darwin":
                _docker_add_macos_path()
            if not command_exists("docker"):
                raise RuntimeError("Docker target requires Docker to be installed and running.")
    if selected == "nginx":
        if os.name == "nt":
            raise RuntimeError("Nginx is not available on Windows. Use IIS or Docker instead.")
        if runtime_value == "node":
            raise RuntimeError("Next.js requires a Node.js runtime. Nginx cannot serve it directly. Use Docker, Node.js, or PM2.")
        if not command_exists("nginx"):
            _install_website_engine("nginx")
            if not command_exists("nginx"):
                raise RuntimeError("Nginx installation failed. Install it manually or use Docker.")
    if selected == "nodejs":
        if runtime_value == "php":
            raise RuntimeError("PHP code cannot run on Node.js. Use Nginx, Docker, or the OS service target.")
        if not command_exists("node"):
            _install_website_engine("nodejs")
            if not command_exists("node"):
                raise RuntimeError("Node.js installation failed. Install it manually.")
    if selected == "pm2":
        if runtime_value == "php":
            raise RuntimeError("PHP code cannot run under PM2. Use Nginx or Docker.")
        if not command_exists("pm2"):
            _install_website_engine("pm2")
            if not command_exists("pm2"):
                raise RuntimeError("PM2 installation failed. Install Node.js and run 'npm install -g pm2'.")
    if selected == "kubernetes":
        if os.name == "nt":
            raise RuntimeError("Kubernetes deployment from this dashboard requires Linux. Enable Kubernetes in Docker Desktop on Windows.")
        if not (command_exists("kubectl") or command_exists("k3s")):
            _install_website_engine("kubernetes")
            if not (command_exists("kubectl") or command_exists("k3s")):
                raise RuntimeError("Kubernetes installation failed.")
    if selected == "service" and runtime_value == "node" and not (command_exists("node") and command_exists("npm")):
        raise RuntimeError("Next.js service target requires Node.js and npm on the host.")
    if selected == "service" and runtime_value == "php" and not command_exists("php"):
        raise RuntimeError("PHP service target requires php on the host.")


def _detect_website_engines():
    """Detect which runtime engines are available on this system."""
    engines = {}

    def _cmd_version(cmd, flag="--version"):
        try:
            r = subprocess.run([cmd, flag], capture_output=True, timeout=10, text=True)
            if r.returncode == 0:
                ver = (r.stdout or r.stderr or "").strip().splitlines()[0].strip()
                # Clean up version string
                for prefix in ("Docker version ", "nginx version: nginx/", "v", "pm2 "):
                    if ver.lower().startswith(prefix.lower()):
                        ver = ver[len(prefix):].split(",")[0].split(" ")[0].strip()
                        break
                return ver
        except Exception:
            pass
        return ""

    # Docker
    if command_exists("docker"):
        engines["docker"] = {"installed": True, "version": _cmd_version("docker", "--version")}
    else:
        engines["docker"] = {"installed": False}

    # Nginx
    if command_exists("nginx"):
        engines["nginx"] = {"installed": True, "version": _cmd_version("nginx", "-v")}
    else:
        engines["nginx"] = {"installed": False}

    # IIS (Windows only)
    if os.name == "nt":
        iis_info = get_iis_info()
        engines["iis"] = {"installed": bool(iis_info.get("installed")), "version": str(iis_info.get("version") or "")}
    else:
        engines["iis"] = {"installed": False}

    # Node.js
    if command_exists("node"):
        engines["nodejs"] = {"installed": True, "version": _cmd_version("node", "--version")}
    else:
        engines["nodejs"] = {"installed": False}

    # Kubernetes (kubectl + k3s/microk8s)
    k8s_installed = False
    k8s_version = ""
    if command_exists("kubectl"):
        k8s_installed = True
        k8s_version = _cmd_version("kubectl", "version --client --short") or _cmd_version("kubectl", "version")
    elif command_exists("k3s"):
        k8s_installed = True
        k8s_version = _cmd_version("k3s", "--version")
    elif command_exists("microk8s"):
        k8s_installed = True
        k8s_version = "microk8s"
    engines["kubernetes"] = {"installed": k8s_installed, "version": k8s_version}

    # PM2
    if command_exists("pm2"):
        engines["pm2"] = {"installed": True, "version": _cmd_version("pm2", "--version")}
    else:
        engines["pm2"] = {"installed": False}

    # OS Service (always available)
    if os.name == "nt":
        engines["service"] = {"installed": True, "version": "Windows Service"}
    else:
        engines["service"] = {"installed": True, "version": "systemd" if command_exists("systemctl") else "launchd" if sys.platform == "darwin" else "service"}

    return engines


def _install_website_engine(engine_id, live_cb=None):
    """Install a runtime engine. Returns (exit_code, output_text)."""
    engine_id = str(engine_id or "").strip().lower()
    output_lines = []

    def log(msg):
        output_lines.append(msg)
        if live_cb:
            live_cb(msg + "\n")

    log(f"=== Installing {engine_id} ===")

    if engine_id == "docker":
        return _install_engine_docker(log)
    elif engine_id == "nginx":
        return _install_engine_nginx(log)
    elif engine_id == "nodejs":
        return _install_engine_nodejs(log)
    elif engine_id == "kubernetes":
        return _install_engine_kubernetes(log)
    elif engine_id == "pm2":
        return _install_engine_pm2(log)
    elif engine_id == "iis":
        return _install_engine_iis(log)
    else:
        log(f"Unknown engine: {engine_id}")
        return 1, "\n".join(output_lines)


def _run_install_cmd(cmd, log, timeout=300):
    """Run an installation command, streaming output."""
    log(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        if isinstance(cmd, str):
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log(line.rstrip())
        proc.wait(timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        log("Command timed out.")
        return 1
    except Exception as e:
        log(f"Error: {e}")
        return 1


def _docker_add_macos_path():
    """Add Docker Desktop binary paths to PATH on macOS."""
    docker_paths = [
        "/Applications/Docker.app/Contents/Resources/bin",
        "/usr/local/bin",
        str(Path.home() / ".docker" / "bin"),
    ]
    current_path = os.environ.get("PATH", "")
    for dp in docker_paths:
        if dp not in current_path and Path(dp).exists():
            os.environ["PATH"] = dp + os.pathsep + current_path
            current_path = os.environ["PATH"]


def _docker_wait_macos(log):
    """Wait for Docker Desktop to finish initialization on macOS."""
    import time
    log("Waiting for Docker Desktop to initialize...")
    # First add Docker bin to PATH
    _docker_add_macos_path()
    # Docker Desktop creates symlinks in /usr/local/bin after first launch
    # Also check the embedded binary directly
    docker_bin = "/Applications/Docker.app/Contents/Resources/bin/docker"
    for i in range(60):
        time.sleep(3)
        _docker_add_macos_path()
        # Check if docker CLI is available via PATH or direct path
        if command_exists("docker"):
            log("Docker CLI found in PATH.")
            # Now wait for Docker daemon to be ready
            try:
                rc, out = run_capture(["docker", "info"], timeout=10)
                if rc == 0:
                    log("Docker is ready.")
                    return 0, "Docker installed."
            except Exception:
                pass
            log(f"Docker CLI available, waiting for daemon... ({i+1}/60)")
        elif Path(docker_bin).exists():
            # Docker binary exists but not in PATH yet — use it directly
            os.environ["PATH"] = str(Path(docker_bin).parent) + os.pathsep + os.environ.get("PATH", "")
            log(f"Found Docker at {docker_bin}, waiting for daemon... ({i+1}/60)")
            try:
                rc, out = run_capture([docker_bin, "info"], timeout=10)
                if rc == 0:
                    log("Docker is ready.")
                    return 0, "Docker installed."
            except Exception:
                pass
        else:
            log(f"Waiting for Docker... ({i+1}/60)")
    # If we get here, Docker Desktop is installed but not ready yet
    if command_exists("docker") or Path(docker_bin).exists():
        log("Docker Desktop is installed but still initializing.")
        log("Please wait for Docker Desktop to finish setup, then retry.")
        return 0, "Docker installed. Docker Desktop is still initializing — retry in a moment."
    return 1, "Docker Desktop installed but CLI not found. Restart Docker Desktop."


def _install_engine_docker(log):
    """Install Docker."""
    # On macOS, Docker Desktop puts the CLI in a non-standard path
    if sys.platform == "darwin":
        _docker_add_macos_path()
    if command_exists("docker"):
        log("Docker is already installed.")
        return 0, "Docker is already installed."

    if os.name == "nt":
        log("On Windows, Docker Desktop must be installed manually.")
        log("Download from: https://www.docker.com/products/docker-desktop/")
        return 1, "Docker Desktop must be installed manually on Windows."

    if sys.platform == "darwin":
        # macOS Apple Silicon: install Rosetta 2 first (required for Docker)
        import platform as _plat
        if _plat.machine() == "arm64":
            log("Installing Rosetta 2 (required for Docker on Apple Silicon)...")
            _run_install_cmd(["softwareupdate", "--install-rosetta", "--agree-to-license"], log, timeout=120)
        # macOS: use brew to install Docker
        log("macOS detected. Installing Docker via Homebrew...")
        if command_exists("brew"):
            code = _run_install_cmd(["brew", "install", "--cask", "docker"], log, timeout=300)
            if code == 0:
                log("Docker Desktop installed. Opening it...")
                _run_install_cmd(["open", "/Applications/Docker.app"], log, timeout=10)
                _docker_add_macos_path()
                return _docker_wait_macos(log)
            else:
                log("brew install failed. Install Docker Desktop manually:")
                log("https://www.docker.com/products/docker-desktop/")
                return 1, "Docker installation failed."
        else:
            # No brew — download Docker Desktop .dmg directly
            log("Homebrew not found. Downloading Docker Desktop directly...")
            import platform as _plat
            arch = _plat.machine()
            if arch == "arm64":
                dmg_url = "https://desktop.docker.com/mac/main/arm64/Docker.dmg"
            else:
                dmg_url = "https://desktop.docker.com/mac/main/amd64/Docker.dmg"
            dmg_path = "/tmp/Docker.dmg"
            code = _run_install_cmd(["curl", "-fSL", dmg_url, "-o", dmg_path], log, timeout=300)
            if code == 0 and Path(dmg_path).exists():
                log("Mounting Docker.dmg...")
                _run_install_cmd(["hdiutil", "attach", dmg_path, "-nobrowse"], log, timeout=30)
                _run_install_cmd(["cp", "-R", "/Volumes/Docker/Docker.app", "/Applications/"], log, timeout=60)
                _run_install_cmd(["hdiutil", "detach", "/Volumes/Docker"], log, timeout=15)
                Path(dmg_path).unlink(missing_ok=True)
                log("Docker Desktop installed. Opening...")
                _run_install_cmd(["open", "/Applications/Docker.app"], log, timeout=10)
                _docker_add_macos_path()
                return _docker_wait_macos(log)
            else:
                log("Download failed. Install Docker Desktop manually:")
                log("https://www.docker.com/products/docker-desktop/")
                return 1, "Docker installation failed."
    else:
        # Linux
        log("Installing Docker via official script...")
        code = _run_install_cmd("curl -fsSL https://get.docker.com | sh", log)
        if code == 0:
            _run_install_cmd(["systemctl", "enable", "--now", "docker"], log)
            log("Docker installed successfully.")
        return code, "Docker installation complete." if code == 0 else "Docker installation failed."


def _install_engine_nginx(log):
    """Install Nginx."""
    if command_exists("nginx"):
        log("Nginx is already installed.")
        return 0, "Nginx is already installed."

    if os.name == "nt":
        log("Nginx is not supported on Windows through this installer. Use IIS or Docker instead.")
        return 1, "Nginx not supported on Windows."

    # Detect package manager
    if command_exists("apt-get"):
        log("Installing Nginx via apt...")
        _run_install_cmd(["apt-get", "update", "-y"], log)
        code = _run_install_cmd(["apt-get", "install", "-y", "nginx"], log)
    elif command_exists("dnf"):
        log("Installing Nginx via dnf...")
        code = _run_install_cmd(["dnf", "install", "-y", "nginx"], log)
    elif command_exists("yum"):
        log("Installing Nginx via yum...")
        code = _run_install_cmd(["yum", "install", "-y", "nginx"], log)
    elif command_exists("brew"):
        log("Installing Nginx via Homebrew...")
        code = _run_install_cmd(["brew", "install", "nginx"], log)
    else:
        log("No supported package manager found (apt/dnf/yum/brew).")
        return 1, "No supported package manager found."

    if code == 0:
        if command_exists("systemctl"):
            _run_install_cmd(["systemctl", "enable", "--now", "nginx"], log)
        log("Nginx installed successfully.")
    return code, "Nginx installation complete." if code == 0 else "Nginx installation failed."


def _install_engine_nodejs(log):
    """Install Node.js."""
    if command_exists("node"):
        log("Node.js is already installed.")
        return 0, "Node.js is already installed."

    if os.name == "nt":
        log("Installing Node.js via winget...")
        code = _run_install_cmd(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements", "--accept-source-agreements"], log)
        if code != 0:
            log("winget failed. Trying direct download...")
            log("Download Node.js from: https://nodejs.org/")
            return 1, "Please install Node.js manually from https://nodejs.org/"
    else:
        log("Installing Node.js via NodeSource...")
        if command_exists("apt-get"):
            _run_install_cmd("curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["apt-get", "install", "-y", "nodejs"], log)
        elif command_exists("dnf"):
            _run_install_cmd("curl -fsSL https://rpm.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["dnf", "install", "-y", "nodejs"], log)
        elif command_exists("yum"):
            _run_install_cmd("curl -fsSL https://rpm.nodesource.com/setup_lts.x | bash -", log)
            code = _run_install_cmd(["yum", "install", "-y", "nodejs"], log)
        elif command_exists("brew"):
            code = _run_install_cmd(["brew", "install", "node"], log)
        else:
            log("No supported package manager found.")
            return 1, "No supported package manager found."

    if code == 0:
        log("Node.js installed successfully.")
    return code, "Node.js installation complete." if code == 0 else "Node.js installation failed."


def _install_engine_kubernetes(log):
    """Install lightweight Kubernetes (K3s on Linux)."""
    if command_exists("kubectl") or command_exists("k3s"):
        log("Kubernetes is already installed.")
        return 0, "Kubernetes is already installed."

    if os.name == "nt":
        log("Kubernetes on Windows requires Docker Desktop with Kubernetes enabled, or WSL2 with K3s.")
        return 1, "Enable Kubernetes in Docker Desktop settings."

    log("Installing K3s (lightweight Kubernetes)...")
    code = _run_install_cmd("curl -sfL https://get.k3s.io | sh -", log)
    if code == 0:
        log("K3s installed successfully. kubectl is available via 'k3s kubectl'.")
    return code, "K3s installation complete." if code == 0 else "K3s installation failed."


def _install_engine_pm2(log):
    """Install PM2 (Node.js process manager)."""
    if command_exists("pm2"):
        log("PM2 is already installed.")
        return 0, "PM2 is already installed."

    if not command_exists("npm"):
        log("PM2 requires Node.js/npm. Installing Node.js first...")
        node_code, _ = _install_engine_nodejs(log)
        if node_code != 0:
            return node_code, "Failed to install Node.js (required for PM2)."

    log("Installing PM2 globally via npm...")
    code = _run_install_cmd(["npm", "install", "-g", "pm2"], log)
    if code == 0:
        if os.name != "nt" and command_exists("pm2"):
            _run_install_cmd(["pm2", "startup"], log)
        log("PM2 installed successfully.")
    return code, "PM2 installation complete." if code == 0 else "PM2 installation failed."


def _install_engine_iis(log):
    """Install IIS (Windows only)."""
    if os.name != "nt":
        log("IIS is only available on Windows.")
        return 1, "IIS is only available on Windows."

    iis_info = get_iis_info()
    if iis_info.get("installed"):
        log("IIS is already installed.")
        return 0, "IIS is already installed."

    log("Installing IIS via DISM...")
    features = [
        "IIS-WebServerRole",
        "IIS-WebServer",
        "IIS-CommonHttpFeatures",
        "IIS-StaticContent",
        "IIS-DefaultDocument",
        "IIS-DirectoryBrowsing",
        "IIS-HttpErrors",
        "IIS-HttpRedirect",
        "IIS-ManagementConsole",
        "IIS-RequestFiltering",
        "IIS-HttpCompressionStatic",
    ]
    for feature in features:
        code = _run_install_cmd(
            ["dism", "/Online", "/Enable-Feature", f"/FeatureName:{feature}", "/All", "/NoRestart"],
            log
        )
        if code != 0:
            log(f"Warning: Feature {feature} returned code {code}")
    log("IIS installation complete. A restart may be required.")
    return 0, "IIS installation complete."


def resolve_unix_python():
    for name in ("python3", "python"):
        path_value = shutil.which(name)
        if path_value:
            return path_value
    return sys.executable


def _prepare_website_deployment(form=None, live_cb=None):
    form = form or {}
    source_value = resolve_source_value(form, "WEBSITE_SOURCE", "WEBSITE_SOURCE_FILE", "WEBSITE_SOURCE_FOLDER")
    if not source_value:
        raise RuntimeError("Project path, uploaded archive, or uploaded folder is required.")
    source_root = prepare_source_dir(source_value, live_cb=live_cb)
    site_name = _safe_website_name((form.get("WEBSITE_SITE_NAME", ["ServerInstallerWebsite"])[0] or "").strip(), "ServerInstallerWebsite")
    runtime_name = _safe_website_runtime_name((form.get("WEBSITE_RUNTIME_NAME", [""])[0] or "").strip() or site_name, "serverinstaller-website")
    site_key = _website_state_key(site_name)
    requested_kind = (form.get("WEBSITE_KIND", ["auto"])[0] or "auto").strip().lower()
    if requested_kind not in ("auto", "static", "flutter", "next-export", "nextjs", "php"):
        requested_kind = "auto"
    target = (form.get("WEBSITE_TARGET", ["auto"])[0] or "auto").strip().lower()
    bind_ip = (form.get("WEBSITE_BIND_IP", [""])[0] or "").strip() or "*"
    domain = (form.get("WEBSITE_DOMAIN", [""])[0] or "").strip()
    host = domain or (bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host())
    port_text = (form.get("WEBSITE_PORT", [""])[0] or "").strip()
    site_port = int(port_text) if port_text.isdigit() and 1 <= int(port_text) <= 65535 else 0
    https_port_text = (form.get("WEBSITE_HTTPS_PORT", [""])[0] or "").strip()
    https_port = int(https_port_text) if https_port_text.isdigit() and 1 <= int(https_port_text) <= 65535 else 0
    if not site_port and not https_port:
        raise RuntimeError("At least one port (HTTP or HTTPS) is required.")
    ssl_cert_name = (form.get("WEBSITE_SSL_CERT", ["self_signed"])[0] or "self_signed").strip()
    deploy_root = WEBSITE_STATE_DIR / site_key
    if requested_kind == "auto":
        detected = _detect_website_stack(source_root)
        detected_kind = str(detected.get("kind") or "static").strip().lower()
        runtime = str(detected.get("runtime") or "static").strip().lower()
        stack_label = str(detected.get("stack_label") or "Website").strip()
    else:
        detected_kind = requested_kind
        runtime_map = {"static": "static", "flutter": "static", "next-export": "static", "nextjs": "node", "php": "php"}
        runtime = runtime_map.get(requested_kind, "static")
        stack_label = _website_stack_label(requested_kind)
    effective_kind = detected_kind if requested_kind == "auto" else requested_kind
    if effective_kind in ("static", "flutter", "next-export"):
        publish_root, publish_rel = _detect_static_website_root(source_root, website_kind=effective_kind)
        if deploy_root.exists():
            shutil.rmtree(deploy_root, ignore_errors=True)
        shutil.copytree(publish_root, deploy_root)
        content_root = deploy_root
        content_rel = publish_rel
    elif effective_kind == "php":
        source_publish_root, publish_rel = _find_php_public_root(source_root)
        _copy_website_source(source_root, deploy_root)
        content_rel = publish_rel
        content_root = deploy_root / publish_rel if publish_rel not in ("", ".") else deploy_root
        runtime = "php"
        stack_label = "PHP Website"
    elif effective_kind == "nextjs":
        _copy_website_source(source_root, deploy_root)
        publish_rel = "."
        content_rel = "."
        content_root = deploy_root
        runtime = "node"
        stack_label = "Next.js Website"
    else:
        raise RuntimeError(f"Unsupported website type '{effective_kind}'.")
    selected_target = _choose_website_target(target, runtime)
    _validate_website_target(effective_kind, runtime, selected_target)
    if live_cb:
        live_cb(f"Detected website type: {stack_label} ({runtime}). Selected target: {selected_target}.\n")
    return {
        "site_name": site_name,
        "runtime_name": runtime_name,
        "site_key": site_key,
        "existing_payload": _website_state_payload_by_key(site_key),
        "website_kind": effective_kind,
        "detected_kind": detected_kind,
        "runtime": runtime,
        "stack_label": stack_label,
        "target": selected_target,
        "bind_ip": bind_ip,
        "domain": domain,
        "host": host,
        "site_port": site_port,
        "https_port": https_port,
        "ssl_cert_name": ssl_cert_name,
        "source_root": str(source_root),
        "publish_root": str(content_root),
        "publish_rel": publish_rel,
        "content_rel": content_rel,
        "deploy_root": str(deploy_root),
    }


def _write_website_state_entry(payload):
    _update_website_state(str(payload.get("name") or payload.get("form_name") or "website"), payload)


def _website_stack_label(website_kind):
    return {
        "flutter": "Flutter / Static Website",
        "next-export": "Next Export / Static Website",
        "nextjs": "Next.js Website",
        "php": "PHP Website",
        "static": "Static Website",
        "auto": "Static Website",
    }.get(str(website_kind or "auto").strip().lower(), "Static Website")


def _cleanup_website_artifacts(runtime_name, remove_files=True):
    payload = _website_state_payload(runtime_name)
    deploy_root = Path(str(payload.get("deploy_root") or "")).expanduser() if payload else None
    image_name = str(payload.get("image_name") or "").strip() if payload else ""
    if remove_files and deploy_root and str(deploy_root).strip():
        shutil.rmtree(deploy_root, ignore_errors=True)
    if image_name and command_exists("docker"):
        run_capture(["docker", "rmi", "-f", image_name], timeout=30)
    _cleanup_website_state_entry(runtime_name)


def _website_service_items():
    state = _read_json_file(WEBSITE_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return []
    items = []
    for payload in deployments.values():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        port_text = str(payload.get("port") or "").strip()
        url = str(payload.get("url") or "").strip()
        bind_ip = str(payload.get("bind_ip") or "").strip()
        runtime_target = str(payload.get("target") or "").strip().lower()
        running = False
        sub_status = ""
        autostart = False
        item_kind = "service"
        if runtime_target == "docker":
            item_kind = "docker"
            details = _get_docker_container_details(name)
            sub_status = str(details.get("state") or "")
            running = sub_status == "running"
            autostart = str(details.get("restart_policy") or "") in ("always", "unless-stopped")
        elif runtime_target == "iis":
            item_kind = "iis_site"
            rc, out = run_capture(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Import-Module WebAdministration; $site=Get-Website -Name '{name}' -ErrorAction SilentlyContinue; if($site){{Write-Output ($site.State + '|' + [string]$site.serverAutoStart + '|' + [string]$site.PhysicalPath)}}",
                ],
                timeout=20,
            )
            physical_path = str(payload.get("deploy_root") or "")
            if rc == 0 and out:
                parts = str(out).strip().split("|", 2)
                sub_status = parts[0] if parts else ""
                running = sub_status.lower() == "started"
                autostart = len(parts) > 1 and parts[1].strip().lower() == "true"
                if len(parts) > 2 and parts[2].strip():
                    physical_path = parts[2].strip()
        else:
            physical_path = str(payload.get("deploy_root") or "")
            if os.name == "nt":
                item_kind = "service"
                state_text, start_mode = _windows_service_state(name)
                sub_status = state_text
                running = state_text.lower() == "running"
                autostart = start_mode.lower() == "auto"
            elif platform.system() == "Darwin":
                item_kind = "website_launchd"
                plist_name = str(payload.get("plist_name") or "").strip()
                rc, out = run_capture(["launchctl", "print", f"system/{plist_name}"], timeout=20)
                running = rc == 0
                sub_status = "running" if running else "stopped"
                autostart = bool(plist_name)
            else:
                item_kind = "service"
                svc = _linux_systemd_unit_status(name)
                sub_status = str(svc.get("active") or "")
                running = bool(svc.get("running"))
                autostart = bool(svc.get("autostart"))
        ports = [{"port": int(port_text), "protocol": "tcp"}] if port_text.isdigit() else []
        https_port_text = str(payload.get("https_port") or "").strip()
        if https_port_text.isdigit() and int(https_port_text) > 0:
            ports.append({"port": int(https_port_text), "protocol": "tcp"})
        https_url = str(payload.get("https_url") or "").strip()
        # Use saved urls array if available (includes both domain and IP URLs)
        saved_urls = payload.get("urls")
        if isinstance(saved_urls, list) and saved_urls:
            all_urls = [str(u) for u in saved_urls if u]
        else:
            all_urls = []
            if url:
                all_urls.append(url)
            if https_url:
                all_urls.append(https_url)
        items.append({
            "kind": item_kind,
            "name": name,
            "display_name": f"{str(payload.get('stack_label') or 'Website').strip()} - {physical_path or '-'}",
            "status": "running" if running else "stopped",
            "sub_status": sub_status or ("running" if running else "stopped"),
            "autostart": autostart,
            "platform": "windows" if os.name == "nt" else "unknown",
            "urls": all_urls,
            "ports": ports,
            "manageable": True,
            "deletable": True,
            "website": True,
            "target_page": "website",
            "form_name": str(payload.get("form_name") or name),
            "project_path": str(payload.get("deploy_root") or payload.get("source_root") or ""),
            "deploy_root": str(payload.get("deploy_root") or ""),
            "host": bind_ip if bind_ip and bind_ip != "*" else str(payload.get("host") or ""),
            "port_value": port_text,
            "https_port_value": https_port_text if https_port_text.isdigit() and int(https_port_text) > 0 else "",
            "stack_label": str(payload.get("stack_label") or "Static Website"),
            "publish_rel": str(payload.get("publish_rel") or "."),
            "kind_value": str(payload.get("website_kind") or "auto"),
            "target_value": runtime_target or "service",
        })
    return items


def get_website_info():
    items = _website_service_items()
    return {
        "installed": len(items) > 0,
        "count": len(items),
        "sites": items,
    }


def _write_windows_website_service_file(deploy_root: Path, runtime_name: str, bind_ip: str, port: int):
    service_script = deploy_root / "serverinstaller_static_website_service.py"
    service_script.write_text(
        "\n".join([
            "import os",
            "import sys",
            "import threading",
            "import socketserver",
            "import http.server",
            "import win32event",
            "import win32service",
            "import win32serviceutil",
            "import servicemanager",
            "",
            f"SERVICE_NAME = {runtime_name!r}",
            f"ROOT_DIR = {str(deploy_root)!r}",
            f"BIND_HOST = {('0.0.0.0' if bind_ip in ('', '*') else bind_ip)!r}",
            f"PORT = {int(port)}",
            "",
            "class ReusableTCPServer(socketserver.ThreadingTCPServer):",
            "    allow_reuse_address = True",
            "",
            "class StaticWebsiteHandler(http.server.SimpleHTTPRequestHandler):",
            "    def __init__(self, *args, **kwargs):",
            "        super().__init__(*args, directory=ROOT_DIR, **kwargs)",
            "",
            "class StaticWebsiteService(win32serviceutil.ServiceFramework):",
            "    _svc_name_ = SERVICE_NAME",
            "    _svc_display_name_ = SERVICE_NAME",
            "    _svc_description_ = 'Server Installer managed static website service'",
            "",
            "    def __init__(self, args):",
            "        win32serviceutil.ServiceFramework.__init__(self, args)",
            "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
            "        self.httpd = None",
            "",
            "    def SvcStop(self):",
            "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
            "        if self.httpd is not None:",
            "            try:",
            "                self.httpd.shutdown()",
            "            except Exception:",
            "                pass",
            "            try:",
            "                self.httpd.server_close()",
            "            except Exception:",
            "                pass",
            "        win32event.SetEvent(self.stop_event)",
            "",
            "    def SvcDoRun(self):",
            "        os.chdir(ROOT_DIR)",
            "        self.httpd = ReusableTCPServer((BIND_HOST, PORT), StaticWebsiteHandler)",
            "        worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)",
            "        worker.start()",
            "        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)",
            "",
            "if __name__ == '__main__':",
            "    if len(sys.argv) == 1:",
            "        servicemanager.Initialize()",
            "        servicemanager.PrepareToHostSingle(StaticWebsiteService)",
            "        servicemanager.StartServiceCtrlDispatcher()",
            "    else:",
            "        win32serviceutil.HandleCommandLine(StaticWebsiteService)",
            "",
        ]),
        encoding="utf-8",
    )
    return service_script


def _find_windows_command(preferred_names):
    for name in preferred_names:
        path_value = shutil.which(name)
        if path_value:
            return path_value
    return preferred_names[0] if preferred_names else ""


def _website_node_start_command(deploy, host_override=""):
    host_value = str(host_override or deploy["bind_ip"] or "").strip()
    host_value = "0.0.0.0" if host_value in ("", "*") else host_value
    port_value = int(deploy["site_port"])
    return {
        "workdir": str(Path(deploy["deploy_root"]).resolve()),
        "install_cmd_unix": "npm install",
        "build_cmd_unix": "npm run build",
        "start_cmd_unix": f"npm run start -- --hostname {shlex.quote(host_value)} --port {port_value}",
        "npm_cmd_windows": _find_windows_command(["npm.cmd", "npm.exe", "npm"]),
        "node_cmd_windows": _find_windows_command(["node.exe", "node"]),
        "host_value": host_value,
        "port_value": port_value,
    }


def _website_php_start_command(deploy, host_override=""):
    host_value = str(host_override or deploy["bind_ip"] or "").strip()
    host_value = "0.0.0.0" if host_value in ("", "*") else host_value
    port_value = int(deploy["site_port"])
    public_rel = str(deploy.get("content_rel") or ".").strip()
    public_dir = Path(deploy["deploy_root"]) / public_rel if public_rel not in ("", ".") else Path(deploy["deploy_root"])
    return {
        "workdir": str(Path(deploy["deploy_root"]).resolve()),
        "php_cmd_windows": _find_windows_command(["php.exe", "php"]),
        "php_cmd_unix": shutil.which("php") or "php",
        "host_value": host_value,
        "port_value": port_value,
        "public_dir": str(public_dir.resolve()),
    }


def _prepare_nextjs_project(deploy, live_cb=None):
    cfg = _website_node_start_command(deploy)
    workdir = cfg["workdir"]
    if os.name == "nt":
        npm_cmd = cfg["npm_cmd_windows"]
        code, output = run_process([npm_cmd, "install"], live_cb=live_cb)
        if code != 0:
            return code, output or "npm install failed."
        code, output = run_process([npm_cmd, "run", "build"], live_cb=live_cb)
        if code != 0:
            return code, output or "npm run build failed."
        return 0, ""
    shell_cmd = "/bin/sh"
    install_build = f"cd {shlex.quote(workdir)} && npm install && npm run build"
    code, output = run_process([shell_cmd, "-lc", install_build], live_cb=live_cb)
    return code, output


def run_windows_website_service(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Website OS service deployment is only available on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    python_executable = resolve_windows_python()
    venv_dir = Path(deploy["deploy_root"]) / ".runtime"
    if venv_dir.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
    rc, out = run_capture([python_executable, "-m", "venv", str(venv_dir)], timeout=240)
    if rc != 0:
        return 1, out or "Failed to create Windows runtime environment for website service."
    venv_python = _python_api_venv_python(venv_dir)
    rc, out = run_capture([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "pywin32"], timeout=600)
    if rc != 0:
        return 1, out or "Failed to install Windows service runtime dependencies."
    rc_post, out_post = run_capture([venv_python, "-m", "pywin32_postinstall", "-install"], timeout=180)
    if rc_post != 0 and live_cb:
        text = str(out_post or "").strip()
        if "No module named pywin32_postinstall" in text:
            live_cb("pywin32_postinstall is not available in this pywin32 build; continuing with direct service host setup.\n")
        else:
            live_cb((text or "pywin32 postinstall returned a non-zero exit code.") + "\n")
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    if runtime == "static":
        service_script = _write_windows_website_service_file(Path(deploy["deploy_root"]), deploy["runtime_name"], deploy["bind_ip"], deploy["site_port"])
    elif runtime == "node":
        node_cfg = _website_node_start_command(deploy)
        code, output = _prepare_nextjs_project(deploy, live_cb=live_cb)
        if code != 0:
            return code, output
        service_script = Path(deploy["deploy_root"]) / "serverinstaller_nextjs_service.py"
        service_script.write_text(
            "\n".join([
                "import os",
                "import subprocess",
                "import sys",
                "import time",
                "import win32event",
                "import win32service",
                "import win32serviceutil",
                "import servicemanager",
                "",
                f"SERVICE_NAME = {deploy['runtime_name']!r}",
                f"WORKDIR = {node_cfg['workdir']!r}",
                f"NPM_CMD = {node_cfg['npm_cmd_windows']!r}",
                f"HOST_VALUE = {node_cfg['host_value']!r}",
                f"PORT_VALUE = {node_cfg['port_value']!r}",
                "",
                "class NextWebsiteService(win32serviceutil.ServiceFramework):",
                "    _svc_name_ = SERVICE_NAME",
                "    _svc_display_name_ = SERVICE_NAME",
                "    _svc_description_ = 'Server Installer managed Next.js website service'",
                "",
                "    def __init__(self, args):",
                "        win32serviceutil.ServiceFramework.__init__(self, args)",
                "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
                "        self.proc = None",
                "",
                "    def SvcStop(self):",
                "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
                "        if self.proc is not None and self.proc.poll() is None:",
                "            try:",
                "                self.proc.terminate()",
                "                self.proc.wait(timeout=20)",
                "            except Exception:",
                "                pass",
                "        win32event.SetEvent(self.stop_event)",
                "",
                "    def SvcDoRun(self):",
                "        os.chdir(WORKDIR)",
                "        self.proc = subprocess.Popen([NPM_CMD, 'run', 'start', '--', '--hostname', HOST_VALUE, '--port', str(PORT_VALUE)], cwd=WORKDIR)",
                "        while win32event.WaitForSingleObject(self.stop_event, 1000) != win32event.WAIT_OBJECT_0:",
                "            if self.proc.poll() is not None:",
                "                raise RuntimeError(f'Next.js process exited with code {self.proc.returncode}.')",
                "",
                "if __name__ == '__main__':",
                "    if len(sys.argv) == 1:",
                "        servicemanager.Initialize()",
                "        servicemanager.PrepareToHostSingle(NextWebsiteService)",
                "        servicemanager.StartServiceCtrlDispatcher()",
                "    else:",
                "        win32serviceutil.HandleCommandLine(NextWebsiteService)",
                "",
            ]),
            encoding="utf-8",
        )
    elif runtime == "php":
        php_cfg = _website_php_start_command(deploy)
        service_script = Path(deploy["deploy_root"]) / "serverinstaller_php_service.py"
        service_script.write_text(
            "\n".join([
                "import os",
                "import subprocess",
                "import sys",
                "import win32event",
                "import win32service",
                "import win32serviceutil",
                "import servicemanager",
                "",
                f"SERVICE_NAME = {deploy['runtime_name']!r}",
                f"WORKDIR = {php_cfg['workdir']!r}",
                f"PHP_CMD = {php_cfg['php_cmd_windows']!r}",
                f"PUBLIC_DIR = {php_cfg['public_dir']!r}",
                f"HOST_VALUE = {php_cfg['host_value']!r}",
                f"PORT_VALUE = {php_cfg['port_value']!r}",
                "",
                "class PhpWebsiteService(win32serviceutil.ServiceFramework):",
                "    _svc_name_ = SERVICE_NAME",
                "    _svc_display_name_ = SERVICE_NAME",
                "    _svc_description_ = 'Server Installer managed PHP website service'",
                "",
                "    def __init__(self, args):",
                "        win32serviceutil.ServiceFramework.__init__(self, args)",
                "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
                "        self.proc = None",
                "",
                "    def SvcStop(self):",
                "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
                "        if self.proc is not None and self.proc.poll() is None:",
                "            try:",
                "                self.proc.terminate()",
                "                self.proc.wait(timeout=20)",
                "            except Exception:",
                "                pass",
                "        win32event.SetEvent(self.stop_event)",
                "",
                "    def SvcDoRun(self):",
                "        os.chdir(WORKDIR)",
                "        self.proc = subprocess.Popen([PHP_CMD, '-S', f'{HOST_VALUE}:{PORT_VALUE}', '-t', PUBLIC_DIR], cwd=WORKDIR)",
                "        while win32event.WaitForSingleObject(self.stop_event, 1000) != win32event.WAIT_OBJECT_0:",
                "            if self.proc.poll() is not None:",
                "                raise RuntimeError(f'PHP process exited with code {self.proc.returncode}.')",
                "",
                "if __name__ == '__main__':",
                "    if len(sys.argv) == 1:",
                "        servicemanager.Initialize()",
                "        servicemanager.PrepareToHostSingle(PhpWebsiteService)",
                "        servicemanager.StartServiceCtrlDispatcher()",
                "    else:",
                "        win32serviceutil.HandleCommandLine(PhpWebsiteService)",
                "",
            ]),
            encoding="utf-8",
        )
    else:
        return 1, f"Unsupported website runtime '{runtime}' for Windows service deployment."
    run_capture(["sc.exe", "stop", deploy["runtime_name"]], timeout=30)
    run_capture([venv_python, str(service_script), "remove"], timeout=60)
    rc, out = run_capture([venv_python, str(service_script), "--startup", "auto", "install"], timeout=180)
    service_started = False
    if rc == 0:
        rc2, out2 = run_capture([venv_python, str(service_script), "start"], timeout=120)
        if rc2 == 0:
            # Verify service is actually running
            import time
            time.sleep(2)
            state_text, _ = _windows_service_state(deploy["runtime_name"])
            service_started = state_text.lower() == "running"
    if not service_started:
        # Fallback: run as a background process (pywin32 service framework often fails)
        if live_cb:
            live_cb("Windows service registration failed or didn't start. Launching as background process...\n")
        import subprocess
        subprocess.Popen(
            [venv_python, str(service_script), "--foreground"] if runtime != "static" else [venv_python, "-m", "http.server", str(deploy["site_port"]), "--bind", "0.0.0.0" if deploy["bind_ip"] in ("", "*") else deploy["bind_ip"], "--directory", str(deploy["deploy_root"])],
            cwd=str(deploy["deploy_root"]),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if live_cb:
            live_cb("Website started as background process.\n")
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    _write_website_state_entry({
        "name": deploy["runtime_name"],
        "form_name": deploy["site_name"],
        "kind": "service",
        "target": "service",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    return 0, f"Website OS service deployed.\nService: {deploy['runtime_name']}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_unix_website_service(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Unix website service deployment is not available on Windows hosts."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    bind_host = "0.0.0.0" if deploy["bind_ip"] in ("", "*") else deploy["bind_ip"]
    python_executable = resolve_unix_python()
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    prefix = _sudo_prefix()
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    if runtime == "static":
        runner_script = Path(deploy["deploy_root"]) / "serve_static_site.py"
        runner_script.write_text(
            "\n".join([
                "import functools",
                "import http.server",
                "import socketserver",
                "",
                f"ROOT_DIR = {str(Path(deploy['deploy_root']).resolve())!r}",
                f"BIND_HOST = {bind_host!r}",
                f"PORT = {int(deploy['site_port'])}",
                "",
                "class ReusableTCPServer(socketserver.ThreadingTCPServer):",
                "    allow_reuse_address = True",
                "",
                "handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT_DIR)",
                "with ReusableTCPServer((BIND_HOST, PORT), handler) as httpd:",
                "    httpd.serve_forever()",
                "",
            ]),
            encoding="utf-8",
        )
        exec_start = f"{shlex.quote(str(python_executable))} {shlex.quote(str(runner_script))}"
    elif runtime == "node":
        node_cfg = _website_node_start_command(deploy, host_override=bind_host)
        code, output = _prepare_nextjs_project(deploy, live_cb=live_cb)
        if code != 0:
            return code, output
        exec_start = f"/bin/sh -lc {shlex.quote(node_cfg['start_cmd_unix'])}"
    elif runtime == "php":
        php_cfg = _website_php_start_command(deploy, host_override=bind_host)
        exec_start = f"{shlex.quote(str(php_cfg['php_cmd_unix']))} -S {bind_host}:{int(deploy['site_port'])} -t {shlex.quote(str(php_cfg['public_dir']))}"
    else:
        return 1, f"Unsupported website runtime '{runtime}' for OS service deployment."
    if platform.system() == "Darwin":
        plist_name = f"com.serverinstaller.website.{deploy['runtime_name']}"
        plist_path = Path("/Library/LaunchDaemons") / f"{plist_name}.plist"
        plist_temp = Path(deploy["deploy_root"]) / f"{plist_name}.plist"
        plist_temp.write_text(
            "\n".join([
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0">',
                "<dict>",
                f"  <key>Label</key><string>{plist_name}</string>",
                "  <key>ProgramArguments</key>",
                "  <array>",
                *([f"    <string>{part}</string>" for part in ([str(python_executable), str(runner_script)] if runtime == "static" else (["/bin/sh", "-lc", node_cfg['install_cmd_unix'] + ' && ' + node_cfg['build_cmd_unix'] + ' && ' + node_cfg['start_cmd_unix']] if runtime == "node" else [str(php_cfg['php_cmd_unix']), "-S", f"{bind_host}:{int(deploy['site_port'])}", "-t", str(php_cfg['public_dir'])]))]),
                "  </array>",
                f"  <key>WorkingDirectory</key><string>{str(Path(deploy['deploy_root']).resolve())}</string>",
                "  <key>RunAtLoad</key><true/>",
                "  <key>KeepAlive</key><true/>",
                "  <key>StandardOutPath</key><string>/tmp/serverinstaller-website.log</string>",
                "  <key>StandardErrorPath</key><string>/tmp/serverinstaller-website.log</string>",
                "</dict>",
                "</plist>",
                "",
            ]),
            encoding="utf-8",
        )
        run_capture(prefix + ["launchctl", "bootout", "system", str(plist_path)], timeout=30)
        run_capture(prefix + ["cp", str(plist_temp), str(plist_path)], timeout=30)
        rc, out = run_capture(prefix + ["launchctl", "bootstrap", "system", str(plist_path)], timeout=60)
        if rc != 0:
            return 1, out or f"Failed to bootstrap launchd website '{plist_name}'."
        _write_website_state_entry({
            "name": deploy["runtime_name"],
            "form_name": deploy["site_name"],
            "kind": "website_launchd",
            "target": "service",
            "website_kind": deploy["website_kind"],
            "stack_label": deploy["stack_label"],
            "url": url,
            "bind_ip": deploy["bind_ip"],
            "host": deploy["host"],
            "port": deploy["site_port"],
            "deploy_root": deploy["deploy_root"],
            "source_root": deploy["source_root"],
            "publish_root": deploy["publish_root"],
            "publish_rel": deploy["publish_rel"],
            "plist_name": plist_name,
        })
        manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
        return 0, f"Website launchd service deployed.\nService: {plist_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"
    unit_name = f"{deploy['runtime_name']}.service"
    unit_temp = Path(deploy["deploy_root"]) / unit_name
    unit_temp.write_text(
        "\n".join([
            "[Unit]",
            f"Description={deploy['site_name']}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={str(Path(deploy['deploy_root']).resolve())}",
            f"ExecStart={exec_start}",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
    run_capture(prefix + ["cp", str(unit_temp), f"/etc/systemd/system/{unit_name}"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    rc, out = run_capture(prefix + ["systemctl", "enable", "--now", unit_name], timeout=60)
    if rc != 0:
        return 1, out or f"Failed to enable website service '{unit_name}'."
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    _write_website_state_entry({
        "name": unit_name,
        "form_name": deploy["site_name"],
        "kind": "service",
        "target": "service",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    return 0, f"Website OS service deployed.\nService: {unit_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_website_docker(form=None, live_cb=None):
    form = form or {}
    if not command_exists("docker"):
        return 1, "Docker is not available on this host."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    runtime = str(deploy.get("runtime") or "static").strip().lower()
    dockerfile = Path(deploy["deploy_root"]) / "Dockerfile"
    if runtime == "static":
        dockerfile.write_text(
            "\n".join([
                "FROM nginx:alpine",
                "WORKDIR /usr/share/nginx/html",
                "RUN rm -rf /usr/share/nginx/html/*",
                "COPY ./ /usr/share/nginx/html/",
                "EXPOSE 80",
                'CMD ["nginx", "-g", "daemon off;"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = 80
    elif runtime == "node":
        dockerfile.write_text(
            "\n".join([
                "FROM node:20-alpine",
                "WORKDIR /app",
                "COPY . ./",
                "RUN npm install",
                "RUN npm run build",
                f"EXPOSE {int(deploy['site_port'])}",
                f'CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "{int(deploy["site_port"])}"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = int(deploy["site_port"])
    elif runtime == "php":
        public_rel = str(deploy.get("content_rel") or ".").strip()
        php_root = f"/app/{public_rel}" if public_rel not in ("", ".") else "/app"
        dockerfile.write_text(
            "\n".join([
                "FROM php:8.2-cli-alpine",
                "WORKDIR /app",
                "COPY . /app/",
                f"EXPOSE {int(deploy['site_port'])}",
                f'CMD ["php", "-S", "0.0.0.0:{int(deploy["site_port"])}", "-t", "{php_root}"]',
                "",
            ]),
            encoding="utf-8",
        )
        container_port = int(deploy["site_port"])
    else:
        return 1, f"Unsupported website runtime '{runtime}' for Docker deployment."
    image_name = f"{deploy['runtime_name']}-image"
    container_name = deploy["runtime_name"]
    run_capture(["docker", "rm", "-f", container_name], timeout=30)
    run_capture(["docker", "rmi", "-f", image_name], timeout=30)
    code, output = run_process(["docker", "build", "-t", image_name, str(deploy["deploy_root"])], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."
    publish_binding = f"{deploy['site_port']}:{container_port}"
    bind_host = str(deploy["bind_ip"] or "").strip()
    if bind_host and bind_host not in ("*", "0.0.0.0"):
        publish_binding = f"{bind_host}:{deploy['site_port']}:{container_port}"
    code, output = run_process(
        [
            "docker", "run", "-d",
            "--restart", "unless-stopped",
            "--name", container_name,
            "--label", "com.serverinstaller.website=true",
            "-p", publish_binding,
            image_name,
        ],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."
    manage_firewall_port("open", deploy["site_port"], "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}" if int(deploy["site_port"]) == 80 else f"http://{deploy['host']}:{deploy['site_port']}"
    _write_website_state_entry({
        "name": container_name,
        "form_name": deploy["site_name"],
        "kind": "docker",
        "target": "docker",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "bind_ip": deploy["bind_ip"],
        "host": deploy["host"],
        "port": deploy["site_port"],
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
        "image_name": image_name,
    })
    return 0, f"Website Docker deployment completed.\nContainer: {container_name}\nURL: {url}\nContent: {deploy['publish_root']}\n"


def run_windows_website_iis(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Website IIS deployment is currently available on Windows hosts only."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    iis_info = get_iis_info()
    if not iis_info.get("installed"):
        return 1, "IIS is not installed. Use the DotNet IIS setup page first."
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    usage = get_port_usage(deploy["site_port"], "tcp")
    if usage.get("busy") and not usage.get("managed_owner"):
        return 1, f"Requested website port {deploy['site_port']} is already in use. Choose another port."
    _cleanup_existing_website_runtime(deploy.get("existing_payload"))
    https_port = deploy.get("https_port", 0)
    if live_cb:
        live_cb(f"Deploying IIS website '{deploy['site_name']}' from {deploy['publish_root']}\n")
        if https_port:
            live_cb(f"HTTPS port: {https_port}\n")
    ssl_cert_name = deploy.get("ssl_cert_name", "self_signed")
    bind_ip = deploy['bind_ip'] if deploy['bind_ip'] != '*' else '*'
    domain = deploy.get("domain", "").strip()
    dns_name = domain or deploy['host']

    # Build HTTPS binding commands if an HTTPS port was specified
    http_port = deploy["site_port"]
    https_ps_lines = []
    if https_port:
        # Include domain in cert if set
        cert_dns_names = [dns_name, "localhost", "127.0.0.1"]
        if domain and domain not in cert_dns_names:
            cert_dns_names.insert(0, domain)
        dns_list = ",".join([f"'{d}'" for d in cert_dns_names])
        https_ps_lines = [
            f"New-WebBinding -Name $siteName -Protocol 'https' -Port {int(https_port)} -IPAddress $ip -ErrorAction SilentlyContinue | Out-Null",
            f"$cert = New-SelfSignedCertificate -DnsName @({dns_list}) -CertStoreLocation 'cert:\\LocalMachine\\My' -FriendlyName ('ServerInstaller Website ' + $siteName)",
            "$bindingPath = ($(if ($ip -eq '*') { '0.0.0.0' } else { $ip })) + '!' + " + str(int(https_port)),
            "if (Test-Path ('IIS:\\SslBindings\\' + $bindingPath)) { Remove-Item ('IIS:\\SslBindings\\' + $bindingPath) -Force -ErrorAction SilentlyContinue }",
            "New-Item ('IIS:\\SslBindings\\' + $bindingPath) -Thumbprint $cert.Thumbprint -SSLFlags 0 | Out-Null",
        ]

    # When only HTTPS is set (no HTTP port), create the site on the HTTPS port with SSL;
    # when only HTTP is set, create normally; when both, create on HTTP and add HTTPS binding.
    initial_port = http_port if http_port else https_port
    initial_protocol_args = "-Ssl" if (not http_port and https_port) else ""

    # Create site with plain port bindings (NO host headers - responds to any hostname)
    # Domain access works via DNS/hosts file, not IIS host headers
    ps_lines = [
        "Import-Module WebAdministration",
        f"$siteName = {_ps_single_quote(deploy['site_name'])}",
        f"$appPool = {_ps_single_quote(deploy['site_name'])}",
        f"$physicalPath = {_ps_single_quote(deploy['deploy_root'])}",
        f"$ip = {_ps_single_quote(bind_ip)}",
        f"$port = {int(initial_port)}",
        # Remove existing site completely
        "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
        "if (Test-Path ('IIS:\\AppPools\\' + $appPool)) { Stop-WebAppPool -Name $appPool -ErrorAction SilentlyContinue | Out-Null; Remove-WebAppPool -Name $appPool -ErrorAction SilentlyContinue | Out-Null }",
        # Create fresh app pool and site
        "New-WebAppPool -Name $appPool | Out-Null",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name managedRuntimeVersion -Value ''",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name processModel.identityType -Value 4",
        f"New-Website -Name $siteName -PhysicalPath $physicalPath -Port $port -IPAddress $ip {initial_protocol_args} -ApplicationPool $appPool | Out-Null".replace("  ", " "),
        *(https_ps_lines if http_port else []),
    ]
    ps_lines.append("Start-Website -Name $siteName | Out-Null")

    # Add domain to hosts file so it resolves on this machine
    if domain:
        ip_for_hosts = bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host()
        _add_hosts_entry(domain, ip_for_hosts, live_cb=live_cb)

    ps = "\n".join(ps_lines)
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=180)
    if rc != 0:
        return 1, out or f"Failed to create IIS website '{deploy['site_name']}'."
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
    if https_port:
        manage_firewall_port("open", https_port, "tcp", host=deploy.get("host"))

    # Build URLs (use domain if set, otherwise IP)
    url_host = deploy['host']
    urls = []
    if http_port:
        http_url = f"http://{url_host}" if http_port == 80 else f"http://{url_host}:{http_port}"
        urls.append(http_url)
    else:
        http_url = ""
    if https_port:
        https_url = f"https://{url_host}" if https_port == 443 else f"https://{url_host}:{https_port}"
        urls.append(https_url)
    else:
        https_url = ""
    # Also build IP-based URLs for display if domain is set
    ip_host = bind_ip if bind_ip not in ("", "*", "0.0.0.0") else choose_service_host()
    if domain and ip_host != domain:
        if http_port:
            ip_http = f"http://{ip_host}" if http_port == 80 else f"http://{ip_host}:{http_port}"
            urls.append(ip_http)
        if https_port:
            ip_https = f"https://{ip_host}" if https_port == 443 else f"https://{ip_host}:{https_port}"
            urls.append(ip_https)
    url = urls[0] if urls else ""

    _write_website_state_entry({
        "name": deploy["site_name"],
        "form_name": deploy["site_name"],
        "kind": "iis_site",
        "target": "iis",
        "website_kind": deploy["website_kind"],
        "stack_label": deploy["stack_label"],
        "url": url,
        "urls": urls,
        "https_url": https_url,
        "bind_ip": deploy["bind_ip"],
        "domain": domain,
        "host": deploy["host"],
        "port": http_port,
        "https_port": https_port,
        "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"],
        "publish_root": deploy["publish_root"],
        "publish_rel": deploy["publish_rel"],
    })
    result_lines = [f"Website IIS deployment completed.", f"Site: {deploy['site_name']}"]
    if domain:
        result_lines.append(f"Domain: {domain}")
    for u in urls:
        result_lines.append(f"URL: {u}")
    result_lines.append(f"Content: {deploy['publish_root']}")
    if domain:
        result_lines.append(f"\nDomain '{domain}' added to this server's hosts file.")
        result_lines.append(f"To access from other devices, add this to their hosts file:")
        if os.name == "nt":
            result_lines.append(f"  Windows: C:\\Windows\\System32\\drivers\\etc\\hosts")
        else:
            result_lines.append(f"  Linux/Mac: /etc/hosts")
        result_lines.append(f"  {ip_host}  {domain}")
    return 0, "\n".join(result_lines) + "\n"


def run_website_deploy(form=None, live_cb=None):
    form = form or {}
    target = (form.get("WEBSITE_TARGET", ["service"])[0] or "service").strip().lower()
    engine = (form.get("WEBSITE_ENGINE", [""])[0] or "").strip().lower()
    # Map engine → target if engine is specified but target is generic
    if engine and engine != target:
        target = engine if engine in ("docker", "iis", "nginx", "nodejs", "kubernetes", "pm2") else target
        form["WEBSITE_TARGET"] = [target]
    if target == "iis":
        return run_windows_website_iis(form=form, live_cb=live_cb)
    if target == "docker":
        return run_website_docker(form=form, live_cb=live_cb)
    if target == "kubernetes":
        return _run_website_kubernetes(form=form, live_cb=live_cb)
    if target == "nginx":
        return _run_website_nginx(form=form, live_cb=live_cb)
    if target == "nodejs":
        return _run_website_nodejs(form=form, live_cb=live_cb)
    if target == "pm2":
        return _run_website_pm2(form=form, live_cb=live_cb)
    if os.name == "nt":
        return run_windows_website_service(form=form, live_cb=live_cb)
    return run_unix_website_service(form=form, live_cb=live_cb)


def _run_website_nginx(form=None, live_cb=None):
    """Deploy website using Nginx."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to Nginx: {deploy['site_name']}\n")
    # Ensure nginx is installed
    if not command_exists("nginx"):
        if live_cb:
            live_cb("Nginx not found. Installing...\n")
        code, msg = _install_website_engine("nginx", live_cb=live_cb)
        if code != 0:
            return code, msg
    site_conf_name = f"serverinstaller-{deploy['runtime_name']}"
    content_root = deploy["publish_root"]
    port = deploy["site_port"] or 80
    server_name = deploy.get("domain") or "_"
    # Build nginx config
    conf_lines = [
        f"server {{",
        f"    listen {port};",
        f"    server_name {server_name};",
        f"    root {content_root};",
        f"    index index.html index.htm index.php;",
        f"",
    ]
    if deploy.get("runtime") == "php":
        conf_lines += [
            f"    location ~ \\.php$ {{",
            f"        fastcgi_pass unix:/run/php/php-fpm.sock;",
            f"        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;",
            f"        include fastcgi_params;",
            f"    }}",
        ]
    conf_lines += [
        f"    location / {{",
        f"        try_files $uri $uri/ /index.html =404;",
        f"    }}",
        f"}}",
    ]
    conf_text = "\n".join(conf_lines) + "\n"
    # Write config
    nginx_sites = Path("/etc/nginx/sites-enabled")
    nginx_conf_d = Path("/etc/nginx/conf.d")
    if nginx_sites.exists():
        conf_path = nginx_sites / f"{site_conf_name}.conf"
    elif nginx_conf_d.exists():
        conf_path = nginx_conf_d / f"{site_conf_name}.conf"
    else:
        return 1, "Cannot find /etc/nginx/sites-enabled or /etc/nginx/conf.d."
    conf_path.write_text(conf_text, encoding="utf-8")
    if live_cb:
        live_cb(f"Wrote Nginx config to {conf_path}\n")
    # Test and reload
    rc, out = run_capture(["nginx", "-t"], timeout=15)
    if rc != 0:
        return 1, f"Nginx config test failed:\n{out}"
    rc, out = run_capture(["nginx", "-s", "reload"], timeout=15)
    if rc != 0:
        if command_exists("systemctl"):
            rc, out = run_capture(["systemctl", "reload", "nginx"], timeout=15)
    manage_firewall_port("open", str(port), "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}:{port}"
    _write_website_state_entry({
        "name": deploy["runtime_name"], "form_name": deploy["site_name"],
        "kind": "website_nginx", "target": "nginx",
        "website_kind": deploy["website_kind"], "stack_label": deploy["stack_label"],
        "url": url, "bind_ip": deploy["bind_ip"], "host": deploy["host"],
        "port": port, "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"], "publish_root": deploy["publish_root"],
        "conf_path": str(conf_path),
    })
    return 0, f"Website deployed to Nginx.\nConfig: {conf_path}\nURL: {url}\nContent: {content_root}\n"


def _run_website_nodejs(form=None, live_cb=None):
    """Deploy website using Node.js (serve or next start)."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to Node.js: {deploy['site_name']}\n")
    if not command_exists("node"):
        if live_cb:
            live_cb("Node.js not found. Installing...\n")
        code, msg = _install_website_engine("nodejs", live_cb=live_cb)
        if code != 0:
            return code, msg
    # For Node.js, fall through to the OS service deployer which already handles node runtime
    form["WEBSITE_TARGET"] = ["service"]
    if os.name == "nt":
        return run_windows_website_service(form=form, live_cb=live_cb)
    return run_unix_website_service(form=form, live_cb=live_cb)


def _run_website_pm2(form=None, live_cb=None):
    """Deploy website using PM2 process manager."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"Deploying to PM2: {deploy['site_name']}\n")
    if not command_exists("pm2"):
        if live_cb:
            live_cb("PM2 not found. Installing...\n")
        code, msg = _install_website_engine("pm2", live_cb=live_cb)
        if code != 0:
            return code, msg
    port = deploy["site_port"] or 3000
    app_name = deploy["runtime_name"]
    content_root = deploy["publish_root"]
    # Determine start command
    if deploy.get("runtime") == "node" and deploy.get("website_kind") == "nextjs":
        # Next.js — npm start
        if live_cb:
            live_cb("Installing npm dependencies...\n")
        try:
            subprocess.run(["npm", "install"], cwd=content_root, timeout=300, capture_output=True)
            subprocess.run(["npm", "run", "build"], cwd=content_root, timeout=300, capture_output=True)
        except Exception:
            pass
        start_script = f"PORT={port} npm start"
    else:
        # Static — use npx serve
        if not command_exists("serve"):
            run_capture(["npm", "install", "-g", "serve"], timeout=60)
        start_script = f"serve -s {content_root} -l {port}"
    # Stop existing PM2 process with same name
    run_capture(["pm2", "delete", app_name], timeout=15)
    # Start with PM2
    rc, out = run_capture(["pm2", "start", "--name", app_name, "--", "bash", "-c", start_script], timeout=60)
    if rc != 0:
        # Try alternative: use pm2 ecosystem file
        ecosystem = {
            "name": app_name,
            "script": "npx",
            "args": f"serve -s {content_root} -l {port}" if deploy.get("runtime") != "node" else "npm start",
            "cwd": content_root,
            "env": {"PORT": str(port)},
        }
        eco_path = Path(content_root) / "ecosystem.config.js"
        eco_path.write_text(f"module.exports = {{ apps: [{json.dumps(ecosystem)}] }};", encoding="utf-8")
        rc, out = run_capture(["pm2", "start", str(eco_path)], timeout=60)
    if rc == 0:
        run_capture(["pm2", "save"], timeout=15)
    manage_firewall_port("open", str(port), "tcp", host=deploy.get("host"))
    url = f"http://{deploy['host']}:{port}"
    _write_website_state_entry({
        "name": deploy["runtime_name"], "form_name": deploy["site_name"],
        "kind": "website_pm2", "target": "pm2",
        "website_kind": deploy["website_kind"], "stack_label": deploy["stack_label"],
        "url": url, "bind_ip": deploy["bind_ip"], "host": deploy["host"],
        "port": port, "deploy_root": deploy["deploy_root"],
        "source_root": deploy["source_root"], "publish_root": deploy["publish_root"],
    })
    return rc, f"Website deployed to PM2.\nApp: {app_name}\nURL: {url}\nContent: {content_root}\n" if rc == 0 else f"PM2 deployment failed:\n{out}"


def _run_website_kubernetes(form=None, live_cb=None):
    """Deploy website to Kubernetes (K3s)."""
    form = form or {}
    try:
        deploy = _prepare_website_deployment(form, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
def _windows_service_state(service_name):
    rc, out = run_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"$svc=Get-CimInstance Win32_Service -Filter \"Name='{service_name}'\" -ErrorAction SilentlyContinue; if($svc){{Write-Output ($svc.State + '|' + $svc.StartMode)}}",
        ],
        timeout=20,
    )
    if rc != 0 or not out:
        return "", ""
    parts = str(out).strip().split("|", 1)
    state = parts[0].strip() if parts else ""
    start_mode = parts[1].strip() if len(parts) > 1 else ""
    return state, start_mode


def run_windows_python_api_service(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python API OS service deployment is only available on Windows from this page."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    service_name = _safe_python_api_name((form.get("PYTHON_API_SERVICE_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, service_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    certfile, keyfile = _ensure_python_api_https_assets(deploy["python_executable"], deploy["host"], service_name)
    if not certfile or not keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API service."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme", "pywin32"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    rc_post, out_post = run_capture([venv_python, "-m", "pywin32_postinstall", "-install"], timeout=180)
    if rc_post != 0 and live_cb:
        text = str(out_post or "").strip()
        if "No module named pywin32_postinstall" in text:
            live_cb("pywin32_postinstall is not available in this pywin32 build; continuing with direct service host setup.\n")
        else:
            live_cb((text or "pywin32 postinstall returned a non-zero exit code.") + "\n")
    # Copy pywintypes DLLs to the venv root so pythonservice.exe can load them.
    # pywin32_postinstall normally does this to the system Python dir; for a venv
    # we replicate the DLLs next to pythonservice.exe (the venv root).
    venv_root = Path(venv_python).resolve().parent
    pywin32_sys32 = venv_root / "Lib" / "site-packages" / "pywin32_system32"
    if pywin32_sys32.is_dir():
        for dll in pywin32_sys32.glob("pywintypes*.dll"):
            dst = venv_root / dll.name
            if not dst.exists():
                try:
                    shutil.copy2(str(dll), str(dst))
                    if live_cb:
                        live_cb(f"Copied {dll.name} to venv root for service DLL resolution.\n")
                except Exception as exc:
                    if live_cb:
                        live_cb(f"Warning: could not copy {dll.name}: {exc}\n")
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        deploy["host"],
        deploy["https_port"],
        certfile=certfile,
        keyfile=keyfile,
    )
    service_script = deploy["deploy_root"] / ".serverinstaller" / "windows_service.py"
    service_log = deploy["deploy_root"] / ".serverinstaller" / "service-runtime.log"
    service_script.write_text(
        "\n".join([
            "import os",
            "import subprocess",
            "import sys",
            "import time",
            "# Bootstrap pywin32 DLL dirs before importing pywin32 modules.",
            "# Required in venvs where pywin32_postinstall has not been run.",
            "def _bootstrap_pywin32():",
            "    venv_root = os.path.dirname(os.path.abspath(sys.executable))",
            "    try:",
            "        import site",
            "        bases = list(site.getsitepackages())",
            "    except Exception:",
            "        bases = []",
            "    bases.append(os.path.join(venv_root, 'Lib', 'site-packages'))",
            "    for base in bases:",
            "        dll_dir = os.path.join(base, 'pywin32_system32')",
            "        if os.path.isdir(dll_dir):",
            "            if hasattr(os, 'add_dll_directory'):",
            "                try: os.add_dll_directory(dll_dir)",
            "                except Exception: pass",
            "            if dll_dir not in sys.path: sys.path.insert(0, dll_dir)",
            "        for rel in ('win32', os.path.join('win32', 'lib'), 'pythonwin'):",
            "            p = os.path.join(base, rel)",
            "            if os.path.isdir(p) and p not in sys.path: sys.path.insert(0, p)",
            "_bootstrap_pywin32()",
            "import win32event",
            "import servicemanager",
            "import win32service",
            "import win32serviceutil",
            "",
            f"RUNNER = r'''{str(runner_script.resolve())}'''",
            f"LOG_PATH = r'''{str(service_log.resolve())}'''",
            f"SERVICE_NAME = {service_name!r}",
            f"DISPLAY_NAME = {service_name.replace('-', ' ').title()!r}",
            "",
            "class PythonApiService(win32serviceutil.ServiceFramework):",
            "    _svc_name_ = SERVICE_NAME",
            "    _svc_display_name_ = DISPLAY_NAME",
            "    _svc_description_ = 'Server Installer managed Python API service'",
            "    def __init__(self, args):",
            "        win32serviceutil.ServiceFramework.__init__(self, args)",
            "        self.stop_event = win32event.CreateEvent(None, 0, 0, None)",
            "        self.proc = None",
            "        self.log_handle = None",
            "    def SvcStop(self):",
            "        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)",
            "        if self.proc and self.proc.poll() is None:",
            "            self.proc.terminate()",
            "            try:",
            "                self.proc.wait(timeout=15)",
            "            except Exception:",
            "                self.proc.kill()",
            "        if self.log_handle:",
            "            self.log_handle.flush()",
            "            self.log_handle.close()",
            "        win32event.SetEvent(self.stop_event)",
            "    def SvcDoRun(self):",
            "        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)",
            "        self.log_handle = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)",
            "        self.log_handle.write(f'[{time.strftime(\"%Y-%m-%d %H:%M:%S\")}] Service starting\\n')",
            f"        self.proc = subprocess.Popen([r'''{venv_python}''', RUNNER], cwd=r'''{str(deploy['deploy_root'].resolve())}''', stdout=self.log_handle, stderr=subprocess.STDOUT, creationflags=0x08000000)",
            "        self.ReportServiceStatus(win32service.SERVICE_RUNNING)",
            "        servicemanager.LogInfoMsg(f'{SERVICE_NAME} started')",
            "        while True:",
            "            status = win32event.WaitForSingleObject(self.stop_event, 2000)",
            "            if status == win32event.WAIT_OBJECT_0:",
            "                break",
            "            if self.proc.poll() is not None:",
            "                if self.log_handle:",
            "                    self.log_handle.write(f'[{time.strftime(\"%Y-%m-%d %H:%M:%S\")}] Runner exited with code {self.proc.returncode}\\n')",
            "                    self.log_handle.flush()",
            "                raise RuntimeError(f'Python API process exited with code {self.proc.returncode}.')",
            "",
            "if __name__ == '__main__':",
            "    if len(sys.argv) == 1:",
            "        servicemanager.Initialize()",
            "        servicemanager.PrepareToHostSingle(PythonApiService)",
            "        servicemanager.StartServiceCtrlDispatcher()",
            "    else:",
            "        win32serviceutil.HandleCommandLine(PythonApiService)",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture([deploy["python_executable"], str(service_script), "remove"], timeout=60)
    code, output = run_process([venv_python, str(service_script), "--startup", "auto", "install"], live_cb=live_cb)
    if code != 0:
        return code, output or "Failed to install the Windows Python API service."
    code, output = run_process([venv_python, str(service_script), "start"], live_cb=live_cb)
    if code != 0 and live_cb:
        live_cb((output or "Service start command returned a non-zero exit code.") + "\n")
    deadline = time.time() + 25
    service_state = ""
    start_mode = ""
    while time.time() < deadline:
        service_state, start_mode = _windows_service_state(service_name)
        if service_state.lower() == "running":
            break
        time.sleep(1)
    if service_state.lower() != "running":
        try:
            runtime_log = service_log.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            runtime_log = ""
        detail = runtime_log[-4000:] if runtime_log else (output or "Service did not reach the Running state.")
        return 1, f"Windows service '{service_name}' failed to start.\nService state: {service_state or 'unknown'}\n{detail}"
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(service_name, {
        "kind": "service",
        "name": service_name,
        "form_name": service_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
        "service_log": str(service_log),
    })
    return 0, f"Python API OS service deployed.\nService: {service_name}\nURL: {url}\nEntry file: {deploy['entry_rel']}\n"


def run_unix_python_api_service(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Python API OS service deployment from this page is for Linux/macOS hosts."
    ensure_repo_files(PYTHON_UNIX_FILES, live_cb=live_cb)
    service_name = _safe_python_api_name((form.get("PYTHON_API_SERVICE_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, service_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    certfile, keyfile = _ensure_python_api_https_assets(deploy["python_executable"], deploy["host"], service_name)
    if not certfile or not keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API service."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        deploy["host"],
        deploy["https_port"],
        certfile=certfile,
        keyfile=keyfile,
    )
    prefix = _sudo_prefix()
    unit_name = f"{service_name}.service"
    unit_temp = deploy["deploy_root"] / f"{unit_name}"
    unit_temp.write_text(
        "\n".join([
            "[Unit]",
            f"Description={service_name}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={str(deploy['deploy_root'])}",
            f"ExecStart={shlex.quote(str(venv_python))} {shlex.quote(str(runner_script))}",
            "Restart=always",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]),
        encoding="utf-8",
    )
    run_capture(prefix + ["systemctl", "stop", unit_name], timeout=30)
    run_capture(prefix + ["cp", str(unit_temp), f"/etc/systemd/system/{unit_name}"], timeout=30)
    run_capture(prefix + ["systemctl", "daemon-reload"], timeout=30)
    rc_enable, out_enable = run_capture(prefix + ["systemctl", "enable", "--now", unit_name], timeout=60)
    if rc_enable != 0:
        return 1, out_enable or f"Failed to enable and start {unit_name}."
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    http_port = deploy.get("http_port", "")
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
        _setup_nginx_http_redirect(service_name, http_port, deploy["https_port"], live_cb=live_cb)
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(service_name, {
        "kind": "service",
        "name": unit_name,
        "form_name": service_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API OS service deployed.\nService: {unit_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_python_api_docker(form=None, live_cb=None):
    form = form or {}
    if not command_exists("docker"):
        return 1, "Docker is not available on this host."
    deployment_name = _safe_python_api_name((form.get("PYTHON_API_CONTAINER_NAME", ["serverinstaller-python-api"])[0] or "").strip(), "serverinstaller-python-api")
    try:
        deploy = _prepare_python_api_deployment(form, deployment_name, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if is_local_tcp_port_listening(deploy["https_port"]):
        usage = get_port_usage(deploy["https_port"], "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested HTTPS port {deploy['https_port']} is already in use. Choose another port."
    # Generate TLS certs on the host first, then copy them into the build context
    host_certfile, host_keyfile = _ensure_python_api_https_assets(deploy["python_executable"], "0.0.0.0", deployment_name)
    if not host_certfile or not host_keyfile:
        return 1, "Failed to create HTTPS certificate files for the Python API Docker container."
    runtime_dir, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        "0.0.0.0",
        deploy["https_port"],
        certfile="/app/.serverinstaller/tls-cert.pem",
        keyfile="/app/.serverinstaller/tls-key.pem",
    )
    shutil.copy2(host_certfile, runtime_dir / "tls-cert.pem")
    shutil.copy2(host_keyfile, runtime_dir / "tls-key.pem")
    # Rewrite run_api.py to use container-internal paths (not host paths)
    _entry_rel = deploy["entry_rel"]
    _app_object = str(deploy["app_object"] or "").strip()
    _https_port = str(deploy["https_port"]).strip()
    runner_script.write_text(
        "\n".join([
            "import os",
            "import runpy",
            f"os.environ['SERVER_INSTALLER_APP_FILE'] = '/app/app/{_entry_rel}'",
            f"os.environ['SERVER_INSTALLER_APP_OBJECT'] = r'''{_app_object}'''",
            "os.environ['SERVER_INSTALLER_HOST'] = '0.0.0.0'",
            f"os.environ['SERVER_INSTALLER_PORT'] = r'''{_https_port}'''",
            "os.environ['SERVER_INSTALLER_CERTFILE'] = '/app/.serverinstaller/tls-cert.pem'",
            "os.environ['SERVER_INSTALLER_KEYFILE'] = '/app/.serverinstaller/tls-key.pem'",
            "runpy.run_path('/app/.serverinstaller/serverinstaller_python_api_host.py', run_name='__main__')",
            "",
        ]),
        encoding="utf-8",
    )
    dockerfile = deploy["deploy_root"] / "Dockerfile"
    dockerfile.write_text(
        "\n".join([
            "FROM python:3.12-slim",
            "WORKDIR /app",
            "COPY app/ /app/app/",
            "COPY .serverinstaller/ /app/.serverinstaller/",
            "RUN python -m venv /opt/serverinstaller-venv \\",
            " && /opt/serverinstaller-venv/bin/python -m pip install --upgrade pip setuptools wheel uvicorn \\",
            " && if [ -f /app/app/requirements.txt ]; then /opt/serverinstaller-venv/bin/python -m pip install -r /app/app/requirements.txt; fi",
            f"EXPOSE {deploy['https_port']}",
            "ENV PATH=/opt/serverinstaller-venv/bin:$PATH",
            f'CMD ["/opt/serverinstaller-venv/bin/python", "/app/.serverinstaller/{runner_script.name}"]',
            "",
        ]),
        encoding="utf-8",
    )
    image_name = deployment_name
    run_capture(["docker", "rm", "-f", deployment_name], timeout=30)
    code, output = run_process(["docker", "build", "-t", image_name, str(deploy["deploy_root"])], live_cb=live_cb)
    if code != 0:
        return code, output or "docker build failed."
    code, output = run_process(
        [
            "docker", "run", "-d",
            "--restart", "unless-stopped",
            "--name", deployment_name,
            "-p", f"{deploy['https_port']}:{deploy['https_port']}",
            image_name,
        ],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output or "docker run failed."
    manage_firewall_port("open", deploy["https_port"], "tcp", host=deploy.get("host"))
    http_port = deploy.get("http_port", "")
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
        _setup_nginx_http_redirect(deployment_name, http_port, deploy["https_port"], live_cb=live_cb)
    url = f"https://{deploy['host']}:{deploy['https_port']}"
    _update_python_api_state(deployment_name, {
        "kind": "docker",
        "name": deployment_name,
        "form_name": deployment_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": deploy["https_port"],
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API Docker deployment completed.\nContainer: {deployment_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_python_api_update_source(service_name, source_path, live_cb=None):
    deploy_key = _safe_python_api_name(service_name)
    state = _read_json_file(PYTHON_API_STATE_FILE)
    deployments = state.get("deployments")
    if not isinstance(deployments, dict):
        return 1, "No Python API deployments found."
    payload = deployments.get(deploy_key)
    if not payload:
        return 1, f"Deployment '{service_name}' not found in state."
    deploy_root = Path(str(payload.get("deploy_root") or ""))
    entry_hint = str(payload.get("entry_file") or "")
    kind = str(payload.get("kind") or "service").lower()
    svc_name = str(payload.get("name") or "")
    if not deploy_root.exists():
        return 1, f"Deployment directory not found: {deploy_root}"
    src = str(source_path or "").strip()
    if not src:
        return 1, "Source path is required."
    if live_cb:
        live_cb(f"[INFO] Updating files from: {src}\n")
    try:
        source_root, entry_file, entry_rel = _resolve_python_api_source(src, entry_hint=entry_hint, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    if live_cb:
        live_cb(f"[INFO] Copying files to {deploy_root / 'app'}...\n")
    try:
        copied_entry, copied_entry_rel = _copy_python_api_source(source_root, entry_file, deploy_root)
    except Exception as ex:
        return 1, f"Failed to copy files: {ex}"
    payload["entry_file"] = copied_entry_rel
    payload["project_path"] = str(deploy_root / "app")
    deployments[deploy_key] = payload
    state["deployments"] = deployments
    _write_json_file(PYTHON_API_STATE_FILE, state)
    if live_cb:
        live_cb(f"[INFO] Files updated. Restarting service '{svc_name}'...\n")
    if kind == "service":
        prefix = _sudo_prefix()
        if os.name != "nt":
            rc, out = run_capture(prefix + ["systemctl", "restart", svc_name], timeout=30)
            if rc != 0 and live_cb:
                live_cb(f"[WARN] Restart failed: {out}\n")
        else:
            run_capture(["sc.exe", "stop", svc_name], timeout=15)
            run_capture(["sc.exe", "start", svc_name], timeout=30)
    elif kind == "docker":
        rc, out = run_capture(["docker", "restart", svc_name], timeout=30)
        if rc != 0 and live_cb:
            live_cb(f"[WARN] Docker restart: {out}\n")
    if live_cb:
        live_cb(f"[INFO] Done. Entry file: {copied_entry_rel}\n")
    return 0, f"Files updated and service restarted.\nEntry: {copied_entry_rel}\n"


def run_windows_python_api_iis(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python API IIS deployment is only available on Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    site_name = (form.get("PYTHON_API_SITE_NAME", ["ServerInstallerPythonApi"])[0] or "ServerInstallerPythonApi").strip()
    site_key = _safe_python_api_name(site_name, "serverinstaller-python-api-iis")
    try:
        deploy = _prepare_python_api_deployment(form, site_key, live_cb=live_cb)
    except Exception as ex:
        return 1, str(ex)
    https_port = deploy["https_port"]
    if is_local_tcp_port_listening(https_port):
        usage = get_port_usage(https_port, "tcp")
        if not usage.get("managed_owner"):
            return 1, f"Requested IIS HTTPS port {https_port} is already in use. Choose another port."
    internal_port = str(pick_free_local_tcp_port(range(18080, 18280)) or "")
    if not internal_port:
        return 1, "Could not find a free internal port for IIS-backed Python API hosting."
    venv_python, code, output = _create_python_api_venv(
        deploy["deploy_root"],
        deploy["python_executable"],
        deploy["deploy_root"] / "app",
        extra_packages=["uvicorn", "trustme"],
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    _, runner_script = _write_python_api_runtime_files(
        deploy["deploy_root"],
        deploy["entry_rel"],
        deploy["app_object"],
        "127.0.0.1",
        internal_port,
    )
    logs_dir = deploy["deploy_root"] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    web_config = deploy["deploy_root"] / "web.config"
    web_config.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="aspNetCore" path="*" verb="*" modules="AspNetCoreModuleV2" resourceType="Unspecified" />
    </handlers>
    <aspNetCore processPath="{html.escape(str(venv_python))}" arguments="{html.escape(str(runner_script))}" stdoutLogEnabled="true" stdoutLogFile="{html.escape(str(logs_dir / 'stdout'))}" hostingModel="OutOfProcess">
      <environmentVariables>
        <environmentVariable name="SERVER_INSTALLER_APP_FILE" value="{html.escape(str((deploy['deploy_root'] / 'app' / deploy['entry_rel']).resolve()))}" />
        <environmentVariable name="SERVER_INSTALLER_APP_OBJECT" value="{html.escape(str(deploy['app_object']))}" />
        <environmentVariable name="SERVER_INSTALLER_HOST" value="127.0.0.1" />
        <environmentVariable name="SERVER_INSTALLER_PORT" value="{html.escape(str(internal_port))}" />
      </environmentVariables>
    </aspNetCore>
  </system.webServer>
</configuration>
""",
        encoding="utf-8",
    )
    bind_ip = (form.get("PYTHON_API_HOST_IP", [""])[0] or "").strip() or "*"
    dns_name = deploy["host"] if re.match(r"^[A-Za-z0-9.-]+$", deploy["host"]) else "localhost"
    http_port = deploy.get("http_port", "")
    http_binding_ps = []
    if http_port and http_port.isdigit():
        http_binding_ps = [f"New-WebBinding -Name $siteName -Protocol 'http' -Port {int(http_port)} -IPAddress $ip -ErrorAction SilentlyContinue | Out-Null"]
    ps = "\n".join([
        "Import-Module WebAdministration",
        f"$siteName = {_ps_single_quote(site_name)}",
        f"$appPool = {_ps_single_quote(site_name)}",
        f"$physicalPath = {_ps_single_quote(str(deploy['deploy_root']))}",
        f"$ip = {_ps_single_quote(bind_ip if bind_ip != '*' else '*')}",
        f"$port = {int(https_port)}",
        f"$dnsName = {_ps_single_quote(dns_name)}",
        "if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) { Stop-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null; Remove-Website -Name $siteName -ErrorAction SilentlyContinue | Out-Null }",
        "if (-not (Test-Path ('IIS:\\AppPools\\' + $appPool))) { New-WebAppPool -Name $appPool | Out-Null }",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name managedRuntimeVersion -Value ''",
        "Set-ItemProperty ('IIS:\\AppPools\\' + $appPool) -Name processModel.identityType -Value 4",
        "New-Website -Name $siteName -PhysicalPath $physicalPath -Port $port -IPAddress $ip -Ssl -ApplicationPool $appPool | Out-Null",
        *http_binding_ps,
        "$cert = New-SelfSignedCertificate -DnsName @($dnsName,'localhost','127.0.0.1') -CertStoreLocation 'cert:\\LocalMachine\\My' -FriendlyName ('ServerInstaller Python API ' + $siteName)",
        "$bindingPath = ($ip -eq '*' ? '0.0.0.0' : $ip) + '!' + $port",
        "if (Test-Path ('IIS:\\SslBindings\\' + $bindingPath)) { Remove-Item ('IIS:\\SslBindings\\' + $bindingPath) -Force -ErrorAction SilentlyContinue }",
        "New-Item ('IIS:\\SslBindings\\' + $bindingPath) -Thumbprint $cert.Thumbprint -SSLFlags 0 | Out-Null",
        "Start-Website -Name $siteName | Out-Null",
    ])
    rc, out = run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=180)
    if rc != 0:
        return 1, out or f"Failed to create IIS site '{site_name}'."
    manage_firewall_port("open", https_port, "tcp", host=deploy.get("host"))
    if http_port:
        manage_firewall_port("open", http_port, "tcp", host=deploy.get("host"))
    url = f"https://{deploy['host']}:{https_port}"
    _update_python_api_state(site_key, {
        "kind": "iis_site",
        "name": site_name,
        "form_name": site_name,
        "deployment_key": deploy["deploy_key"],
        "url": url,
        "deploy_root": str(deploy["deploy_root"]),
        "project_path": str(deploy["deploy_root"] / "app"),
        "entry_file": deploy["entry_rel"],
        "host": deploy["host"],
        "port": https_port,
    })
    extra_urls = f"\nHTTP URL:  http://{deploy['host']}:{http_port}" if http_port else ""
    return 0, f"Python API IIS deployment completed.\nSite: {site_name}\nURL: {url}{extra_urls}\nEntry file: {deploy['entry_rel']}\n"


def run_windows_python_installer(form=None, live_cb=None):
    form = form or {}
    if os.name != "nt":
        return 1, "Python installer is currently configured for Windows hosts."
    if not is_windows_admin():
        return 1, "Dashboard is not running as Administrator. Restart launcher and accept UAC prompt."
    ensure_repo_files(PYTHON_WINDOWS_FILES, live_cb=live_cb)
    env = os.environ.copy()
    version = (form.get("PYTHON_VERSION", ["3.12"])[0] or "3.12").strip()
    install_jupyter = (form.get("PYTHON_INSTALL_JUPYTER", ["yes"])[0] or "yes").strip().lower()
    host_ip = (form.get("PYTHON_HOST_IP", [""])[0] or "").strip()
    jupyter_port = (form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip()
    notebook_dir = _resolve_python_notebook_dir((form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip())
    system_user = (form.get("SYSTEM_USERNAME", [""])[0] or "").strip()
    system_password = (form.get("SYSTEM_PASSWORD", [""])[0] or "").strip()
    env["PYTHON_VERSION"] = version
    env["PYTHON_INSTALL_JUPYTER"] = "1" if install_jupyter in ("1", "true", "yes", "y", "on") else "0"
    env["PYTHON_JUPYTER_PORT"] = jupyter_port
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    if host_ip:
        env["PYTHON_HOST_IP"] = host_ip
    code, output = run_process(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PYTHON_WINDOWS_INSTALLER)],
        env=env,
        live_cb=live_cb,
    )
    if code != 0:
        return code, output
    state = _read_json_file(PYTHON_STATE_FILE)
    if host_ip:
        state["host"] = host_ip
    if jupyter_port:
        state["jupyter_port"] = jupyter_port
    state["default_notebook_dir"] = notebook_dir
    state["notebook_dir"] = notebook_dir
    if system_user:
        state["jupyter_username"] = system_user
    state["jupyter_password_hash"] = ""
    state["jupyter_auth_enabled"] = bool(system_user and system_password)
    state["jupyter_https_enabled"] = True
    _write_json_file(PYTHON_STATE_FILE, state)
    if install_jupyter in ("1", "true", "yes", "y", "on"):
        start_code, start_output = start_python_jupyter(
            host=host_ip or str(state.get("host") or choose_service_host()),
            port=jupyter_port,
            notebook_dir=notebook_dir,
            auth_username=system_user,
            auth_password=system_password,
            live_cb=live_cb,
        )
        if start_output:
            output = f"{output.rstrip()}\n{start_output}".strip()
        if start_code != 0:
            return start_code, output
    return 0, output


def run_unix_python_installer(form=None, live_cb=None):
    form = form or {}
    if os.name == "nt":
        return 1, "Unix Python installer can only run on Linux or macOS hosts."
    ensure_repo_files(PYTHON_UNIX_FILES, live_cb=live_cb)
    env = os.environ.copy()
    version = (form.get("PYTHON_VERSION", ["3.12"])[0] or "3.12").strip()
    install_jupyter = "yes"
    host_ip = (form.get("PYTHON_HOST_IP", [""])[0] or "").strip()
    jupyter_port = (form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip()
    notebook_dir = _resolve_python_notebook_dir((form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip())
    system_user = (form.get("SYSTEM_USERNAME", [""])[0] or "").strip()
    system_password = (form.get("SYSTEM_PASSWORD", [""])[0] or "").strip()
    env["PYTHON_VERSION"] = version
    env["PYTHON_INSTALL_JUPYTER"] = "1"
    env["PYTHON_JUPYTER_PORT"] = jupyter_port
    env["SERVER_INSTALLER_DATA_DIR"] = str(SERVER_INSTALLER_DATA)
    env["PYTHON_NOTEBOOK_DIR"] = notebook_dir
    if host_ip:
        env["PYTHON_HOST_IP"] = host_ip
    if system_user:
        env["PYTHON_JUPYTER_USER"] = system_user
    if system_password:
        env["PYTHON_JUPYTER_PASSWORD"] = system_password
    cmd = ["bash", str(PYTHON_UNIX_INSTALLER)]
    if hasattr(os, "geteuid") and os.geteuid() != 0 and command_exists("sudo"):
        cmd = ["sudo", "env"]
        for key in ("PYTHON_VERSION", "PYTHON_INSTALL_JUPYTER", "PYTHON_JUPYTER_PORT", "PYTHON_HOST_IP", "PYTHON_NOTEBOOK_DIR", "PYTHON_JUPYTER_USER", "PYTHON_JUPYTER_PASSWORD", "SERVER_INSTALLER_DATA_DIR"):
            value = env.get(key, "").strip()
            if value:
                cmd.append(f"{key}={value}")
        cmd += ["bash", str(PYTHON_UNIX_INSTALLER)]
    code, output = run_process(cmd, env=env, live_cb=live_cb)
    if code != 0:
        return code, output
    state = _read_json_file(PYTHON_STATE_FILE)
    if host_ip:
        state["host"] = host_ip
    if jupyter_port:
        state["jupyter_port"] = jupyter_port
        state["jupyter_url"] = f"https://{host_ip or str(state.get('host') or choose_service_host())}:{jupyter_port}/lab"
    state["default_notebook_dir"] = notebook_dir
    state["notebook_dir"] = notebook_dir
    if host_ip:
        state["host"] = host_ip
    if system_user:
        state["jupyter_username"] = system_user
    if system_user or state.get("jupyter_username"):
        state["jupyter_auth_enabled"] = True
    state["jupyter_https_enabled"] = True
    state["service_mode"] = True
    _write_json_file(PYTHON_STATE_FILE, state)
    return 0, output


def run_python_command(form=None, live_cb=None):
    form = form or {}
    command_text = (form.get("PYTHON_CMD", [""])[0] or "").strip()
    if not command_text:
        return 1, "PYTHON_CMD is required."
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or "").strip()
    if not python_executable:
        return 1, "Install Python first."
    env = _python_env(python_executable)
    if live_cb:
        live_cb(f"[INFO] Running command with Python: {python_executable}\n")
    cmd = ["cmd.exe", "/c", command_text] if os.name == "nt" else ["bash", "-lc", command_text]
    return run_process(cmd, env=env, live_cb=live_cb)


def start_python_jupyter(host="", port="8888", notebook_dir="", auth_username="", auth_password="", live_cb=None):
    if os.name != "nt":
        state = _read_json_file(PYTHON_STATE_FILE)
        if state.get("service_mode") and command_exists("systemctl"):
            rc, out = run_capture(["systemctl", "restart", JUPYTER_SYSTEMD_SERVICE], timeout=60)
            if rc == 0:
                url = str(state.get("jupyter_url") or f"https://{state.get('host') or choose_service_host()}:{state.get('jupyter_port') or port or '8888'}/lab").strip()
                message = out or f"Jupyter Lab service restarted at {url}."
                if live_cb:
                    live_cb(message + "\n")
                return 0, message
            return 1, (out or f"Failed to restart {JUPYTER_SYSTEMD_SERVICE}.")
    resolved = _resolve_any_python()
    python_executable = str(resolved.get("python_executable") or "").strip()
    if not python_executable:
        return 1, "Install Python first."
    python_state = _read_json_file(PYTHON_STATE_FILE)
    auth_username = str(auth_username or "").strip()
    auth_password = str(auth_password or "")
    rc_j, out_j = run_capture([python_executable, "-m", "jupyter", "--version"], timeout=20)
    if rc_j != 0:
        return 1, "Jupyter is not installed for the managed Python interpreter."
    stop_python_jupyter()
    host = (host or choose_service_host()).strip() or "127.0.0.1"
    port = str(port or "8888").strip() or "8888"
    if not port.isdigit():
        return 1, "Jupyter port must be numeric."
    is_windows_proxy_mode = os.name == "nt"
    if is_windows_proxy_mode and (not auth_username or not auth_password):
        return 1, "Windows Jupyter requires the current OS username and password."
    if is_local_tcp_port_listening(port):
        usage = get_port_usage(port, "tcp")
        if usage.get("managed_owner"):
            stop_python_jupyter()
            deadline = time.time() + 10
            while time.time() < deadline and is_local_tcp_port_listening(port):
                time.sleep(0.5)
        if is_local_tcp_port_listening(port):
            return 1, f"Requested Jupyter port {port} is already in use. Choose another port."
    notebook_dir = _resolve_python_notebook_dir(notebook_dir)
    bind_host = host
    public_port = port
    backend_port = port
    jupyter_config_dir = PYTHON_STATE_DIR / "jupyter-config"
    jupyter_data_dir = PYTHON_STATE_DIR / "jupyter-data"
    jupyter_runtime_dir = PYTHON_STATE_DIR / "jupyter-runtime"
    ipython_dir = PYTHON_STATE_DIR / "ipython"
    for path in (jupyter_config_dir, jupyter_data_dir, jupyter_runtime_dir, ipython_dir):
        path.mkdir(parents=True, exist_ok=True)
    jupyter_config_file = jupyter_config_dir / "jupyter_server_config.py"
    if os.name == "nt":
        if host not in ("127.0.0.1", "localhost", "::1"):
            bind_host = "0.0.0.0"
        ok_fw, _ = manage_firewall_port("open", port, "tcp", host=host)
        if not ok_fw and live_cb:
            live_cb(f"[WARN] Failed to open Windows Firewall for TCP {port}. Jupyter may be unreachable from other devices.\n")
    PYTHON_JUPYTER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_path = PYTHON_STATE_DIR / "jupyter.log"
    certfile = ""
    keyfile = ""
    scheme = "http"
    if os.name == "nt":
        certfile, keyfile = _ensure_windows_jupyter_https_assets(python_executable, host)
        if certfile and keyfile:
            scheme = "https"
        if not _ensure_windows_jupyter_proxy_support(python_executable):
            return 1, "Failed to install Windows Jupyter proxy support."
        backend_port_value = pick_free_local_tcp_port([
            18888,
            18889,
            18890,
            18891,
            18892,
            18893,
            18894,
            18895,
            18896,
            18897,
            18898,
            18899,
        ])
        if not backend_port_value or str(backend_port_value) == str(public_port):
            backend_port_value = pick_free_local_tcp_port(range(18900, 19050))
        if not backend_port_value:
            return 1, "Could not find a free internal port for Windows Jupyter."
        backend_port = str(backend_port_value)
        config_text = (
            "c = get_config()\n"
            "c.ServerApp.allow_remote_access = True\n"
            "c.ServerApp.open_browser = False\n"
            "c.ServerApp.trust_xheaders = True\n"
            f"c.ServerApp.allow_origin = {f'https://{host}:{public_port}'!r}\n"
            f"c.ServerApp.local_hostnames = {[host, '127.0.0.1', 'localhost']!r}\n"
            f"c.ServerApp.ip = {'127.0.0.1'!r}\n"
            f"c.ServerApp.port = {int(backend_port)}\n"
            f"c.ServerApp.root_dir = {notebook_dir!r}\n"
            "c.ServerApp.token = ''\n"
            "c.ServerApp.password = ''\n"
            "c.ServerApp.terminals_enabled = True\n"
            "c.ServerApp.jpserver_extensions = {\n"
            "    'jupyterlab': True,\n"
            "    'jupyter_server_terminals': True,\n"
            "}\n"
            "c.TerminalManager.shell_command = ['cmd.exe']\n"
        )
        jupyter_config_file.write_text(config_text, encoding="utf-8")
    args = [
        python_executable,
        "-m",
        "jupyter",
        "lab",
        "--no-browser",
        f"--ServerApp.ip={'127.0.0.1' if is_windows_proxy_mode else bind_host}",
        f"--ServerApp.port={backend_port}",
        "--ServerApp.port_retries=0",
        "--ServerApp.allow_remote_access=True",
        "--ServerApp.trust_xheaders=True",
        f"--ServerApp.allow_origin=https://{host}:{public_port}",
        f"--ServerApp.local_hostnames={host},127.0.0.1,localhost",
        f"--ServerApp.root_dir={notebook_dir}",
    ]
    if os.name == "nt":
        args.append(f"--config={jupyter_config_file}")
    args.append("--ServerApp.token=")
    args.append("--ServerApp.password=")
    if certfile and keyfile and not is_windows_proxy_mode:
        args.append(f"--ServerApp.certfile={certfile}")
        args.append(f"--ServerApp.keyfile={keyfile}")
    env = _python_env(python_executable)
    env["JUPYTER_CONFIG_DIR"] = str(jupyter_config_dir)
    env["JUPYTER_DATA_DIR"] = str(jupyter_data_dir)
    env["JUPYTER_RUNTIME_DIR"] = str(jupyter_runtime_dir)
    env["JUPYTER_NO_CONFIG"] = "1"
    env["JUPYTER_PREFER_ENV_PATH"] = "1"
    env["JUPYTER_ALLOW_INSECURE_WRITES"] = "true"
    env["IPYTHONDIR"] = str(ipython_dir)
    try:
        log_handle = open(log_path, "ab")
        if os.name == "nt":
            args.append("--ServerApp.terminals_enabled=True")
        kwargs = {
            "cwd": notebook_dir,
            "env": env,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(args, **kwargs)
        backend_proc = proc
        proxy_proc = None
        deadline = time.time() + 20
        while time.time() < deadline:
            if is_local_tcp_port_listening(backend_port):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.5)
        if not is_local_tcp_port_listening(backend_port):
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                log_text = ""
            if proc.poll() is not None:
                return 1, (log_text.strip() or f"Jupyter Lab exited early with code {proc.returncode}.")
            return 1, (log_text.strip() or f"Jupyter Lab did not start listening on port {backend_port}.")
        if is_windows_proxy_mode:
            proxy_script = _ensure_windows_jupyter_proxy_script()
            proxy_args = [
                python_executable,
                proxy_script,
                "--listen-host", bind_host,
                "--listen-port", public_port,
                "--backend-host", "127.0.0.1",
                "--backend-port", backend_port,
                "--username", auth_username,
                "--password", auth_password,
                "--certfile", certfile,
                "--keyfile", keyfile,
            ]
            proxy_kwargs = {
                "cwd": notebook_dir,
                "env": env,
                "stdout": log_handle,
                "stderr": subprocess.STDOUT,
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            }
            proxy_proc = subprocess.Popen(proxy_args, **proxy_kwargs)
            deadline = time.time() + 20
            while time.time() < deadline:
                if is_local_tcp_port_listening(public_port):
                    break
                if proxy_proc.poll() is not None:
                    break
                time.sleep(0.5)
            if not is_local_tcp_port_listening(public_port):
                try:
                    log_text = log_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    log_text = ""
                if proxy_proc.poll() is not None:
                    return 1, (log_text.strip() or f"Windows Jupyter proxy exited early with code {proxy_proc.returncode}.")
                return 1, (log_text.strip() or f"Windows Jupyter proxy did not start listening on port {public_port}.")
        url = f"{scheme}://{host}:{public_port}/lab"
        state = _read_json_file(PYTHON_STATE_FILE)
        state["host"] = host
        state["jupyter_port"] = public_port
        state["default_notebook_dir"] = notebook_dir
        state["notebook_dir"] = notebook_dir
        if is_windows_proxy_mode:
            state["jupyter_username"] = auth_username
            state["jupyter_auth_enabled"] = True
            state["jupyter_https_enabled"] = True
            state["jupyter_password_hash"] = ""
        _write_json_file(PYTHON_STATE_FILE, state)
        _write_json_file(PYTHON_JUPYTER_STATE_FILE, {
            "pid": proxy_proc.pid if proxy_proc is not None else proc.pid,
            "backend_pid": backend_proc.pid if is_windows_proxy_mode else None,
            "host": host,
            "port": public_port,
            "backend_port": backend_port if is_windows_proxy_mode else public_port,
            "url": url,
            "log_path": str(log_path),
            "notebook_dir": notebook_dir,
            "username": auth_username if is_windows_proxy_mode else str(python_state.get("jupyter_username") or "").strip(),
            "auth_enabled": bool(auth_username and auth_password) if is_windows_proxy_mode else bool(python_state.get("jupyter_password_hash")),
            "https_enabled": bool(certfile and keyfile) if is_windows_proxy_mode else bool(certfile and keyfile),
            "running": True,
        })
        message = f"Jupyter Lab started at {url}."
        if live_cb:
            live_cb(message + "\n")
        return 0, message
    except Exception as ex:
        return 1, f"Failed to start Jupyter Lab: {ex}"


def stop_python_jupyter(live_cb=None):
    state = _read_json_file(PYTHON_STATE_FILE)
    if os.name != "nt" and state.get("service_mode") and command_exists("systemctl"):
        rc, out = run_capture(["systemctl", "stop", JUPYTER_SYSTEMD_SERVICE], timeout=60)
        if rc != 0:
            return 1, (out or f"Failed to stop {JUPYTER_SYSTEMD_SERVICE}.")
        jupyter_state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
        if jupyter_state:
            jupyter_state["running"] = False
            _write_json_file(PYTHON_JUPYTER_STATE_FILE, jupyter_state)
        message = "Jupyter Lab service stopped."
        if live_cb:
            live_cb(message + "\n")
        return 0, message
    state = _read_json_file(PYTHON_JUPYTER_STATE_FILE)
    pid = state.get("pid")
    backend_pid = state.get("backend_pid")
    port = str(state.get("port") or _read_json_file(PYTHON_STATE_FILE).get("jupyter_port") or "").strip()
    killed_any = False
    try:
        pid_num = int(pid)
    except Exception:
        pid_num = 0
    if pid_num > 0:
        if os.name == "nt":
            rc, out = run_capture(["taskkill", "/PID", str(pid_num), "/F"], timeout=20)
        else:
            rc, out = run_capture(["kill", "-TERM", str(pid_num)], timeout=20)
        if rc != 0 and _python_process_running(pid_num):
            return 1, (out or f"Failed to stop Jupyter process {pid_num}.")
        killed_any = True
    try:
        backend_pid_num = int(backend_pid)
    except Exception:
        backend_pid_num = 0
    if backend_pid_num > 0 and backend_pid_num != pid_num:
        if os.name == "nt":
            rc, out = run_capture(["taskkill", "/PID", str(backend_pid_num), "/F"], timeout=20)
        else:
            rc, out = run_capture(["kill", "-TERM", str(backend_pid_num)], timeout=20)
        if rc != 0 and _python_process_running(backend_pid_num):
            return 1, (out or f"Failed to stop Jupyter backend process {backend_pid_num}.")
        killed_any = True
    if os.name == "nt" and port.isdigit():
        listener_pids = []
        for item in get_listening_ports(limit=5000):
            proto = str(item.get("proto", "")).lower()
            if not proto.startswith("tcp"):
                continue
            if int(item.get("port", 0)) != int(port):
                continue
            try:
                listener_pid = int(str(item.get("pid") or "0"))
            except Exception:
                continue
            if listener_pid <= 0 or listener_pid == pid_num:
                continue
            if _windows_process_matches_managed_jupyter(listener_pid, port):
                listener_pids.append(listener_pid)
        for listener_pid in sorted(set(listener_pids)):
            rc, out = run_capture(["taskkill", "/PID", str(listener_pid), "/F"], timeout=20)
            if rc != 0 and _python_process_running(listener_pid):
                return 1, (out or f"Failed to stop Jupyter process {listener_pid}.")
            killed_any = True
    if not killed_any:
        return 0, "Jupyter Lab is not running."
    state["pid"] = None
    state["backend_pid"] = None
    state["running"] = False
    _write_json_file(PYTHON_JUPYTER_STATE_FILE, state)
    message = "Jupyter Lab stopped."
    if live_cb:
        live_cb(message + "\n")
    return 0, message
