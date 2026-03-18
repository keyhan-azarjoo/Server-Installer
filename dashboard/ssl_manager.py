"""SSL/TLS Certificate Manager for Server Installer Dashboard.

Handles:
- Certificate storage (per-domain under SERVER_INSTALLER_DATA/ssl/certs/)
- Let's Encrypt issuance via certbot (HTTP-01 or DNS-01 challenge)
- Upload/import of user-provided PEM or PFX/P12 certificates
- Cert validation (openssl subprocess or Python ssl fallback)
- Assignment to IIS (Windows), nginx, or custom paths
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path


# ─── Storage helpers ─────────────────────────────────────────────────────────

def _ssl_root():
    from server_installer_dashboard import SERVER_INSTALLER_DATA
    d = SERVER_INSTALLER_DATA / "ssl" / "certs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_cert_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", (name or "cert").strip().lower())


def _cert_dir(name: str) -> Path:
    d = _ssl_root() / _safe_cert_name(name)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ─── Openssl helpers ──────────────────────────────────────────────────────────

def _openssl_bin():
    """Locate openssl, including common Windows paths."""
    w = shutil.which("openssl")
    if w:
        return w
    # Windows common install paths
    for p in [
        r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
        r"C:\Program Files\OpenSSL\bin\openssl.exe",
        r"C:\OpenSSL-Win64\bin\openssl.exe",
        r"C:\OpenSSL\bin\openssl.exe",
    ]:
        if os.path.isfile(p):
            return p
    # Git for Windows ships openssl
    git = shutil.which("git")
    if git:
        git_dir = Path(git).parent.parent
        candidate = git_dir / "usr" / "bin" / "openssl.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _run_openssl(args, input_data=None, timeout=20):
    openssl = _openssl_bin()
    if not openssl:
        raise RuntimeError(
            "openssl not found. Install OpenSSL and make sure it is in PATH.\n"
            "Download: https://slproweb.com/products/Win32OpenSSL.html (Windows) "
            "or use: apt install openssl"
        )
    return subprocess.run(
        [openssl] + args,
        capture_output=True, text=True, timeout=timeout,
        input=input_data,
    )


# ─── Certificate info ─────────────────────────────────────────────────────────

def ssl_cert_info(cert_pem: str) -> dict:
    """Return parsed info from a PEM certificate string."""
    info = {"ok": False}
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8") as f:
            f.write(cert_pem)
            tmp = f.name
        try:
            r = _run_openssl([
                "x509", "-in", tmp, "-noout",
                "-subject", "-issuer", "-dates",
                "-ext", "subjectAltName",
            ])
            if r.returncode != 0:
                info["error"] = r.stderr.strip()
                return info
            out = r.stdout
            info["ok"] = True
            info["raw"] = out.strip()
            m = re.search(r"(?:subject=|subject\s*:\s*)(.+)", out)
            if m:
                info["subject"] = m.group(1).strip()
                cn = re.search(r"CN\s*=\s*([^\s,/\n]+)", m.group(1))
                if cn:
                    info["cn"] = cn.group(1).strip()
            m2 = re.search(r"(?:issuer=|issuer\s*:\s*)(.+)", out)
            if m2:
                info["issuer_raw"] = m2.group(1).strip()
                org = re.search(r"O\s*=\s*([^\n,/]+)", m2.group(1))
                if org:
                    info["issuer"] = org.group(1).strip()
                cn2 = re.search(r"CN\s*=\s*([^\s,/\n]+)", m2.group(1))
                if cn2:
                    info["issuer_cn"] = cn2.group(1).strip()
            after = re.search(r"notAfter\s*=\s*(.+)", out)
            if after:
                info["not_after"] = after.group(1).strip()
            before = re.search(r"notBefore\s*=\s*(.+)", out)
            if before:
                info["not_before"] = before.group(1).strip()
            sans_raw = re.findall(r"DNS:([^\s,\n]+)", out)
            info["sans"] = [s.strip() for s in sans_raw]
            sub_str = info.get("subject", "")
            iss_str = info.get("issuer_raw", "")
            info["self_signed"] = bool(sub_str and iss_str and sub_str.strip() == iss_str.strip())
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    except Exception as ex:
        info["error"] = str(ex)
    return info


def ssl_validate_pair(cert_pem: str, key_pem: str) -> tuple:
    """Returns (ok: bool, message: str). Checks that cert and private key match."""
    tc = tk = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8") as f:
            f.write(cert_pem)
            tc = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8") as f:
            f.write(key_pem)
            tk = f.name
        rc = _run_openssl(["x509", "-noout", "-modulus", "-in", tc])
        if rc.returncode != 0:
            return False, f"Invalid certificate: {rc.stderr.strip()}"
        rk = _run_openssl(["rsa", "-noout", "-modulus", "-in", tk])
        if rk.returncode != 0:
            # Try EC key (no modulus)
            rk2 = _run_openssl(["ec", "-noout", "-in", tk])
            if rk2.returncode == 0:
                return True, "EC key: format accepted"
            return False, f"Invalid private key: {rk.stderr.strip()}"
        if rc.stdout.strip() == rk.stdout.strip():
            return True, "Certificate and key match"
        return False, "Certificate and private key do NOT match"
    except Exception as ex:
        return False, f"Validation error: {ex}"
    finally:
        for t in [tc, tk]:
            if t:
                try:
                    os.unlink(t)
                except Exception:
                    pass


# ─── Certificate storage ─────────────────────────────────────────────────────

def ssl_save_cert(name: str, cert_pem: str, key_pem: str,
                  chain_pem: str = "", source: str = "upload") -> dict:
    """Save a certificate to the managed cert store. Returns metadata dict."""
    d = _cert_dir(name)
    (d / "cert.pem").write_text(cert_pem.strip() + "\n", encoding="utf-8")
    (d / "key.pem").write_text(key_pem.strip() + "\n", encoding="utf-8")
    if chain_pem and chain_pem.strip():
        (d / "chain.pem").write_text(chain_pem.strip() + "\n", encoding="utf-8")
    fullchain = cert_pem.strip() + "\n" + (chain_pem.strip() + "\n" if chain_pem and chain_pem.strip() else "")
    (d / "fullchain.pem").write_text(fullchain, encoding="utf-8")
    info = ssl_cert_info(cert_pem)
    meta = {
        "name": _safe_cert_name(name),
        "domain": name,
        "source": source,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cert_path": str(d / "cert.pem"),
        "key_path": str(d / "key.pem"),
        "fullchain_path": str(d / "fullchain.pem"),
        "info": info,
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def ssl_list_certs() -> list:
    """Return list of all managed certificates as dicts."""
    results = []
    try:
        for d in sorted(_ssl_root().iterdir()):
            if not d.is_dir():
                continue
            cert_file = d / "cert.pem"
            if not cert_file.exists():
                continue
            meta_file = d / "meta.json"
            meta = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            info = meta.get("info") or ssl_cert_info(cert_file.read_text(encoding="utf-8"))
            results.append({
                "name": d.name,
                "domain": meta.get("domain") or d.name,
                "source": meta.get("source") or "unknown",
                "saved_at": meta.get("saved_at") or "",
                "not_after": info.get("not_after") or "",
                "issuer": info.get("issuer") or info.get("issuer_cn") or "",
                "cn": info.get("cn") or "",
                "sans": info.get("sans") or [],
                "self_signed": info.get("self_signed", True),
                "cert_path": str(d / "cert.pem"),
                "key_path": str(d / "key.pem"),
                "fullchain_path": str(d / "fullchain.pem"),
                "has_chain": (d / "chain.pem").exists(),
            })
    except Exception:
        pass
    return results


def ssl_delete_cert(name: str) -> tuple:
    """Delete a managed certificate. Returns (ok, message)."""
    try:
        d = _ssl_root() / _safe_cert_name(name)
        if not d.exists():
            return False, f"Certificate '{name}' not found."
        shutil.rmtree(d)
        return True, f"Certificate '{name}' deleted."
    except Exception as ex:
        return False, f"Delete failed: {ex}"


# ─── PFX / P12 import ────────────────────────────────────────────────────────

def ssl_import_pfx(pfx_bytes: bytes, password: str, domain: str,
                   live_cb=None) -> tuple:
    """Convert a PFX/P12 file to PEM cert+key.
    Returns (ok: bool, cert_pem: str, key_pem: str, chain_pem: str, error: str)
    """
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    tf = tk = tc = tchain = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pfx", delete=False) as f:
            f.write(pfx_bytes)
            tf = f.name
        tc = tf + ".cert.pem"
        tk = tf + ".key.pem"
        tchain = tf + ".chain.pem"

        passarg = f"pass:{password}" if password else "pass:"

        # Extract certificate(s)
        rc = _run_openssl([
            "pkcs12", "-in", tf, "-nokeys", "-out", tc,
            "-passin", passarg, "-passout", "pass:",
        ])
        if rc.returncode != 0:
            # Try legacy mode (for older PFX files)
            rc = _run_openssl([
                "pkcs12", "-in", tf, "-nokeys", "-out", tc,
                "-passin", passarg, "-passout", "pass:", "-legacy",
            ])
        if rc.returncode != 0:
            return False, "", "", "", f"PFX cert extraction failed: {rc.stderr.strip()}"

        # Extract private key (no password on output)
        rk = _run_openssl([
            "pkcs12", "-in", tf, "-nocerts", "-nodes", "-out", tk,
            "-passin", passarg,
        ])
        if rk.returncode != 0:
            rk = _run_openssl([
                "pkcs12", "-in", tf, "-nocerts", "-nodes", "-out", tk,
                "-passin", passarg, "-legacy",
            ])
        if rk.returncode != 0:
            return False, "", "", "", f"PFX key extraction failed: {rk.stderr.strip()}"

        cert_pem = Path(tc).read_text(encoding="utf-8")
        key_pem = Path(tk).read_text(encoding="utf-8")
        log(f"PFX imported successfully for domain: {domain}")
        return True, cert_pem, key_pem, "", ""

    except Exception as ex:
        traceback.print_exc()
        return False, "", "", "", f"PFX import error: {ex}"
    finally:
        for t in [tf, tc, tk, tchain]:
            if t:
                try:
                    os.unlink(t)
                except Exception:
                    pass


# ─── Let's Encrypt (certbot) ─────────────────────────────────────────────────

def _find_certbot():
    """Find certbot binary, including Python Scripts directory (common on Windows)."""
    w = shutil.which("certbot")
    if w:
        return w
    # Check alongside the running Python interpreter (covers pip-installed scripts)
    scripts_dir = Path(sys.executable).parent
    for candidate in [
        scripts_dir / "certbot.exe",
        scripts_dir / "certbot",
        scripts_dir / "Scripts" / "certbot.exe",
        scripts_dir / "Scripts" / "certbot",
    ]:
        if candidate.is_file():
            return str(candidate)
    # Common install paths on Linux / macOS
    for p in ["/usr/bin/certbot", "/usr/local/bin/certbot", "/snap/bin/certbot"]:
        if os.path.isfile(p):
            return p
    # Module-based fallback: check if certbot is importable
    try:
        r = subprocess.run(
            [sys.executable, "-m", "certbot", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            # Return a sentinel so callers know to use `python -m certbot`
            return "__module__"
    except Exception:
        pass
    return None


def _certbot_cmd(certbot_path):
    """Return the command list prefix for certbot."""
    if certbot_path == "__module__":
        return [sys.executable, "-m", "certbot"]
    return [certbot_path]


def _install_certbot_if_needed(live_cb=None):
    """Try to install certbot. Returns path/sentinel or None."""
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    found = _find_certbot()
    if found:
        log(f"certbot found: {found}")
        return found

    log("certbot not found — attempting to install...")
    is_windows = os.name == "nt"

    if not is_windows:
        for installer, cmd in [
            ("snap", ["snap", "install", "--classic", "certbot"]),
            ("apt-get", ["apt-get", "install", "-y", "certbot"]),
            ("yum", ["yum", "install", "-y", "certbot"]),
            ("pip", [sys.executable, "-m", "pip", "install", "certbot"]),
        ]:
            if not shutil.which(installer):
                continue
            log(f"Trying: {' '.join(cmd)}")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                found = _find_certbot()
                if found:
                    log(f"certbot installed: {found}")
                    return found
    else:
        # Windows: install via pip into the current Python environment
        log("On Windows, trying: pip install certbot")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "certbot"],
            capture_output=True, text=True, timeout=240,
        )
        if r.returncode == 0:
            found = _find_certbot()
            if found:
                log(f"certbot installed: {found}")
                return found
            # pip succeeded but binary lookup failed — try as a module directly
            try:
                rv = subprocess.run(
                    [sys.executable, "-m", "certbot", "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                if rv.returncode == 0:
                    log("certbot available as Python module.")
                    return "__module__"
            except Exception:
                pass
        log(f"pip output: {r.stdout.strip()[-800:] if r.stdout else ''}{r.stderr.strip()[-400:] if r.stderr else ''}")
        log("certbot could not be installed via pip.")

    return None


def run_ssl_letsencrypt(form, live_cb=None) -> tuple:
    """Obtain or renew a Let's Encrypt certificate via certbot.
    Returns (exit_code: int, output: str)
    """
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    domain = (form.get("SSL_DOMAIN", [""])[0] or "").strip().lower()
    email = (form.get("SSL_EMAIL", [""])[0] or "").strip()
    challenge = (form.get("SSL_CHALLENGE", ["http"])[0] or "http").strip().lower()
    extra_raw = (form.get("SSL_EXTRA_DOMAINS", [""])[0] or "").strip()
    extra_domains = [d.strip().lower() for d in extra_raw.split(",") if d.strip()]

    if not domain:
        return 1, "Domain name is required."
    if not email:
        return 1, "Email address is required for Let's Encrypt notifications."
    if not re.match(r"^(\*\.)?[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)*\.[a-z]{2,}$", domain):
        return 1, f"Invalid domain name: '{domain}'"

    log(f"=== Let's Encrypt — {domain} ===")
    log(f"Challenge: {challenge.upper()}-01")
    log(f"Email: {email}")
    if extra_domains:
        log(f"Extra SANs: {', '.join(extra_domains)}")
    log("")

    certbot = _install_certbot_if_needed(live_cb)
    if not certbot:
        return 1, (
            "certbot is not available and could not be installed automatically.\n"
            "Please install certbot manually: https://certbot.eff.org/\n"
            "On Windows: use Certify The Web (https://certifytheweb.com/) or win-acme (https://www.win-acme.com/)."
        )

    certs_dir = _ssl_root()
    is_windows = os.name == "nt"

    # certbot config/work/logs dirs (important on Windows, certbot defaults need admin)
    certbot_config = certs_dir / "_certbot" / "config"
    certbot_work = certs_dir / "_certbot" / "work"
    certbot_logs = certs_dir / "_certbot" / "logs"
    for p in [certbot_config, certbot_work, certbot_logs]:
        p.mkdir(parents=True, exist_ok=True)

    all_domains = [domain] + extra_domains
    domain_args = []
    for d in all_domains:
        domain_args += ["-d", d]

    cmd = _certbot_cmd(certbot) + [
        "certonly",
        "--non-interactive", "--agree-tos",
        "--email", email,
        "--cert-name", domain,
        "--config-dir", str(certbot_config),
        "--work-dir", str(certbot_work),
        "--logs-dir", str(certbot_logs),
    ] + domain_args

    if challenge == "http":
        cmd += ["--standalone", "--http-01-port", "80"]
        log("HTTP-01 challenge: certbot will temporarily listen on port 80.")
        log("Ensure port 80 is open and reachable from the internet for domain verification.")
    elif challenge == "dns":
        cmd += ["--manual", "--preferred-challenges", "dns", "--manual-public-ip-logging-ok"]
        log("DNS-01 challenge: certbot will prompt you to add a DNS TXT record.")
        log("Watch the terminal for the TXT record value to add to your DNS provider.")
    else:
        return 1, f"Unknown challenge type: '{challenge}'"

    log(f"Running: {' '.join(cmd)}\n")

    output_lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            log(line.rstrip())
            output_lines.append(line)
        proc.wait()

        if proc.returncode != 0:
            return 1, "".join(output_lines)

        # Find the live cert dir
        live_dir = certbot_config / "live" / domain
        if not live_dir.exists():
            # certbot may add a suffix if domain was already used
            import glob
            candidates = sorted(certbot_config.glob(f"live/{domain}*/"))
            if candidates:
                live_dir = candidates[-1]
            else:
                return 1, (
                    "certbot succeeded but certificate directory not found.\n"
                    + "".join(output_lines)
                )

        cert_pem = (live_dir / "cert.pem").read_text(encoding="utf-8")
        key_pem = (live_dir / "privkey.pem").read_text(encoding="utf-8")
        chain_pem_path = live_dir / "chain.pem"
        chain_pem = chain_pem_path.read_text(encoding="utf-8") if chain_pem_path.exists() else ""

        meta = ssl_save_cert(domain, cert_pem, key_pem, chain_pem, source="letsencrypt")
        info = meta.get("info") or {}

        log("")
        log(f"✓ Certificate saved: {domain}")
        log(f"  Expiry:  {info.get('not_after', 'unknown')}")
        log(f"  Issuer:  {info.get('issuer', "Let's Encrypt")}")
        log(f"  SANs:    {', '.join(info.get('sans', [domain]))}")
        log("")
        log("Use 'Assign Certificate to Service' to apply it to IIS, nginx, or any service.")
        return 0, "".join(output_lines)

    except FileNotFoundError:
        return 1, "certbot executable not found."
    except Exception as ex:
        traceback.print_exc()
        return 1, f"Error running certbot: {ex}"


def run_ssl_renew_all(form, live_cb=None) -> tuple:
    """Renew all Let's Encrypt certs via certbot renew."""
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    certbot = _find_certbot()
    if not certbot:
        return 1, "certbot not found. Cannot auto-renew."

    certs_dir = _ssl_root()
    certbot_config = certs_dir / "_certbot" / "config"
    certbot_work = certs_dir / "_certbot" / "work"
    certbot_logs = certs_dir / "_certbot" / "logs"

    cmd = _certbot_cmd(certbot) + [
        "renew", "--non-interactive",
        "--config-dir", str(certbot_config),
        "--work-dir", str(certbot_work),
        "--logs-dir", str(certbot_logs),
    ]

    log(f"Running: {' '.join(cmd)}")
    output_lines = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log(line.rstrip())
            output_lines.append(line)
        proc.wait()

        if proc.returncode != 0:
            return 1, "".join(output_lines)

        # Re-copy renewed certs into our store
        live_root = certbot_config / "live"
        if live_root.exists():
            for live_dir in live_root.iterdir():
                if not live_dir.is_dir():
                    continue
                cert_file = live_dir / "cert.pem"
                key_file = live_dir / "privkey.pem"
                chain_file = live_dir / "chain.pem"
                if cert_file.exists() and key_file.exists():
                    domain = live_dir.name
                    cert_pem = cert_file.read_text(encoding="utf-8")
                    key_pem = key_file.read_text(encoding="utf-8")
                    chain_pem = chain_file.read_text(encoding="utf-8") if chain_file.exists() else ""
                    ssl_save_cert(domain, cert_pem, key_pem, chain_pem, source="letsencrypt")
                    log(f"Updated cert in store: {domain}")

        log("")
        log("Renewal complete. Check the terminal for details on which certs were renewed.")
        return 0, "".join(output_lines)
    except Exception as ex:
        return 1, f"Renew error: {ex}"


