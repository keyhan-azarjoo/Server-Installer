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
HTTPS_PORT="${OPENCLAW_HTTPS_PORT:-18801}"
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
OPENCLAW_VERSION="${OPENCLAW_VERSION:-2026.4.2}"
MIN_NODE_VERSION="${OPENCLAW_MIN_NODE_VERSION:-22.19.0}"
GATEWAY_OK=0
DASHBOARD_OK=0

log() { echo "[OpenClaw] $*"; }
mkdir -p "$STATE_DIR"

detect_real_user_home() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local console_user home_dir
        console_user="$(stat -f%Su /dev/console 2>/dev/null || true)"
        if [ -n "$console_user" ] && [ "$console_user" != "root" ] && [ "$console_user" != "loginwindow" ]; then
            home_dir="$(dscl . -read "/Users/$console_user" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
            if [ -n "$home_dir" ]; then
                printf '%s\n' "$home_dir"
                return 0
            fi
        fi
    fi
    printf '%s\n' "$OPENCLAW_HOME"
}

link_real_user_dirs() {
    local real_home="$1"
    local dir_name src dst
    [ -n "$real_home" ] || return 0
    for dir_name in Desktop Documents Downloads; do
        src="${real_home}/${dir_name}"
        dst="${HOME}/${dir_name}"
        if [ -e "$src" ] || [ -L "$src" ]; then
            rm -rf "$dst" 2>/dev/null || true
            ln -s "$src" "$dst" 2>/dev/null || true
        fi
    done
}

version_ge() {
    [ "$1" = "$2" ] && return 0
    local first
    first=$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)
    [ "$first" = "$2" ]
}

has_runtime_dep() {
    local pkg_dir="$1"
    local dep_name="$2"
    [ -d "$pkg_dir" ] || return 1
    local dep_dir="${pkg_dir}/node_modules/${dep_name}"
    if [ -f "${dep_dir}/package.json" ]; then
        return 0
    fi
    return 1
}

install_openclaw_runtime_deps() {
    local pkg_dir="$1"
    shift
    [ -d "$pkg_dir" ] || return 1
    [ "$#" -gt 0 ] || return 0
    log "Installing OpenClaw runtime dependencies: $*"
    (cd "$pkg_dir" && npm install --no-save --ignore-scripts --package-lock=false "$@" 2>&1) || return 1
}

ensure_openclaw_runtime_deps() {
    local pkg_dir="$1"
    local dep
    local missing=()
    for dep in "@buape/carbon" "@larksuiteoapi/node-sdk" "@slack/web-api"; do
        if ! has_runtime_dep "$pkg_dir" "$dep"; then
            missing+=("$dep")
        fi
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        for dep in "${missing[@]}"; do
            log "Repairing missing OpenClaw runtime dependency: $dep"
        done
        install_openclaw_runtime_deps "$pkg_dir" "${missing[@]}" || return 1
        for dep in "${missing[@]}"; do
            has_runtime_dep "$pkg_dir" "$dep" || return 1
        done
    fi
}

repair_runtime_deps_from_log() {
    local pkg_dir="$1"
    local dep
    local missing=()
    for dep in $(grep -oE "Cannot find module '[^']+'" "$LOG_FILE" 2>/dev/null | sed "s/Cannot find module '//; s/'$//" | sort -u); do
        case "$dep" in
            "@buape/carbon"|@larksuiteoapi/node-sdk|@slack/web-api)
                log "Repairing runtime dependency reported by gateway log: $dep"
                missing+=("$dep")
                ;;
        esac
    done
    [ "${#missing[@]}" -gt 0 ] || return 1
    install_openclaw_runtime_deps "$pkg_dir" "${missing[@]}" || return 1
    for dep in "${missing[@]}"; do
        has_runtime_dep "$pkg_dir" "$dep" || return 1
    done
    return 0
}

verify_openclaw_install() {
    [ -x "$OPENCLAW_BIN" ] || return 1
    "$OPENCLAW_BIN" --version >/dev/null 2>&1 || return 1
    local bin_dir pkg_dir
    bin_dir="$(cd "$(dirname "$OPENCLAW_BIN")" && pwd)" || return 1
    pkg_dir="$(cd "${bin_dir}/../lib/node_modules/openclaw" 2>/dev/null && pwd)" || return 1
    ensure_openclaw_runtime_deps "$pkg_dir" || return 1
}

