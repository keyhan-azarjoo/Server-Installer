import json
import os
import re
import socket
import subprocess
import urllib.request
from pathlib import Path

from constants import (
    DASHBOARD_CERT_CONFIG_FILE,
    DASHBOARD_SELFSIGNED_CERT,
    DASHBOARD_SELFSIGNED_KEY,
    INSTALLED_COMMIT_FILE,
    REPO_RAW_BASE,
    SERVER_INSTALLER_DATA,
)


def _repo_api_url():
    """Derive the GitHub API commits URL from REPO_RAW_BASE."""
    # REPO_RAW_BASE = https://raw.githubusercontent.com/<owner>/<repo>/<branch>
    raw = REPO_RAW_BASE.rstrip("/")
    parts = raw.split("/")
    # parts[-3]=owner, parts[-2]=repo, parts[-1]=branch
    if len(parts) >= 3:
        owner, repo, branch = parts[-3], parts[-2], parts[-1]
        return f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
    return None

def _fetch_remote_commit_sha(timeout=8):
    """Return the latest commit SHA on the remote branch, or empty string on failure."""
    api_url = _repo_api_url()
    if not api_url:
        return ""
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "dashboard-version-check/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return str(data.get("sha", "")).strip()
    except Exception:
        return ""

def _read_installed_commit():
    try:
        return INSTALLED_COMMIT_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _save_installed_commit(sha):
    try:
        INSTALLED_COMMIT_FILE.write_text(sha.strip(), encoding="utf-8")
    except Exception:
        pass


def _dashboard_cert_config():
    """Read dashboard cert config. Returns dict with 'mode' and optional 'name'."""
    try:
        if DASHBOARD_CERT_CONFIG_FILE.exists():
            return json.loads(DASHBOARD_CERT_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"mode": "self-signed"}


def _set_dashboard_cert_config(mode: str, name: str = "") -> None:
    DASHBOARD_CERT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_CERT_CONFIG_FILE.write_text(
        json.dumps({"mode": mode, "name": name}, indent=2), encoding="utf-8"
    )


def _get_managed_cert_paths(name: str):
    """Return (cert_pem_path, key_pem_path) for a managed cert, or ('', '') if not found."""
    if not name:
        return "", ""
    safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", name)
    cert_dir = SERVER_INSTALLER_DATA / "ssl" / "certs" / safe
    cert_p = cert_dir / "cert.pem"
    key_p = cert_dir / "key.pem"
    if cert_p.exists() and key_p.exists():
        return str(cert_p), str(key_p)
    return "", ""


def _find_openssl_bin():
    """Return path to openssl binary, or '' if not found."""
    import shutil as _shutil
    candidate = _shutil.which("openssl")
    if candidate:
        return candidate
    if os.name == "nt":
        for p in [
            r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
            r"C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe",
        ]:
            if Path(p).exists():
                return p
        # Git for Windows
        git = _shutil.which("git")
        if git:
            git_dir = Path(git).parent.parent
            candidate = git_dir / "usr" / "bin" / "openssl.exe"
            if candidate.exists():
                return str(candidate)
    return ""


def _generate_dashboard_selfsigned():
    """Generate a self-signed dashboard cert. Returns (cert_path, key_path) or ('', '')."""
    cert_dir = DASHBOARD_SELFSIGNED_CERT.parent
    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "", ""

    openssl = _find_openssl_bin()
    if not openssl:
        return "", ""

    san_entries = ["DNS:localhost", "IP:127.0.0.1"]
    try:
        hostname = socket.gethostname()
        if hostname and hostname not in ("localhost",):
            san_entries.append(f"DNS:{hostname}")
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 53))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            entry = f"IP:{ip}"
            if entry not in san_entries:
                san_entries.append(entry)
    except Exception:
        pass

    import tempfile as _tempfile
    config_text = (
        "[req]\ndefault_bits = 2048\nprompt = no\ndefault_md = sha256\n"
        "x509_extensions = v3_req\ndistinguished_name = dn\n"
        "[dn]\nCN = localhost\n"
        "[v3_req]\n"
        f"subjectAltName = {', '.join(san_entries)}\n"
        "basicConstraints = CA:true\n"
        "keyUsage = critical, digitalSignature, keyEncipherment, keyCertSign\n"
        "extendedKeyUsage = serverAuth\n"
    )
    try:
        with _tempfile.NamedTemporaryFile("w", delete=False, suffix=".cnf", encoding="utf-8") as f:
            f.write(config_text)
            cfg_path = f.name
        result = subprocess.run(
            [openssl, "req", "-x509", "-nodes", "-newkey", "rsa:2048",
             "-keyout", str(DASHBOARD_SELFSIGNED_KEY),
             "-out", str(DASHBOARD_SELFSIGNED_CERT),
             "-days", "825", "-config", cfg_path, "-extensions", "v3_req"],
            capture_output=True, timeout=60,
        )
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        if result.returncode != 0:
            print(f"[dashboard cert] openssl failed: {result.stderr.decode(errors='ignore')}")
            return "", ""
        return str(DASHBOARD_SELFSIGNED_CERT), str(DASHBOARD_SELFSIGNED_KEY)
    except Exception as ex:
        print(f"[dashboard cert] generation error: {ex}")
        return "", ""


