#!/usr/bin/env bash
set -euo pipefail

REQUESTED_VERSION="${PYTHON_VERSION:-3.12}"
INSTALL_JUPYTER="${PYTHON_INSTALL_JUPYTER:-1}"
JUPYTER_PORT="${PYTHON_JUPYTER_PORT:-8888}"
HOST_IP="${PYTHON_HOST_IP:-}"
BASE_STATE_DIR="${SERVER_INSTALLER_DATA_DIR:-${HOME}/.server-installer}"
STATE_DIR="${BASE_STATE_DIR}/python"
STATE_FILE="${STATE_DIR}/python-state.json"
VENV_DIR="${STATE_DIR}/venv"

mkdir -p "${STATE_DIR}"

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
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "python${major_minor}" python3-pip >&2 || dnf install -y python3 python3-pip >&2
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 python3-pip >&2
  elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive install python3 python3-pip >&2
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm python python-pip >&2
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

MAJOR_MINOR="$(printf '%s' "${REQUESTED_VERSION}" | cut -d. -f1,2)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  PYTHON_CMD="$(ensure_python_macos "${MAJOR_MINOR}")"
else
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

"${VENV_PYTHON}" -m ensurepip --upgrade >/dev/null 2>&1 || true
"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel

if [[ "${INSTALL_JUPYTER,,}" =~ ^(1|true|yes|y|on)$ ]]; then
  "${VENV_PYTHON}" -m pip install --upgrade jupyterlab notebook
  JUPYTER_INSTALLED=true
else
  JUPYTER_INSTALLED=false
fi

cat > "${STATE_FILE}" <<EOF
{
  "requested_version": "${REQUESTED_VERSION}",
  "python_version": "${PYTHON_VERSION_REAL}",
  "python_executable": "${VENV_PYTHON}",
  "base_python_executable": "${PYTHON_EXE}",
  "venv_dir": "${VENV_DIR}",
  "scripts_dir": "${SCRIPTS_DIR}",
  "jupyter_installed": ${JUPYTER_INSTALLED},
  "jupyter_port": "${JUPYTER_PORT}",
  "host": "${HOST_IP}",
  "updated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

echo "Python ready: ${VENV_PYTHON}"
echo "Base Python: ${PYTHON_EXE}"
if [[ "${JUPYTER_INSTALLED}" == "true" ]]; then
  echo "Jupyter packages installed."
fi
