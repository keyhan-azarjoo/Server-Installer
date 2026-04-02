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
# Valid --bind: loopback, lan, tailnet, auto, custom
if [ "$HOST_IP" = "0.0.0.0" ] || [ "$HOST_IP" = "*" ] || [ -z "$HOST_IP" ]; then
    BIND_ARG="--bind lan"
else
    BIND_ARG="--bind lan"
fi

# ── Step 1: Create dedicated user ───────────────────────────────────────────
log "Step 1: Creating openclaw user..."
if id "$OPENCLAW_USER" &>/dev/null; then
    log "User $OPENCLAW_USER already exists."
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS — use current user, writable home dir
        OPENCLAW_USER="$(whoami)"
        OPENCLAW_HOME="$HOME"
        # /var/root is read-only on macOS, use state dir instead
        if [ ! -w "$OPENCLAW_HOME" ]; then
            OPENCLAW_HOME="$STATE_DIR"
        fi
        NPM_GLOBAL="${OPENCLAW_HOME}/.npm-global"
        OPENCLAW_BIN="${NPM_GLOBAL}/bin/openclaw"
        log "macOS — using user: $OPENCLAW_USER (home: $OPENCLAW_HOME)"
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
# Check common Node.js install locations (may exist from a previous install)
for _np in "${STATE_DIR}/node/bin" /usr/local/bin /opt/homebrew/bin /opt/homebrew/opt/node@22/bin; do
    if [ -x "$_np/node" ] && [ "$("$_np/node" --version 2>/dev/null | sed 's/v//' | cut -d. -f1)" -ge 22 ] 2>/dev/null; then
        export PATH="$_np:$PATH"
        break
    fi
done
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS — find brew or install node directly
    if ! command -v node &>/dev/null || [ "$(node --version | sed 's/v//' | cut -d. -f1)" -lt 22 ] 2>/dev/null; then
        BREW_CMD=""
        for bp in /opt/homebrew/bin/brew /usr/local/bin/brew "$(which brew 2>/dev/null)"; do
            if [ -x "$bp" ] 2>/dev/null; then BREW_CMD="$bp"; break; fi
        done
        if [ -n "$BREW_CMD" ]; then
            log "Found brew at $BREW_CMD"
            "$BREW_CMD" install node@22 2>/dev/null || "$BREW_CMD" install node 2>/dev/null || true
            # Add brew node to PATH
            for np in /opt/homebrew/opt/node@22/bin /opt/homebrew/bin /usr/local/bin; do
                if [ -x "$np/node" ]; then export PATH="$np:$PATH"; break; fi
            done
        else
            # Direct download from nodejs.org
            log "Downloading Node.js directly..."
            ARCH=$(uname -m)
            if [ "$ARCH" = "arm64" ]; then
                NODE_PKG="https://nodejs.org/dist/v22.16.0/node-v22.16.0-darwin-arm64.tar.gz"
            else
                NODE_PKG="https://nodejs.org/dist/v22.16.0/node-v22.16.0-darwin-x64.tar.gz"
            fi
            NODE_INSTALL_DIR="${STATE_DIR}/node"
            mkdir -p "$NODE_INSTALL_DIR"
            if curl -fsSL "$NODE_PKG" -o /tmp/node.tar.gz 2>&1 && \
               tar -xzf /tmp/node.tar.gz -C "$NODE_INSTALL_DIR" --strip-components=1 2>&1; then
                rm -f /tmp/node.tar.gz
                log "Node.js installed to $NODE_INSTALL_DIR"
            else
                # Fallback: try /usr/local
                mkdir -p /usr/local/bin 2>/dev/null || true
                tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 2>&1 || true
                rm -f /tmp/node.tar.gz
                NODE_INSTALL_DIR="/usr/local"
                log "Node.js installed to /usr/local (fallback)"
            fi
            export PATH="${NODE_INSTALL_DIR}/bin:$PATH"
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
if command -v node &>/dev/null; then
    log "Node.js: $(node --version)"
else
    log "ERROR: Node.js not found. Cannot continue."
    log "Install manually: https://nodejs.org/en/download"
    exit 1
fi
if ! command -v npm &>/dev/null; then
    log "ERROR: npm not found. Cannot continue."
    exit 1
fi

