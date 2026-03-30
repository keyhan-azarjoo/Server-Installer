#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Linux / macOS
# Follows: https://mer.vin/2026/02/openclaw-remote-server-setup/
# ─────────────────────────────────────────────────────────────────────────────
set -eo pipefail
HOME="${HOME:-/root}"
export HOME

SERVICE_NAME="serverinstaller-openclaw"
GATEWAY_SERVICE="clawdbot-gateway"
HTTP_PORT="${OPENCLAW_HTTP_PORT:-18789}"
HTTPS_PORT="${OPENCLAW_HTTPS_PORT:-}"
HOST_IP="${OPENCLAW_HOST_IP:-0.0.0.0}"
DOMAIN="${OPENCLAW_DOMAIN:-}"
USERNAME="${OPENCLAW_USERNAME:-}"
PASSWORD="${OPENCLAW_PASSWORD:-}"

BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/openclaw"
STATE_FILE="${STATE_DIR}/openclaw-state.json"
LOG_FILE="${STATE_DIR}/openclaw.log"

OPENCLAW_USER="openclaw"
OPENCLAW_HOME="/home/${OPENCLAW_USER}"
NPM_GLOBAL="${OPENCLAW_HOME}/.npm-global"
OPENCLAW_BIN="${NPM_GLOBAL}/bin/openclaw"

log() { echo "[OpenClaw] $*"; }
mkdir -p "$STATE_DIR"

# Determine bind mode
if [ "$HOST_IP" = "0.0.0.0" ] || [ "$HOST_IP" = "*" ] || [ -z "$HOST_IP" ]; then
    BIND_ARG="--bind any"
else
    BIND_ARG="--bind loopback"
fi

# ── Step 1: Create dedicated user ───────────────────────────────────────────
log "Step 1: Creating openclaw user..."
if id "$OPENCLAW_USER" &>/dev/null; then
    log "User $OPENCLAW_USER already exists."
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS — use current user, skip user creation
        OPENCLAW_USER="$(whoami)"
        OPENCLAW_HOME="$HOME"
        NPM_GLOBAL="${OPENCLAW_HOME}/.npm-global"
        OPENCLAW_BIN="${NPM_GLOBAL}/bin/openclaw"
        log "macOS — using current user: $OPENCLAW_USER"
    else
        adduser --disabled-password --gecos "" "$OPENCLAW_USER" 2>/dev/null || useradd -m "$OPENCLAW_USER" 2>/dev/null || true
        usermod -aG sudo "$OPENCLAW_USER" 2>/dev/null || true
        echo "${OPENCLAW_USER} ALL=(ALL) NOPASSWD: ALL" > "/etc/sudoers.d/${OPENCLAW_USER}" 2>/dev/null || true
        chmod 440 "/etc/sudoers.d/${OPENCLAW_USER}" 2>/dev/null || true
        log "User $OPENCLAW_USER created."
    fi
fi

# ── Step 2: Install required packages ────────────────────────────────────────
log "Step 2: Installing Node.js & build tools..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if ! command -v node &>/dev/null || [ "$(node --version | sed 's/v//' | cut -d. -f1)" -lt 22 ] 2>/dev/null; then
        if command -v brew &>/dev/null; then
            brew install node@22 2>/dev/null || brew install node 2>/dev/null || true
        else
            log "Install Node.js 22+ from https://nodejs.org/"
        fi
    fi
else
    # Linux
    if ! command -v node &>/dev/null || [ "$(node --version | sed 's/v//' | cut -d. -f1)" -lt 22 ] 2>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>&1 || true
        if command -v apt-get &>/dev/null; then
            apt-get install -y nodejs build-essential python3 2>&1
        elif command -v dnf &>/dev/null; then
            dnf install -y nodejs python3 gcc-c++ make 2>&1
        elif command -v yum &>/dev/null; then
            yum install -y nodejs python3 gcc-c++ make 2>&1
        fi
    fi
fi
log "Node.js: $(node --version 2>/dev/null || echo 'not found')"

# ── Step 3a: Install OpenClaw ────────────────────────────────────────────────
log "Step 3a: Installing OpenClaw..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS — install as current user
    mkdir -p "$NPM_GLOBAL"
    npm config set prefix "$NPM_GLOBAL" 2>/dev/null || true
    export PATH="$NPM_GLOBAL/bin:$PATH"
    npm install -g openclaw@latest 2>&1
