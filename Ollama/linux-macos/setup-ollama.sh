#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Ollama Installer for Linux / macOS
# Installs Ollama LLM server + Web UI on user-selected IP:Port
# ─────────────────────────────────────────────────────────────────────────────
set -eo pipefail

# Ensure HOME is set (may be empty when running via sudo)
HOME="${HOME:-/root}"
export HOME

OLLAMA_SERVICE_NAME="serverinstaller-ollama"
OLLAMA_INTERNAL_PORT="11434"  # Ollama always runs internally on this
HTTP_PORT="${OLLAMA_HTTP_PORT:-}"
HTTPS_PORT="${OLLAMA_HTTPS_PORT:-}"
HOST_IP="${OLLAMA_HOST_IP:-0.0.0.0}"
DOMAIN="${OLLAMA_DOMAIN:-}"
USERNAME="${OLLAMA_USERNAME:-}"
PASSWORD="${OLLAMA_PASSWORD:-}"

BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/ollama"
STATE_FILE="${STATE_DIR}/ollama-state.json"
INSTALL_DIR="${STATE_DIR}/app"
VENV_DIR="${INSTALL_DIR}/venv"
CERT_DIR="${STATE_DIR}/certs"
LOG_FILE="${STATE_DIR}/ollama.log"

SYSTEMD_FILE="/etc/systemd/system/${OLLAMA_SERVICE_NAME}.service"
SYSTEMD_WEBUI_FILE="/etc/systemd/system/${OLLAMA_SERVICE_NAME}-webui.service"
NGINX_CONF="/etc/nginx/conf.d/${OLLAMA_SERVICE_NAME}.conf"

log() { echo "[Ollama] $*"; }

mkdir -p "$STATE_DIR" "$INSTALL_DIR" "$CERT_DIR"

# ── Step 1: Install Ollama ───────────────────────────────────────────────────
log "Checking for Ollama..."
if command -v ollama &>/dev/null; then
    log "Ollama already installed: $(command -v ollama)"
else
    log "Installing Ollama..."
    # The official install script may return non-zero on macOS even when successful
    curl -fsSL https://ollama.com/install.sh | sh || true
    # macOS: ollama may be in /usr/local/bin or installed as an app
    if ! command -v ollama &>/dev/null; then
        # Check common macOS paths
        for p in /usr/local/bin/ollama /opt/homebrew/bin/ollama "$HOME/.ollama/bin/ollama"; do
            if [ -x "$p" ]; then
                export PATH="$(dirname "$p"):$PATH"
                break
            fi
        done
    fi
    if command -v ollama &>/dev/null; then
        log "Ollama installed: $(command -v ollama)"
    else
        log "WARNING: Ollama binary not found in PATH after install."
        log "If Ollama was installed as an app, open it once to enable the CLI."
        log "Continuing with web UI setup..."
    fi
fi

# ── Step 2: Start Ollama on internal port ────────────────────────────────────
log "Configuring Ollama on internal port ${OLLAMA_INTERNAL_PORT}..."
if command -v systemctl &>/dev/null; then
    cat > "${SYSTEMD_FILE}" <<SVCEOF
[Unit]
Description=Ollama LLM Server
After=network-online.target

[Service]
Type=simple
User=root
Environment=OLLAMA_HOST=127.0.0.1:${OLLAMA_INTERNAL_PORT}
Environment=OLLAMA_ORIGINS=*
ExecStart=$(command -v ollama) serve
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable "${OLLAMA_SERVICE_NAME}" 2>/dev/null || true
    systemctl restart "${OLLAMA_SERVICE_NAME}"
    log "Ollama systemd service started on 127.0.0.1:${OLLAMA_INTERNAL_PORT}"
else
    # macOS or no systemd — start Ollama in background
    export OLLAMA_HOST="127.0.0.1:${OLLAMA_INTERNAL_PORT}"
    export OLLAMA_ORIGINS="*"
    if command -v ollama &>/dev/null; then
        ollama serve >> "$LOG_FILE" 2>&1 &
        disown 2>/dev/null || true
        log "Ollama started in background."
    else
        # On macOS, Ollama app may already be running its own server on 11434
        log "Ollama CLI not in PATH. Checking if Ollama app server is running..."
    fi
fi
sleep 3

# Verify — check both configured port and default 11434
OLLAMA_RUNNING=false
for check_port in "${OLLAMA_INTERNAL_PORT}" "11434"; do
    if curl -sf "http://127.0.0.1:${check_port}/api/tags" >/dev/null 2>&1; then
        log "Ollama is running on port ${check_port}."
        OLLAMA_INTERNAL_PORT="${check_port}"
        OLLAMA_RUNNING=true
        break
    fi
done
if [ "$OLLAMA_RUNNING" = "false" ]; then
    # Wait more and retry
    for i in $(seq 1 10); do
        if curl -sf "http://127.0.0.1:${OLLAMA_INTERNAL_PORT}/api/tags" >/dev/null 2>&1; then
            log "Ollama is running."
            OLLAMA_RUNNING=true
            break
        fi
        if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
            log "Ollama is running on default port 11434."
            OLLAMA_INTERNAL_PORT="11434"
            OLLAMA_RUNNING=true
            break
        fi
        [ "$i" -eq 10 ] && log "WARNING: Ollama not responding. Start it manually: open /Applications/Ollama.app or run 'ollama serve'"
        sleep 2
    done
