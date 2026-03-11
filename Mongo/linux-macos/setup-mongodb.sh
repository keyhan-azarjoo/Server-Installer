#!/usr/bin/env bash
set -euo pipefail

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
err() { printf '[ERROR] %s\n' "$*" >&2; }

detect_os() {
  case "$(uname -s)" in
    Linux) echo "linux" ;;
    Darwin) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

choose_host() {
  if [ -n "${LOCALMONGO_HOST:-}" ]; then
    printf '%s\n' "${LOCALMONGO_HOST}"
    return
  fi
  if [ -n "${LOCALMONGO_HOST_IP:-}" ]; then
    printf '%s\n' "${LOCALMONGO_HOST_IP}"
    return
  fi
  if [ "$(detect_os)" = "macos" ]; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
  else
    hostname -I 2>/dev/null | awk '{print $1}' || true
  fi
}

require_port() {
  local name="$1" value="$2"
  case "$value" in
    ''|*[!0-9]*) err "$name must be numeric."; exit 1 ;;
  esac
  if [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
    err "$name must be between 1 and 65535."
    exit 1
  fi
}

port_free() {
  local port="$1"
  if has_cmd lsof; then
    ! lsof -iTCP:"$port" -sTCP:LISTEN -Pn >/dev/null 2>&1
    return
  fi
  if has_cmd ss; then
    ! ss -ltn "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .
    return
  fi
  return 0
}

wait_for_port() {
  local port="$1" timeout="$2" elapsed=0
  while [ "$elapsed" -lt "$timeout" ]; do
    if ! port_free "$port"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 1
}

ensure_docker_linux() {
  if has_cmd docker && docker info >/dev/null 2>&1; then
    info "Docker is already available."
    return
  fi
  if ! has_cmd apt-get; then
    err "Docker is required. Automatic install is only implemented for apt-based Linux hosts."
    exit 1
  fi
  info "Installing Docker on Linux..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends docker.io ca-certificates curl
  systemctl enable --now docker || true
  if ! has_cmd docker || ! docker info >/dev/null 2>&1; then
    err "Docker install completed but docker is not ready."
    exit 1
  fi
}

ensure_docker() {
  local os_name="$1"
  if [ "$os_name" = "linux" ]; then
    ensure_docker_linux
    return
  fi
  if ! has_cmd docker; then
    err "Docker Desktop is required on macOS. Install it, start it, then rerun."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker Desktop is installed but the engine is not running."
    exit 1
  fi
}

ensure_hosts_entry() {
  local host="$1" ip_value="$2" hosts_file="/etc/hosts"
  case "$host" in
    localhost|127.0.0.1|'') return ;;
    *[!0-9.]*)
      if ! grep -Eq "[[:space:]]${host}([[:space:]]|\$)" "$hosts_file"; then
        printf '%s %s\n' "$ip_value" "$host" >> "$hosts_file"
      fi
      ;;
  esac
}

trust_caddy_root_linux() {
  local cert_path="$1"
  [ -f "$cert_path" ] || return 0
  mkdir -p /usr/local/share/ca-certificates
  cp "$cert_path" /usr/local/share/ca-certificates/localmongo.crt
  if has_cmd update-ca-certificates; then
    update-ca-certificates >/dev/null 2>&1 || true
  fi
}

trust_caddy_root_macos() {
  local cert_path="$1"
  [ -f "$cert_path" ] || return 0
  security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$cert_path" >/dev/null 2>&1 || true
}

open_linux_firewall_port() {
  local port="$1"
  if has_cmd ufw; then
    ufw allow "${port}/tcp" >/dev/null 2>&1 || true
    return
  fi
  if has_cmd firewall-cmd; then
    firewall-cmd --permanent --add-port="${port}/tcp" >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
    return
  fi
}

