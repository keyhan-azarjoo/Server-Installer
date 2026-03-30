#!/usr/bin/env python3
"""
LM Studio Web UI — Professional chat interface and API proxy for LM Studio.
"""
import os
import json
import secrets
import requests
from functools import wraps
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for

app = Flask(__name__,
    template_folder=os.path.join(os.path.dirname(__file__), "web", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "web", "static"),
)
app.secret_key = os.environ.get("LMSTUDIO_SECRET_KEY", secrets.token_hex(32))

LMSTUDIO_BASE = os.environ.get("LMSTUDIO_API_BASE", "http://127.0.0.1:1234")
AUTH_USERNAME = os.environ.get("LMSTUDIO_AUTH_USERNAME", "")
AUTH_PASSWORD = os.environ.get("LMSTUDIO_AUTH_PASSWORD", "")


def _check_auth():
    if not AUTH_USERNAME:
        return True
    if session.get("authenticated"):
        return True
    auth = request.authorization
    return auth and auth.username == AUTH_USERNAME and auth.password == AUTH_PASSWORD


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_auth():
            if request.path.startswith("/api/") or request.path.startswith("/v1/"):
                return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="LM Studio"'})
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def _lms(method, path, json_data=None, stream=False, timeout=120):
    url = f"{LMSTUDIO_BASE}{path}"
    try:
        r = requests.request(method, url, json=json_data, stream=stream, timeout=timeout)
        if stream:
            return r
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            return r.json()
        return {"raw": r.text}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to LM Studio. Start the local server in LM Studio app."}
    except Exception as e:
        return {"error": str(e)}


# ── Auth ────────────────────────────────────────────────────────────────────

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


# ── Pages ───────────────────────────────────────────────────────────────────

@app.route("/")
@_require_auth
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    try:
        r = requests.get(f"{LMSTUDIO_BASE}/v1/models", timeout=5)
        models = r.json().get("data", [])
        return jsonify({"ok": True, "status": "healthy", "lmstudio": LMSTUDIO_BASE, "model_count": len(models)})
    except Exception:
        return jsonify({"ok": False, "status": "unhealthy", "lmstudio": LMSTUDIO_BASE}), 503


# ── Models ──────────────────────────────────────────────────────────────────

@app.route("/api/models")
@_require_auth
def list_models():
    result = _lms("GET", "/v1/models")
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, "models": result.get("data", [])})


# ── Chat ────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
@_require_auth
def chat():
    data = request.get_json(silent=True) or {}
    model = data.get("model", "")
    messages = data.get("messages", [])
    stream = data.get("stream", True)

    if not model:
        models = _lms("GET", "/v1/models")
        if models.get("data"):
            model = models["data"][0].get("id", "")

    payload = {"model": model, "messages": messages, "stream": stream}
    for key in ("temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty", "stop"):
        if key in data:
            payload[key] = data[key]

    if stream:
        def generate():
            try:
                r = _lms("POST", "/v1/chat/completions", payload, stream=True)
                if isinstance(r, dict) and "error" in r:
                    yield f'data: {json.dumps({"error": r["error"]})}\n\n'
                    return
                for line in r.iter_lines():
                    if line:
                        decoded = line.decode()
                        if decoded.startswith("data: "):
                            yield f"{decoded}\n\n"
                        else:
                            yield f"data: {decoded}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'
        return Response(stream_with_context(generate()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    else:
        result = _lms("POST", "/v1/chat/completions", payload)
        if "error" in result:
            return jsonify({"ok": False, "error": result["error"]}), 500
        return jsonify({"ok": True, **result})


@app.route("/api/generate", methods=["POST"])
@_require_auth
def generate():
    data = request.get_json(silent=True) or {}
    payload = {k: data[k] for k in data if k in ("model", "prompt", "max_tokens", "temperature", "top_p")}
    result = _lms("POST", "/v1/completions", payload)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, **result})


@app.route("/api/embeddings", methods=["POST"])
@_require_auth
def embeddings():
    result = _lms("POST", "/v1/embeddings", request.get_json(silent=True))
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]}), 500
    return jsonify({"ok": True, **result})


# ── OpenAI-compatible passthrough ───────────────────────────────────────────

@app.route("/v1/chat/completions", methods=["POST"])
@_require_auth
def v1_chat():
    return jsonify(_lms("POST", "/v1/chat/completions", request.get_json(silent=True)))

@app.route("/v1/completions", methods=["POST"])
@_require_auth
def v1_completions():
    return jsonify(_lms("POST", "/v1/completions", request.get_json(silent=True)))

@app.route("/v1/models")
@_require_auth
def v1_models():
    return jsonify(_lms("GET", "/v1/models"))

@app.route("/v1/embeddings", methods=["POST"])
@_require_auth
def v1_embeddings():
    return jsonify(_lms("POST", "/v1/embeddings", request.get_json(silent=True)))


if __name__ == "__main__":
    import ssl
    import threading
    import subprocess as _sp

    port = int(os.environ.get("LMSTUDIO_WEB_PORT", 8080))
    https_port = os.environ.get("LMSTUDIO_HTTPS_PORT", "").strip()
    cert_dir = os.environ.get("LMSTUDIO_CERT_DIR", os.path.join(os.path.dirname(__file__), "certs"))
    cert_file = os.path.join(cert_dir, "lmstudio.crt")
    key_file = os.path.join(cert_dir, "lmstudio.key")

    if https_port and https_port.isdigit() and int(https_port) > 0:
        os.makedirs(cert_dir, exist_ok=True)
        if not os.path.exists(cert_file):
            try:
                _sp.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                         "-keyout", key_file, "-out", cert_file, "-days", "3650",
                         "-subj", "/CN=LMStudio/O=ServerInstaller/C=US"],
                        capture_output=True, timeout=30)
                print(f"SSL cert created: {cert_file}")
            except Exception as e:
                print(f"SSL cert generation failed: {e}")
                https_port = ""
        if https_port and os.path.exists(cert_file):
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

    print(f"HTTP on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
