#!/usr/bin/env python3
import argparse
import html
import ipaddress
import os
import secrets
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_INSTALLER = ROOT / "DotNet" / "windows" / "install-windows-dotnet-host.ps1"
LINUX_INSTALLER = ROOT / "DotNet" / "linux" / "install-linux-dotnet-runner.sh"

SESSIONS = set()


def validate_os_credentials(username, password):
    username = (username or "").strip()
    if not username or not password:
        return False, "Username and password are required."

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

    try:
        import crypt
        import spwd

        hashed = spwd.getspnam(username).sp_pwdp
        if not hashed or hashed in ("x", "*", "!", "!!"):
            return False, "This Linux account cannot be validated by password."
        return (crypt.crypt(password, hashed) == hashed, "Invalid Linux username/password.")
    except PermissionError:
        return False, "Run dashboard as root to validate Linux system credentials for remote login."
    except Exception:
        return False, "Invalid Linux username/password."


def run_process(cmd, env=None):
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout


def run_windows_installer(form):
    if os.name != "nt":
        return 1, "Windows installer can only run on Windows hosts."

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WINDOWS_INSTALLER),
    ]

    keys = [
        "DeploymentMode",
        "DotNetChannel",
        "SourceValue",
        "DomainName",
        "SiteName",
        "SitePort",
        "HttpsPort",
        "DockerHostPort",
    ]
    for key in keys:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            cmd.extend([f"-{key}", value])

    return run_process(cmd)


def run_windows_setup_only(form, target):
    if os.name != "nt":
        return 1, "Windows setup actions can only run on Windows hosts."

    dotnet_channel = (form.get("DotNetChannel", ["8.0"])[0] or "8.0").strip()
    if not dotnet_channel:
        dotnet_channel = "8.0"

    if target == "iis":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'common.ps1'}';"
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'iis-mode.ps1'}';"
                f"Install-WindowsFeatureSet;"
                f"Install-DotNetPrerequisites -Channel '{dotnet_channel}'"
            ),
        ]
        return run_process(cmd)

    if target == "docker":
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'common.ps1'}';"
                f". '{ROOT / 'DotNet' / 'windows' / 'modules' / 'docker-mode.ps1'}';"
                f"Install-DotNetPrerequisites -Channel '{dotnet_channel}' -SkipHostingBundle;"
                f"Ensure-DockerInstalled"
            ),
        ]
        return run_process(cmd)

    return 1, "Unknown Windows setup target."


