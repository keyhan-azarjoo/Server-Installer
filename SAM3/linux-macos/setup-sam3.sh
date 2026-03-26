#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# SAM3 Linux/macOS Installer
# Installs SAM3 (Segment Anything Model 3) as a managed service
# Supports: OS service (systemd), Docker, Nginx HTTPS reverse proxy
# ============================================================

SAM3_SERVICE_NAME="serverinstaller-sam3"
HOST_IP="${SAM3_HOST_IP:-}"
HTTP_PORT="${SAM3_HTTP_PORT:-5000}"
HTTPS_PORT="${SAM3_HTTPS_PORT:-5443}"
DOMAIN="${SAM3_DOMAIN:-}"
USERNAME="${SAM3_USERNAME:-}"
PASSWORD="${SAM3_PASSWORD:-}"
USE_OS_AUTH="${SAM3_USE_OS_AUTH:-}"
GPU_DEVICE="${SAM3_GPU_DEVICE:-auto}"
DOWNLOAD_MODEL="${SAM3_DOWNLOAD_MODEL:-}"
DEPLOY_MODE="${SAM3_DEPLOY_MODE:-os}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/sam3"
STATE_FILE="${STATE_DIR}/sam3-state.json"
INSTALL_DIR="${STATE_DIR}/app"
VENV_DIR="${INSTALL_DIR}/venv"
MODEL_DIR="${INSTALL_DIR}/models"
CERT_DIR="${STATE_DIR}/certs"
CERT_FILE="${CERT_DIR}/sam3.crt"
KEY_FILE="${CERT_DIR}/sam3.key"
NGINX_CONF="/etc/nginx/conf.d/${SAM3_SERVICE_NAME}.conf"
AUTH_DIR="/etc/nginx/auth"
AUTH_FILE="${AUTH_DIR}/${SAM3_SERVICE_NAME}.htpasswd"
LOG_FILE="${STATE_DIR}/sam3.log"
SYSTEMD_FILE="/etc/systemd/system/${SAM3_SERVICE_NAME}.service"

mkdir -p "${STATE_DIR}" "${INSTALL_DIR}" "${MODEL_DIR}" "${INSTALL_DIR}/temp/videos" "${CERT_DIR}"

has_cmd() { command -v "$1" >/dev/null 2>&1; }