else
    # Linux — install as openclaw user
    su - "$OPENCLAW_USER" -c "npm config set prefix ~/.npm-global && npm install -g openclaw@latest" 2>&1
    su - "$OPENCLAW_USER" -c 'grep -q npm-global ~/.bashrc 2>/dev/null || echo "export PATH=\"\$HOME/.npm-global/bin:\$PATH\"" >> ~/.bashrc'
fi

# Verify
if [ -x "$OPENCLAW_BIN" ]; then
    log "OpenClaw installed: $OPENCLAW_BIN"
    log "Version: $("$OPENCLAW_BIN" --version 2>/dev/null || echo 'unknown')"
else
    log "ERROR: OpenClaw binary not found at $OPENCLAW_BIN"
    # Try to find it
    for p in "$(which openclaw 2>/dev/null)" "${HOME}/.npm-global/bin/openclaw" "/usr/local/bin/openclaw"; do
        if [ -x "$p" ] 2>/dev/null; then
            OPENCLAW_BIN="$p"
            log "Found at: $OPENCLAW_BIN"
            break
        fi
    done
    if [ ! -x "$OPENCLAW_BIN" ]; then
        log "FATAL: Cannot find openclaw binary. Install manually: npm install -g openclaw@latest"
        exit 1
    fi
fi

# ── Step 3b: Create systemd service ─────────────────────────────────────────
log "Step 3b: Creating systemd service..."
if command -v systemctl &>/dev/null; then
    cat > "/etc/systemd/system/${GATEWAY_SERVICE}.service" <<SVCEOF
[Unit]
Description=Clawdbot Gateway (always-on)
After=network-online.target
Wants=network-online.target

[Service]
User=${OPENCLAW_USER}
WorkingDirectory=${OPENCLAW_HOME}
Environment=PATH=/usr/bin:/bin:${NPM_GLOBAL}/bin:/usr/local/bin
ExecStart=${OPENCLAW_BIN} gateway ${BIND_ARG} --port ${HTTP_PORT} --verbose
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
SVCEOF
    # Alias for our naming convention
    ln -sf "/etc/systemd/system/${GATEWAY_SERVICE}.service" "/etc/systemd/system/${SERVICE_NAME}.service" 2>/dev/null || true
    log "Systemd service created."
fi

# ── Step 3c: Configure OpenClaw (onboard) ────────────────────────────────────
log "Step 3c: Running OpenClaw onboarding..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    "$OPENCLAW_BIN" onboard 2>&1 || log "Onboarding may need manual completion."
else
    su - "$OPENCLAW_USER" -c "'$OPENCLAW_BIN' onboard" 2>&1 || log "Onboarding may need manual completion."
fi

# ── Step 3d: Enable & start service ──────────────────────────────────────────
log "Step 3d: Enabling & starting gateway service..."
if command -v systemctl &>/dev/null; then
    systemctl daemon-reload
    systemctl enable "${GATEWAY_SERVICE}.service" 2>/dev/null || true
    systemctl start "${GATEWAY_SERVICE}.service"
    sleep 3
    systemctl status "${GATEWAY_SERVICE}.service" --no-pager 2>&1 || true
else
    # macOS — run in background
    log "Starting gateway in background (macOS)..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        "$OPENCLAW_BIN" gateway $BIND_ARG --port "$HTTP_PORT" --verbose >> "$LOG_FILE" 2>&1 &
        log "Gateway started (PID $!)."
        sleep 3
    fi
fi

# ── Step 4a: Install Ollama & configure model ────────────────────────────────
log "Step 4a: Installing Ollama & configuring model..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh 2>&1 || true
fi
if command -v ollama &>/dev/null; then
    log "Ollama installed."
    log "Pulling model (llama3.2:3b)..."
    ollama pull llama3.2:3b 2>&1 || true

    # Stop gateway to configure model
    if command -v systemctl &>/dev/null; then
        systemctl stop "${GATEWAY_SERVICE}.service" 2>/dev/null || true
    fi
    mkdir -p /tmp/ollama-backups && chmod 1777 /tmp/ollama-backups 2>/dev/null || true

    # Configure OpenClaw to use the Ollama model
    OLLAMA_MODEL=$(ollama list 2>/dev/null | grep -v "^NAME" | head -1 | awk '{print $1}')
    if [ -n "$OLLAMA_MODEL" ]; then
        log "Configuring OpenClaw with model: $OLLAMA_MODEL"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            "$OPENCLAW_BIN" launch openclaw --model "$OLLAMA_MODEL" --config 2>&1 || \
            "$OPENCLAW_BIN" models add ollama "$OLLAMA_MODEL" 2>&1 || \
            log "Model config may need manual setup in dashboard."
        else
            su - "$OPENCLAW_USER" -c "ollama launch openclaw --model '$OLLAMA_MODEL' --config" 2>&1 || \
            su - "$OPENCLAW_USER" -c "'$OPENCLAW_BIN' launch openclaw --model '$OLLAMA_MODEL' --config" 2>&1 || \
            log "Model config may need manual setup in dashboard."
        fi
    fi