def run_linux_installer(form):
    if os.name == "nt":
        return 1, "Linux installer can only run on Linux hosts."

    installer_cmd = ["bash", str(LINUX_INSTALLER)]
    if os.geteuid() != 0 and subprocess.run(["which", "sudo"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        installer_cmd = ["sudo"] + installer_cmd

    env = os.environ.copy()
    for key in [
        "DOTNET_CHANNEL",
        "SOURCE_VALUE",
        "DOMAIN_NAME",
        "SERVICE_NAME",
        "SERVICE_PORT",
        "HTTP_PORT",
        "HTTPS_PORT",
        "GITHUB_TOKEN",
    ]:
        value = (form.get(key, [""])[0] or "").strip()
        if value:
            env[key] = value

    return run_process(installer_cmd, env=env)


def page_login(message=""):
    msg = f"<p style='color:#b42318'>{html.escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Login</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f4f7fb;margin:0;padding:40px}}
.card{{max-width:420px;margin:auto;background:#fff;border-radius:12px;padding:20px;box-shadow:0 8px 30px rgba(2,32,71,.08)}}
input{{width:100%;padding:10px;margin:6px 0 12px;border:1px solid #d0d7e2;border-radius:8px}}
button{{background:#0f766e;color:#fff;border:0;padding:10px 14px;border-radius:8px}}
</style></head>
<body><div class="card"><h2>Server Installer</h2>{msg}
<p>Remote access requires this computer's OS username/password.</p>
<form method="post" action="/login">
<label>Server Username</label><input name="username" required>
<label>Server Password</label><input type="password" name="password" required>
<button type="submit">Open Dashboard</button>
</form></div></body></html>"""


def page_dashboard(message=""):
    msg = (
        f"<div class='flash'>{html.escape(message)}</div>" if message else ""
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Dashboard</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:"Segoe UI",Arial,sans-serif;background:linear-gradient(180deg,#f3f6fc,#eef3fb);margin:0;color:#0f172a}}
.layout{{display:grid;grid-template-columns:280px 1fr;min-height:100vh}}
.sidebar{{background:linear-gradient(180deg,#0b1f3a,#102b4f);color:#e8eef9;padding:22px 18px;border-right:1px solid rgba(255,255,255,.08)}}
.brand{{font-size:22px;font-weight:700;margin-bottom:18px;letter-spacing:.2px}}
.navgroup{{margin-bottom:14px}}
.navtitle{{font-size:12px;text-transform:uppercase;opacity:.75;margin-bottom:8px}}
.navitem{{padding:11px 12px;margin:7px 0;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.08);border-radius:10px;font-size:14px}}
.main{{padding:26px}}
.header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}}
.title{{font-size:30px;font-weight:700}}
.subtitle{{font-size:14px;color:#475569}}
.flash{{padding:12px 14px;background:#ecfdf3;border:1px solid #86efac;border-radius:10px;margin-bottom:16px;color:#14532d}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#fff;border-radius:14px;padding:16px 16px 12px;box-shadow:0 10px 30px rgba(2,32,71,.07);border:1px solid #e5eaf4}}
.card h3{{margin:0 0 6px 0;font-size:18px}}
.card p{{margin:0 0 12px 0;font-size:13px;color:#475569}}
.divider{{height:1px;background:#e2e8f0;margin:12px 0}}
label{{display:block;font-size:12px;color:#334155;font-weight:600;letter-spacing:.2px}}
input,select{{width:100%;padding:10px;margin-top:6px;margin-bottom:10px;border:1px solid #cfd8e6;border-radius:9px;background:#fff}}
button{{background:#1249b0;color:white;border:0;padding:10px 14px;border-radius:9px;font-weight:600;cursor:pointer}}
.btn-secondary{{background:#0f766e}}
.btn-dark{{background:#1e293b}}
.onecol{{grid-template-columns:1fr}}
@media (max-width:1100px){{.layout{{grid-template-columns:1fr}}.sidebar{{padding-bottom:10px}}.row{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="layout">
<div class="sidebar">
<div class="brand">Server Installer</div>
<div class="navgroup">
  <div class="navtitle">Installers</div>
  <div class="navitem">Dot Net Installer</div>
  <div class="navitem">IIS Installer (Windows)</div>
  <div class="navitem">Docker Installer</div>
  <div class="navitem">Combined Server Installers</div>
</div>
<div class="navgroup">
  <div class="navtitle">Scope</div>
  <div class="navitem">Windows Server Actions</div>
  <div class="navitem">Linux Server Actions</div>
</div>
</div>
<div class="main">
<div class="header">
  <div>
    <div class="title">Server Installer Control Center</div>
    <div class="subtitle">Professional deployment and server setup workflows from one dashboard.</div>
  </div>
</div>
{msg}
<div class="row">
<div class="card">
<h3>Windows Combined (.NET + IIS/Docker)</h3>
<p>Run full deployment on Windows with all deployment options.</p>
<form method="post" action="/run/windows">
<label>Deployment Mode</label><select name="DeploymentMode"><option>IIS</option><option>Docker</option></select>
<label>.NET Channel</label><input name="DotNetChannel" value="8.0">
<label>Source Path or URL</label><input name="SourceValue" placeholder="D:\\app\\published or https://..." required>
<label>Domain Name</label><input name="DomainName">
<label>Site Name</label><input name="SiteName" value="DotNetApp">
<label>HTTP Port</label><input name="SitePort" value="80">
<label>HTTPS Port</label><input name="HttpsPort" value="443">
<label>Docker Host Port</label><input name="DockerHostPort" value="8080">
<button type="submit">Run Windows Installer</button>
</form>
</div>
<div class="card">
<h3>Windows Separate Installers</h3>
<p>Install only the part you need: IIS stack or Docker stack.</p>
<form method="post" action="/run/windows_setup_iis">
<label>.NET Channel</label><input name="DotNetChannel" value="8.0">
<button class="btn-secondary" type="submit">Install IIS Stack Only</button>
</form>
<div class="divider"></div>
<form method="post" action="/run/windows_setup_docker">
<label>.NET Channel</label><input name="DotNetChannel" value="8.0">
<button class="btn-dark" type="submit">Install Docker Stack Only</button>
</form>
<div class="divider"></div>
<form method="post" action="/run/windows_iis">
<label>Source Path or URL</label><input name="SourceValue" required>
<label>.NET Channel</label><input name="DotNetChannel" value="8.0">
<button type="submit">Install IIS Mode</button>
</form>
<div class="divider"></div>
<form method="post" action="/run/windows_docker">
<label>Source Path or URL</label><input name="SourceValue" required>
<label>.NET Channel</label><input name="DotNetChannel" value="8.0">
<label>Docker Host Port</label><input name="DockerHostPort" value="8080">
<button type="submit">Install Docker Mode</button>
</form>
</div>
</div>
<div class="row" style="margin-top:16px">
<div class="card">
<h3>Linux Combined (.NET + Nginx)</h3>
<p>Run Linux deployment pipeline with application and web proxy setup.</p>
<form method="post" action="/run/linux">
<label>.NET Channel</label><input name="DOTNET_CHANNEL" value="8.0">
<label>Source Path or URL</label><input name="SOURCE_VALUE" placeholder="/srv/app or https://..." required>
<label>Domain Name</label><input name="DOMAIN_NAME">
<label>Service Name</label><input name="SERVICE_NAME" value="dotnet-app">
<label>Service Port</label><input name="SERVICE_PORT" value="5000">
<label>HTTP Port</label><input name="HTTP_PORT" value="80">
<label>HTTPS Port</label><input name="HTTPS_PORT" value="443">
<button type="submit">Run Linux Installer</button>
</form>
</div>
<div class="card">
<h3>Linux DotNet Prerequisites</h3>
<p>Install base runtime and prerequisites without deploying app payload.</p>
<form method="post" action="/run/linux_prereq">
<label>.NET Channel</label><input name="DOTNET_CHANNEL" value="8.0">
<button type="submit">Install Linux Prerequisites Only</button>
</form>
</div>
</div>
</div></div></body></html>"""


def page_output(title, output, code):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Consolas,monospace;background:#0d1117;color:#c9d1d9;padding:16px}}a{{color:#58a6ff}}</style>
</head><body><h2>{html.escape(title)} (exit {code})</h2><pre>{html.escape(output)}</pre><a href="/">Back</a></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def is_local_client(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except Exception:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def parse_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def set_cookie(self, sid):
        self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly")

    def get_sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sid="):
                return part[4:]
        return ""

    def is_auth(self):
        sid = self.get_sid()
        return bool(sid and sid in SESSIONS)

    def write_html(self, content, status=HTTPStatus.OK, cookie_sid=None):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cookie_sid:
            self.set_cookie(cookie_sid)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            if self.is_local_client() or self.is_auth():
                self.write_html(page_dashboard())
            else:
                self.write_html(page_login())
            return
        self.write_html("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/login":
            form = self.parse_form()
            user = (form.get("username", [""])[0] or "").strip()
            password = (form.get("password", [""])[0] or "").strip()
            ok, error = validate_os_credentials(user, password)
            if ok:
                sid = secrets.token_hex(16)
                SESSIONS.add(sid)
                self.write_html(page_dashboard("Login successful."), cookie_sid=sid)
            else:
                self.write_html(page_login(error), HTTPStatus.UNAUTHORIZED)
            return

        if (not self.is_local_client()) and (not self.is_auth()):
            self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
            return

        form = self.parse_form()

        if self.path == "/run/windows":
            code, output = run_windows_installer(form)
            self.write_html(page_output("Windows Combined Installer", output, code))
            return
        if self.path == "/run/windows_iis":
            form["DeploymentMode"] = ["IIS"]
            code, output = run_windows_installer(form)
            self.write_html(page_output("Windows IIS Installer", output, code))
            return
        if self.path == "/run/windows_setup_iis":
            code, output = run_windows_setup_only(form, "iis")
            self.write_html(page_output("Windows IIS Stack Setup", output, code))
            return
        if self.path == "/run/windows_setup_docker":
            code, output = run_windows_setup_only(form, "docker")
            self.write_html(page_output("Windows Docker Stack Setup", output, code))
            return
        if self.path == "/run/windows_docker":
            form["DeploymentMode"] = ["Docker"]
            code, output = run_windows_installer(form)
            self.write_html(page_output("Windows Docker Installer", output, code))
            return
        if self.path == "/run/linux":
            code, output = run_linux_installer(form)
            self.write_html(page_output("Linux Combined Installer", output, code))
            return
        if self.path == "/run/linux_prereq":
            form["SOURCE_VALUE"] = [""]
            code, output = run_linux_installer(form)
            self.write_html(page_output("Linux Prerequisites Installer", output, code))
            return

        self.write_html("Not found", HTTPStatus.NOT_FOUND)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard started at http://{args.host}:{args.port}")
    print("Localhost access: no login required.")
    print("Remote access: requires OS username/password of this computer.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