# ─── Upload handler ───────────────────────────────────────────────────────────

def run_ssl_upload(form, parts, live_cb=None) -> tuple:
    """
    Handle cert upload from multipart form.
    form fields: SSL_DOMAIN, SSL_CERT_NAME
    parts: list of multipart parts (name: cert_file | key_file | chain_file | pfx_file)
    Also accepts form fields SSL_CERT_PEM, SSL_KEY_PEM, SSL_CHAIN_PEM for textarea paste.
    Returns (exit_code, message)
    """
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    domain = (form.get("SSL_DOMAIN", [""])[0] or "").strip()
    cert_name = (form.get("SSL_CERT_NAME", [""])[0] or domain or "").strip()
    pfx_password = (form.get("SSL_PFX_PASSWORD", [""])[0] or "").strip()

    # Collect file contents from parts
    cert_pem = ""
    key_pem = ""
    chain_pem = ""
    pfx_bytes = None

    for part in (parts or []):
        pname = part.get("name", "")
        content = part.get("content", b"")
        if pname == "cert_file" and content:
            cert_pem = content.decode("utf-8", errors="replace")
        elif pname == "key_file" and content:
            key_pem = content.decode("utf-8", errors="replace")
        elif pname == "chain_file" and content:
            chain_pem = content.decode("utf-8", errors="replace")
        elif pname == "pfx_file" and content:
            pfx_bytes = content

    # Also accept pasted PEM text fields
    if not cert_pem:
        cert_pem = (form.get("SSL_CERT_PEM", [""])[0] or "").strip()
    if not key_pem:
        key_pem = (form.get("SSL_KEY_PEM", [""])[0] or "").strip()
    if not chain_pem:
        chain_pem = (form.get("SSL_CHAIN_PEM", [""])[0] or "").strip()

    # PFX import path
    if pfx_bytes and not cert_pem:
        if not domain and not cert_name:
            return 1, "Domain / certificate name is required for PFX import."
        log(f"Importing PFX for: {domain or cert_name}")
        ok, cert_pem, key_pem, chain_pem, err = ssl_import_pfx(
            pfx_bytes, pfx_password, domain or cert_name, live_cb
        )
        if not ok:
            return 1, err

    if not cert_pem.strip():
        return 1, "Certificate PEM is required (upload a .pem/.crt file or paste it)."
    if not key_pem.strip():
        return 1, "Private key PEM is required (upload a .key file or paste it)."

    # Auto-extract domain from cert CN if not provided
    if not domain and not cert_name:
        info = ssl_cert_info(cert_pem)
        domain = info.get("cn") or "custom"
        cert_name = domain

    log(f"Validating certificate for: {domain or cert_name}")
    ok, msg = ssl_validate_pair(cert_pem, key_pem)
    if not ok:
        return 1, f"Certificate validation failed: {msg}"
    log(f"Validation: {msg}")

    info = ssl_cert_info(cert_pem)
    log(f"Subject CN: {info.get('cn', 'unknown')}")
    log(f"Issuer:     {info.get('issuer', info.get('issuer_cn', 'unknown'))}")
    log(f"Expiry:     {info.get('not_after', 'unknown')}")
    if info.get("sans"):
        log(f"SANs:       {', '.join(info['sans'])}")
    if info.get("self_signed"):
        log("Note: This certificate appears to be self-signed.")

    ssl_save_cert(cert_name or domain, cert_pem, key_pem, chain_pem, source="upload")
    log(f"\n✓ Certificate saved as '{cert_name or domain}'.")
    log("Use 'Assign Certificate to Service' to apply it.")
    return 0, f"Certificate '{cert_name or domain}' saved successfully."