json_escape() {
    python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

# ── GPU/TPU Detection ──────────────────────────────────────

detect_gpu() {
    local gpu_type="cpu"
    local gpu_name=""
    local gpu_vram=""

    # Check for NVIDIA GPU
    if has_cmd nvidia-smi; then
        gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
        gpu_vram="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 || true)"
        if [ -n "$gpu_name" ]; then
            gpu_type="cuda"
            echo "[INFO] NVIDIA GPU detected: ${gpu_name} (${gpu_vram} MB)" >&2
        fi
    fi

    # Check for AMD GPU (ROCm)
    if [ "$gpu_type" = "cpu" ] && has_cmd rocm-smi; then
        gpu_name="$(rocm-smi --showproductname 2>/dev/null | grep -i 'card' | head -1 || true)"
        if [ -n "$gpu_name" ]; then
            gpu_type="rocm"
            echo "[INFO] AMD GPU detected: ${gpu_name}" >&2
        fi
    fi

    # Check for Google TPU
    if [ "$gpu_type" = "cpu" ] && [ -d "/dev/accel" ]; then
        gpu_type="tpu"
        gpu_name="Google TPU"
        echo "[INFO] Google TPU detected" >&2
    fi

    # Check for Apple Silicon (MPS)
    if [ "$gpu_type" = "cpu" ] && [ "$(uname -s)" = "Darwin" ]; then
        local chip
        chip="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || true)"
        if echo "$chip" | grep -qi "Apple"; then
            gpu_type="mps"
            gpu_name="$chip"
            echo "[INFO] Apple Silicon detected: ${gpu_name}" >&2
        fi
    fi

    echo "${gpu_type}|${gpu_name}|${gpu_vram}"
}

GPU_INFO="$(detect_gpu)"
DETECTED_GPU_TYPE="$(echo "$GPU_INFO" | cut -d'|' -f1)"
DETECTED_GPU_NAME="$(echo "$GPU_INFO" | cut -d'|' -f2)"
DETECTED_GPU_VRAM="$(echo "$GPU_INFO" | cut -d'|' -f3)"

if [ "$GPU_DEVICE" = "auto" ]; then
    SELECTED_DEVICE="$DETECTED_GPU_TYPE"
else
    SELECTED_DEVICE="$GPU_DEVICE"
fi

echo "[INFO] SAM3 will use device: ${SELECTED_DEVICE}"

# ── Install System Dependencies ────────────────────────────

ensure_python() {
    local major_minor="$1"

    local os_type
    os_type="$(uname -s)"

    if [ "$os_type" = "Darwin" ]; then
        if has_cmd "python${major_minor}"; then
            echo "python${major_minor}"
            return 0
        fi
        if ! has_cmd brew; then
            echo "Homebrew is required on macOS." >&2
            return 1
        fi
        brew install "python@${major_minor}" || brew install python
        has_cmd "python${major_minor}" && echo "python${major_minor}" && return 0
        has_cmd python3 && echo "python3" && return 0
        return 1
    fi

    # Linux - always ensure venv and other deps are installed even if python exists
    if has_cmd apt-get; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update >&2
        apt-get install -y "python${major_minor}" "python${major_minor}-venv" "python${major_minor}-dev" python3-pip nginx openssl ca-certificates curl git libgl1 libglib2.0-0 >&2 || \
            apt-get install -y python3 python3-venv python3-dev python3-pip nginx openssl ca-certificates curl git libgl1 libglib2.0-0 >&2
    elif has_cmd dnf; then
        dnf install -y "python${major_minor}" python3-pip python3-devel nginx openssl ca-certificates curl git mesa-libGL glib2 >&2 || \
            dnf install -y python3 python3-pip python3-devel nginx openssl ca-certificates curl git mesa-libGL glib2 >&2
    elif has_cmd yum; then
        yum install -y python3 python3-pip python3-devel nginx openssl ca-certificates curl git mesa-libGL glib2 >&2
    elif has_cmd zypper; then
        zypper --non-interactive install python3 python3-pip python3-devel nginx openssl ca-certificates curl git libGL1 libglib-2_0-0 >&2
    elif has_cmd pacman; then
        pacman -Sy --noconfirm python python-pip nginx openssl ca-certificates curl git mesa glib2 >&2
    elif has_cmd brew; then
        brew install "python@${major_minor}" nginx openssl curl git || true
    else
        echo "No supported package manager found." >&2
        return 1
    fi

    has_cmd "python${major_minor}" && echo "python${major_minor}" && return 0
    has_cmd python3 && echo "python3" && return 0
    return 1
}

ensure_root_if_linux() {
    if [ "$(uname -s)" != "Darwin" ] && [ "$(id -u)" -ne 0 ]; then
        echo "Run this script as root or with sudo on Linux." >&2
        exit 1
    fi
}

open_firewall_port() {
    local port="$1"
    if has_cmd ufw; then
        local ufw_status
        ufw_status="$(ufw status 2>/dev/null | head -n 1 || true)"
        if [[ "${ufw_status}" =~ [Aa]ctive ]]; then
            ufw allow "${port}/tcp" >/dev/null 2>&1 || true
        fi
    fi
    if has_cmd firewall-cmd; then
        if systemctl is-active --quiet firewalld 2>/dev/null; then
            firewall-cmd --quiet --add-port="${port}/tcp" >/dev/null 2>&1 || true
            firewall-cmd --quiet --permanent --add-port="${port}/tcp" >/dev/null 2>&1 || true
            firewall-cmd --quiet --reload >/dev/null 2>&1 || true
        fi
    fi
    if has_cmd iptables; then
        iptables -C INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || \
            iptables -I INPUT -p tcp --dport "${port}" -j ACCEPT >/dev/null 2>&1 || true
    fi
}

if [ "$(uname -s)" != "Darwin" ]; then
    ensure_root_if_linux
fi

MAJOR_MINOR="$(printf '%s' "${PYTHON_VERSION}" | cut -d. -f1,2)"
PYTHON_CMD="$(ensure_python "${MAJOR_MINOR}")"
PYTHON_EXE="$("${PYTHON_CMD}" -c 'import sys; print(sys.executable)')"
echo "[INFO] Using Python: ${PYTHON_EXE}"

# ── Copy SAM3 Application Files ────────────────────────────

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON_DIR="${SCRIPT_ROOT}/common"

echo "[INFO] Copying SAM3 application files..."
for subdir in core web/templates web/static/js web/static/css; do
    mkdir -p "${INSTALL_DIR}/${subdir}"
done

FILES_TO_COPY=(
    "app.py" "requirements.txt"
    "core/detector.py" "core/video_processor.py" "core/tracker.py"
    "core/exporter.py" "core/utils.py" "core/__init__.py"
    "web/templates/index.html"
    "web/static/js/dashboard.js"
    "web/static/css/dashboard.css"
)

for file in "${FILES_TO_COPY[@]}"; do
    src="${COMMON_DIR}/${file}"
    dst="${INSTALL_DIR}/${file}"
    if [ -f "$src" ]; then
        cp -f "$src" "$dst"
    else
        echo "[WARN] Missing source file: ${file}" >&2
    fi
done

# ── Create Virtual Environment & Install Dependencies ──────

create_venv() {
    echo "[INFO] Creating virtual environment..."
    rm -rf "${VENV_DIR}"
    "${PYTHON_EXE}" -m venv "${VENV_DIR}" 2>/dev/null || {
        echo "[INFO] venv with pip failed, trying --without-pip..."
        rm -rf "${VENV_DIR}"
        "${PYTHON_EXE}" -m venv --without-pip "${VENV_DIR}"
    }
}

# Create venv if it does not exist
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    create_venv
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"

# If pip is missing inside the venv, the venv is broken — recreate then bootstrap
if ! "${VENV_PYTHON}" -m pip --version >/dev/null 2>&1; then
    echo "[INFO] pip not found in venv, recreating..."
    create_venv
    echo "[INFO] Bootstrapping pip with get-pip.py..."
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    "${VENV_PYTHON}" /tmp/get-pip.py
    rm -f /tmp/get-pip.py
fi

echo "[INFO] Upgrading pip..."
"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel

# Install PyTorch based on GPU selection
echo "[INFO] Installing PyTorch for device: ${SELECTED_DEVICE}..."
case "$SELECTED_DEVICE" in
    cuda)
        "${VENV_PIP}" install torch torchvision --index-url https://download.pytorch.org/whl/cu124
        ;;
    rocm)
        "${VENV_PIP}" install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.0
        ;;
    mps|tpu)
        "${VENV_PIP}" install torch torchvision
        ;;
    *)
        "${VENV_PIP}" install torch torchvision --index-url https://download.pytorch.org/whl/cpu
        ;;
