#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LM Studio Installer for Linux / macOS
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

LMSTUDIO_SERVICE_NAME="serverinstaller-lmstudio"
LMSTUDIO_INTERNAL_PORT="1234"
HTTP_PORT="${LMSTUDIO_HTTP_PORT:-}"
HTTPS_PORT="${LMSTUDIO_HTTPS_PORT:-}"
HOST_IP="${LMSTUDIO_HOST_IP:-0.0.0.0}"
DOMAIN="${LMSTUDIO_DOMAIN:-}"
USERNAME="${LMSTUDIO_USERNAME:-}"
PASSWORD="${LMSTUDIO_PASSWORD:-}"

BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/lmstudio"
STATE_FILE="${STATE_DIR}/lmstudio-state.json"
INSTALL_DIR="${STATE_DIR}/app"
VENV_DIR="${INSTALL_DIR}/venv"
CERT_DIR="${STATE_DIR}/certs"
LOG_FILE="${STATE_DIR}/lmstudio.log"
SYSTEMD_FILE="/etc/systemd/system/${LMSTUDIO_SERVICE_NAME}-webui.service"

log() { echo "[LM Studio] $*"; }
mkdir -p "$STATE_DIR" "$INSTALL_DIR" "$CERT_DIR"

# ── Step 1: Check/Install LM Studio CLI ─────────────────────────────────────
log "Checking for LM Studio CLI (lms)..."
if command -v lms &>/dev/null; then
    log "lms CLI found: $(command -v lms)"
else
    log "lms CLI not found. Trying npm install..."
    if command -v npm &>/dev/null; then
        npm install -g @lmstudio/cli 2>/dev/null || true
    fi
    if ! command -v lms &>/dev/null; then
        log "LM Studio CLI not available."
        log "Install LM Studio from https://lmstudio.ai/download"
        log "Then: LM Studio > Settings > Enable CLI"
        log "Continuing with web UI setup..."
    fi
fi

# ── Step 2: Start LM Studio server ──────────────────────────────────────────
if command -v lms &>/dev/null; then
    log "Starting LM Studio server on port ${LMSTUDIO_INTERNAL_PORT}..."
    lms server start --port "${LMSTUDIO_INTERNAL_PORT}" 2>/dev/null || true
fi