# ── Step 3a: Install OpenClaw ────────────────────────────────────────────────
log "Step 3a: Installing OpenClaw..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS — npm needs writable HOME for cache. /var/root is read-only.
    NPM_GLOBAL="$STATE_DIR/.npm-global"
    NPM_CACHE="$STATE_DIR/.npm-cache"
    mkdir -p "$NPM_GLOBAL" "$NPM_CACHE"
    OPENCLAW_BIN="$NPM_GLOBAL/bin/openclaw"
    export npm_config_prefix="$NPM_GLOBAL"
    export npm_config_cache="$NPM_CACHE"
    export HOME="$STATE_DIR"
    export PATH="$NPM_GLOBAL/bin:$PATH"
    log "npm prefix: $NPM_GLOBAL"
    log "npm cache: $NPM_CACHE"
    npm install -g openclaw@latest 2>&1 || { log "npm global install failed, trying local"; npm install --prefix "$NPM_GLOBAL" openclaw@latest 2>&1 || true; }
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
ExecStart=${OPENCLAW_BIN} gateway --bind loopback --allow-unconfigured --port ${HTTP_PORT} --verbose
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

# ── Step 3c: Skip interactive onboard — configure via CLI instead ─────────────
log "Step 3c: Configuring OpenClaw (non-interactive)..."
# Onboard is interactive (requires TTY). Skip it and configure directly.
# The gateway will start with --allow-unconfigured and user can configure via dashboard.
"$OPENCLAW_BIN" config set gateway.mode local 2>/dev/null || true
"$OPENCLAW_BIN" config set gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true 2>/dev/null || true
log "Config set. User can configure channels via the dashboard after install."

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
        if [ ! -x "$OPENCLAW_BIN" ]; then
            log "ERROR: OpenClaw binary not found at $OPENCLAW_BIN"
            log "Trying to find it..."
            for p in "$(which openclaw 2>/dev/null)" "$NPM_GLOBAL/bin/openclaw" "/usr/local/bin/openclaw" "$STATE_DIR/.npm-global/bin/openclaw"; do
                if [ -x "$p" ] 2>/dev/null; then
                    OPENCLAW_BIN="$p"
                    log "Found: $OPENCLAW_BIN"
                    break
                fi
            done
        fi
        if [ -x "$OPENCLAW_BIN" ]; then
            export PATH="$(dirname "$OPENCLAW_BIN"):$PATH"
            log "Running: $OPENCLAW_BIN gateway --bind loopback --allow-unconfigured --port $HTTP_PORT --verbose"
            "$OPENCLAW_BIN" gateway --bind loopback --allow-unconfigured --port "$HTTP_PORT" --verbose >> "$LOG_FILE" 2>&1 &
            GW_PID=$!
            log "Gateway process started (PID $GW_PID)."
            sleep 5
            # Check if it's still running
            if kill -0 "$GW_PID" 2>/dev/null; then
                log "Gateway is running."
                # Verify port is listening
                if curl -sf "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
                    log "Gateway responding on port ${HTTP_PORT}."
                else
                    log "Gateway running but not responding yet. Check log: $LOG_FILE"
                    tail -10 "$LOG_FILE" 2>/dev/null | while read line; do log "  $line"; done
                fi
            else
                log "ERROR: Gateway process died. Check log: $LOG_FILE"
                tail -20 "$LOG_FILE" 2>/dev/null | while read line; do log "  $line"; done
            fi
        else
            log "FATAL: Cannot find openclaw binary. Install failed."
            log "Try manually: npm install -g openclaw@latest"
        fi
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

    # Configure OpenClaw to use Ollama as LLM backend
    OLLAMA_MODEL=$(ollama list 2>/dev/null | grep -v "^NAME" | head -1 | awk '{print $1}')
    if [ -n "$OLLAMA_MODEL" ]; then
        log "Ollama model available: $OLLAMA_MODEL"

        # Determine agent config dir
        if [[ "$OSTYPE" == "darwin"* ]]; then
            AGENT_DIR="${STATE_DIR}/.openclaw/agents/main/agent"
        else
            AGENT_DIR="${OPENCLAW_HOME}/.openclaw/agents/main/agent"
        fi
        mkdir -p "$AGENT_DIR"

        # Write auth-profiles.json so OpenClaw knows about Ollama provider
        cat > "$AGENT_DIR/auth-profiles.json" <<'APROF'
{
  "ollama": {
    "provider": "ollama",
    "baseUrl": "http://127.0.0.1:11434",
    "apiKey": "ollama"
  }
}
APROF
        log "Auth profiles written: $AGENT_DIR/auth-profiles.json"

        # Write agent settings to make Ollama the default model
        cat > "$AGENT_DIR/settings.json" <<ASET
{
  "model": "ollama/${OLLAMA_MODEL}",
  "provider": "ollama",
  "customInstructions": ""
}
ASET
        log "Agent settings written: $AGENT_DIR/settings.json (model: ollama/${OLLAMA_MODEL})"

        # Also set via config CLI as fallback
        "$OPENCLAW_BIN" config set models.default.provider ollama 2>/dev/null || true
        "$OPENCLAW_BIN" config set models.default.model "$OLLAMA_MODEL" 2>/dev/null || true
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