esac

echo "[INFO] Installing SAM3 requirements..."
"${VENV_PIP}" install -r "${INSTALL_DIR}/requirements.txt"

# Install CLIP (required separately)
echo "[INFO] Installing CLIP..."
"${VENV_PIP}" install "git+https://github.com/ultralytics/CLIP.git" || echo "[WARN] CLIP installation failed - exemplar detection may not work"

# ── Modify app.py for configurable model path ─────────────

# app.py now natively reads SAM3_MODEL_PATH and SAM3_DEVICE env vars - no patching needed

# ── SSL Certificates ──────────────────────────────────────

if [ -n "${HTTPS_PORT}" ]; then
    if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
        echo "[INFO] Generating self-signed SSL certificate..."
        openssl req -x509 -nodes -newkey rsa:2048 \
            -keyout "${KEY_FILE}" \
            -out "${CERT_FILE}" \
            -days 3650 \
            -subj "/CN=${DOMAIN:-${HOST_IP:-localhost}}/O=ServerInstaller/C=US" 2>&1
        chmod 600 "${KEY_FILE}" 2>/dev/null || true
        chmod 644 "${CERT_FILE}" 2>/dev/null || true
        if [ -f "${CERT_FILE}" ] && [ -f "${KEY_FILE}" ]; then
            echo "[INFO] SSL certificate generated successfully."
        else
            echo "[WARN] SSL certificate generation failed. HTTPS will not be available."
        fi
    else
        echo "[INFO] SSL certificate already exists."
    fi