# ── Step 3: Skip web UI if no ports ──────────────────────────────────────────
if [ -z "${HTTP_PORT}" ] && [ -z "${HTTPS_PORT}" ]; then
    log "No ports configured — skipping web UI."
    DISPLAY_HOST="$HOST_IP"
    [ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    cat > "$STATE_FILE" <<EOF
{"installed":true,"service_name":"${LMSTUDIO_SERVICE_NAME}","install_dir":"${INSTALL_DIR}","host":"${HOST_IP}","http_port":"${LMSTUDIO_INTERNAL_PORT}","http_url":"http://${DISPLAY_HOST}:${LMSTUDIO_INTERNAL_PORT}","deploy_mode":"os","running":true}
EOF
    exit 0
fi

# ── Step 4: Python + venv ────────────────────────────────────────────────────
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
"$VENV_PYTHON" -m pip install flask requests --quiet 2>/dev/null

# ── Step 5: Copy files ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="$(dirname "$SCRIPT_DIR")/common"
[ -d "$COMMON_DIR" ] && cp -r "$COMMON_DIR"/* "$INSTALL_DIR/"

# ── Step 6: Startup script ───────────────────────────────────────────────────
WEB_PORT="${HTTP_PORT:-${HTTPS_PORT}}"
cat > "${INSTALL_DIR}/start-lmstudio-webui.py" <<PYEOF
#!/usr/bin/env python3
import os, sys, ssl, threading, time
LMSTUDIO_INTERNAL = "http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
WEB_PORT = int(os.environ.get("LMSTUDIO_WEB_PORT", "${WEB_PORT}"))
HTTPS_PORT = os.environ.get("LMSTUDIO_HTTPS_PORT", "${HTTPS_PORT}").strip()
CERT_FILE = os.environ.get("LMSTUDIO_CERT_FILE", "${CERT_DIR}/lmstudio.crt")
KEY_FILE = os.environ.get("LMSTUDIO_KEY_FILE", "${CERT_DIR}/lmstudio.key")
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
    os.environ["LMSTUDIO_API_BASE"] = LMSTUDIO_INTERNAL
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lmstudio_web import app
    if HTTPS_PORT and HTTPS_PORT.isdigit() and os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE):
        threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), CERT_FILE, KEY_FILE), daemon=True).start()
    print(f"LM Studio Web UI on http://0.0.0.0:{WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT)
PYEOF
chmod +x "${INSTALL_DIR}/start-lmstudio-webui.py"

# ── Step 7: SSL ──────────────────────────────────────────────────────────────
if [ -n "$HTTPS_PORT" ] && [ "$HTTPS_PORT" != "0" ] && [ ! -f "${CERT_DIR}/lmstudio.crt" ]; then
    CN="${DOMAIN:-$HOST_IP}"; [ "$CN" = "0.0.0.0" ] && CN="localhost"
    openssl req -x509 -nodes -newkey rsa:2048 -keyout "${CERT_DIR}/lmstudio.key" -out "${CERT_DIR}/lmstudio.crt" -days 3650 -subj "/CN=${CN}/O=ServerInstaller/C=US" 2>/dev/null
fi

# ── Step 8: systemd service ──────────────────────────────────────────────────
if command -v systemctl &>/dev/null; then
    cat > "${SYSTEMD_FILE}" <<SVCEOF
[Unit]
Description=LM Studio Web UI
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=LMSTUDIO_API_BASE=http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}
Environment=LMSTUDIO_WEB_PORT=${WEB_PORT}
Environment=LMSTUDIO_HTTPS_PORT=${HTTPS_PORT}
Environment=LMSTUDIO_CERT_FILE=${CERT_DIR}/lmstudio.crt
Environment=LMSTUDIO_KEY_FILE=${CERT_DIR}/lmstudio.key
ExecStart=${VENV_PYTHON} ${INSTALL_DIR}/start-lmstudio-webui.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}
[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable "${LMSTUDIO_SERVICE_NAME}-webui" 2>/dev/null || true
    systemctl restart "${LMSTUDIO_SERVICE_NAME}-webui"
    log "Web UI systemd service started."
else
    log "Starting Web UI in background on port ${WEB_PORT}..."
    export LMSTUDIO_API_BASE="http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
    export LMSTUDIO_WEB_PORT="${WEB_PORT}"
    nohup "${VENV_PYTHON}" "${INSTALL_DIR}/start-lmstudio-webui.py" >> "${LOG_FILE}" 2>&1 &
    log "Web UI started (PID: $!)."
fi

# ── Step 9: Firewall ────────────────────────────────────────────────────────
for port in "$HTTP_PORT" "$HTTPS_PORT"; do
    [ -z "$port" ] && continue
    command -v ufw &>/dev/null && ufw allow "$port/tcp" 2>/dev/null || true
    command -v firewall-cmd &>/dev/null && firewall-cmd --permanent --add-port="${port}/tcp" 2>/dev/null || true
done
command -v firewall-cmd &>/dev/null && firewall-cmd --reload 2>/dev/null || true

# ── Step 10: State ───────────────────────────────────────────────────────────
DISPLAY_HOST="$HOST_IP"
[ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
HTTP_URL=""; HTTPS_URL=""
[ -n "$HTTP_PORT" ] && HTTP_URL="http://${DISPLAY_HOST}:${HTTP_PORT}"
[ -n "$HTTPS_PORT" ] && HTTPS_URL="https://${DISPLAY_HOST}:${HTTPS_PORT}"

cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${LMSTUDIO_SERVICE_NAME}",
    "install_dir": "${INSTALL_DIR}", "host": "${HOST_IP}", "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}", "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}", "https_url": "${HTTPS_URL}",
    "deploy_mode": "os", "running": true,
    "lmstudio_internal": "http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
}
STEOF

log ""
log "================================================================="
log " LM Studio Installation Complete!"
log "================================================================="
[ -n "$HTTP_URL" ] && log " Web UI (HTTP):  $HTTP_URL"
[ -n "$HTTPS_URL" ] && log " Web UI (HTTPS): $HTTPS_URL"
log " LM Studio API:  http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
log "================================================================="