check_gateway_http() {
    curl -sf "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1
}

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
    CURRENT_NODE_VERSION="$(node --version 2>/dev/null | sed 's/^v//')"
    if ! command -v node &>/dev/null || ! version_ge "${CURRENT_NODE_VERSION:-0.0.0}" "$MIN_NODE_VERSION"; then
        BREW_CMD=""
        for bp in /opt/homebrew/bin/brew /usr/local/bin/brew "$(which brew 2>/dev/null)"; do
            if [ -x "$bp" ] 2>/dev/null; then BREW_CMD="$bp"; break; fi
        done
        if [ -n "$BREW_CMD" ]; then
            log "Found brew at $BREW_CMD"
            "$BREW_CMD" install node@22 2>/dev/null || "$BREW_CMD" upgrade node@22 2>/dev/null || "$BREW_CMD" install node 2>/dev/null || "$BREW_CMD" upgrade node 2>/dev/null || true
            # Add brew node to PATH
            for np in /opt/homebrew/opt/node@22/bin /opt/homebrew/bin /usr/local/bin; do
                if [ -x "$np/node" ]; then export PATH="$np:$PATH"; break; fi
            done
        else
            # Direct download from nodejs.org
            log "Downloading Node.js directly..."
            ARCH=$(uname -m)
            if [ "$ARCH" = "arm64" ]; then
                NODE_PKG="https://nodejs.org/dist/v${MIN_NODE_VERSION}/node-v${MIN_NODE_VERSION}-darwin-arm64.tar.gz"
            else
                NODE_PKG="https://nodejs.org/dist/v${MIN_NODE_VERSION}/node-v${MIN_NODE_VERSION}-darwin-x64.tar.gz"
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
CURRENT_NODE_VERSION="$(node --version 2>/dev/null | sed 's/^v//')"
if ! version_ge "${CURRENT_NODE_VERSION:-0.0.0}" "$MIN_NODE_VERSION"; then
    log "ERROR: Node.js ${CURRENT_NODE_VERSION:-unknown} is too old. Need >= ${MIN_NODE_VERSION}."
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
    log "OpenClaw target version: $OPENCLAW_VERSION"
    log "npm prefix: $NPM_GLOBAL"
    log "npm cache: $NPM_CACHE"
    log "Removing previous OpenClaw install and runtime state..."
    pkill -f "openclaw gateway" 2>/dev/null || true
    pkill -f "https-proxy.py" 2>/dev/null || true
    rm -rf "${HOME}/.openclaw" 2>/dev/null || true
    rm -f "$STATE_FILE" "$LOG_FILE" "${STATE_DIR}/https-proxy.py" 2>/dev/null || true
    rm -rf "$NPM_GLOBAL/lib/node_modules/openclaw" "$NPM_GLOBAL/bin/openclaw" 2>/dev/null || true
    npm uninstall -g openclaw 2>&1 || true
    npm install -g "openclaw@${OPENCLAW_VERSION}" 2>&1 || { log "npm global install failed, trying local"; npm install --prefix "$NPM_GLOBAL" "openclaw@${OPENCLAW_VERSION}" 2>&1 || true; }
    REAL_USER_HOME="$(detect_real_user_home)"
    link_real_user_dirs "$REAL_USER_HOME"
    # Install optional peer dependencies for channels (Telegram, Discord, Slack, etc.)
    OC_PKG_DIR="$NPM_GLOBAL/lib/node_modules/openclaw"
    if [ -d "$OC_PKG_DIR" ]; then
        ensure_openclaw_runtime_deps "$OC_PKG_DIR" || true
    fi
else
    # Linux — install as openclaw user
    su - "$OPENCLAW_USER" -c "npm config set prefix ~/.npm-global && npm uninstall -g openclaw 2>/dev/null || true" 2>&1
    su - "$OPENCLAW_USER" -c "npm config set prefix ~/.npm-global && npm install -g openclaw@${OPENCLAW_VERSION}" 2>&1
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
        log "FATAL: Cannot find openclaw binary. Install manually: npm install -g openclaw@${OPENCLAW_VERSION}"
        exit 1
    fi
