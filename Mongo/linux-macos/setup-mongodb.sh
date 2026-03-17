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

test_https_url() {
  local url="$1"
  if has_cmd curl; then
    curl -kfsS --max-time 10 "$url" >/dev/null 2>&1
    return $?
  fi
  return 0
}

test_http_url_ready() {
  local url="$1"
  if has_cmd curl; then
    local code
    code="$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || true)"
    case "$code" in
      200|301|302|401|403) return 0 ;;
    esac
    return 1
  fi
  return 0
}

wait_for_http_url() {
  local url="$1" timeout="$2" elapsed=0
  while [ "$elapsed" -lt "$timeout" ]; do
    if test_http_url_ready "$url"; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

dump_mongo_debug() {
  warn "Docker container status:"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
  warn "HTTPS proxy logs:"
  docker logs --tail 120 localmongo-https 2>&1 || true
  warn "Mongo web logs:"
  docker logs --tail 80 localmongo-web 2>&1 || true
}

ensure_docker_linux() {
  info "[1/3] Checking Docker CLI..."
  if has_cmd docker; then
    info "      Docker CLI found: $(command -v docker)"
  else
    warn "      Docker CLI: NOT found."
  fi

  info "[2/3] Checking if Docker Engine is running..."
  if has_cmd docker && docker info >/dev/null 2>&1; then
    info "      Docker Engine is running."
    return
  fi

  info "[3/3] Installing / starting Docker..."
  if ! has_cmd docker; then
    info "      Docker not installed. Installing now..."
    export DEBIAN_FRONTEND=noninteractive
    if has_cmd apt-get; then
      apt-get update -y 2>&1 | tail -3
      apt-get install -y --no-install-recommends docker.io ca-certificates curl
    elif has_cmd yum; then
      yum install -y docker
    elif has_cmd dnf; then
      dnf install -y docker
    else
      info "      apt/yum/dnf not found. Trying get.docker.com install script..."
      curl -fsSL https://get.docker.com | sh
    fi
    info "      Docker installed."
  else
    info "      Docker CLI found but engine not running. Starting Docker service..."
  fi

  systemctl enable --now docker 2>/dev/null || service docker start 2>/dev/null || true
  # Wait up to 30s for daemon
  local elapsed=0
  while [ $elapsed -lt 30 ]; do
    sleep 2; elapsed=$((elapsed + 2))
    if docker info >/dev/null 2>&1; then
      info "      Docker Engine is ready."
      return
    fi
  done

  if ! has_cmd docker || ! docker info >/dev/null 2>&1; then
    err "Docker is not ready after installation/start attempt."
    exit 1
  fi
}

ensure_docker() {
  local os_name="$1"
  if [ "$os_name" = "linux" ]; then
    ensure_docker_linux
    return
  fi
  # macOS
  info "[1/3] Checking Docker CLI..."
  if has_cmd docker; then
    info "      Docker CLI found: $(command -v docker)"
  else
    err "      Docker Desktop is NOT installed on macOS."
    err "      Install it from https://www.docker.com/products/docker-desktop/ and start it, then retry."
    exit 1
  fi
  info "[2/3] Checking if Docker Engine is running..."
  if ! docker info >/dev/null 2>&1; then
    err "      Docker Desktop is installed but the engine is not running."
    err "      Open Docker Desktop and wait for 'Engine running', then retry."
    exit 1
  fi
  info "[3/3] Docker Engine is running."
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

clear_existing_localmongo() {
  local root_dir="$1" os_name="$2"
  docker rm -f localmongo-https localmongo-web localmongo-mongodb >/dev/null 2>&1 || true
  docker network rm localmongo-net >/dev/null 2>&1 || true
  docker volume rm -f localmongo-data >/dev/null 2>&1 || true
  rm -rf "$root_dir" >/dev/null 2>&1 || true
  if [ "$os_name" = "linux" ]; then
    systemctl disable --now localmongo-stack >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/localmongo-stack.service >/dev/null 2>&1 || true
    systemctl daemon-reload >/dev/null 2>&1 || true
  else
    launchctl bootout system /Library/LaunchDaemons/com.localmongo.stack.plist >/dev/null 2>&1 || true
    rm -f /Library/LaunchDaemons/com.localmongo.stack.plist >/dev/null 2>&1 || true
  fi
}

install_localmongo_service() {
  local os_name="$1"
  if [ "$os_name" = "linux" ]; then
    cat >/etc/systemd/system/localmongo-stack.service <<'EOF'
[Unit]
Description=LocalMongoDB Docker Stack
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/docker start localmongo-mongodb localmongo-web localmongo-https
ExecStop=/usr/bin/docker stop localmongo-https localmongo-web localmongo-mongodb
TimeoutStartSec=120
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now localmongo-stack >/dev/null 2>&1 || true
    return
  fi

  cat >/Library/LaunchDaemons/com.localmongo.stack.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.localmongo.stack</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-lc</string>
    <string>docker start localmongo-mongodb localmongo-web localmongo-https >/dev/null 2>&1 || true</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF
  chmod 644 /Library/LaunchDaemons/com.localmongo.stack.plist
  launchctl bootout system /Library/LaunchDaemons/com.localmongo.stack.plist >/dev/null 2>&1 || true
  launchctl bootstrap system /Library/LaunchDaemons/com.localmongo.stack.plist >/dev/null 2>&1 || true
}

generate_tls_cert() {
  local cert_dir="$1" host_value="$2"
  local san="IP:127.0.0.1,DNS:localhost"
  case "$host_value" in
    ''|localhost|127.0.0.1) ;;
    *[!0-9.]*)
      san="${san},DNS:${host_value}"
      ;;
    *)
      san="${san},IP:${host_value}"
      ;;
  esac
  mkdir -p "$cert_dir"
  if has_cmd openssl; then
    openssl req -x509 -nodes -newkey rsa:2048 \
      -keyout "${cert_dir}/localmongo.key" \
      -out "${cert_dir}/localmongo.crt" \
      -days 825 \
      -subj "/CN=${host_value}" \
      -addext "subjectAltName=${san}" >/dev/null 2>&1
    return
  fi
  docker run --rm -v "${cert_dir}:/out" alpine:3.20 sh -lc \
    "apk add --no-cache openssl >/dev/null && openssl req -x509 -nodes -newkey rsa:2048 -keyout /out/localmongo.key -out /out/localmongo.crt -days 825 -subj '/CN=${host_value}' -addext 'subjectAltName=${san}'" >/dev/null
}