fi

# ── Step 3: Skip web UI if no ports ──────────────────────────────────────────
if [ -z "${HTTP_PORT}" ] && [ -z "${HTTPS_PORT}" ]; then
    log "No HTTP/HTTPS ports — skipping web UI."
    DISPLAY_HOST="$HOST_IP"
    [ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${OLLAMA_SERVICE_NAME}",
    "install_dir": "${INSTALL_DIR}", "host": "${HOST_IP}",
    "http_port": "${OLLAMA_INTERNAL_PORT}",
    "http_url": "http://${DISPLAY_HOST}:${OLLAMA_INTERNAL_PORT}",
    "deploy_mode": "os", "running": true
}
STEOF
    log "Ollama API: http://${DISPLAY_HOST}:${OLLAMA_INTERNAL_PORT}"
    exit 0
fi

# ── Step 4: Resolve Python ───────────────────────────────────────────────────
log "Resolving Python..."
PYTHON_CMD=""
for py in python3 python; do
    if command -v "$py" &>/dev/null && "$py" --version 2>&1 | grep -q "Python 3"; then
        PYTHON_CMD="$py"
        break
    fi
done
if [ -z "$PYTHON_CMD" ]; then
    log "Installing Python 3..."
    if command -v apt-get &>/dev/null; then
        apt-get update -y && apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf &>/dev/null; then
        dnf install -y python3 python3-pip
    elif command -v brew &>/dev/null; then
        brew install python3
    fi
    PYTHON_CMD="python3"
fi

