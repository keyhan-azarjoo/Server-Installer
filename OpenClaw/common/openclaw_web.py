#!/usr/bin/env python3
"""
OpenClaw Web UI — Web interface for the OpenClaw AI agent framework.
Provides a chat-like interface to run agent tasks, view history, and manage plugins.
"""
import os
import json
import subprocess
import sys
import threading
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__,
    template_folder=os.path.join(os.path.dirname(__file__), "web", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "web", "static"),
)

AUTH_USERNAME = os.environ.get("OPENCLAW_AUTH_USERNAME", "")
AUTH_PASSWORD = os.environ.get("OPENCLAW_AUTH_PASSWORD", "")
VENV_DIR = os.environ.get("OPENCLAW_VENV_DIR", "")


def _check_auth():
    if not AUTH_USERNAME:
        return True
    auth = request.authorization
    return auth and auth.username == AUTH_USERNAME and auth.password == AUTH_PASSWORD


def _require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _check_auth():
            return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="OpenClaw"'})
        return f(*args, **kwargs)
    return decorated


def _get_openclaw_bin():
    """Find the openclaw CLI binary."""
    if VENV_DIR:
        venv_bin = os.path.join(VENV_DIR, "Scripts" if os.name == "nt" else "bin", "openclaw")
        if os.path.isfile(venv_bin):
            return venv_bin
        venv_bin += ".exe"
        if os.path.isfile(venv_bin):
            return venv_bin
    import shutil
    return shutil.which("openclaw") or "openclaw"


def _run_openclaw(args, timeout=120):
    """Run an openclaw command and return output."""
    cmd = [_get_openclaw_bin()] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": proc.returncode == 0, "output": proc.stdout, "error": proc.stderr}
    except FileNotFoundError:
        return {"ok": False, "error": "openclaw CLI not found. Install: pip install openclaw"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.route("/")
@_require_auth
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    result = _run_openclaw(["--version"], timeout=10)
    return jsonify({
        "ok": result["ok"],
        "status": "healthy" if result["ok"] else "unhealthy",
        "service": "openclaw",
        "version": result.get("output", "").strip() if result["ok"] else "",
    })


@app.route("/api/run", methods=["POST"])
@_require_auth
def run_task():
    """Run an OpenClaw agent task."""
    data = request.get_json(silent=True) or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"ok": False, "error": "Task description required."}), 400

    result = _run_openclaw(["run", task], timeout=300)
    return jsonify(result)


@app.route("/api/run/stream", methods=["POST"])
@_require_auth
def run_task_stream():
    """Run an OpenClaw agent task with streaming output."""
    data = request.get_json(silent=True) or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"ok": False, "error": "Task required."}), 400

    def generate():
        cmd = [_get_openclaw_bin(), "run", task]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            proc.wait()
            yield f"data: {json.dumps({'done': True, 'exit_code': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/plugins")
@_require_auth
def list_plugins():
    """List available OpenClaw plugins."""
    result = _run_openclaw(["plugins", "list"], timeout=30)
    return jsonify(result)


@app.route("/api/config")
@_require_auth
def get_config():
    """Get OpenClaw configuration."""
    result = _run_openclaw(["config", "show"], timeout=15)
    return jsonify(result)


@app.route("/api/version")
@_require_auth
def version():
    result = _run_openclaw(["--version"], timeout=10)
    return jsonify({"ok": result["ok"], "version": result.get("output", "").strip()})


if __name__ == "__main__":
    port = int(os.environ.get("OPENCLAW_WEB_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