fi

# ── Step 3b: Create systemd service ─────────────────────────────────────────
if ! verify_openclaw_install; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log "WARNING: OpenClaw preflight dependency verification did not fully pass."
        log "Continuing on macOS and letting gateway startup repair missing runtime deps."
    else
        log "FATAL: OpenClaw installation is incomplete or invalid."
        log "Dependency repair failed under ${NPM_GLOBAL}/lib/node_modules/openclaw"
        exit 1
    fi
fi
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
ExecStart=${OPENCLAW_BIN} gateway ${BIND_ARG} --allow-unconfigured --port ${HTTP_PORT} --verbose
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
"$OPENCLAW_BIN" config set gateway.controlUi.dangerouslyDisableDeviceAuth true 2>/dev/null || true
# Enable full computer access: native commands, code execution, filesystem
"$OPENCLAW_BIN" config set commands.native auto 2>/dev/null || true
"$OPENCLAW_BIN" config set commands.nativeSkills auto 2>/dev/null || true
"$OPENCLAW_BIN" config set agents.defaults.maxConcurrent 4 2>/dev/null || true
"$OPENCLAW_BIN" config set agents.defaults.subagents.maxConcurrent 8 2>/dev/null || true
# Write channel tokens and API keys to .env file for the gateway
OC_ENV_FILE="${HOME}/.openclaw/.env"
mkdir -p "$(dirname "$OC_ENV_FILE")"
# Build env file using python3 (bash 3.x on macOS lacks associative arrays)
python3 -c "
import os, pathlib
env_file = '$OC_ENV_FILE'
data = {}
p = pathlib.Path(env_file)
if p.exists():
    for line in p.read_text(errors='ignore').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            data[k.strip()] = v.strip()
mapping = {
    'OPENCLAW_TELEGRAM_TOKEN': 'TELEGRAM_BOT_TOKEN',
    'OPENCLAW_DISCORD_TOKEN': 'DISCORD_TOKEN',
    'OPENCLAW_SLACK_TOKEN': 'SLACK_BOT_TOKEN',
    'OPENCLAW_WHATSAPP_PHONE': 'WHATSAPP_PHONE',
    'OPENCLAW_OPENAI_KEY': 'OPENAI_API_KEY',
    'OPENCLAW_ANTHROPIC_KEY': 'ANTHROPIC_API_KEY',
}
for form_key, env_key in mapping.items():
    val = os.environ.get(form_key, '').strip()
    if val:
        data[env_key] = val
