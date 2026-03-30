#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Linux / macOS
# Based on: https://mer.vin/2026/02/openclaw-remote-server-setup/
# Installs OpenClaw AI Agent platform with Ollama local LLM backend
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
BIND_MODE="${OPENCLAW_BIND:-any}"  # "loopback" or "any"

BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/openclaw"
STATE_FILE="${STATE_DIR}/openclaw-state.json"
INSTALL_DIR="${STATE_DIR}/app"
LOG_FILE="${STATE_DIR}/openclaw.log"

log() { echo "[OpenClaw] $*"; }
mkdir -p "$STATE_DIR" "$INSTALL_DIR"

# ── Step 1: Install Node.js 22+ ─────────────────────────────────────────────
log "Step 1: Checking Node.js..."
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VER=$(node --version 2>/dev/null | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "${NODE_MAJOR:-0}" -ge 22 ] 2>/dev/null; then
        NODE_OK=true
        log "Node.js v$NODE_VER found."
    else
        log "Node.js v$NODE_VER found but need v22+."
    fi
fi

if [ "$NODE_OK" = false ]; then
    log "Installing Node.js 22..."
    if command -v apt-get &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash - 2>&1 || true
        apt-get install -y nodejs build-essential python3 2>&1 || true
    elif command -v dnf &>/dev/null; then
        curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - 2>&1 || true
        dnf install -y nodejs python3 gcc-c++ make 2>&1 || true
    elif command -v yum &>/dev/null; then
        curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - 2>&1 || true
        yum install -y nodejs python3 gcc-c++ make 2>&1 || true
    elif command -v brew &>/dev/null; then
        brew install node@22 2>/dev/null || brew install node 2>/dev/null || true
    fi
    if command -v node &>/dev/null; then
        log "Node.js $(node --version) installed."
    else
        log "ERROR: Could not install Node.js. Install Node.js 22+ from https://nodejs.org/"
        exit 1
    fi
fi

# ── Step 2: Install OpenClaw via npm ─────────────────────────────────────────
log "Step 2: Installing OpenClaw..."
# Set npm global prefix to avoid permission issues
NPM_GLOBAL="${HOME}/.npm-global"
mkdir -p "$NPM_GLOBAL"
npm config set prefix "$NPM_GLOBAL" 2>/dev/null || true
export PATH="$NPM_GLOBAL/bin:$PATH"

if command -v openclaw &>/dev/null; then
    CURRENT_VER=$(openclaw --version 2>/dev/null || echo "unknown")
    log "OpenClaw $CURRENT_VER already installed. Updating..."
    npm install -g openclaw@latest 2>&1 || true
else
    log "Installing openclaw@latest globally..."
    npm install -g openclaw@latest 2>&1
fi

# Find openclaw binary
OPENCLAW_BIN=""
for p in "$NPM_GLOBAL/bin/openclaw" "$(npm config get prefix 2>/dev/null)/bin/openclaw" "$(which openclaw 2>/dev/null)"; do
    if [ -x "$p" ] 2>/dev/null; then
        OPENCLAW_BIN="$p"
        break
    fi
done

if [ -z "$OPENCLAW_BIN" ]; then
    log "ERROR: openclaw binary not found after install."
    log "Searched: $NPM_GLOBAL/bin/openclaw"
    exit 1
fi
log "OpenClaw binary: $OPENCLAW_BIN"
log "Version: $($OPENCLAW_BIN --version 2>/dev/null || echo 'unknown')"

# ── Step 3: Install Ollama for local LLM ────────────────────────────────────
log "Step 3: Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    log "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh 2>&1 || true
fi
if command -v ollama &>/dev/null; then
    log "Ollama installed: $(ollama --version 2>/dev/null || echo 'yes')"
    # Pull a small model if none exist
    MODELS_COUNT=$(ollama list 2>/dev/null | grep -c '.' || echo "0")
    if [ "$MODELS_COUNT" -le 1 ]; then
        log "Pulling default model (llama3.2:3b)..."
        ollama pull llama3.2:3b 2>&1 || ollama pull mistral 2>&1 || log "Model pull skipped."
    fi
else
    log "WARNING: Ollama not installed. OpenClaw will work but needs an LLM backend."
fi

# ── Step 4: Run OpenClaw onboarding ─────────────────────────────────────────
log "Step 4: Running onboarding..."
OPENCLAW_HOME="${HOME}/.openclaw"
mkdir -p "$OPENCLAW_HOME"
# Non-interactive onboard (skip if already configured)
if [ ! -f "$OPENCLAW_HOME/config.yaml" ] && [ ! -f "$OPENCLAW_HOME/gateway.json" ]; then
    "$OPENCLAW_BIN" onboard --install-daemon 2>&1 || log "Onboarding may need manual completion."
