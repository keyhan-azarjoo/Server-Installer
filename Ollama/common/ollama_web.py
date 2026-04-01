#!/usr/bin/env python3
"""
Ollama Web UI — A professional chat interface for Ollama LLMs.
Provides web-based chat, model management, and API proxy.
"""
import os
import json
import time
import hashlib
import secrets
import requests
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for

app = Flask(__name__,
    template_folder=os.path.join(os.path.dirname(__file__), "web", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "web", "static"),
)
app.secret_key = os.environ.get("OLLAMA_SECRET_KEY", secrets.token_hex(32))

OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
AUTH_USERNAME = os.environ.get("OLLAMA_AUTH_USERNAME", "")
AUTH_PASSWORD = os.environ.get("OLLAMA_AUTH_PASSWORD", "")
DEPLOY_MODE = os.environ.get("OLLAMA_DEPLOY_MODE", "").strip().lower()
HOST_OS = os.environ.get("OLLAMA_HOST_OS", "").strip().lower()


def _parse_meminfo():
    info = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                parts = value.strip().split()
                if not parts:
                    continue
                try:
                    info[key] = int(parts[0]) * 1024
                except ValueError:
                    continue
    except Exception:
        pass
    return info


def _read_memory_limit_bytes():
    candidates = [
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ]
    for path in candidates:
        try:
            raw = open(path, "r", encoding="utf-8").read().strip()
        except Exception:
            continue
        if not raw or raw == "max":
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        # Ignore obviously unbounded/sentinel values.
        if value <= 0 or value >= (1 << 60):
            continue
        return value
    return 0


def _gib(value):
    if not value:
        return 0.0
    return round(float(value) / (1024 ** 3), 1)


def _runtime_info():
    meminfo = _parse_meminfo()
    total_bytes = int(meminfo.get("MemTotal", 0) or 0)
    available_bytes = int(meminfo.get("MemAvailable", 0) or 0)
    limit_bytes = int(_read_memory_limit_bytes() or 0)
    effective_total = min(total_bytes, limit_bytes) if total_bytes and limit_bytes else (limit_bytes or total_bytes)
    in_docker = os.path.exists("/.dockerenv")
    return {
        "deploy_mode": DEPLOY_MODE or ("docker" if in_docker else "os"),
        "host_os": HOST_OS,
        "in_docker": in_docker,
        "memory_total_bytes": effective_total or total_bytes,
        "memory_available_bytes": available_bytes,
        "memory_limit_bytes": limit_bytes,
        "memory_total_gib": _gib(effective_total or total_bytes),
        "memory_available_gib": _gib(available_bytes),
        "memory_limit_gib": _gib(limit_bytes),
    }


def _check_auth():
    """Check session or basic auth."""
    if not AUTH_USERNAME:
        return True
    # Session auth
    if session.get("authenticated"):
        return True
    # Basic auth (for API clients)
    auth = request.authorization
    if auth and auth.username == AUTH_USERNAME and auth.password == AUTH_PASSWORD:
        return True
    return False


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_auth():
            # For API requests, return 401
            if request.path.startswith("/api/") or request.path.startswith("/v1/"):
                return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Ollama"'})
            # For page requests, redirect to login
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def _ollama(method, path, json_data=None, stream=False, timeout=120):
    """Make a request to the Ollama API."""
    url = f"{OLLAMA_BASE}{path}"
    try:
        r = requests.request(method, url, json=json_data, stream=stream, timeout=timeout)
        if stream:
            return r
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            return r.json()
        return {"raw": r.text}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to Ollama. Is the server running?"}
    except Exception as e:
        return {"error": str(e)}


# ── Auth Routes ─────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET"])
def login_page():
    if not AUTH_USERNAME or _check_auth():
        return redirect("/")
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def login():
    if not AUTH_USERNAME:
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    if data.get("username") == AUTH_USERNAME and data.get("password") == AUTH_PASSWORD:
        session["authenticated"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Invalid username or password"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth-status")
def auth_status():
    return jsonify({"ok": True, "auth_required": bool(AUTH_USERNAME), "authenticated": _check_auth()})