data.setdefault('OLLAMA_API_KEY', 'ollama-local')
p.write_text('\n'.join(f'{k}={v}' for k, v in sorted(data.items())) + '\n')
" 2>/dev/null || true
# Source env so gateway picks them up
if [ -f "$OC_ENV_FILE" ]; then set -a; . "$OC_ENV_FILE"; set +a; fi
[ -n "$OPENCLAW_TELEGRAM_TOKEN" ] && log "Telegram bot token configured."
[ -n "$OPENCLAW_DISCORD_TOKEN" ] && log "Discord bot token configured."
[ -n "$OPENCLAW_SLACK_TOKEN" ] && log "Slack bot token configured."
[ -n "$OPENCLAW_OPENAI_KEY" ] && log "OpenAI API key configured."
[ -n "$OPENCLAW_ANTHROPIC_KEY" ] && log "Anthropic API key configured."
log "Config set. Channels and API keys written to $OC_ENV_FILE."

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
        pkill -f "openclaw gateway" 2>/dev/null || true
        pkill -f "https-proxy.py" 2>/dev/null || true
        sleep 1
        : > "$LOG_FILE"
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
            OC_PKG_DIR="${NPM_GLOBAL}/lib/node_modules/openclaw"
            STARTUP_REPAIRED=0
            for attempt in 1 2; do
                log "Running: $OPENCLAW_BIN gateway $BIND_ARG --allow-unconfigured --port $HTTP_PORT --verbose"
                "$OPENCLAW_BIN" gateway $BIND_ARG --allow-unconfigured --port "$HTTP_PORT" --verbose >> "$LOG_FILE" 2>&1 &
                GW_PID=$!
                log "Gateway process started (PID $GW_PID)."
                sleep 5
                if kill -0 "$GW_PID" 2>/dev/null; then
                    log "Gateway is running."
                    if check_gateway_http; then
                        GATEWAY_OK=1
                        log "Gateway responding on port ${HTTP_PORT}."
                        break
                    else
                        log "Gateway running but not responding yet. Check log: $LOG_FILE"
                        tail -10 "$LOG_FILE" 2>/dev/null | while read line; do log "  $line"; done
                        exit 1
                    fi
                fi
                log "ERROR: Gateway process died. Check log: $LOG_FILE"
                tail -20 "$LOG_FILE" 2>/dev/null | while read line; do log "  $line"; done
                if [ "$attempt" -eq 1 ] && [ -d "$OC_PKG_DIR" ]; then
                    if repair_runtime_deps_from_log "$OC_PKG_DIR"; then
                        STARTUP_REPAIRED=1
                        : > "$LOG_FILE"
                        continue
                    fi
                fi
                exit 1
            done
            [ "$STARTUP_REPAIRED" -eq 1 ] && log "Gateway recovered after runtime dependency repair."
        else
            log "FATAL: Cannot find openclaw binary. Install failed."
            log "Try manually: npm install -g openclaw@${OPENCLAW_VERSION}"
            exit 1
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

        # Determine agent config dir (must match where openclaw CLI reads from: $HOME/.openclaw/)
        AGENT_DIR="${HOME}/.openclaw/agents/main/agent"
        mkdir -p "$AGENT_DIR"

        # Write agent auth + model config in the current OpenClaw schema.
        OPENCLAW_MODEL="$OLLAMA_MODEL" OPENCLAW_PROVIDER="ollama" python3 - <<'PYEOF'
import json, os, pathlib
import urllib.parse

home_dir = pathlib.Path(os.environ.get("HOME", ""))
agent_dir = home_dir / ".openclaw" / "agents" / "main" / "agent"
agent_dir.mkdir(parents=True, exist_ok=True)
auth_path = agent_dir / "auth-profiles.json"
settings_path = agent_dir / "settings.json"
cfg_path = home_dir / ".openclaw" / "openclaw.json"

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}

provider = (os.environ.get("OPENCLAW_PROVIDER") or "").strip()
model = (os.environ.get("OPENCLAW_MODEL") or "").strip()
ollama_key = os.environ.get("OLLAMA_API_KEY") or "ollama-local"
ollama_url = (os.environ.get("OPENCLAW_OLLAMA_URL") or "").strip()
lmstudio_url = (os.environ.get("OPENCLAW_LMSTUDIO_URL") or "").strip()
lmstudio_key = (os.environ.get("LMSTUDIO_API_KEY") or "").strip() or "lmstudio-local"
openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

auth_data = load_json(auth_path)
profiles = auth_data.get("profiles") if isinstance(auth_data.get("profiles"), dict) else {}
last_good = auth_data.get("lastGood") if isinstance(auth_data.get("lastGood"), dict) else {}
profiles["ollama:local"] = {"type": "api_key", "provider": "ollama", "key": ollama_key}
last_good["ollama"] = "ollama:local"
if openai_key:
    profiles["openai:default"] = {"type": "api_key", "provider": "openai", "key": openai_key}
    last_good["openai"] = "openai:default"
if anthropic_key:
    profiles["anthropic:default"] = {"type": "api_key", "provider": "anthropic", "key": anthropic_key}
    last_good["anthropic"] = "anthropic:default"
auth_path.write_text(json.dumps({"version": 1, "profiles": profiles, "lastGood": last_good}, indent=2), encoding="utf-8")

settings = load_json(settings_path)
settings["provider"] = provider
settings["model"] = f"{provider}/{model}"
settings.setdefault("customInstructions", "")
settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

