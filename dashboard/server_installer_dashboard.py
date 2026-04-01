#!/usr/bin/env python3
"""
Server Installer Dashboard — thin entry point.

All functionality is split into focused modules:
  constants.py        — paths, file lists, global state
  utils.py            — JSON I/O, command helpers, downloads
  cert_manager.py     — dashboard certificate management
  python_manager.py   — Python environment, Jupyter, Python API
  website_manager.py  — website stack detection & deployment
  system_info.py      — system info (uptime, memory, CPU, IPs, Docker, .NET)
  port_manager.py     — port/network utilities, firewall
  mongo_manager.py    — MongoDB native operations
  service_manager.py  — service items, lifecycle, cleanup
  installer_runners.py— Windows/Linux/Docker installers
  ai_services.py      — Ollama, LMStudio, OpenClaw, TGWUI, ComfyUI, Whisper, Piper
  system_admin.py     — credentials, process management, uploads, power
  pages.py            — page rendering (login, dashboard, output, mongo UI)
  handler.py          — HTTP Handler class
"""
import argparse
import socket
import ssl
import warnings

from http.server import ThreadingHTTPServer

from cert_manager import _generate_dashboard_selfsigned, _resolve_dashboard_cert
from handler import Handler  # noqa: F401 — used by ThreadingHTTPServer

warnings.filterwarnings("ignore", category=DeprecationWarning)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--cert", default="")
    parser.add_argument("--key", default="")
    args = parser.parse_args()

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as ex:
        print(f"Failed to bind dashboard on {args.host}:{args.port} -> {ex}")
        if getattr(ex, "errno", None) in (13,):
            print("Hint: Port requires elevated privileges. Try a higher port (e.g. 8090) or run as root/admin.")
        if getattr(ex, "errno", None) in (98, 10048):
            print("Hint: Port is already in use by another process. Choose another port.")
        return

    # Resolve certificate: explicit args → managed cert config → auto self-signed
    cert_path, key_path = _resolve_dashboard_cert(args.cert, args.key)
    scheme = "http"
    if cert_path and key_path:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            scheme = "https"
            print(f"[dashboard] HTTPS enabled with certificate: {cert_path}")
        except Exception as ex:
            print(f"[dashboard] Failed to load certificate ({ex}), retrying with fresh self-signed...")
            # Force-regenerate and try once more
            cert_path, key_path = _generate_dashboard_selfsigned()
            if cert_path and key_path:
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                    server.socket = ctx.wrap_socket(server.socket, server_side=True)
                    scheme = "https"
                    print(f"[dashboard] HTTPS enabled with new self-signed certificate: {cert_path}")
                except Exception as ex2:
                    print(f"[dashboard] HTTPS setup failed ({ex2}). Running without TLS.")
            else:
                print("[dashboard] Could not generate self-signed cert. Running without TLS.")
    else:
        print("[dashboard] No certificate available. Running without TLS (HTTP only).")

    urls = [f"{scheme}://127.0.0.1:{args.port}"]
    if args.host not in ("127.0.0.1", "localhost", "0.0.0.0", ""):
        explicit = f"{scheme}://{args.host}:{args.port}"
        if explicit not in urls:
            urls.append(explicit)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and (not primary_ip.startswith("127.")):
            candidate = f"{scheme}://{primary_ip}:{args.port}"
            if candidate not in urls:
                urls.append(candidate)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
