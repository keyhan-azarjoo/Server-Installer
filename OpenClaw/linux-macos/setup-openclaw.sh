#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Linux / macOS
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

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
[ -d "$COMMON_DIR" ] && cp -r "$COMMON_DIR"/* "$INSTALL_DIR/"

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
