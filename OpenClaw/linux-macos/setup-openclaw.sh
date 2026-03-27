#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Linux / macOS
# ─────────────────────────────────────────────────────────────────────────────
set -eo pipefail
HOME="${HOME:-/root}"
export HOME

SERVICE_NAME="serverinstaller-openclaw"
HTTP_PORT="${OPENCLAW_HTTP_PORT:-}"
HTTPS_PORT="${OPENCLAW_HTTPS_PORT:-}"
HOST_IP="${OPENCLAW_HOST_IP:-0.0.0.0}"
DOMAIN="${OPENCLAW_DOMAIN:-}"
USERNAME="${OPENCLAW_USERNAME:-}"
PASSWORD="${OPENCLAW_PASSWORD:-}"

BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/openclaw"
STATE_FILE="${STATE_DIR}/openclaw-state.json"
INSTALL_DIR="${STATE_DIR}/app"
VENV_DIR="${INSTALL_DIR}/venv"
CERT_DIR="${STATE_DIR}/certs"
LOG_FILE="${STATE_DIR}/openclaw.log"
SYSTEMD_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() { echo "[OpenClaw] $*"; }
mkdir -p "$STATE_DIR" "$INSTALL_DIR" "$CERT_DIR"

# ── Step 1: Python + venv ────────────────────────────────────────────────────
log "Resolving Python..."
PYTHON_CMD=""
for py in python3 python; do
    command -v "$py" &>/dev/null && "$py" --version 2>&1 | grep -q "Python 3" && PYTHON_CMD="$py" && break
done
if [ -z "$PYTHON_CMD" ]; then
    log "Installing Python..."
    command -v apt-get &>/dev/null && apt-get update -y && apt-get install -y python3 python3-venv python3-pip
    command -v dnf &>/dev/null && dnf install -y python3 python3-pip
    command -v brew &>/dev/null && brew install python3
    PYTHON_CMD="python3"
fi
VENV_PYTHON="${VENV_DIR}/bin/python"
[ ! -f "$VENV_PYTHON" ] && "$PYTHON_CMD" -m venv "$VENV_DIR"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null

# ── Step 2: Install OpenClaw ─────────────────────────────────────────────────
log "Installing OpenClaw..."
"$VENV_PYTHON" -m pip install openclaw flask requests --quiet 2>/dev/null
log "OpenClaw installed."