cfg = load_json(cfg_path)
agents = cfg.setdefault("agents", {})
defaults = agents.setdefault("defaults", {})
model_cfg = defaults.setdefault("model", {})
models_cfg = cfg.setdefault("models", {})
models_cfg["mode"] = "replace"
providers_cfg = models_cfg.get("providers")
if isinstance(providers_cfg, dict):
    providers_cfg.pop("ollama", None)
    if not providers_cfg:
        models_cfg.pop("providers", None)
models_catalog = defaults.get("models")
if isinstance(models_catalog, dict):
    for key in [k for k in list(models_catalog.keys()) if "/" in str(k)]:
        models_catalog.pop(key, None)
    if not models_catalog:
        defaults.pop("models", None)
model_cfg["primary"] = f"{provider}/{model}"

def _safe_json(url, headers=None):
    try:
        import ssl, urllib.request
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        ctx = ssl._create_unverified_context() if str(url).startswith("https://") else None
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}

def _normalize_ollama_root(url):
    base = str(url or "").strip().rstrip("/")
    if not base:
        return "http://127.0.0.1:11434"
    for suffix in ("/api/tags", "/api", "/v1"):
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    return base.rstrip("/")

def _normalize_lmstudio_base(url):
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/models"):
        base = base[:-len("/models")]
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base.rstrip("/")

def _make_model_entry(model_id, name=None, context_window=128000, max_tokens=16384):
    mid = str(model_id or "").strip()
    display = str(name or mid).strip()
    return {
        "id": mid,
        "name": display,
        "reasoning": False,
        "input": ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": int(context_window),
        "maxTokens": int(max_tokens),
    }

def _allow_cloud_model(provider_name, model_id):
    mid = str(model_id or "").strip().lower()
    if not mid:
        return False
    blocked = ("embedding", "image", "audio", "transcribe", "tts", "realtime", "search", "moderation", "whisper", "sora")
    if any(part in mid for part in blocked):
        return False
    if provider_name == "openai":
        return mid.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))
    if provider_name == "anthropic":
        return mid.startswith("claude")
    return True

agent_models = {"mode": "replace", "providers": {}}
ollama_root = _normalize_ollama_root(ollama_url)
ollama_result = _safe_json(ollama_root + "/api/tags")
ollama_models = []
for item in ollama_result.get("models") or []:
    mid = str(item.get("name") or item.get("model") or "").strip()
    if mid:
        ollama_models.append(_make_model_entry(mid, mid, int(item.get("context_length") or 16384), 4096))
if not ollama_models and model:
    ollama_models.append(_make_model_entry(model, model, 16384, 4096))
if ollama_models:
    agent_models["providers"]["ollama"] = {
        "baseUrl": ollama_root,
        "api": "ollama",
        "apiKey": ollama_key,
        "models": ollama_models,
    }
lmstudio_base = _normalize_lmstudio_base(lmstudio_url)
lmstudio_models = []
if lmstudio_base:
    result = _safe_json(lmstudio_base + "/models", {"Authorization": f"Bearer {lmstudio_key}"})
    for item in result.get("data") or []:
        mid = str(item.get("id") or "").strip()
        if mid:
            lmstudio_models.append(_make_model_entry(mid, mid, 16384, 4096))
    lmstudio_models.sort(key=lambda item: str(item.get("id") or "").lower())
if lmstudio_models:
    agent_models["providers"]["lmstudio"] = {
        "baseUrl": lmstudio_base,
        "api": "openai-responses",
        "apiKey": lmstudio_key,
        "models": lmstudio_models,
    }
openai_models = []
if openai_key:
    result = _safe_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {openai_key}"})
    for item in result.get("data") or []:
        mid = str(item.get("id") or "").strip()
        if _allow_cloud_model("openai", mid):
            openai_models.append(_make_model_entry(mid, mid, 128000, 16384))
    openai_models.sort(key=lambda item: str(item.get("id") or "").lower())
if openai_models:
    agent_models["providers"]["openai"] = {
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": openai_key,
        "models": openai_models,
    }
anthropic_models = []
if anthropic_key:
    result = _safe_json("https://api.anthropic.com/v1/models", {"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"})
    for item in result.get("data") or []:
        mid = str(item.get("id") or "").strip()
        if _allow_cloud_model("anthropic", mid):
            anthropic_models.append(_make_model_entry(mid, item.get("display_name") or mid, 200000, 16384))
    anthropic_models.sort(key=lambda item: str(item.get("id") or "").lower())