# ── Step 5: Setup venv + copy files ──────────────────────────────────────────
VENV_PYTHON="${VENV_DIR}/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi
"$VENV_PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null
"$VENV_PYTHON" -m pip install flask requests --quiet 2>/dev/null

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="$(dirname "$SCRIPT_DIR")/common"
if [ -d "$COMMON_DIR" ]; then
    cp -r "$COMMON_DIR"/* "$INSTALL_DIR/"
fi

# ── Step 6: Startup script ───────────────────────────────────────────────────
WEB_PORT="${HTTP_PORT:-${HTTPS_PORT}}"
cat > "${INSTALL_DIR}/start-ollama-webui.py" <<PYEOF
#!/usr/bin/env python3
import os, sys, ssl, subprocess, threading, time

OLLAMA_INTERNAL = "http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
WEB_PORT = int(os.environ.get("OLLAMA_WEB_PORT", "${WEB_PORT}"))
HTTPS_PORT = os.environ.get("OLLAMA_HTTPS_PORT", "${HTTPS_PORT}").strip()
CERT_FILE = os.environ.get("OLLAMA_CERT_FILE", "${CERT_DIR}/ollama.crt")
KEY_FILE = os.environ.get("OLLAMA_KEY_FILE", "${CERT_DIR}/ollama.key")

def ensure_ollama():
    try:
        import urllib.request
        urllib.request.urlopen(OLLAMA_INTERNAL + "/api/tags", timeout=3)
    except Exception:
        print("[Startup] Starting Ollama...")
        env = dict(os.environ)
        env["OLLAMA_HOST"] = "127.0.0.1:${OLLAMA_INTERNAL_PORT}"
        subprocess.Popen(["ollama", "serve"], env=env, stdout=open(os.devnull,"w"), stderr=open(os.devnull,"w"))
        time.sleep(5)

def run_https(app, port, certfile, keyfile):
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile, keyfile)
        from werkzeug.serving import make_server
        server = make_server("0.0.0.0", port, app, ssl_context=ctx, threaded=True)
        print(f"Ollama HTTPS on https://0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"HTTPS failed: {e}")

if __name__ == "__main__":
    ensure_ollama()
    os.environ["OLLAMA_API_BASE"] = OLLAMA_INTERNAL
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ollama_web import app
    if HTTPS_PORT and HTTPS_PORT.isdigit() and os.path.isfile(CERT_FILE) and os.path.isfile(KEY_FILE):
        t = threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), CERT_FILE, KEY_FILE), daemon=True)
        t.start()
    print(f"Ollama Web UI on http://0.0.0.0:{WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT)
PYEOF
chmod +x "${INSTALL_DIR}/start-ollama-webui.py"

# ── Step 7: SSL certificate ──────────────────────────────────────────────────
if [ -n "$HTTPS_PORT" ] && [ "$HTTPS_PORT" != "0" ]; then
    CERT_FILE="${CERT_DIR}/ollama.crt"
    KEY_FILE="${CERT_DIR}/ollama.key"
    if [ ! -f "$CERT_FILE" ]; then
        log "Generating SSL certificate..."
        CN="${DOMAIN:-$HOST_IP}"
        [ "$CN" = "0.0.0.0" ] && CN="localhost"
        openssl req -x509 -nodes -newkey rsa:2048 -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -days 3650 -subj "/CN=${CN}/O=ServerInstaller/C=US" 2>/dev/null
    fi
    # Nginx HTTPS proxy
    if command -v nginx &>/dev/null; then
        cat > "$NGINX_CONF" <<NGXEOF
server {
    listen ${HTTPS_PORT} ssl;
    server_name ${DOMAIN:-_};
    ssl_certificate ${CERT_FILE};
    ssl_certificate_key ${KEY_FILE};
    client_max_body_size 500m;
    proxy_read_timeout 600;
    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
    }
}
NGXEOF
        nginx -t 2>/dev/null && (systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null) || true
    fi
fi

# ── Step 8: Register and start Web UI service ────────────────────────────────
export OLLAMA_API_BASE="http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
export OLLAMA_WEB_PORT="${WEB_PORT}"
export OLLAMA_HTTPS_PORT="${HTTPS_PORT}"
export OLLAMA_CERT_FILE="${CERT_DIR}/ollama.crt"
export OLLAMA_KEY_FILE="${CERT_DIR}/ollama.key"

if command -v systemctl &>/dev/null; then
    cat > "${SYSTEMD_WEBUI_FILE}" <<WUIEOF
[Unit]
Description=Ollama Web UI
After=network.target ${OLLAMA_SERVICE_NAME}.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=OLLAMA_API_BASE=http://127.0.0.1:${OLLAMA_INTERNAL_PORT}
Environment=OLLAMA_WEB_PORT=${WEB_PORT}
Environment=OLLAMA_HTTPS_PORT=${HTTPS_PORT}
Environment=OLLAMA_CERT_FILE=${CERT_DIR}/ollama.crt
Environment=OLLAMA_KEY_FILE=${CERT_DIR}/ollama.key
ExecStart=${VENV_PYTHON} ${INSTALL_DIR}/start-ollama-webui.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
WUIEOF
    systemctl daemon-reload
    systemctl enable "${OLLAMA_SERVICE_NAME}-webui" 2>/dev/null || true
    systemctl restart "${OLLAMA_SERVICE_NAME}-webui"
    log "Web UI systemd service started."
else
    # macOS or no systemd — use Python to launch as daemon
    log "Starting Web UI in background on port ${WEB_PORT}..."
    "${VENV_PYTHON}" -c "
import subprocess, sys, os
log = open('${LOG_FILE}', 'a')
env = dict(os.environ)
env['OLLAMA_API_BASE'] = 'http://127.0.0.1:${OLLAMA_INTERNAL_PORT}'
env['OLLAMA_WEB_PORT'] = '${WEB_PORT}'
env['OLLAMA_HTTPS_PORT'] = '${HTTPS_PORT}'
env['OLLAMA_CERT_FILE'] = '${CERT_DIR}/ollama.crt'
env['OLLAMA_KEY_FILE'] = '${CERT_DIR}/ollama.key'
p = subprocess.Popen(
    [sys.executable, '${INSTALL_DIR}/start-ollama-webui.py'],
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

# ── Step 9: Firewall ─────────────────────────────────────────────────────────
for port in "$HTTP_PORT" "$HTTPS_PORT"; do
    [ -z "$port" ] && continue
    if command -v ufw &>/dev/null; then
        ufw allow "$port/tcp" 2>/dev/null || true
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port="${port}/tcp" 2>/dev/null || true
    fi
done
command -v firewall-cmd &>/dev/null && firewall-cmd --reload 2>/dev/null || true

# ── Step 10: Save state ──────────────────────────────────────────────────────
DISPLAY_HOST="$HOST_IP"
if [ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ]; then
    DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
fi

HTTP_URL=""
HTTPS_URL=""
[ -n "$HTTP_PORT" ] && HTTP_URL="http://${DISPLAY_HOST}:${HTTP_PORT}"
[ -n "$HTTPS_PORT" ] && HTTPS_URL="https://${DISPLAY_HOST}:${HTTPS_PORT}"

OLLAMA_VERSION=$(ollama --version 2>/dev/null | sed 's/ollama version //' || echo "")

cat > "$STATE_FILE" <<STEOF
{
    "installed": true,
    "service_name": "${OLLAMA_SERVICE_NAME}",
    "install_dir": "${INSTALL_DIR}",
    "host": "${HOST_IP}",
    "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}",
    "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}",
    "https_url": "${HTTPS_URL}",
    "deploy_mode": "os",
    "auth_enabled": $([ -n "$USERNAME" ] && echo "true" || echo "false"),
    "auth_username": "${USERNAME}",
    "running": true,
    "version": "${OLLAMA_VERSION}",
    "ollama_internal": "http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
}
STEOF

log ""
log "================================================================="
log " Ollama Installation Complete!"
log "================================================================="
[ -n "$HTTP_URL" ] && log " Web UI (HTTP):  $HTTP_URL"
[ -n "$HTTPS_URL" ] && log " Web UI (HTTPS): $HTTPS_URL"
log " Ollama API:     http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
log "================================================================="