# ── Web UI Routes ───────────────────────────────────────────────────────────

@app.route("/")
@_require_auth
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    runtime = _runtime_info()
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = r.json().get("models", [])
        return jsonify({
            "ok": True, "status": "healthy", "ollama": OLLAMA_BASE,
            "model_count": len(models),
            "runtime": runtime,
        })
    except Exception:
        return jsonify({"ok": True, "status": "web_ui_only", "ollama": OLLAMA_BASE, "ollama_server": False,
                        "message": "Web UI is running. Ollama server is not responding at " + OLLAMA_BASE,
                        "runtime": runtime})


@app.route("/api/runtime-info")
def runtime_info():
    return jsonify({"ok": True, "runtime": _runtime_info()})


# ── Model Management ────────────────────────────────────────────────────────

@app.route("/api/models")
@_require_auth
def list_models():
    result = _ollama("GET", "/api/tags")
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, "models": result.get("models", [])})


@app.route("/api/models/running")
@_require_auth
def running_models():
    result = _ollama("GET", "/api/ps")
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, "models": result.get("models", [])})


@app.route("/api/models/pull", methods=["POST"])
@_require_auth
def pull_model():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"ok": False, "error": "Model name required"}), 400

    def generate():
        try:
            r = _ollama("POST", "/api/pull", {"name": name, "stream": True}, stream=True)
            if isinstance(r, dict) and "error" in r:
                yield f'data: {{"error":"{r["error"]}"}}\n\n'
                return
            for line in r.iter_lines():
                if line:
                    yield f"data: {line.decode()}\n\n"
            yield 'data: {"status":"success"}\n\n'
        except Exception as e:
            yield f'data: {{"error":"{e}"}}\n\n'

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/models/delete", methods=["POST"])
@_require_auth
def delete_model():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"ok": False, "error": "Model name required"}), 400
    result = _ollama("DELETE", "/api/delete", {"name": name})
    return jsonify({"ok": "error" not in result})


@app.route("/api/models/info", methods=["POST"])
@_require_auth
def model_info():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    result = _ollama("POST", "/api/show", {"name": name})
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, **result})


@app.route("/api/models/copy", methods=["POST"])
@_require_auth
def copy_model():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")
    destination = data.get("destination", "")
    if not source or not destination:
        return jsonify({"ok": False, "error": "Source and destination required"}), 400
    result = _ollama("POST", "/api/copy", {"source": source, "destination": destination})
    return jsonify({"ok": "error" not in result})


# ── Chat ────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
@_require_auth
def chat():
    data = request.get_json(silent=True) or {}
    model = data.get("model", "")
    messages = data.get("messages", [])
    stream = data.get("stream", True)

    if not model:
        return jsonify({"ok": False, "error": "Model name required"}), 400

    options = data.get("options", {})
    payload = {"model": model, "messages": messages, "stream": stream}
    if options:
        payload["options"] = options

    if stream:
        def generate():
            try:
                r = _ollama("POST", "/api/chat", {**payload, "stream": True}, stream=True)
                if isinstance(r, dict) and "error" in r:
                    yield f'data: {json.dumps({"error": r["error"]})}\n\n'
                    return
                for line in r.iter_lines():
                    if line:
                        yield f"data: {line.decode()}\n\n"
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'
        return Response(stream_with_context(generate()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    else:
        result = _ollama("POST", "/api/chat", {**payload, "stream": False})
        if "error" in result:
            return jsonify({"ok": False, "error": result["error"]}), 500
        return jsonify({"ok": True, **result})


@app.route("/api/generate", methods=["POST"])
@_require_auth
def generate_text():
    data = request.get_json(silent=True) or {}
    model = data.get("model", "")
    prompt = data.get("prompt", "")
    options = data.get("options", {})
    payload = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    result = _ollama("POST", "/api/generate", payload)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, **result})


# ── Proxy / OpenAI-compatible ───────────────────────────────────────────────

@app.route("/api/tags")
@_require_auth
def proxy_tags():
    return jsonify(_ollama("GET", "/api/tags"))