main() {
  local os_name host_value https_port mongo_port web_port mongo_user mongo_password ui_user ui_password
  local root_dir nginx_conf nginx_certs https_url lan_url mongo_url

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

  ensure_docker "$os_name"

  root_dir="/opt/localmongo"
  [ "$os_name" = "macos" ] && root_dir="/usr/local/localmongo"
  nginx_conf="${root_dir}/nginx/conf"
  nginx_certs="${root_dir}/nginx/certs"
  info "Clearing previous LocalMongoDB containers, volumes, and config..."
  clear_existing_localmongo "$root_dir" "$os_name"

  if ! port_free "$https_port" || ! port_free "$mongo_port" || ! port_free "$web_port"; then
    err "One or more requested ports are still in use after cleanup."
    exit 1
  fi

  mkdir -p "$root_dir" "$nginx_conf" "$nginx_certs"

  docker network create localmongo-net >/dev/null
  docker volume create localmongo-data >/dev/null

  generate_tls_cert "$nginx_certs" "$host_value"
  cat > "${nginx_conf}/default.conf" <<EOF
server {
    listen ${https_port} ssl;
    server_name localhost ${host_value};

    ssl_certificate /etc/nginx/certs/localmongo.crt;
    ssl_certificate_key /etc/nginx/certs/localmongo.key;

    location / {
        proxy_pass http://localmongo-web:8081;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

  docker run -d \
    --name localmongo-mongodb \
    --label com.localmongo.installer=true \
    --label com.localmongo.role=mongodb \
    --restart always \
    --network localmongo-net \
    -p "0.0.0.0:${mongo_port}:27017" \
    -e "MONGO_INITDB_ROOT_USERNAME=${mongo_user}" \
    -e "MONGO_INITDB_ROOT_PASSWORD=${mongo_password}" \
    -v localmongo-data:/data/db \
    mongo:7 >/dev/null

  docker run -d \
    --name localmongo-web \
    --label com.localmongo.installer=true \
    --label com.localmongo.role=web \
    --restart always \
    --network localmongo-net \
    -p "127.0.0.1:${web_port}:8081" \
    -e "ME_CONFIG_MONGODB_SERVER=localmongo-mongodb" \
    -e "ME_CONFIG_MONGODB_URL=mongodb://${mongo_user}:${mongo_password}@localmongo-mongodb:27017/" \
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
    --restart always \
    --network localmongo-net \
    -p "0.0.0.0:${https_port}:${https_port}" \
    -v "${nginx_conf}/default.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "${nginx_certs}:/etc/nginx/certs:ro" \
    nginx:alpine >/dev/null

  wait_for_port "$web_port" 45 || { err "Mongo web admin UI TCP port did not open."; exit 1; }
  wait_for_http_url "http://127.0.0.1:${web_port}/" 120 || { err "Mongo web admin UI did not become ready."; dump_mongo_debug; exit 1; }
  wait_for_port "$https_port" 45 || { err "Mongo HTTPS proxy did not start."; exit 1; }
  if [ "$os_name" = "linux" ]; then
    open_linux_firewall_port "$https_port"
    open_linux_firewall_port "$mongo_port"
  fi

  ensure_hosts_entry "$host_value" "127.0.0.1"

  https_url="https://localhost:${https_port}"
  lan_url=""
  if [ "$host_value" != "localhost" ] && [ "$host_value" != "127.0.0.1" ]; then
    lan_url="https://${host_value}:${https_port}"
  fi
  mongo_url="mongodb://localhost:${mongo_port}/"

  if ! wait_for_http_url "$https_url" 60; then
    err "Local HTTPS endpoint did not respond correctly: $https_url"
    dump_mongo_debug
    exit 1
  fi

  install_localmongo_service "$os_name"

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
  if [ "$os_name" = "linux" ]; then
    printf 'Service:                       localmongo-stack (enabled)\n'
  else
    printf 'Service:                       com.localmongo.stack (loaded)\n'
  fi
}

main "$@"