# ─── Certificate assignment ───────────────────────────────────────────────────

def run_ssl_assign(form, live_cb=None) -> tuple:
    """
    Assign a managed certificate to a service.
    form fields:
      SSL_CERT_NAME       - name of stored cert (required)
      SSL_SERVICE_KIND    - iis | nginx | python-api | custom
      SSL_SITE_NAME       - IIS site name (for IIS)
      SSL_CUSTOM_CERT_DEST - destination path for cert.pem (custom)
      SSL_CUSTOM_KEY_DEST  - destination path for key.pem (custom)
      SSL_RESTART_SERVICE  - true|false
    Returns (exit_code, output_str)
    """
    def log(s):
        if live_cb:
            live_cb(s + "\n")

    cert_name = (form.get("SSL_CERT_NAME", [""])[0] or "").strip()
    service_kind = (form.get("SSL_SERVICE_KIND", ["custom"])[0] or "custom").strip().lower()
    site_name = (form.get("SSL_SITE_NAME", [""])[0] or "").strip()
    custom_cert_dest = (form.get("SSL_CUSTOM_CERT_DEST", [""])[0] or "").strip()
    custom_key_dest = (form.get("SSL_CUSTOM_KEY_DEST", [""])[0] or "").strip()
    restart = (form.get("SSL_RESTART_SERVICE", ["true"])[0] or "true").strip().lower() == "true"

    if not cert_name:
        return 1, "Certificate name is required."

    d = _ssl_root() / _safe_cert_name(cert_name)
    if not d.exists():
        return 1, f"Certificate '{cert_name}' not found in the store."

    cert_path = d / "cert.pem"
    key_path = d / "key.pem"
    fullchain_path = d / "fullchain.pem"

    if not cert_path.exists() or not key_path.exists():
        return 1, f"Certificate files missing for '{cert_name}'."

    log(f"Assigning certificate '{cert_name}' to {service_kind}" +
        (f" / {site_name}" if site_name else "") + " ...")
    log(f"  cert:      {cert_path}")
    log(f"  key:       {key_path}")
    log(f"  fullchain: {fullchain_path}")
    log("")

    is_windows = os.name == "nt"

    if service_kind == "iis":
        if not is_windows:
            return 1, "IIS certificate assignment requires Windows."
        return _assign_iis(cert_name, site_name, cert_path, key_path, fullchain_path, log, restart)

    if service_kind == "nginx":
        return _assign_nginx(cert_name, site_name, cert_path, key_path, fullchain_path, log, restart)

    if service_kind == "custom":
        if not custom_cert_dest or not custom_key_dest:
            return 1, "Custom mode requires SSL_CUSTOM_CERT_DEST and SSL_CUSTOM_KEY_DEST."
        try:
            shutil.copy2(str(cert_path), custom_cert_dest)
            shutil.copy2(str(key_path), custom_key_dest)
            log(f"Copied cert → {custom_cert_dest}")
            log(f"Copied key  → {custom_key_dest}")
            # Also copy fullchain if it exists and dest dir is given
            fc_dest = str(Path(custom_cert_dest).parent / "fullchain.pem")
            if fullchain_path.exists():
                shutil.copy2(str(fullchain_path), fc_dest)
                log(f"Copied fullchain → {fc_dest}")
            log("")
            log("Done. Restart your service to apply the new certificate.")
            return 0, f"Certificate files copied to {custom_cert_dest}."
        except Exception as ex:
            return 1, f"Copy failed: {ex}"

    return 1, f"Unknown service kind '{service_kind}'. Supported: iis, nginx, custom."