else
    log "OpenClaw already configured."
fi

# ── Step 5: Create systemd service for gateway ──────────────────────────────
log "Step 5: Setting up gateway service..."
GATEWAY_PORT="$HTTP_PORT"
# Bind mode: "loopback" for security (SSH tunnel), "any" for remote access
if [ "$HOST_IP" = "0.0.0.0" ] || [ "$HOST_IP" = "*" ]; then
    BIND_ARG="--bind any"
else
    BIND_ARG="--bind loopback"
fi

if command -v systemctl &>/dev/null; then
    cat > "/etc/systemd/system/${GATEWAY_SERVICE}.service" <<SVCEOF
[Unit]
Description=OpenClaw Gateway (AI Agent Platform)
After=network-online.target
Wants=network-online.target

[Service]
User=$(whoami)
WorkingDirectory=${HOME}
Environment=PATH=/usr/bin:/bin:${NPM_GLOBAL}/bin:/usr/local/bin
Environment=HOME=${HOME}
ExecStart=${OPENCLAW_BIN} gateway ${BIND_ARG} --port ${GATEWAY_PORT} --verbose
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
SVCEOF

    # Also create a service alias for our naming convention
    if [ "${GATEWAY_SERVICE}" != "${SERVICE_NAME}" ]; then
        ln -sf "/etc/systemd/system/${GATEWAY_SERVICE}.service" "/etc/systemd/system/${SERVICE_NAME}.service" 2>/dev/null || true
    fi

    systemctl daemon-reload
    systemctl enable "${GATEWAY_SERVICE}.service" 2>/dev/null || true
    systemctl restart "${GATEWAY_SERVICE}.service"
    sleep 3
    if systemctl is-active --quiet "${GATEWAY_SERVICE}.service"; then
        log "OpenClaw gateway service started on port ${GATEWAY_PORT}."
    else
        log "WARNING: Gateway service may not have started. Check: journalctl -u ${GATEWAY_SERVICE}"
    fi
else
    # macOS or no systemd — run in background
    log "Starting gateway in background..."
    "$OPENCLAW_BIN" gateway $BIND_ARG --port "$GATEWAY_PORT" --verbose >> "$LOG_FILE" 2>&1 &
    GATEWAY_PID=$!
    log "Gateway started (PID $GATEWAY_PID)."
    sleep 3
fi

# ── Step 6: Get dashboard URL ───────────────────────────────────────────────
log "Step 6: Getting dashboard URL..."
DASHBOARD_URL=""
DASHBOARD_OUTPUT=$("$OPENCLAW_BIN" dashboard --no-open 2>&1 || echo "")
if echo "$DASHBOARD_OUTPUT" | grep -q "http"; then
    DASHBOARD_URL=$(echo "$DASHBOARD_OUTPUT" | grep -oE 'https?://[^ ]+' | head -1)
    log "Dashboard: $DASHBOARD_URL"
else
    DASHBOARD_URL="http://127.0.0.1:${GATEWAY_PORT}"
    log "Dashboard URL: $DASHBOARD_URL"
fi

# ── Step 7: State file ──────────────────────────────────────────────────────
DISPLAY_HOST="$HOST_IP"
[ "$DISPLAY_HOST" = "0.0.0.0" ] || [ -z "$DISPLAY_HOST" ] && DISPLAY_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
HTTP_URL="http://${DISPLAY_HOST}:${HTTP_PORT}"
HTTPS_URL=""
[ -n "$HTTPS_PORT" ] && HTTPS_URL="https://${DISPLAY_HOST}:${HTTPS_PORT}"

cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${SERVICE_NAME}",
    "install_dir": "${INSTALL_DIR}", "host": "${HOST_IP}", "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}", "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}", "https_url": "${HTTPS_URL}",
    "deploy_mode": "os", "running": true,
    "openclaw_bin": "${OPENCLAW_BIN}",
    "gateway_port": "${GATEWAY_PORT}",
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
[ -n "$HTTPS_URL" ] && log " HTTPS:          ${HTTPS_URL}"
log " Gateway:        ws://${DISPLAY_HOST}:${GATEWAY_PORT}"
[ -n "$DASHBOARD_URL" ] && log " Local Dashboard: ${DASHBOARD_URL}"
log " CLI:            ${OPENCLAW_BIN} --help"
log ""
log " Features:"
log "   - 20+ messaging channels (WhatsApp, Telegram, Discord...)"
log "   - Browser automation, code execution, file management"
log "   - Persistent memory, cron jobs, voice support"
log "   - Local LLM via Ollama"
log ""
log " Next steps:"
log "   - Open the dashboard URL above"
log "   - Configure messaging channels"
log "   - Start chatting with your AI agent"
log "================================================================="