if anthropic_models:
    agent_models["providers"]["anthropic"] = {
        "baseUrl": "https://api.anthropic.com/v1",
        "apiKey": anthropic_key,
        "models": anthropic_models,
    }
(cfg.setdefault("models", {}))["mode"] = "replace"
cfg["models"]["providers"] = json.loads(json.dumps(agent_models["providers"]))
if not cfg["models"]["providers"]:
    cfg["models"].pop("providers", None)
(agent_dir / "models.json").write_text(json.dumps(agent_models, indent=2), encoding="utf-8")
available_models = []
for provider_name, provider_cfg in agent_models.get("providers", {}).items():
    for item in provider_cfg.get("models") or []:
        mid = str(item.get("id") or "").strip()
        if mid:
            available_models.append(f"{provider_name}/{mid}")
if available_models and f"{provider}/{model}" not in available_models:
    preferred = next((m for m in available_models if m.startswith("ollama/")), "") or available_models[0]
    settings["provider"], _, resolved_model = preferred.partition("/")
    settings["model"] = preferred
    model_cfg["primary"] = preferred
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
cfg_path.parent.mkdir(parents=True, exist_ok=True)
cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
print(f"Auth profiles written: {auth_path}")
print(f"Agent settings written: {settings_path} (model: {settings['model']})")
print(f"Configured primary model: {model_cfg['primary']}")
print(f"Agent model registry written: {agent_dir / 'models.json'}")
PYEOF

        # Also set via config CLI as fallback for older builds.
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
    if check_gateway_http; then
        GATEWAY_OK=1
    else
        log "ERROR: Gateway did not come up on port ${HTTP_PORT}."
        exit 1
    fi
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
    DASHBOARD_OK=1
else
    if [ "$GATEWAY_OK" -eq 1 ]; then
        DASHBOARD_URL="http://127.0.0.1:${HTTP_PORT}"
        log "Dashboard: $DASHBOARD_URL"
        DASHBOARD_OK=1
    else
        log "ERROR: Could not determine dashboard URL because the gateway is unavailable."
        exit 1
    fi
fi

# ── Step 4c: Set up HTTPS reverse proxy ────────────────────────────────────
if [ -n "$HTTPS_PORT" ] && command -v openssl &>/dev/null; then
    log "Step 4c: Setting up HTTPS proxy on port $HTTPS_PORT..."
    CERT_DIR="${STATE_DIR}/certs"
    mkdir -p "$CERT_DIR"
    CERT_HOST_IP="$HOST_IP"
    [ "$CERT_HOST_IP" = "0.0.0.0" ] || [ -z "$CERT_HOST_IP" ] && CERT_HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    # Generate self-signed cert with SANs
    cat > /tmp/openclaw-cert.cnf <<CERTCNF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no
[req_distinguished_name]
CN = openclaw
O = ServerInstaller
[v3_req]
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = openclaw
IP.1 = 127.0.0.1
IP.2 = ${CERT_HOST_IP}
CERTCNF
    if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ] || true; then
        openssl req -x509 -nodes -newkey rsa:2048 \
            -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
            -days 3650 -config /tmp/openclaw-cert.cnf -extensions v3_req 2>/dev/null
        log "SSL certificate generated."
    else
        log "SSL certificate already exists."
    fi
    rm -f /tmp/openclaw-cert.cnf

    # Start a TCP-level SSL proxy (supports WebSocket + all HTTP traffic transparently)
    HTTPS_PROXY_SCRIPT="${STATE_DIR}/https-proxy.py"
    cat > "$HTTPS_PROXY_SCRIPT" <<'PYPROXY'
import socket, ssl, threading, os, sys, signal, traceback

CERT = os.environ["OC_CERT"]
KEY = os.environ["OC_KEY"]
LISTEN_PORT = int(os.environ["OC_HTTPS_PORT"])
BACKEND_PORT = int(os.environ["OC_HTTP_PORT"])

