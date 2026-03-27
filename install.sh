#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Server Installer — One-line setup script
# Installs Python if needed, then downloads and runs the dashboard.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

REPO_RAW="https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"

echo "========================================"
echo " Server Installer — Setup"
echo "========================================"

# ── Step 1: Ensure Python 3 is installed ─────────────────────────────────────
PYTHON_CMD=""
for py in python3 python; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" --version 2>&1)
        if echo "$ver" | grep -q "Python 3"; then
            PYTHON_CMD="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[INFO] Python 3 not found. Installing..."
    OS_TYPE="$(uname -s)"
    if [ "$OS_TYPE" = "Darwin" ]; then
        # macOS
        if command -v brew &>/dev/null; then
            echo "[INFO] Installing Python via Homebrew..."
            brew install python3
        else
            echo "[INFO] Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for this session
            if [ -f /opt/homebrew/bin/brew ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -f /usr/local/bin/brew ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            brew install python3
        fi
    elif command -v apt-get &>/dev/null; then
        echo "[INFO] Installing Python via apt..."
        sudo apt-get update -y && sudo apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf &>/dev/null; then
        echo "[INFO] Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
    elif command -v yum &>/dev/null; then
        echo "[INFO] Installing Python via yum..."
        sudo yum install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        echo "[INFO] Installing Python via pacman..."
        sudo pacman -Sy --noconfirm python python-pip
    elif command -v zypper &>/dev/null; then
        echo "[INFO] Installing Python via zypper..."
        sudo zypper --non-interactive install python3 python3-pip
    else
        echo "[ERROR] Could not install Python 3. Please install it manually."
        echo "  macOS:  brew install python3"
        echo "  Ubuntu: sudo apt install python3"
        echo "  Fedora: sudo dnf install python3"
        exit 1
    fi
    # Re-check
    for py in python3 python; do
        if command -v "$py" &>/dev/null; then
            ver=$("$py" --version 2>&1)
            if echo "$ver" | grep -q "Python 3"; then
                PYTHON_CMD="$py"
                break
            fi
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        echo "[ERROR] Python 3 installation failed."
        exit 1
    fi
fi

echo "[INFO] Using Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"

# ── Step 2: Fix macOS SSL certificates ───────────────────────────────────────
if [ "$(uname -s)" = "Darwin" ]; then
    PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    CERT_CMD="/Applications/Python ${PY_VER}/Install Certificates.command"
    if [ -f "$CERT_CMD" ]; then
        echo "[INFO] Installing SSL certificates for Python ${PY_VER}..."
        bash "$CERT_CMD" 2>/dev/null || true
    fi
fi

# ── Step 3: Download and run the dashboard ───────────────────────────────────
INSTALL_DIR="${HOME}/.server-installer"
mkdir -p "$INSTALL_DIR"

STARTER="${INSTALL_DIR}/start-server-dashboard.py"
echo "[INFO] Downloading dashboard launcher..."
curl -fsSL "${REPO_RAW}/dashboard/start-server-dashboard.py" -o "$STARTER"

echo "[INFO] Starting Server Installer Dashboard..."
echo "========================================"
exec $PYTHON_CMD "$STARTER" "$@"
