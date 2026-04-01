import ctypes
import getpass
import os
import secrets
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

from constants import SERVER_INSTALLER_DATA

def is_windows_admin():
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_windows_local_system():
    if os.name != "nt":
        return False
    username = str(os.environ.get("USERNAME") or "").strip().lower()
    userdomain = str(os.environ.get("USERDOMAIN") or "").strip().lower()
    if username == "system":
        return True
    return userdomain == "nt authority" and username == "system"


def _ps_single_quote(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _add_hosts_entry(domain, ip, live_cb=None):
    """Add a domain→IP entry to the system hosts file."""
    try:
        if os.name == "nt":
            hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
        else:
            hosts_path = Path("/etc/hosts")

        entry = f"{ip}  {domain}"
        existing = ""
        try:
            existing = hosts_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

        if domain in existing:
            if live_cb:
                live_cb(f"Domain '{domain}' already in hosts file.\n")
            return

        with open(str(hosts_path), "a", encoding="utf-8") as f:
            f.write(f"\n{entry}\n")

        if live_cb:
            live_cb(f"Added '{entry}' to {hosts_path}\n")
    except Exception as ex:
        if live_cb:
            live_cb(f"[WARN] Could not update hosts file: {ex}\n")


def get_active_windows_user():
    if os.name != "nt":
        return ""
    rc, out = run_capture(["query", "user"], timeout=15)
    if rc != 0 or not out:
        return ""
    for line in out.splitlines():
        match = re.match(r"^\s*>?(?P<user>\S+)\s+\S+\s+\d+\s+Active\b", line)
        if match:
            return match.group("user").strip()
    return ""


def run_windows_interactive_powershell_file(script_path, env=None, live_cb=None, timeout=3600):
    if os.name != "nt":
        return 1, "Interactive Windows runner is only available on Windows hosts."
    active_user = get_active_windows_user()
    if not active_user:
        return 1, "No active signed-in Windows user session was found."
    job_dir = SERVER_INSTALLER_DATA / "jobs" / "interactive"
    job_dir.mkdir(parents=True, exist_ok=True)
    token = f"{int(time.time())}-{secrets.token_hex(4)}"
    task_name = f"ServerInstaller-Interactive-{token}"
    runner_path = job_dir / f"{token}-runner.ps1"
    log_path = job_dir / f"{token}.log"
    exit_path = job_dir / f"{token}.exit"
    env = env or os.environ.copy()
    passthrough_keys = sorted(
        key for key, value in env.items()
        if str(value or "").strip()
    )
    runner_lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$logFile = {_ps_single_quote(str(log_path))}",
        f"$exitFile = {_ps_single_quote(str(exit_path))}",
        f"$targetScript = {_ps_single_quote(str(script_path))}",
        "$null = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($logFile))",
        "Set-Content -Path $logFile -Value '' -Encoding UTF8",
    ]
    for key in passthrough_keys:
        runner_lines.append(f"$env:{key} = {_ps_single_quote(env.get(key, ''))}")
    runner_lines += [
        "try {",
        "  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $targetScript *>&1 | Tee-Object -FilePath $logFile -Append",
        "  $code = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }",
        "} catch {",
        "  ($_ | Out-String) | Tee-Object -FilePath $logFile -Append | Out-Null",
        "  $code = 1",
        "}",
        "Set-Content -Path $exitFile -Value $code -Encoding ASCII",
        "exit $code",
    ]
    runner_path.write_text("\r\n".join(runner_lines) + "\r\n", encoding="utf-8")

    register_ps = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$taskName = {_ps_single_quote(task_name)}",
        f"$runner = {_ps_single_quote(str(runner_path))}",
        f"$user = {_ps_single_quote(active_user)}",
        "schtasks /Delete /TN $taskName /F 1>$null 2>$null | Out-Null",
        "$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File \"' + $runner + '\"')",
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries",
        "Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null",
        "Start-ScheduledTask -TaskName $taskName",
    ])
    rc, out = run_capture(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", register_ps],
        timeout=60,
    )
    if rc != 0:
        try:
            runner_path.unlink(missing_ok=True)
        except Exception:
            pass
        return 1, out or "Failed to start interactive installer task."

    chunks = []
    offset = 0
    deadline = time.time() + max(30, int(timeout))
    try:
        while time.time() < deadline:
            if log_path.exists():
                try:
                    content = log_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""
                if offset < len(content):
                    new_text = content[offset:]
                    offset = len(content)
                    chunks.append(new_text)
                    if live_cb and new_text:
                        live_cb(new_text)
            if exit_path.exists():
                break
            time.sleep(0.7)
        if not exit_path.exists():
            return 1, "".join(chunks).rstrip() + ("\nTimed out waiting for interactive installer task." if chunks else "Timed out waiting for interactive installer task.")
        try:
            exit_code = int(exit_path.read_text(encoding="ascii", errors="ignore").strip() or "1")
        except Exception:
            exit_code = 1
        return exit_code, "".join(chunks).strip()
    finally:
        cleanup_ps = "\n".join([
            f"$taskName = {_ps_single_quote(task_name)}",
            "Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null",
        ])
        run_capture(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cleanup_ps], timeout=30)
        for path in (runner_path, exit_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


def validate_os_credentials(username, password):
    username = (username or "").strip()
    if not username or not password:
        return False, "Username and password are required."

    # Check custom dashboard credentials first (works on ALL platforms)
    try:
        creds_file = SERVER_INSTALLER_DATA / "dashboard-credentials.json"
        if not creds_file.exists():
            # Search ALL possible locations (sudo user, root, real user, etc.)
            search_paths = [
                Path.home() / ".server-installer" / "dashboard-credentials.json",
                Path("/var/root/.server-installer/dashboard-credentials.json"),
                Path("/root/.server-installer/dashboard-credentials.json"),
                Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "dashboard-credentials.json",
            ]
            # Also check each user's home on macOS
            if sys.platform == "darwin":
                try:
                    for entry in Path("/Users").iterdir():
                        if entry.is_dir() and not entry.name.startswith("."):
                            search_paths.append(entry / ".server-installer" / "dashboard-credentials.json")
                except Exception:
                    pass
            for alt in search_paths:
                try:
                    if alt.exists():
                        creds_file = alt
                        break
                except Exception:
                    pass
        if creds_file.exists():
            import hashlib
            creds = json.loads(creds_file.read_text(encoding="utf-8"))
            stored_user = str(creds.get("username", "")).strip()
            stored_hash = str(creds.get("password_hash", "")).strip()
            if stored_user and stored_hash:
                input_hash = hashlib.sha256(password.encode()).hexdigest()
                if username == stored_user and input_hash == stored_hash:
                    return True, ""
    except Exception:
        pass

    # Also check environment variable credentials
    env_user = os.environ.get("DASHBOARD_CUSTOM_USER", "").strip()
    env_hash = os.environ.get("DASHBOARD_CUSTOM_PASS_HASH", "").strip()
    if env_user and env_hash:
        import hashlib
        if username == env_user and hashlib.sha256(password.encode()).hexdigest() == env_hash:
            return True, ""

    # Then try OS-level authentication
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        logon_user = ctypes.windll.advapi32.LogonUserW
        close_handle = ctypes.windll.kernel32.CloseHandle
        token = wintypes.HANDLE()

        domain = "."
        user = username
        if "\\" in username:
            domain, user = username.split("\\", 1)
        elif "@" in username:
            domain = None

        ok = logon_user(
            user,
            domain,
            password,
            3,  # LOGON32_LOGON_NETWORK
            0,  # LOGON32_PROVIDER_DEFAULT
            ctypes.byref(token),
        )
        if ok:
            close_handle(token)
            return True, ""
        return False, "Invalid Windows username/password."

    # macOS: use dscl to authenticate against Open Directory
    if sys.platform == "darwin":
        last_err = ""
        # Try all combinations of directory node and user path format
        attempts = [
            ["dscl", "/Local/Default", "-authonly", f"/Users/{username}", password],
            ["dscl", ".", "-authonly", f"/Users/{username}", password],
            ["dscl", "/Local/Default", "-authonly", username, password],
            ["dscl", ".", "-authonly", username, password],
            ["dscl", "/Search", "-authonly", f"/Users/{username}", password],
        ]
        for cmd in attempts:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    return True, ""
                last_err = (proc.stderr or proc.stdout or "").strip()
            except Exception as ex:
                last_err = str(ex)
        # Log the error for debugging
        print(f"[AUTH] macOS dscl auth failed for '{username}': {last_err}")
        return False, "Invalid macOS username or password."

    # Linux: use crypt/spwd or PAM
    try:
        import crypt
        import spwd

        hashed = spwd.getspnam(username).sp_pwdp
        if not hashed or hashed in ("x", "*", "!", "!!"):
            # Try PAM as fallback
            try:
                rc, _ = run_capture(["su", "-c", "true", username], timeout=10)
                # su requires stdin password — use a different approach
                raise Exception("spwd unavailable")
            except Exception:
                return False, "This account cannot be validated by password."
        return (crypt.crypt(password, hashed) == hashed, "Invalid Linux username/password.")
    except ImportError:
        # crypt/spwd not available (Python 3.13+ removed crypt)
        # Fallback: use PAM via subprocess
        try:
            proc = subprocess.run(
                ["python3", "-c", f"import pam; p=pam.pam(); print(p.authenticate('{username}','{password}'))"],
                capture_output=True, text=True, timeout=10,
            )
            if "True" in proc.stdout:
                return True, ""
        except Exception:
            pass
        # Last resort: try su
        try:
            import pty
            # Can't easily do su non-interactively, so try dscl even on Linux
            rc, _ = run_capture(["dscl", "/Local/Default", "-authonly", username, password], timeout=10)
            if rc == 0:
                return True, ""
        except Exception:
            pass
        return False, "Could not validate credentials. Install python3-pam or run as root."
    except PermissionError:
        return False, "Run dashboard as root to validate Linux system credentials for remote login."
    except Exception:
        return False, "Invalid username/password."


def run_process(cmd, env=None, live_cb=None, input_text=None):
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    chunks = []
    try:
        if input_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(input_text)
                proc.stdin.flush()
            except Exception:
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        if proc.stdout is not None:
            # Stream character-level output so long-running commands are visible live
            # even when underlying tools do not flush newline-delimited lines.
            while True:
                ch = proc.stdout.read(1)
                if ch == "":
                    if proc.poll() is not None:
                        break
                    continue
                chunks.append(ch)
                if live_cb:
                    live_cb(ch)
        proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.returncode, "".join(chunks)


def upload_root_dir():
    candidates = []
    if os.name == "nt":
        d_drive = Path("D:/")
        if d_drive.exists():
            candidates.append(d_drive / "Server-Installer" / "uploads")
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "Server-Installer" / "uploads")
        candidates.append(Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "uploads")
        temp_dir = os.environ.get("TEMP")
        if temp_dir:
            candidates.append(Path(temp_dir) / "Server-Installer" / "uploads")
    else:
        candidates = [
            Path("/var/tmp/server-installer/uploads"),
            Path("/tmp/server-installer/uploads"),
        ]

    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / f".probe-{secrets.token_hex(4)}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return cand
        except Exception:
            continue

    raise RuntimeError("No writable upload directory found.")