def _resolve_dashboard_cert(arg_cert: str = "", arg_key: str = "") -> tuple:
    """Resolve the dashboard cert/key to use. Returns (cert_path, key_path)."""
    # Explicit args take priority
    if arg_cert and arg_key and Path(arg_cert).exists() and Path(arg_key).exists():
        return arg_cert, arg_key

    # Check dashboard cert config for managed cert preference
    cfg_data = _dashboard_cert_config()
    if cfg_data.get("mode") == "managed" and cfg_data.get("name"):
        c, k = _get_managed_cert_paths(cfg_data["name"])
        if c and k:
            return c, k

    # Check if explicit args point to files that just don't exist yet — use self-signed path
    cert_path = arg_cert or str(DASHBOARD_SELFSIGNED_CERT)
    key_path = arg_key or str(DASHBOARD_SELFSIGNED_KEY)

    # If self-signed files exist, use them
    if Path(cert_path).exists() and Path(key_path).exists():
        return cert_path, key_path

    # Generate new self-signed cert
    print("[dashboard cert] Generating new self-signed certificate...")
    return _generate_dashboard_selfsigned()


def run_dashboard_apply_cert(form, live_cb=None) -> tuple:
    """Configure the dashboard certificate (self-signed or managed) and restart the service."""
    def log(msg):
        if live_cb:
            live_cb(msg + "\n")
        else:
            print(msg)

    mode = (form.get("CERT_MODE", ["self-signed"])[0] or "self-signed").strip().lower()
    name = (form.get("CERT_NAME", [""])[0] or "").strip()

    if mode == "managed":
        if not name:
            return 1, "Managed cert name is required."
        c, k = _get_managed_cert_paths(name)
        if not c or not k:
            return 1, f"Managed certificate '{name}' not found. Import it via SSL & Certificates first."
        _set_dashboard_cert_config("managed", name)
        log(f"Dashboard cert set to managed: {name}")
        log(f"  cert: {c}")
        log(f"  key:  {k}")
    else:
        _set_dashboard_cert_config("self-signed", "")
        log("Dashboard cert set to: self-signed (auto-generated)")
        # Regenerate self-signed cert
        c, k = _generate_dashboard_selfsigned()
        if not c:
            return 1, "Failed to generate self-signed certificate. Make sure openssl is installed."
        log(f"Self-signed cert generated: {c}")

    # Restart the dashboard service so the new cert takes effect
    log("\nRestarting dashboard service...")
    if os.name == "nt":
        rc, out = _restart_windows_dashboard_service()
    else:
        rc, out = _restart_linux_dashboard_service()

    if rc == 0:
        log(out or "Dashboard service restarted.")
        log("\nDone. Reload the dashboard page after a few seconds.")
        return 0, "Dashboard certificate updated and service restarted."
    else:
        log(f"Service restart note: {out or 'restart returned non-zero'}")
        log("The new certificate will take effect on next dashboard restart.")
        return 0, "Dashboard certificate saved. Restart the dashboard to apply it."


def _restart_linux_dashboard_service():
    try:
        rc, out = subprocess.run(
            ["systemctl", "restart", "server-installer-dashboard.service"],
            capture_output=True, text=True, timeout=30,
        ).returncode, ""
        return rc, "systemctl restart completed."
    except Exception as ex:
        return 1, str(ex)


def _restart_windows_dashboard_service():
    try:
        import ctypes as _ctypes
        if not _ctypes.windll.shell32.IsUserAnAdmin():
            return 1, "Restart requires Administrator privileges."
        rc, out = subprocess.run(
            ["sc.exe", "stop", "ServerInstallerDashboard"],
            capture_output=True, text=True, timeout=15,
        ).returncode, ""
        subprocess.run(
            ["sc.exe", "start", "ServerInstallerDashboard"],
            capture_output=True, text=True, timeout=15,
        )
        return 0, "Service restarted."
    except Exception as ex:
        return 1, str(ex)