else
    log "WARNING: Ollama not installed."
fi

# ── Step 4b: Start gateway & get dashboard URL ──────────────────────────────
log "Step 4b: Starting gateway & getting dashboard URL..."
if command -v systemctl &>/dev/null; then
    systemctl start "${GATEWAY_SERVICE}.service"
    sleep 3
    systemctl status "${GATEWAY_SERVICE}.service" --no-pager 2>&1 || true
fi

DASHBOARD_URL=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    DASHBOARD_OUTPUT=$("$OPENCLAW_BIN" dashboard --no-open 2>&1 || echo "")
else
    DASHBOARD_OUTPUT=$(su - "$OPENCLAW_USER" -c "'$OPENCLAW_BIN' dashboard --no-open" 2>&1 || echo "")
fi
if echo "$DASHBOARD_OUTPUT" | grep -qoE 'https?://'; then
    DASHBOARD_URL=$(echo "$DASHBOARD_OUTPUT" | grep -oE 'https?://[^ ]+' | head -1)
    log "Dashboard URL: $DASHBOARD_URL"
else
    DASHBOARD_URL="http://127.0.0.1:${HTTP_PORT}"
    log "Dashboard: $DASHBOARD_URL (default)"
fi

# ── Step 5: Firewall ────────────────────────────────────────────────────────
for port in "$HTTP_PORT" "$HTTPS_PORT"; do
    [ -z "$port" ] && continue
    command -v ufw &>/dev/null && ufw allow "$port/tcp" 2>/dev/null || true
    command -v firewall-cmd &>/dev/null && firewall-cmd --permanent --add-port="${port}/tcp" 2>/dev/null || true
done
command -v firewall-cmd &>/dev/null && firewall-cmd --reload 2>/dev/null || true

# ── Step 6: State file ──────────────────────────────────────────────────────
DISPLAY_HOST="$HOST_IP"
[ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
HTTP_URL="http://${DISPLAY_HOST}:${HTTP_PORT}"
HTTPS_URL=""
[ -n "$HTTPS_PORT" ] && HTTPS_URL="https://${DISPLAY_HOST}:${HTTPS_PORT}"

cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${SERVICE_NAME}",
    "install_dir": "${OPENCLAW_HOME}", "host": "${HOST_IP}", "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}", "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}", "https_url": "${HTTPS_URL}",
    "deploy_mode": "os", "running": true,
    "openclaw_bin": "${OPENCLAW_BIN}",
    "gateway_port": "${HTTP_PORT}",
    "dashboard_url": "${DASHBOARD_URL}",
    "auth_enabled": $([ -n "$USERNAME" ] && echo "true" || echo "false"),
    "auth_username": "${USERNAME}"
}
STEOF

log ""
log "================================================================="
log " OpenClaw Installation Complete!"
log "================================================================="
log " Dashboard:      ${HTTP_URL}"
[ -n "$DASHBOARD_URL" ] && [ "$DASHBOARD_URL" != "$HTTP_URL" ] && log " Local:          ${DASHBOARD_URL}"
[ -n "$HTTPS_URL" ] && log " HTTPS:          ${HTTPS_URL}"
log " Gateway:        ws://${DISPLAY_HOST}:${HTTP_PORT}"
log " CLI:            ${OPENCLAW_BIN} --help"
log ""
log " To access remotely via SSH tunnel:"
log "   ssh -N -L ${HTTP_PORT}:127.0.0.1:${HTTP_PORT} ${OPENCLAW_USER}@${DISPLAY_HOST}"
log ""
log " Features: 20+ messaging channels, browser automation,"
log "   code execution, file management, persistent memory"
log "================================================================="