def save_uploaded_stream(filename, stream):
    safe_name = Path(filename or "upload.bin").name
    base = upload_root_dir()
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{int(time.time())}-{secrets.token_hex(4)}-{safe_name}"
    with target.open("wb") as f:
        shutil.copyfileobj(stream, f)
    return str(target)


def _safe_rel_path(name: str):
    rel = (name or "file.bin").replace("\\", "/")
    if ":" in rel:
        rel = rel.split(":", 1)[1]
    rel = rel.lstrip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts:
        return "file.bin"
    return "/".join(parts)


def save_uploaded_folder(items):
    base = upload_root_dir()
    base.mkdir(parents=True, exist_ok=True)
    folder_name = f"folder-{int(time.time())}-{secrets.token_hex(4)}"
    source_dir = base / folder_name
    source_dir.mkdir(parents=True, exist_ok=True)

    for it in items:
        rel = _safe_rel_path(getattr(it, "filename", "") or "file.bin")
        target = source_dir / Path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as f:
            shutil.copyfileobj(it.file, f)

    zip_path = base / f"{folder_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in source_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(source_dir))

    extract_dir = base / f"{folder_name}-extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # If archive expands to a single wrapper directory, use that as source root.
    children = [p for p in extract_dir.iterdir()]
    chosen_dir = extract_dir
    if len(children) == 1 and children[0].is_dir():
        chosen_dir = children[0]

    # Cleanup transient artifacts created only for transport.
    shutil.rmtree(source_dir, ignore_errors=True)
    try:
        zip_path.unlink(missing_ok=True)
    except Exception:
        pass

    return str(chosen_dir)


