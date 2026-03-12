#!/usr/bin/env bash
set -euo pipefail

REQUESTED_VERSION="${PYTHON_VERSION:-3.12}"
INSTALL_JUPYTER="${PYTHON_INSTALL_JUPYTER:-1}"
JUPYTER_PORT="${PYTHON_JUPYTER_PORT:-8888}"
HOST_IP="${PYTHON_HOST_IP:-}"
NOTEBOOK_DIR_INPUT="${PYTHON_NOTEBOOK_DIR:-}"
JUPYTER_USER="${PYTHON_JUPYTER_USER:-}"
JUPYTER_PASSWORD="${PYTHON_JUPYTER_PASSWORD:-}"
BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/python"
STATE_FILE="${STATE_DIR}/python-state.json"
JUPYTER_STATE_FILE="${STATE_DIR}/jupyter-state.json"
VENV_DIR="${STATE_DIR}/venv"
JUPYTER_SERVICE_NAME="serverinstaller-jupyter"
JUPYTER_SERVICE_FILE="/etc/systemd/system/${JUPYTER_SERVICE_NAME}.service"
JUPYTER_NGINX_CONF="/etc/nginx/conf.d/${JUPYTER_SERVICE_NAME}.conf"
JUPYTER_CERT_DIR="/etc/nginx/ssl/${JUPYTER_SERVICE_NAME}"
JUPYTER_CERT_FILE="${JUPYTER_CERT_DIR}/jupyter.crt"
JUPYTER_KEY_FILE="${JUPYTER_CERT_DIR}/jupyter.key"
JUPYTER_AUTH_DIR="/etc/nginx/auth"
JUPYTER_AUTH_FILE="${JUPYTER_AUTH_DIR}/${JUPYTER_SERVICE_NAME}.htpasswd"
JUPYTER_LOG_FILE="${STATE_DIR}/jupyter.log"
JUPYTER_INTERNAL_PORT=""
NGINX_RUN_USER=""

mkdir -p "${STATE_DIR}"

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

