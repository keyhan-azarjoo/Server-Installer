#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8090}"
HOST="${HOST:-0.0.0.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_SCRIPT="${SCRIPT_DIR}/../../dashboard/server_installer_dashboard.py"

if [[ ! -f "${DASHBOARD_SCRIPT}" ]]; then
  echo "Dashboard script not found: ${DASHBOARD_SCRIPT}" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install python3 and rerun." >&2
  exit 1
fi

ARGS=("${DASHBOARD_SCRIPT}" --host "${HOST}" --port "${PORT}")

echo "Starting dashboard on http://${HOST}:${PORT}"
exec python3 "${ARGS[@]}"