main() {
  local os_name host_value https_port mongo_port web_port mongo_user mongo_password ui_user ui_password
  local root_dir caddyfile data_dir config_dir caddy_root cert_path addresses https_url lan_url mongo_url

  os_name="$(detect_os)"
  [ "$os_name" != "unknown" ] || { err "Unsupported OS."; exit 1; }
  info "===== Local MongoDB Installer (${os_name}) ====="

  host_value="$(choose_host)"
  [ -n "$host_value" ] || host_value="localhost"
  https_port="${LOCALMONGO_HTTPS_PORT:-9445}"
  mongo_port="${LOCALMONGO_MONGO_PORT:-27017}"
  web_port="${LOCALMONGO_WEB_PORT:-8081}"
  mongo_user="${LOCALMONGO_ADMIN_USER:-admin}"
  mongo_password="${LOCALMONGO_ADMIN_PASSWORD:-StrongPassword123}"
  ui_user="${LOCALMONGO_UI_USER:-$mongo_user}"
  ui_password="${LOCALMONGO_UI_PASSWORD:-$mongo_password}"

  require_port "LOCALMONGO_HTTPS_PORT" "$https_port"
  require_port "LOCALMONGO_MONGO_PORT" "$mongo_port"
  require_port "LOCALMONGO_WEB_PORT" "$web_port"

  if [ "$https_port" = "$mongo_port" ] || [ "$https_port" = "$web_port" ] || [ "$mongo_port" = "$web_port" ]; then
    err "HTTPS, MongoDB, and Web UI ports must be different."
    exit 1
  fi

  if ! port_free "$https_port" || ! port_free "$mongo_port" || ! port_free "$web_port"; then
    err "One or more requested ports are already in use."
    exit 1
  fi

  ensure_docker "$os_name"

  root_dir="/opt/localmongo"
  [ "$os_name" = "macos" ] && root_dir="/usr/local/localmongo"
  data_dir="${root_dir}/caddy-data"
  config_dir="${root_dir}/caddy-config"
  mkdir -p "$root_dir" "$data_dir" "$config_dir"

  docker rm -f localmongo-https localmongo-web localmongo-mongodb >/dev/null 2>&1 || true
  docker network rm localmongo-net >/dev/null 2>&1 || true
  docker network create localmongo-net >/dev/null
  docker volume create localmongo-data >/dev/null

  addresses="https://localhost:${https_port}"
  if [ "$host_value" != "localhost" ] && [ "$host_value" != "127.0.0.1" ]; then
    addresses="${addresses}, https://${host_value}:${https_port}"
  fi
  caddyfile="${root_dir}/Caddyfile"
  cat > "$caddyfile" <<EOF
{
  auto_https disable_redirects
}

${addresses} {
  tls internal
  reverse_proxy localmongo-web:8081
  encode gzip
}
EOF

  docker run -d \
    --name localmongo-mongodb \
    --label com.localmongo.installer=true \
    --label com.localmongo.role=mongodb \
    --restart unless-stopped \
    --network localmongo-net \
    -p "${mongo_port}:27017" \
    -e "MONGO_INITDB_ROOT_USERNAME=${mongo_user}" \
    -e "MONGO_INITDB_ROOT_PASSWORD=${mongo_password}" \
    -v localmongo-data:/data/db \
    mongo:7 >/dev/null

  docker run -d \
    --name localmongo-web \
    --label com.localmongo.installer=true \
    --label com.localmongo.role=web \
    --restart unless-stopped \
    --network localmongo-net \
    -p "127.0.0.1:${web_port}:8081" \
    -e "ME_CONFIG_MONGODB_SERVER=localmongo-mongodb" \
    -e "ME_CONFIG_MONGODB_PORT=27017" \
    -e "ME_CONFIG_MONGODB_ENABLE_ADMIN=true" \
    -e "ME_CONFIG_MONGODB_AUTH_DATABASE=admin" \
    -e "ME_CONFIG_MONGODB_ADMINUSERNAME=${mongo_user}" \
    -e "ME_CONFIG_MONGODB_ADMINPASSWORD=${mongo_password}" \
    -e "ME_CONFIG_BASICAUTH_USERNAME=${ui_user}" \
    -e "ME_CONFIG_BASICAUTH_PASSWORD=${ui_password}" \
    mongo-express:latest >/dev/null

  docker run -d \
    --name localmongo-https \
    --label com.localmongo.installer=true \
    --label com.localmongo.role=https \
    --restart unless-stopped \
    --network localmongo-net \
    -p "${https_port}:443" \
    -v "${caddyfile}:/etc/caddy/Caddyfile:ro" \
    -v "${data_dir}:/data" \
    -v "${config_dir}:/config" \
    caddy:2-alpine >/dev/null

  wait_for_port "$web_port" 45 || { err "Mongo web admin UI did not start."; exit 1; }
  wait_for_port "$https_port" 45 || { err "Mongo HTTPS proxy did not start."; exit 1; }

  cert_path="${data_dir}/caddy/pki/authorities/local/root.crt"
  [ -f "$cert_path" ] || cert_path="${data_dir}/pki/authorities/local/root.crt"
  if [ "$os_name" = "linux" ]; then
    trust_caddy_root_linux "$cert_path"
    open_linux_firewall_port "$https_port"
    open_linux_firewall_port "$mongo_port"
  else
    trust_caddy_root_macos "$cert_path"
  fi

  ensure_hosts_entry "$host_value" "127.0.0.1"

  https_url="https://localhost:${https_port}"
  lan_url=""
  if [ "$host_value" != "localhost" ] && [ "$host_value" != "127.0.0.1" ]; then
    lan_url="https://${host_value}:${https_port}"
  fi
  mongo_url="mongodb://localhost:${mongo_port}/"

  printf '\n===== INSTALLATION COMPLETE =====\n'
  printf 'Compass-style web UI (HTTPS): %s\n' "$https_url"
  [ -n "$lan_url" ] && printf 'Compass-style web UI (Host):  %s\n' "$lan_url"
  printf 'Direct web UI (HTTP localhost): http://127.0.0.1:%s\n' "$web_port"
  printf 'MongoDB connection:            %s\n' "$mongo_url"
  if [ "$host_value" != "localhost" ] && [ "$host_value" != "127.0.0.1" ]; then
    printf 'MongoDB connection (Host):     mongodb://%s:%s/\n' "$host_value" "$mongo_port"
  fi
  printf 'MongoDB root user:             %s\n' "$mongo_user"
  printf 'MongoDB root password:         %s\n' "$mongo_password"
  printf 'Web UI username:               %s\n' "$ui_user"
  printf 'Web UI password:               %s\n' "$ui_password"
}

main "$@"