fi

# ── Authentication ─────────────────────────────────────────

if [ -n "${USERNAME}" ] && [ -n "${PASSWORD}" ]; then
    mkdir -p "${AUTH_DIR}"
    printf '%s:%s\n' "${USERNAME}" "$(openssl passwd -apr1 "${PASSWORD}")" > "${AUTH_FILE}"
    chmod 640 "${AUTH_FILE}"

    # Set nginx user permissions
    NGINX_USER="$(awk '/^[[:space:]]*user[[:space:]]+/ {gsub(/;/, "", $2); print $2; exit}' /etc/nginx/nginx.conf 2>/dev/null || true)"
    if [ -z "$NGINX_USER" ]; then
        for candidate in www-data nginx nobody; do
            if id -u "${candidate}" >/dev/null 2>&1; then
                NGINX_USER="${candidate}"
                break
            fi
        done
    fi
    if [ -n "$NGINX_USER" ] && [ -f "${AUTH_FILE}" ]; then
        chown "root:${NGINX_USER}" "${AUTH_FILE}" >/dev/null 2>&1 || true
        chmod 640 "${AUTH_FILE}" >/dev/null 2>&1 || true
    fi
fi

# ── Model Download ─────────────────────────────────────────

MODEL_PATH="${MODEL_DIR}/sam3.pt"
if echo "${DOWNLOAD_MODEL}" | grep -qiE '^(1|true|yes|y|on)$'; then
    if [ ! -f "${MODEL_PATH}" ]; then
        echo "[INFO] Downloading SAM3 model (sam3.pt ~3.4 GB)... This may take a while."
        "${VENV_PYTHON}" -c "from ultralytics import SAM; model = SAM('sam3.pt')" 2>/dev/null || true
        DEFAULT_MODEL="${INSTALL_DIR}/sam3.pt"
        if [ -f "$DEFAULT_MODEL" ]; then
            mv "$DEFAULT_MODEL" "$MODEL_PATH"
        fi
        if [ -f "$MODEL_PATH" ]; then
            echo "[INFO] SAM3 model downloaded successfully."
        else
            echo "[WARN] Model download failed. You can download manually from the dashboard."
        fi
    else
        echo "[INFO] SAM3 model already exists."
    fi
fi

# ── Create Startup Script ──────────────────────────────────

cat > "${INSTALL_DIR}/start-sam3.py" <<PYEOF
import os, sys, ssl, functools, threading
from flask import request, Response

os.environ.setdefault('SAM3_MODEL_PATH', os.path.join(os.path.dirname(__file__), 'models', 'sam3.pt'))
os.environ.setdefault('SAM3_DEVICE', '${SELECTED_DEVICE}')
os.environ.setdefault('SAM3_HOST', '0.0.0.0')
os.environ.setdefault('SAM3_PORT', '${HTTP_PORT}')

sys.path.insert(0, os.path.dirname(__file__))

SAM3_USERNAME = os.environ.get('SAM3_USERNAME', '${USERNAME}')
SAM3_PASSWORD = os.environ.get('SAM3_PASSWORD', '${PASSWORD}')
SAM3_USE_OS_AUTH = os.environ.get('SAM3_USE_OS_AUTH', '${USE_OS_AUTH}')
SAM3_HTTPS_PORT = os.environ.get('SAM3_HTTPS_PORT', '${HTTPS_PORT}')
SAM3_CERT_FILE = os.environ.get('SAM3_CERT_FILE', '${CERT_FILE}')
SAM3_KEY_FILE = os.environ.get('SAM3_KEY_FILE', '${KEY_FILE}')

from app import app