def save_uploaded_archive_or_file(item):
    saved = save_uploaded_stream(item.filename, item.file)
    path_obj = Path(saved)
    lower = path_obj.name.lower()
    if lower.endswith(".zip"):
        extract_dir = upload_root_dir() / f"extract-{int(time.time())}-{secrets.token_hex(4)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path_obj, "r") as zf:
            zf.extractall(extract_dir)
        return str(extract_dir)
    if lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar"):
        extract_dir = upload_root_dir() / f"extract-{int(time.time())}-{secrets.token_hex(4)}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        mode = "r:gz" if (lower.endswith(".tar.gz") or lower.endswith(".tgz")) else "r:"
        with tarfile.open(path_obj, mode) as tf:
            tf.extractall(extract_dir)
        return str(extract_dir)
    return saved

def run_system_power(action, live_cb=None):
    """action: 'restart' or 'shutdown'"""
    def emit(msg):
        if live_cb:
            live_cb(msg if msg.endswith("\n") else msg + "\n")

    if action not in ("restart", "shutdown"):
        return 1, f"Unknown action: {action}"

    label = "Restart" if action == "restart" else "Shut Down"
    emit(f"[INFO] {label} requested...")

    if os.name == "nt":
        # Use PowerShell Restart-Computer/Stop-Computer — more reliable than
        # shutdown.exe when called from a Python subprocess or Windows service context.
        ps_cmd = "Restart-Computer -Force" if action == "restart" else "Stop-Computer -Force"
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
    else:
        flag = "-r" if action == "restart" else "-h"
        cmd = ["shutdown", flag, "now"]
        if os.geteuid() != 0 and subprocess.run(
            ["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            cmd = ["sudo"] + cmd

    emit(f"[INFO] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()
            emit(f"[ERROR] {msg}")
            return 1, msg
        emit(f"[INFO] {label} command sent. System will {action} shortly.")
        return 0, f"{label} command sent."
    except Exception as ex:
        emit(f"[ERROR] {ex}")
        return 1, str(ex)