pick_internal_port() {
  local candidate
  for candidate in 18888 28888 38888 48888 58888; do
    if [[ "${candidate}" != "${JUPYTER_PORT}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done
  echo "18888"
}

ensure_python_linux() {
  local major_minor="$1"
  if command -v "python${major_minor}" >/dev/null 2>&1; then
    echo "python${major_minor}"
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >&2
    if apt-cache show "python${major_minor}" >/dev/null 2>&1; then
      apt-get install -y "python${major_minor}" "python${major_minor}-venv" "python${major_minor}-distutils" python3-pip >&2 || \
        apt-get install -y python3 python3-venv python3-pip >&2
    else
      apt-get install -y python3 python3-venv python3-pip >&2
    fi
    apt-get install -y nginx openssl ca-certificates >&2
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "python${major_minor}" python3-pip nginx openssl ca-certificates >&2 || dnf install -y python3 python3-pip nginx openssl ca-certificates >&2
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip nginx openssl ca-certificates >&2
  elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive install python3 python3-pip nginx openssl ca-certificates >&2
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm python python-pip nginx openssl ca-certificates >&2
  else
    echo "No supported Linux package manager found." >&2
    return 1
  fi
  command -v "python${major_minor}" >/dev/null 2>&1 && echo "python${major_minor}" && return 0
  command -v python3 >/dev/null 2>&1 && echo "python3" && return 0
  return 1
}

ensure_python_macos() {
  local major_minor="$1"
  if command -v "python${major_minor}" >/dev/null 2>&1; then
    echo "python${major_minor}"
    return 0
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required to install Python automatically on macOS." >&2
    return 1
  fi
  brew install "python@${major_minor}" || brew install python
  command -v "python${major_minor}" >/dev/null 2>&1 && echo "python${major_minor}" && return 0
  command -v python3 >/dev/null 2>&1 && echo "python3" && return 0
  return 1
}

ensure_linux_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
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

port_is_listening() {
  local port="$1"
  if has_cmd ss; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "(^|:)${port}$"
    return $?
  fi
  if has_cmd netstat; then
    netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "(^|:)${port}$"
    return $?
  fi
  return 1
}

local_https_ready() {
  local port="$1"
  local path="${2:-/lab}"
  python3 - "$port" "$path" <<'PY'
import ssl
import sys
import urllib.error
import urllib.request

port = sys.argv[1]
path = sys.argv[2]
url = f"https://127.0.0.1:{port}{path}"
ctx = ssl._create_unverified_context()

try:
    with urllib.request.urlopen(url, context=ctx, timeout=10) as response:
        status = getattr(response, "status", 200)
        raise SystemExit(0 if status in (200, 301, 302, 401, 403) else 1)
except urllib.error.HTTPError as exc:
    raise SystemExit(0 if exc.code in (200, 301, 302, 401, 403) else 1)
except Exception:
    raise SystemExit(1)
PY
}

public_access_note() {
  local port="$1"
  if [[ "$port" != "80" && "$port" != "443" ]]; then
    cat <<EOF
NOTE: Public access on TCP ${port} depends on your VPS/cloud firewall too.
If the browser times out, allow inbound TCP ${port} in the provider security group/firewall, or use 443 if it is available.
EOF
  fi
}

ensure_tls_material() {
  mkdir -p "${JUPYTER_CERT_DIR}"
  if [[ ! -f "${JUPYTER_CERT_FILE}" || ! -f "${JUPYTER_KEY_FILE}" ]]; then
    openssl req -x509 -nodes -newkey rsa:2048 \
      -keyout "${JUPYTER_KEY_FILE}" \
      -out "${JUPYTER_CERT_FILE}" \
      -days 3650 \
      -subj "/CN=${HOST_IP:-localhost}/O=ServerInstaller/C=US" >/dev/null 2>&1
    chmod 600 "${JUPYTER_KEY_FILE}"
    chmod 644 "${JUPYTER_CERT_FILE}"
  fi
}

ensure_auth_file() {
  mkdir -p "${JUPYTER_AUTH_DIR}"
  if [[ -z "${JUPYTER_USER}" ]]; then
    if [[ -f "${STATE_FILE}" ]]; then
      JUPYTER_USER="$(python3 -c 'import json,sys; from pathlib import Path; path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}; print(str(data.get("jupyter_username") or "").strip())' "${STATE_FILE}")"
    fi
  fi
  if [[ -z "${JUPYTER_USER}" ]]; then
    echo "PYTHON_JUPYTER_USER is required for HTTPS login." >&2
    exit 1
  fi
  if [[ -n "${JUPYTER_PASSWORD}" ]]; then
    printf '%s:%s\n' "${JUPYTER_USER}" "$(openssl passwd -apr1 "${JUPYTER_PASSWORD}")" > "${JUPYTER_AUTH_FILE}"
    chmod 640 "${JUPYTER_AUTH_FILE}"
    return 0
  fi
  if [[ ! -f "${JUPYTER_AUTH_FILE}" ]]; then
    echo "PYTHON_JUPYTER_PASSWORD is required the first time Jupyter is installed." >&2
    exit 1
  fi
}

detect_nginx_user() {
  local configured_user=""
  configured_user="$(awk '/^[[:space:]]*user[[:space:]]+/ {gsub(/;/, "", $2); print $2; exit}' /etc/nginx/nginx.conf 2>/dev/null || true)"
  if [[ -n "${configured_user}" ]]; then
    echo "${configured_user}"
    return 0
  fi
  for candidate in www-data nginx nobody; do
    if id -u "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  echo ""
}

ensure_nginx_can_read_auth_file() {
  local nginx_user="$1"
  if [[ -z "${nginx_user}" || ! -f "${JUPYTER_AUTH_FILE}" ]]; then
    return 0
  fi

  chown root:"${nginx_user}" "${JUPYTER_AUTH_FILE}" >/dev/null 2>&1 || true
  chmod 640 "${JUPYTER_AUTH_FILE}" >/dev/null 2>&1 || true

  if ! su -s /bin/sh -c "test -r '${JUPYTER_AUTH_FILE}'" "${nginx_user}" >/dev/null 2>&1; then
    chmod 644 "${JUPYTER_AUTH_FILE}" >/dev/null 2>&1 || true
  fi
}

write_systemd_service() {
  cat > "${JUPYTER_SERVICE_FILE}" <<EOF
[Unit]
Description=Server Installer Jupyter Lab
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${NOTEBOOK_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${VENV_PYTHON} -m jupyter lab --allow-root --no-browser --ServerApp.ip=127.0.0.1 --ServerApp.port=${JUPYTER_INTERNAL_PORT} --ServerApp.token= --ServerApp.password= --ServerApp.allow_remote_access=True --ServerApp.trust_xheaders=True --ServerApp.root_dir=${NOTEBOOK_DIR}
Restart=always
RestartSec=5
StandardOutput=append:${JUPYTER_LOG_FILE}
StandardError=append:${JUPYTER_LOG_FILE}

[Install]
WantedBy=multi-user.target
EOF
}

write_nginx_config() {
  cat > "${JUPYTER_NGINX_CONF}" <<EOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen ${JUPYTER_PORT} ssl;
    server_name _;

    ssl_certificate ${JUPYTER_CERT_FILE};
    ssl_certificate_key ${JUPYTER_KEY_FILE};

    auth_basic "Restricted Jupyter";
    auth_basic_user_file ${JUPYTER_AUTH_FILE};

    client_max_body_size 2g;

    location / {
        proxy_pass http://127.0.0.1:${JUPYTER_INTERNAL_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Scheme https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_redirect off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
EOF
}

write_state_files() {
  local url="https://${HOST_IP}:${JUPYTER_PORT}/lab"
  cat > "${STATE_FILE}" <<EOF
{
  "requested_version": $(json_escape "${REQUESTED_VERSION}"),
  "python_version": $(json_escape "${PYTHON_VERSION_REAL}"),
  "python_executable": $(json_escape "${VENV_PYTHON}"),
  "base_python_executable": $(json_escape "${PYTHON_EXE}"),
  "venv_dir": $(json_escape "${VENV_DIR}"),
  "scripts_dir": $(json_escape "${SCRIPTS_DIR}"),
  "jupyter_installed": ${JUPYTER_INSTALLED},
  "jupyter_port": $(json_escape "${JUPYTER_PORT}"),
  "jupyter_internal_port": $(json_escape "${JUPYTER_INTERNAL_PORT}"),
  "jupyter_url": $(json_escape "${url}"),
  "jupyter_username": $(json_escape "${JUPYTER_USER}"),
  "jupyter_auth_enabled": true,
  "jupyter_https_enabled": true,
  "service_mode": true,
  "host": $(json_escape "${HOST_IP}"),
  "default_notebook_dir": $(json_escape "${NOTEBOOK_DIR}"),
  "notebook_dir": $(json_escape "${NOTEBOOK_DIR}"),
  "updated_at": $(json_escape "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
}
EOF
  cat > "${JUPYTER_STATE_FILE}" <<EOF
{
  "service_name": $(json_escape "${JUPYTER_SERVICE_NAME}.service"),
  "host": $(json_escape "${HOST_IP}"),
  "port": $(json_escape "${JUPYTER_PORT}"),
  "internal_port": $(json_escape "${JUPYTER_INTERNAL_PORT}"),
  "url": $(json_escape "${url}"),
  "username": $(json_escape "${JUPYTER_USER}"),
  "https_enabled": true,
  "auth_enabled": true,
  "log_path": $(json_escape "${JUPYTER_LOG_FILE}"),
  "notebook_dir": $(json_escape "${NOTEBOOK_DIR}"),
  "running": true
}
EOF
}

MAJOR_MINOR="$(printf '%s' "${REQUESTED_VERSION}" | cut -d. -f1,2)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  PYTHON_CMD="$(ensure_python_macos "${MAJOR_MINOR}")"
else
  ensure_linux_root
  PYTHON_CMD="$(ensure_python_linux "${MAJOR_MINOR}")"
fi

PYTHON_EXE="$("${PYTHON_CMD}" -c 'import sys; print(sys.executable)')"
PYTHON_VERSION_REAL="$("${PYTHON_CMD}" -c 'import sys; print(sys.version.split()[0])')"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  rm -rf "${VENV_DIR}"
  "${PYTHON_EXE}" -m venv "${VENV_DIR}"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
SCRIPTS_DIR="${VENV_DIR}/bin"
NOTEBOOK_DIR="${NOTEBOOK_DIR_INPUT:-${STATE_DIR}/notebooks}"
mkdir -p "${NOTEBOOK_DIR}"

"${VENV_PYTHON}" -m ensurepip --upgrade >/dev/null 2>&1 || true
"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel

if [[ "${INSTALL_JUPYTER,,}" =~ ^(1|true|yes|y|on)$ ]]; then
  "${VENV_PYTHON}" -m pip install --upgrade jupyterlab notebook
  JUPYTER_INSTALLED=true
else
  JUPYTER_INSTALLED=false
fi

if [[ -z "${HOST_IP}" ]]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [[ -z "${HOST_IP}" ]]; then
  HOST_IP="127.0.0.1"
fi

if [[ "$(uname -s)" == "Darwin" || "${JUPYTER_INSTALLED}" != "true" ]]; then
  cat > "${STATE_FILE}" <<EOF
{
  "requested_version": $(json_escape "${REQUESTED_VERSION}"),
  "python_version": $(json_escape "${PYTHON_VERSION_REAL}"),
  "python_executable": $(json_escape "${VENV_PYTHON}"),
  "base_python_executable": $(json_escape "${PYTHON_EXE}"),
  "venv_dir": $(json_escape "${VENV_DIR}"),
  "scripts_dir": $(json_escape "${SCRIPTS_DIR}"),
  "jupyter_installed": ${JUPYTER_INSTALLED},
  "jupyter_port": $(json_escape "${JUPYTER_PORT}"),
  "host": $(json_escape "${HOST_IP}"),
  "default_notebook_dir": $(json_escape "${NOTEBOOK_DIR}"),
  "notebook_dir": $(json_escape "${NOTEBOOK_DIR}"),
  "updated_at": $(json_escape "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
}
EOF
  echo "Python ready: ${VENV_PYTHON}"
  echo "Base Python: ${PYTHON_EXE}"
  if [[ "${JUPYTER_INSTALLED}" == "true" ]]; then
    echo "Jupyter packages installed."
  fi
  exit 0
fi

JUPYTER_INTERNAL_PORT="$(pick_internal_port)"
ensure_tls_material
ensure_auth_file
NGINX_RUN_USER="$(detect_nginx_user)"
ensure_nginx_can_read_auth_file "${NGINX_RUN_USER}"
write_systemd_service
write_nginx_config

systemctl daemon-reload
systemctl enable "${JUPYTER_SERVICE_NAME}"
systemctl restart "${JUPYTER_SERVICE_NAME}"
nginx -t >/dev/null
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx
open_firewall_port "${JUPYTER_PORT}"

if ! systemctl is-active --quiet "${JUPYTER_SERVICE_NAME}"; then
  echo "Jupyter service failed to stay active: ${JUPYTER_SERVICE_NAME}.service" >&2
  exit 1
fi

if ! systemctl is-active --quiet nginx; then
  echo "nginx failed to stay active." >&2
  exit 1
fi

if ! port_is_listening "${JUPYTER_PORT}"; then
  echo "Public HTTPS port ${JUPYTER_PORT} is not listening after nginx reload." >&2
  exit 1
fi

if ! local_https_ready "${JUPYTER_PORT}" "/lab"; then
  echo "Local HTTPS probe to https://127.0.0.1:${JUPYTER_PORT}/lab failed after startup." >&2
  exit 1
fi

write_state_files

echo "Python ready: ${VENV_PYTHON}"
echo "Base Python: ${PYTHON_EXE}"
echo "Jupyter packages installed."
echo "Jupyter service enabled: ${JUPYTER_SERVICE_NAME}.service"
echo "Jupyter Lab started at https://${HOST_IP}:${JUPYTER_PORT}/lab."
public_access_note "${JUPYTER_PORT}"
