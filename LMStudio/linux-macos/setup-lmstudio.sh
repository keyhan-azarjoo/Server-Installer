#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LM Studio Installer for Linux / macOS
# ─────────────────────────────────────────────────────────────────────────────
set -eo pipefail
HOME="${HOME:-/root}"
export HOME

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

# ── Step 1: Install LM Studio ────────────────────────────────────────────────
log "Checking for LM Studio..."
OS_TYPE="$(uname -s)"
ARCH="$(uname -m)"

# Check if LM Studio app is already installed
LMSTUDIO_APP_INSTALLED=false
if [ "$OS_TYPE" = "Darwin" ]; then
    [ -d "/Applications/LM Studio.app" ] && LMSTUDIO_APP_INSTALLED=true
elif [ -f "/opt/lmstudio/lm-studio" ] || [ -f "$HOME/.local/bin/lm-studio" ]; then
    LMSTUDIO_APP_INSTALLED=true
fi
command -v lms &>/dev/null && LMSTUDIO_APP_INSTALLED=true

if [ "$LMSTUDIO_APP_INSTALLED" = "true" ]; then
    log "LM Studio already installed."
else
    log "Downloading and installing LM Studio..."
    INSTALLED_OK=false

    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS: Method 1 — brew (most reliable)
        if command -v brew &>/dev/null; then
            log "Installing via Homebrew..."
            brew install --cask lm-studio 2>&1 || true
            if [ -d "/Applications/LM Studio.app" ]; then
                log "LM Studio installed via Homebrew."
                INSTALLED_OK=true
            fi
        fi

        # macOS: Method 2 — get URL from brew API and download directly
        if [ "$INSTALLED_OK" = "false" ]; then
            log "Trying direct download..."
            # Get the real versioned URL from Homebrew API
            DMG_URL=""
            if command -v python3 &>/dev/null; then
                DMG_URL=$(curl -s "https://formulae.brew.sh/api/cask/lm-studio.json" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))" 2>/dev/null)
            fi
            if [ -z "$DMG_URL" ]; then
                # Fallback: construct URL from known pattern
                if [ "$ARCH" = "arm64" ]; then
                    DMG_URL="https://installers.lmstudio.ai/darwin/arm64/0.4.8-1/LM-Studio-0.4.8-1-arm64.dmg"
                else
                    DMG_URL="https://installers.lmstudio.ai/darwin/x64/0.4.8-1/LM-Studio-0.4.8-1-x64.dmg"
                fi
            fi
            DMG_PATH="/tmp/LMStudio.dmg"
            log "Downloading from ${DMG_URL}..."
            curl -fSL "$DMG_URL" -o "$DMG_PATH" 2>&1 || true
            if [ -f "$DMG_PATH" ] && [ "$(stat -f%z "$DMG_PATH" 2>/dev/null || stat -c%s "$DMG_PATH" 2>/dev/null)" -gt 1000000 ]; then
                log "Mounting DMG..."
                MOUNT_OUTPUT=$(hdiutil attach "$DMG_PATH" -nobrowse -noverify 2>&1)
                MOUNT_POINT=$(echo "$MOUNT_OUTPUT" | grep "/Volumes" | sed 's/.*\(\/Volumes\/.*\)/\1/' | head -1)
                if [ -n "$MOUNT_POINT" ]; then
                    log "Copying LM Studio to /Applications..."
                    # Find the .app in the mounted volume
                    APP_PATH=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" -type d | head -1)
                    if [ -n "$APP_PATH" ]; then
                        cp -R "$APP_PATH" /Applications/ 2>&1
                        log "LM Studio installed to /Applications."
                        INSTALLED_OK=true
                    fi
                    hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
                else
                    log "WARNING: Could not mount DMG. Output: $MOUNT_OUTPUT"
                fi
                rm -f "$DMG_PATH"
            else
                rm -f "$DMG_PATH" 2>/dev/null
                log "WARNING: Download failed or file too small."
            fi
        fi

        if [ "$INSTALLED_OK" = "false" ]; then
            log ""
            log "=============================================="
            log " Could not auto-install LM Studio."
            log " Please install manually:"
            log "   1. Go to https://lmstudio.ai/download"
            log "   2. Download the macOS version"
            log "   3. Open the .dmg and drag to Applications"
            log "   4. Open LM Studio and enable the local server"
            log "   5. Re-run this installer"
            log "=============================================="
        else
            # Open the app
            log "Opening LM Studio..."
            open "/Applications/LM Studio.app" 2>/dev/null || true
            sleep 5
        fi
    else
        # Linux: download AppImage via brew API
        APPIMAGE_PATH="/opt/lmstudio/lm-studio"
        mkdir -p /opt/lmstudio
        APPIMAGE_URL=""
        if command -v python3 &>/dev/null; then
            APPIMAGE_URL=$(curl -s "https://formulae.brew.sh/api/cask/lm-studio.json" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
url=d.get('url','')
# Convert mac URL to linux URL pattern
url=url.replace('/darwin/','/linux/').replace('-arm64.dmg','.AppImage').replace('-x64.dmg','.AppImage')
print(url)" 2>/dev/null)
        fi
        if [ -n "$APPIMAGE_URL" ]; then
            log "Downloading from ${APPIMAGE_URL}..."
            curl -fSL "$APPIMAGE_URL" -o "$APPIMAGE_PATH" 2>&1 || true
        fi
        if [ -f "$APPIMAGE_PATH" ] && [ "$(stat -c%s "$APPIMAGE_PATH" 2>/dev/null || echo 0)" -gt 1000000 ]; then
            chmod +x "$APPIMAGE_PATH"
            log "LM Studio installed to ${APPIMAGE_PATH}."
        else
            log "Download failed. Install manually from https://lmstudio.ai/download"
        fi
    fi
fi

# Install CLI tool
if ! command -v lms &>/dev/null; then
    if command -v npm &>/dev/null; then
        log "Installing LM Studio CLI (lms) via npm..."
        npm install -g @lmstudio/cli 2>/dev/null || true
    fi
fi

# ── Step 2: Start LM Studio server ──────────────────────────────────────────
log "Starting LM Studio server..."
if command -v lms &>/dev/null; then
    lms server start --port "${LMSTUDIO_INTERNAL_PORT}" 2>/dev/null || true
    log "LM Studio server started on port ${LMSTUDIO_INTERNAL_PORT}."
elif [ "$OS_TYPE" = "Darwin" ] && [ -d "/Applications/LM Studio.app" ]; then
    # On macOS, open the app which starts its own server
    open "/Applications/LM Studio.app" 2>/dev/null || true
    log "LM Studio app opened. Enable the local server in: LM Studio > Local Server > Start"
    sleep 3
elif [ -x "/opt/lmstudio/lm-studio" ]; then
    nohup /opt/lmstudio/lm-studio --headless --port "${LMSTUDIO_INTERNAL_PORT}" >> "${LOG_FILE}" 2>&1 &
    log "LM Studio started in headless mode."
    sleep 3
fi

# Check if LM Studio server is responding
LMSTUDIO_RUNNING=false
for check_port in "${LMSTUDIO_INTERNAL_PORT}" "1234"; do
    if curl -sf "http://127.0.0.1:${check_port}/v1/models" >/dev/null 2>&1; then
        log "LM Studio server running on port ${check_port}."
        LMSTUDIO_INTERNAL_PORT="${check_port}"
        LMSTUDIO_RUNNING=true
        break
    fi
done
if [ "$LMSTUDIO_RUNNING" = "false" ]; then
    log "WARNING: LM Studio server not responding. Open LM Studio and start the local server."
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
WEB_PORT="${HTTP_PORT}"
cat > "${INSTALL_DIR}/start-lmstudio-webui.py" <<PYEOF
#!/usr/bin/env python3
import os, sys, ssl, threading, time
LMSTUDIO_INTERNAL = "http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
HTTP_PORT_STR = os.environ.get("LMSTUDIO_WEB_PORT", "${WEB_PORT}").strip()
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
    http_port = int(HTTP_PORT_STR) if HTTP_PORT_STR and HTTP_PORT_STR.isdigit() and int(HTTP_PORT_STR) > 0 else 0
    has_https = HTTPS_PORT and HTTPS_PORT.isdigit() and int(HTTPS_PORT) > 0 and os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE)
    if has_https and http_port > 0:
        threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), CERT_FILE, KEY_FILE), daemon=True).start()
        print(f"LM Studio Web UI on http://0.0.0.0:{http_port}")
        app.run(host="0.0.0.0", port=http_port)
    elif has_https:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(CERT_FILE, KEY_FILE)
        print(f"LM Studio Web UI on https://0.0.0.0:{HTTPS_PORT} (HTTPS only)")
        app.run(host="0.0.0.0", port=int(HTTPS_PORT), ssl_context=ctx)
    elif http_port > 0:
        print(f"LM Studio Web UI on http://0.0.0.0:{http_port}")
        app.run(host="0.0.0.0", port=http_port)
    else:
        print("No HTTP or HTTPS port configured.")
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
    "${VENV_PYTHON}" -c "
import subprocess, sys, os
log = open('${LOG_FILE}', 'a')
env = dict(os.environ)
env['LMSTUDIO_API_BASE'] = 'http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}'
env['LMSTUDIO_WEB_PORT'] = '${WEB_PORT}'
env['LMSTUDIO_HTTPS_PORT'] = '${HTTPS_PORT}'
env['LMSTUDIO_CERT_FILE'] = '${CERT_DIR}/lmstudio.crt'
env['LMSTUDIO_KEY_FILE'] = '${CERT_DIR}/lmstudio.key'
p = subprocess.Popen(
    [sys.executable, '${INSTALL_DIR}/start-lmstudio-webui.py'],
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
    fi
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