def check_auth(u, p):
    if SAM3_USE_OS_AUTH in ('1', 'true', 'yes'):
        import subprocess
        try:
            result = subprocess.run(['su', '-', u, '-c', 'true'], input=p + '\n',
                                     capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
    return u == SAM3_USERNAME and p == SAM3_PASSWORD

def authenticate():
    return Response('Authentication required', 401,
                    {'WWW-Authenticate': 'Basic realm="SAM3"'})

def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not SAM3_USERNAME and SAM3_USE_OS_AUTH not in ('1', 'true', 'yes'):
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

for rule in list(app.url_map.iter_rules()):
    endpoint = app.view_functions.get(rule.endpoint)
    if endpoint and rule.endpoint != 'static':
        app.view_functions[rule.endpoint] = requires_auth(endpoint)

def run_https(app, host, port, certfile, keyfile):
    """Run Flask with SSL in a separate thread."""
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        from werkzeug.serving import make_server
        server = make_server(host, port, app, ssl_context=ctx, threaded=True)
        print(f'SAM3 HTTPS running on https://{host}:{port}')
        server.serve_forever()
    except Exception as e:
        print(f'HTTPS server failed: {e}')

if __name__ == '__main__':
    host = os.environ.get('SAM3_HOST', '0.0.0.0')
    http_port = int(os.environ.get('SAM3_PORT', ${HTTP_PORT}))

    # Start HTTPS in a background thread if certs exist
    https_port = SAM3_HTTPS_PORT.strip()
    if https_port and https_port.isdigit() and os.path.isfile(SAM3_CERT_FILE) and os.path.isfile(SAM3_KEY_FILE):
        https_thread = threading.Thread(
            target=run_https,
            args=(app, host, int(https_port), SAM3_CERT_FILE, SAM3_KEY_FILE),
            daemon=True,
        )
        https_thread.start()
        print(f'SAM3 starting HTTP on http://{host}:{http_port} and HTTPS on https://{host}:{https_port}')
    else:
        print(f'SAM3 starting on http://{host}:{http_port}')

    app.run(host=host, port=http_port, debug=False)
PYEOF

# ── Systemd Service (Linux only) ──────────────────────────

if [ "$(uname -s)" != "Darwin" ] && [ "$DEPLOY_MODE" = "os" ]; then
    echo "[INFO] Setting up SAM3 systemd service..."

    cat > "${SYSTEMD_FILE}" <<EOF
[Unit]
Description=SAM3 AI Object Detection Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=SAM3_MODEL_PATH=${MODEL_PATH}
Environment=SAM3_DEVICE=${SELECTED_DEVICE}
Environment=SAM3_HOST=0.0.0.0
Environment=SAM3_PORT=${HTTP_PORT}
Environment=SAM3_HTTPS_PORT=${HTTPS_PORT}
Environment=SAM3_CERT_FILE=${CERT_FILE}
Environment=SAM3_KEY_FILE=${KEY_FILE}
Environment=SAM3_USERNAME=${USERNAME}
Environment=SAM3_PASSWORD=${PASSWORD}
Environment=SAM3_USE_OS_AUTH=${USE_OS_AUTH}
ExecStart=${VENV_PYTHON} ${INSTALL_DIR}/start-sam3.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SAM3_SERVICE_NAME}"
    systemctl restart "${SAM3_SERVICE_NAME}"
    echo "[INFO] SAM3 systemd service enabled and started."
fi

# ── Nginx HTTPS Reverse Proxy (optional, non-fatal) ───────

setup_nginx_proxy() {
    if [ "$(uname -s)" = "Darwin" ] || ! has_cmd nginx; then
        return 0
    fi
    if [ -z "${HTTPS_PORT}" ]; then
        echo "[INFO] No HTTPS port configured, skipping Nginx proxy."
        return 0
    fi

    echo "[INFO] Configuring Nginx HTTPS reverse proxy for SAM3..."

    local auth_block=""
    if [ -f "${AUTH_FILE}" ]; then
        auth_block="    auth_basic \"SAM3 Login\";
    auth_basic_user_file ${AUTH_FILE};"
    fi

    cat > "${NGINX_CONF}" <<NGINXEOF
server {
    listen ${HTTPS_PORT} ssl;
    server_name _;

    ssl_certificate ${CERT_FILE};
    ssl_certificate_key ${KEY_FILE};

${auth_block}

    client_max_body_size 5g;

    location / {
        proxy_pass http://127.0.0.1:${HTTP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$http_host;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_redirect off;
        proxy_read_timeout 600;
        proxy_send_timeout 600;
    }
}
NGINXEOF

    if nginx -t >/dev/null 2>&1; then
        systemctl enable nginx >/dev/null 2>&1 || true
        systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx >/dev/null 2>&1 || true
        echo "[INFO] Nginx HTTPS proxy configured on port ${HTTPS_PORT}."
    else
        echo "[WARN] Nginx config test failed (port ${HTTPS_PORT} may conflict with another service)."
        echo "[WARN] SAM3 HTTP is still available at http://${HOST_IP:-localhost}:${HTTP_PORT}"
        rm -f "${NGINX_CONF}"
        systemctl reload nginx >/dev/null 2>&1 || true
    fi
}