@app.route("/api/ps")
@_require_auth
def proxy_ps():
    return jsonify(_ollama("GET", "/api/ps"))

@app.route("/api/embeddings", methods=["POST"])
@_require_auth
def proxy_embeddings():
    return jsonify(_ollama("POST", "/api/embeddings", request.get_json(silent=True)))

@app.route("/v1/chat/completions", methods=["POST"])
@_require_auth
def proxy_v1_chat():
    return jsonify(_ollama("POST", "/v1/chat/completions", request.get_json(silent=True)))

@app.route("/v1/models")
@_require_auth
def proxy_v1_models():
    return jsonify(_ollama("GET", "/v1/models"))

@app.route("/v1/completions", methods=["POST"])
@_require_auth
def proxy_v1_completions():
    return jsonify(_ollama("POST", "/v1/completions", request.get_json(silent=True)))

# Native Ollama API pass-through (so dashboard API gateway can use standard paths)
@app.route("/api/pull", methods=["POST"])
@_require_auth
def proxy_api_pull():
    return jsonify(_ollama("POST", "/api/pull", request.get_json(silent=True)))

@app.route("/api/delete", methods=["DELETE"])
@_require_auth
def proxy_api_delete():
    return jsonify(_ollama("DELETE", "/api/delete", request.get_json(silent=True)))

@app.route("/api/show", methods=["POST"])
@_require_auth
def proxy_api_show():
    return jsonify(_ollama("POST", "/api/show", request.get_json(silent=True)))

@app.route("/api/copy", methods=["POST"])
@_require_auth
def proxy_api_copy():
    return jsonify(_ollama("POST", "/api/copy", request.get_json(silent=True)))


if __name__ == "__main__":
    import ssl
    import threading
    import subprocess as _sp

    http_port_str = os.environ.get("OLLAMA_WEBUI_PORT", "").strip()
    https_port = os.environ.get("OLLAMA_HTTPS_PORT", "").strip()
    cert_dir = os.environ.get("OLLAMA_CERT_DIR", os.path.join(os.path.dirname(__file__), "certs"))
    cert_file = os.path.join(cert_dir, "ollama.crt")
    key_file = os.path.join(cert_dir, "ollama.key")

    # Determine which ports to serve
    http_port = int(http_port_str) if http_port_str and http_port_str.isdigit() and int(http_port_str) > 0 else 0
    has_https = https_port and https_port.isdigit() and int(https_port) > 0

    # Generate SSL cert if HTTPS is requested
    if has_https:
        os.makedirs(cert_dir, exist_ok=True)
        if not os.path.exists(cert_file):
            try:
                _sp.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                         "-keyout", key_file, "-out", cert_file, "-days", "3650",
                         "-subj", "/CN=Ollama/O=ServerInstaller/C=US"],
                        capture_output=True, timeout=30)
                print(f"SSL cert created: {cert_file}")
            except Exception as e:
                print(f"SSL cert generation failed: {e}")
                has_https = False

        if has_https and not os.path.exists(cert_file):
            has_https = False

    if has_https and http_port > 0:
        # Both HTTP and HTTPS — run HTTPS in background thread, HTTP in main
        def _run_https():
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.load_cert_chain(cert_file, key_file)
                from werkzeug.serving import make_server
                srv = make_server("0.0.0.0", int(https_port), app, ssl_context=ctx, threaded=True)
                print(f"HTTPS on port {https_port}")
                srv.serve_forever()
            except Exception as e:
                print(f"HTTPS failed: {e}")
        threading.Thread(target=_run_https, daemon=True).start()
        print(f"HTTP on port {http_port}")
        app.run(host="0.0.0.0", port=http_port, debug=False)
    elif has_https:
        # HTTPS only — run in main thread
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_file, key_file)
        print(f"HTTPS on port {https_port} (no HTTP)")
        app.run(host="0.0.0.0", port=int(https_port), ssl_context=ctx, debug=False)
    else:
        # HTTP only
        port = http_port if http_port > 0 else 3080
        print(f"HTTP on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)