def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle(raw_client):
    ssl_client = None
    try:
        ssl_client = ctx.wrap_socket(raw_client, server_side=True)
        backend = socket.create_connection(("127.0.0.1", BACKEND_PORT), timeout=10)
        t1 = threading.Thread(target=pipe, args=(ssl_client, backend), daemon=True)
        t2 = threading.Thread(target=pipe, args=(backend, ssl_client), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()
    except Exception:
        pass
    finally:
        if ssl_client:
            try: ssl_client.close()
            except: pass
        try: raw_client.close()
        except: pass

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(CERT, KEY)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", LISTEN_PORT))
srv.listen(128)
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
print(f"TLS proxy listening on :{LISTEN_PORT} -> 127.0.0.1:{BACKEND_PORT}", flush=True)

while True:
    try:
        client, addr = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()
    except Exception:
        pass
PYPROXY
    # Kill any existing HTTPS proxy
    pkill -f "https-proxy.py" 2>/dev/null || true
    sleep 1
    # Start HTTPS proxy in background
    OC_HTTP_PORT="$HTTP_PORT" OC_HTTPS_PORT="$HTTPS_PORT" \
        OC_CERT="$CERT_DIR/cert.pem" OC_KEY="$CERT_DIR/key.pem" \
        python3 "$HTTPS_PROXY_SCRIPT" >> "$LOG_FILE" 2>&1 &
    HTTPS_PID=$!
    sleep 2
    if kill -0 "$HTTPS_PID" 2>/dev/null; then
        log "HTTPS proxy running on port $HTTPS_PORT (PID $HTTPS_PID)."
    else
        log "WARNING: HTTPS proxy failed to start on port $HTTPS_PORT. The port may already be in use."
    fi
elif [ -n "$HTTPS_PORT" ]; then
    log "WARNING: openssl not found, skipping HTTPS setup."
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
# Read token directly from config JSON (CLI redacts sensitive values)
GATEWAY_TOKEN=""
OC_CONFIG_JSON="${HOME}/.openclaw/openclaw.json"
if [ -f "$OC_CONFIG_JSON" ] && command -v python3 &>/dev/null; then
    GATEWAY_TOKEN=$(python3 -c "
import json, sys
try:
    c = json.load(open('$OC_CONFIG_JSON'))
    print(c.get('gateway',{}).get('auth',{}).get('token',''))
except: pass
" 2>/dev/null || echo "")
fi
# Fallback: try CLI
if [ -z "$GATEWAY_TOKEN" ] || echo "$GATEWAY_TOKEN" | grep -qi "REDACTED"; then
    CLI_TOKEN=$("$OPENCLAW_BIN" config get gateway.auth.token 2>/dev/null || echo "")
    CLI_TOKEN=$(echo "$CLI_TOKEN" | tr -d '[:space:]')
    if [ -n "$CLI_TOKEN" ] && ! echo "$CLI_TOKEN" | grep -qi "REDACTED"; then
        GATEWAY_TOKEN="$CLI_TOKEN"
    fi
fi

cat > "$STATE_FILE" <<STEOF
{
    "installed": true, "service_name": "${SERVICE_NAME}",
    "install_dir": "${OPENCLAW_HOME}", "host": "${HOST_IP}", "domain": "${DOMAIN}",
    "http_port": "${HTTP_PORT}", "https_port": "${HTTPS_PORT}",
    "http_url": "${HTTP_URL}", "https_url": "${HTTPS_URL}",
    "deploy_mode": "os", "running": $([ "$GATEWAY_OK" -eq 1 ] && echo "true" || echo "false"),
    "openclaw_bin": "${OPENCLAW_BIN}",
    "gateway_port": "${HTTP_PORT}",
    "gateway_token": "${GATEWAY_TOKEN}",
    "dashboard_url": "${DASHBOARD_URL}",
    "auth_enabled": $([ -n "$USERNAME" ] && echo "true" || echo "false"),
    "auth_username": "${USERNAME}"
}
STEOF

log ""
log "================================================================="
if [ "$GATEWAY_OK" -ne 1 ] || [ "$DASHBOARD_OK" -ne 1 ]; then
    log "ERROR: Installation finished without a reachable dashboard."
    exit 1
fi
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