setup_nginx_proxy || true

# ── Open Firewall ──────────────────────────────────────────

open_firewall_port "${HTTP_PORT}"
open_firewall_port "${HTTPS_PORT}"

# ── Detect Host IP ─────────────────────────────────────────

if [ -z "${HOST_IP}" ]; then
    HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
if [ -z "${HOST_IP}" ]; then
    HOST_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [ -z "${HOST_IP}" ]; then
    HOST_IP="127.0.0.1"
fi

# ── Write State File ──────────────────────────────────────

# Determine auth and HTTPS state
HAS_AUTH="false"
if [ -n "${USERNAME}" ]; then HAS_AUTH="true"; fi
HAS_OS_AUTH="false"
if echo "${USE_OS_AUTH}" | grep -qiE '^(1|true|yes)$' 2>/dev/null; then HAS_OS_AUTH="true"; HAS_AUTH="true"; fi

# Build URLs - only include HTTPS if nginx conf exists
HTTP_URL=""
HTTPS_URL=""
if [ -n "${HTTP_PORT}" ]; then HTTP_URL="http://${HOST_IP}:${HTTP_PORT}"; fi
if [ -n "${HTTPS_PORT}" ] && [ -f "${NGINX_CONF}" ]; then HTTPS_URL="https://${HOST_IP}:${HTTPS_PORT}"; fi

cat > "${STATE_FILE}" <<EOF
{
  "service_name": $(json_escape "${SAM3_SERVICE_NAME}"),
  "install_dir": $(json_escape "${INSTALL_DIR}"),
  "venv_dir": $(json_escape "${VENV_DIR}"),
  "python_executable": $(json_escape "${VENV_PYTHON}"),
  "model_path": $(json_escape "${MODEL_PATH}"),
  "model_downloaded": $([ -f "${MODEL_PATH}" ] && echo "true" || echo "false"),
  "device": $(json_escape "${SELECTED_DEVICE}"),
  "detected_gpu_type": $(json_escape "${DETECTED_GPU_TYPE}"),
  "detected_gpu_name": $(json_escape "${DETECTED_GPU_NAME}"),
  "detected_gpu_vram": $(json_escape "${DETECTED_GPU_VRAM}"),
  "host": $(json_escape "${HOST_IP}"),
  "domain": $(json_escape "${DOMAIN}"),
  "http_port": $(json_escape "${HTTP_PORT}"),
  "https_port": $(json_escape "${HTTPS_PORT}"),
  "http_url": $(json_escape "${HTTP_URL}"),
  "https_url": $(json_escape "${HTTPS_URL}"),
  "deploy_mode": $(json_escape "${DEPLOY_MODE}"),
  "auth_enabled": ${HAS_AUTH},
  "auth_username": $(json_escape "${USERNAME}"),
  "use_os_auth": ${HAS_OS_AUTH},
  "cert_path": $(json_escape "${CERT_FILE}"),
  "key_path": $(json_escape "${KEY_FILE}"),
  "log_path": $(json_escape "${LOG_FILE}"),
  "running": true,
  "updated_at": $(json_escape "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
}
EOF

echo ""
echo "============================================================"
echo "SAM3 Installation Complete"
echo "============================================================"
echo "Device: ${SELECTED_DEVICE}"
if [ -n "${HTTP_URL}" ]; then echo "HTTP:   ${HTTP_URL}"; fi
if [ -n "${HTTPS_URL}" ]; then echo "HTTPS:  ${HTTPS_URL}"; fi
echo "Mode:   ${DEPLOY_MODE}"
if [ -f "${MODEL_PATH}" ]; then
    echo "Model:  Ready"
else
    echo "Model:  Not downloaded (download from dashboard)"
fi
echo "============================================================"