def _assign_iis(cert_name, site_name, cert_path, key_path, fullchain_path, log, restart):
    """Import cert into Windows cert store and bind to an IIS site."""
    openssl = _openssl_bin()
    if not openssl:
        return 1, "openssl not found — needed to create PFX for IIS import."

    pfx_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pfx", delete=False) as f:
            pfx_tmp = f.name

        r = subprocess.run(
            [openssl, "pkcs12", "-export",
             "-out", pfx_tmp,
             "-inkey", str(key_path),
             "-in", str(fullchain_path) if fullchain_path.exists() else str(cert_path),
             "-passout", "pass:ServerInstallerTemp!"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return 1, f"Failed to create PFX: {r.stderr.strip()}"
        log("Created temporary PFX from cert+key.")

        pfx_escaped = pfx_tmp.replace("\\", "\\\\")
        ps = f"""
$pfxPath = '{pfx_escaped}'
$pfxPwd  = ConvertTo-SecureString 'ServerInstallerTemp!' -Force -AsPlainText
$cert    = Import-PfxCertificate -FilePath $pfxPath -CertStoreLocation Cert:\\LocalMachine\\My -Password $pfxPwd
if (-not $cert) {{ throw "Import-PfxCertificate returned null" }}
$thumb = $cert.Thumbprint
Write-Host "Imported certificate thumbprint: $thumb"
Write-Host "Subject: $($cert.Subject)"
Write-Host "Expiry:  $($cert.NotAfter)"
"""
        if site_name:
            site_escaped = site_name.replace("'", "''")
            ps += f"""
Import-Module WebAdministration -ErrorAction SilentlyContinue
$siteName = '{site_escaped}'
$binding  = Get-WebBinding -Name $siteName -Protocol https 2>$null | Select-Object -First 1
if ($binding) {{
    $binding.AddSslCertificate($thumb, "My")
    Write-Host "Bound to IIS site '$siteName' (HTTPS)"
}} else {{
    # Create HTTPS binding if not present
    New-WebBinding -Name $siteName -Protocol https -Port 443 -IPAddress "*" -ErrorAction SilentlyContinue
    $binding = Get-WebBinding -Name $siteName -Protocol https | Select-Object -First 1
    if ($binding) {{
        $binding.AddSslCertificate($thumb, "My")
        Write-Host "Created new HTTPS binding and bound certificate to '$siteName'."
    }} else {{
        Write-Host "Warning: could not find or create HTTPS binding for '$siteName'."
    }}
}}
"""
        if restart and site_name:
            site_escaped2 = site_name.replace("'", "''")
            ps += f"""
try {{
    Restart-WebSite -Name '{site_escaped2}'
    Write-Host "IIS site '{site_escaped2}' restarted."
}} catch {{
    Write-Host "Note: Could not restart site: $($_.Exception.Message)"
}}
"""

        r2 = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=60,
        )
        if r2.stdout:
            log(r2.stdout.strip())
        if r2.stderr:
            log(r2.stderr.strip())
        if r2.returncode != 0:
            return 1, f"PowerShell cert import failed (exit {r2.returncode})."
        log("")
        log(f"✓ Certificate '{cert_name}' assigned to IIS.")
        return 0, r2.stdout

    except Exception as ex:
        traceback.print_exc()
        return 1, f"IIS assignment error: {ex}"
    finally:
        if pfx_tmp:
            try:
                os.unlink(pfx_tmp)
            except Exception:
                pass


def _assign_nginx(cert_name, config_name, cert_path, key_path, fullchain_path, log, restart):
    """Update nginx server blocks to use the given certificate."""
    nginx_dirs = [
        Path("/etc/nginx/sites-enabled"),
        Path("/etc/nginx/conf.d"),
        Path("/etc/nginx"),
    ]

    updated_files = []
    fc = str(fullchain_path) if fullchain_path.exists() else str(cert_path)

    for conf_dir in nginx_dirs:
        if not conf_dir.exists():
            continue
        pattern = "*.conf"
        files = list(conf_dir.glob(pattern))
        if conf_dir == Path("/etc/nginx"):
            files = [conf_dir / "nginx.conf"]
        for conf_file in files:
            if not conf_file.is_file():
                continue
            try:
                content = conf_file.read_text(encoding="utf-8")
                if "ssl_certificate" not in content:
                    continue
                new_content = re.sub(
                    r"ssl_certificate\s+[^;]+;",
                    f"ssl_certificate {fc};",
                    content,
                )
                new_content = re.sub(
                    r"ssl_certificate_key\s+[^;]+;",
                    f"ssl_certificate_key {key_path};",
                    new_content,
                )
                if new_content != content:
                    conf_file.write_text(new_content, encoding="utf-8")
                    updated_files.append(str(conf_file))
                    log(f"Updated: {conf_file}")
            except Exception as ex:
                log(f"Could not update {conf_file}: {ex}")

    if not updated_files:
        log("No existing nginx ssl_certificate directives found to update.")
        log(f"Manually set in your nginx config:")
        log(f"  ssl_certificate     {fc};")
        log(f"  ssl_certificate_key {key_path};")

    if restart and shutil.which("nginx"):
        log("Testing nginx configuration...")
        rt = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=15)
        if rt.returncode == 0:
            log("Config OK. Reloading nginx...")
            subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, timeout=15)
            log("nginx reloaded.")
        else:
            log(f"nginx -t failed: {rt.stderr.strip()}")
            log("Fix nginx configuration before reloading.")
            return 1, rt.stderr.strip()

    log("")
    log(f"✓ Updated {len(updated_files)} nginx config file(s) with certificate '{cert_name}'.")
    return 0, f"Assigned '{cert_name}' to nginx ({len(updated_files)} file(s) updated)."
