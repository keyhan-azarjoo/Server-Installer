#!/usr/bin/env bash

set -euo pipefail

DOTNET_CHANNEL="${DOTNET_CHANNEL:-8.0}"
SERVICE_NAME="${SERVICE_NAME:-dotnet-app}"
SERVICE_PORT="${SERVICE_PORT:-5000}"
APP_ROOT="/opt/dotnet-apps"
DOTNET_ROOT="/usr/share/dotnet"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script as root or with sudo."
    exit 1
  fi
}

run_cmd() {
  echo ">> $*"
  "$@"
}

install_os_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    run_cmd apt-get update
    run_cmd apt-get install -y curl git ca-certificates
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    run_cmd dnf install -y curl git ca-certificates
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    run_cmd yum install -y curl git ca-certificates
    return
  fi

  echo "Unsupported package manager. Install curl and git manually, then rerun this script."
  exit 1
}

install_dotnet() {
  local installer
  installer="$(mktemp)"

  run_cmd curl -fsSL https://dot.net/v1/dotnet-install.sh -o "${installer}"
  chmod +x "${installer}"

  mkdir -p "${DOTNET_ROOT}"
  run_cmd "${installer}" --channel "${DOTNET_CHANNEL}" --install-dir "${DOTNET_ROOT}" --quality ga
  run_cmd "${installer}" --channel "${DOTNET_CHANNEL}" --runtime aspnetcore --install-dir "${DOTNET_ROOT}" --quality ga

  ln -sf "${DOTNET_ROOT}/dotnet" /usr/bin/dotnet
  rm -f "${installer}"
}

ensure_service_user() {
  if ! id -u dotnetapp >/dev/null 2>&1; then
    run_cmd useradd --system --create-home --home-dir /home/dotnetapp --shell /usr/sbin/nologin dotnetapp
  fi
}

repository_name() {
  local repo_url="$1"
  local name
  name="$(basename "${repo_url}")"
  name="${name%.git}"
  printf '%s' "${name}"
}

find_project() {
  local repo_path="$1"
  find "${repo_path}" -name '*.csproj' | head -n 1
}

write_service() {
  local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
  local publish_path="$1"
  local dll_name="$2"

  cat > "${service_file}" <<EOF
[Unit]
Description=.NET application runner for ${SERVICE_NAME}
After=network.target

[Service]
WorkingDirectory=${publish_path}
ExecStart=/usr/bin/dotnet ${publish_path}/${dll_name}.dll
Restart=always
RestartSec=10
KillSignal=SIGINT
SyslogIdentifier=${SERVICE_NAME}
User=dotnetapp
Environment=ASPNETCORE_ENVIRONMENT=Production
Environment=ASPNETCORE_URLS=http://0.0.0.0:${SERVICE_PORT}

[Install]
WantedBy=multi-user.target
EOF
}

main() {
  require_root
  install_os_packages
  install_dotnet
  ensure_service_user

  read -r -p "Enter a Git repository URL to deploy (leave blank to skip): " repo_url
  if [[ -z "${repo_url}" ]]; then
    echo "Setup completed. .NET prerequisites are installed."
    exit 0
  fi

  mkdir -p "${APP_ROOT}"

  local repo_name
  repo_name="$(repository_name "${repo_url}")"
  local repo_path="${APP_ROOT}/${repo_name}"

  if [[ -d "${repo_path}/.git" ]]; then
    run_cmd git -C "${repo_path}" pull
  else
    run_cmd git clone "${repo_url}" "${repo_path}"
  fi

  local project_path
  project_path="$(find_project "${repo_path}")"
  if [[ -z "${project_path}" ]]; then
    echo "No .csproj file was found in ${repo_path}."
    exit 1
  fi

  local dll_name
  dll_name="$(basename "${project_path}" .csproj)"
  local publish_path="${repo_path}/published"

  run_cmd dotnet restore "${project_path}"
  run_cmd dotnet publish "${project_path}" -c Release -o "${publish_path}"

  chown -R dotnetapp:dotnetapp "${repo_path}"
  write_service "${publish_path}" "${dll_name}"

  run_cmd systemctl daemon-reload
  run_cmd systemctl enable --now "${SERVICE_NAME}"

  echo "Deployment complete."
  echo "Service: ${SERVICE_NAME}"
  echo "Kestrel URL: http://localhost:${SERVICE_PORT}"
}

main "$@"