# ── Step 3: Copy web UI files ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="$(dirname "$SCRIPT_DIR")/common"
if [ -d "$COMMON_DIR" ]; then
    cp -r "$COMMON_DIR"/* "$INSTALL_DIR/"
    log "Web UI files copied from $COMMON_DIR"
else
    log "WARNING: Common dir not found at $COMMON_DIR"
    log "Checking alternative paths..."
    # Try to find the common dir relative to the root
    for alt in "$(dirname "$(dirname "$SCRIPT_DIR")")/OpenClaw/common" "$(dirname "$SCRIPT_DIR")/../OpenClaw/common"; do
        if [ -d "$alt" ]; then
            cp -r "$alt"/* "$INSTALL_DIR/"
            log "Files copied from $alt"
            break
        fi
    done
fi
# Verify critical files
if [ ! -f "${INSTALL_DIR}/openclaw_web.py" ]; then
    log "openclaw_web.py missing — creating minimal web server..."
    cat > "${INSTALL_DIR}/openclaw_web.py" <<'WEBEOF'
import os, json, subprocess
from flask import Flask, request, jsonify, Response
app = Flask(__name__)
@app.route("/")
def index():
    return """<!DOCTYPE html><html><head><meta charset=utf-8><title>OpenClaw</title>
    <style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}
    .c{background:#1e293b;border-radius:16px;padding:48px;max-width:600px;text-align:center;border:1px solid #334155}
    h1{font-size:32px;margin-bottom:16px;color:#f97316}p{color:#94a3b8;line-height:1.8;margin-bottom:16px}
    input{width:100%;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:8px;padding:12px;font-size:15px;margin-bottom:12px}
    button{background:#f97316;color:#fff;border:none;border-radius:8px;padding:12px 24px;font-size:15px;font-weight:700;cursor:pointer;width:100%}
    button:hover{background:#ea580c}pre{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;text-align:left;margin-top:16px;font-size:13px;white-space:pre-wrap;max-height:300px;overflow:auto;color:#94a3b8}</style></head>
    <body><div class=c><h1>OpenClaw</h1><p>AI Agent Framework</p>
    <input id=t placeholder="Describe a task..." onkeydown="if(event.key==='Enter')run()">
    <button onclick="run()">Run Task</button><pre id=o></pre>
    <script>async function run(){const t=document.getElementById('t').value;if(!t)return;document.getElementById('o').textContent='Running...';
    try{const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:t})});
    const j=await r.json();document.getElementById('o').textContent=j.output||j.error||JSON.stringify(j);}catch(e){document.getElementById('o').textContent='Error: '+e;}}</script>
    </div></body></html>"""
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "status": "healthy", "service": "openclaw"})
@app.route("/api/run", methods=["POST"])
def run_task():
    data = request.get_json(silent=True) or {}
    task = data.get("task", "")
    if not task:
        return jsonify({"ok": False, "error": "Task required"}), 400
    try:
        proc = subprocess.run(["openclaw", "run", task], capture_output=True, text=True, timeout=120)
        return jsonify({"ok": proc.returncode == 0, "output": proc.stdout, "error": proc.stderr})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "openclaw not found. Run: pip install openclaw"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
@app.route("/api/version")
def version():
    try:
        proc = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=10)
        return jsonify({"ok": True, "version": proc.stdout.strip()})
    except:
        return jsonify({"ok": False, "version": "unknown"})
WEBEOF
    log "Minimal openclaw_web.py created."
fi
if [ ! -d "${INSTALL_DIR}/web/templates" ]; then
    mkdir -p "${INSTALL_DIR}/web/templates"
fi

# ── Step 4: Skip web UI if no ports ──────────────────────────────────────────
if [ -z "${HTTP_PORT}" ] && [ -z "${HTTPS_PORT}" ]; then
    log "No ports — OpenClaw installed as CLI only."
    DISPLAY_HOST="$HOST_IP"
    [ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    cat > "$STATE_FILE" <<EOF
{"installed":true,"service_name":"${SERVICE_NAME}","install_dir":"${INSTALL_DIR}","host":"${HOST_IP}","deploy_mode":"os","running":false}
EOF
    exit 0
fi

# ── Step 5: Startup script ───────────────────────────────────────────────────
WEB_PORT="${HTTP_PORT:-${HTTPS_PORT}}"
cat > "${INSTALL_DIR}/start-openclaw-webui.py" <<PYEOF
#!/usr/bin/env python3
import os, sys, ssl, threading
WEB_PORT = int(os.environ.get("OPENCLAW_WEB_PORT", "${WEB_PORT}"))
HTTPS_PORT = os.environ.get("OPENCLAW_HTTPS_PORT", "${HTTPS_PORT}").strip()
CERT_FILE = os.environ.get("OPENCLAW_CERT_FILE", "${CERT_DIR}/openclaw.crt")
KEY_FILE = os.environ.get("OPENCLAW_KEY_FILE", "${CERT_DIR}/openclaw.key")
def run_https(app, port, cf, kf):
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cf, kf)
        from werkzeug.serving import make_server
        make_server("0.0.0.0", port, app, ssl_context=ctx, threaded=True).serve_forever()
    except Exception as e:
        print(f"HTTPS failed: {e}")
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from openclaw_web import app
    if HTTPS_PORT and HTTPS_PORT.isdigit() and os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE):
        threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), CERT_FILE, KEY_FILE), daemon=True).start()
    print(f"OpenClaw Web UI on http://0.0.0.0:{WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT)
PYEOF
chmod +x "${INSTALL_DIR}/start-openclaw-webui.py"

# ── Step 6: SSL ──────────────────────────────────────────────────────────────
if [ -n "$HTTPS_PORT" ] && [ "$HTTPS_PORT" != "0" ] && [ ! -f "${CERT_DIR}/openclaw.crt" ]; then
    CN="${DOMAIN:-$HOST_IP}"; [ "$CN" = "0.0.0.0" ] && CN="localhost"
    openssl req -x509 -nodes -newkey rsa:2048 -keyout "${CERT_DIR}/openclaw.key" -out "${CERT_DIR}/openclaw.crt" -days 3650 -subj "/CN=${CN}/O=ServerInstaller/C=US" 2>/dev/null
fi

# ── Step 7: systemd ──────────────────────────────────────────────────────────
if command -v systemctl &>/dev/null; then
    cat > "${SYSTEMD_FILE}" <<SVCEOF
[Unit]
Description=OpenClaw Web UI
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=OPENCLAW_WEB_PORT=${WEB_PORT}
Environment=OPENCLAW_HTTPS_PORT=${HTTPS_PORT}
Environment=OPENCLAW_CERT_FILE=${CERT_DIR}/openclaw.crt
Environment=OPENCLAW_KEY_FILE=${CERT_DIR}/openclaw.key
ExecStart=${VENV_PYTHON} ${INSTALL_DIR}/start-openclaw-webui.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}
[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}" 2>/dev/null || true
    systemctl restart "${SERVICE_NAME}"
    log "Web UI systemd service started."
else
    log "Starting Web UI in background on port ${WEB_PORT}..."
    export OPENCLAW_WEB_PORT="${WEB_PORT}"
    # Use Python to launch as a proper daemon (nohup fails from non-terminal)
    "${VENV_PYTHON}" -c "
import subprocess, sys, os
log = open('${LOG_FILE}', 'a')
env = dict(os.environ)
env['OPENCLAW_WEB_PORT'] = '${WEB_PORT}'
env['OPENCLAW_HTTPS_PORT'] = '${HTTPS_PORT}'
env['OPENCLAW_CERT_FILE'] = '${CERT_DIR}/openclaw.crt'
env['OPENCLAW_KEY_FILE'] = '${CERT_DIR}/openclaw.key'
p = subprocess.Popen(
    [sys.executable, '${INSTALL_DIR}/start-openclaw-webui.py'],
    cwd='${INSTALL_DIR}', env=env,
    stdout=log, stderr=log,
    start_new_session=True
)
print(f'Started PID {p.pid}')
" 2>&1
    sleep 3
    if curl -sf "http://127.0.0.1:${WEB_PORT}/api/health" >/dev/null 2>&1; then
        log "Web UI running on port ${WEB_PORT}."
    else
        log "Web UI may still be starting. Check log: ${LOG_FILE}"
        tail -5 "${LOG_FILE}" 2>/dev/null | while read line; do log "  $line"; done
    fi
fi

# ── Step 8: Firewall ────────────────────────────────────────────────────────
for port in "$HTTP_PORT" "$HTTPS_PORT"; do
    [ -z "$port" ] && continue
    command -v ufw &>/dev/null && ufw allow "$port/tcp" 2>/dev/null || true
    command -v firewall-cmd &>/dev/null && firewall-cmd --permanent --add-port="${port}/tcp" 2>/dev/null || true
done
command -v firewall-cmd &>/dev/null && firewall-cmd --reload 2>/dev/null || true

# ── Step 9: State ────────────────────────────────────────────────────────────
DISPLAY_HOST="$HOST_IP"
[ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
HTTP_URL=""; HTTPS_URL=""
[ -n "$HTTP_PORT" ] && HTTP_URL="http://${DISPLAY_HOST}:${HTTP_PORT}"
[ -n "$HTTPS_PORT" ] && HTTPS_URL="https://${DISPLAY_HOST}:${HTTPS_PORT}"

cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${SERVICE_NAME}",
    "install_dir": "${INSTALL_DIR}", "host": "${HOST_IP}", "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}", "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}", "https_url": "${HTTPS_URL}",
    "deploy_mode": "os", "running": true
}
STEOF

log ""
log "================================================================="
log " OpenClaw Installation Complete!"
log "================================================================="
[ -n "$HTTP_URL" ] && log " Web UI (HTTP):  $HTTP_URL"
[ -n "$HTTPS_URL" ] && log " Web UI (HTTPS): $HTTPS_URL"
log " CLI: openclaw --help"
log "================================================================="
