# ─────────────────────────────────────────────────────────────────────────────
# LM Studio Installer for Windows
# Installs LM Studio + Web UI proxy on user-selected IP:Port
# ─────────────────────────────────────────────────────────────────────────────
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LMSTUDIO_SERVICE_NAME = "ServerInstaller-LMStudio"
$LMSTUDIO_INTERNAL_PORT = "1234"
$programData = [Environment]::GetFolderPath("CommonApplicationData")
if ($env:SERVER_INSTALLER_DATA_DIR) { $baseStateDir = $env:SERVER_INSTALLER_DATA_DIR } else { $baseStateDir = Join-Path $programData "Server-Installer" }
$stateDir   = Join-Path $baseStateDir "lmstudio"
$statePath  = Join-Path $stateDir "lmstudio-state.json"
$installDir = Join-Path $stateDir "app"
$venvDir    = Join-Path $installDir "venv"
$certDir    = Join-Path $stateDir "certs"
$logFile    = Join-Path $stateDir "lmstudio.log"

if ($env:LMSTUDIO_HTTP_PORT)  { $httpPort  = $env:LMSTUDIO_HTTP_PORT }  else { $httpPort  = "" }
if ($env:LMSTUDIO_HTTPS_PORT) { $httpsPort = $env:LMSTUDIO_HTTPS_PORT } else { $httpsPort = "" }
if ($env:LMSTUDIO_HOST_IP)    { $hostIp    = $env:LMSTUDIO_HOST_IP }    else { $hostIp    = "0.0.0.0" }
if ($env:LMSTUDIO_DOMAIN)     { $domain    = $env:LMSTUDIO_DOMAIN }     else { $domain    = "" }
if ($env:LMSTUDIO_USERNAME)   { $username  = $env:LMSTUDIO_USERNAME }   else { $username  = "" }
if ($env:LMSTUDIO_PASSWORD)   { $password  = $env:LMSTUDIO_PASSWORD }   else { $password  = "" }

function Log($msg) { Write-Host "[LM Studio] $msg" }

foreach ($d in @($stateDir, $installDir, $certDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ── Step 1: Install LM Studio ───────────────────────────────────────────────
Log "Checking for LM Studio..."
$lmsPath = Get-Command "lms" -ErrorAction SilentlyContinue
if (-not $lmsPath) {
    Log "LM Studio CLI (lms) not found. Installing..."
    try {
        # Try winget first
        $wingetResult = winget install -e --id "ElementLabs.LMStudio" --accept-package-agreements --accept-source-agreements 2>&1
        Log $wingetResult
    } catch {
        Log "winget install failed. Trying npm..."
    }
    # Install lms CLI via npm if available
    $npmPath = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($npmPath) {
        try {
            & npm install -g @lmstudio/cli 2>&1
            Log "LM Studio CLI installed via npm."
        } catch {
            Log "npm install failed."
        }
    }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $lmsPath = Get-Command "lms" -ErrorAction SilentlyContinue
    if (-not $lmsPath) {
        Log "LM Studio CLI not found after install attempts."
        Log "Please install LM Studio from https://lmstudio.ai/download"
        Log "Then enable the CLI: LM Studio > Settings > Enable CLI (lms)"
        Log "Continuing with web UI setup anyway..."
    } else {
        Log "LM Studio CLI available: $($lmsPath.Source)"
    }
}

# ── Step 2: Start LM Studio server ──────────────────────────────────────────
Log "Checking LM Studio server..."
$lmsPath = Get-Command "lms" -ErrorAction SilentlyContinue
if ($lmsPath) {
    try {
        & lms server start --port $LMSTUDIO_INTERNAL_PORT 2>&1
        Log "LM Studio server started on port $LMSTUDIO_INTERNAL_PORT"
    } catch {
        Log "Could not auto-start LM Studio server: $_"
        Log "Start it manually: LM Studio app > Local Server > Start"
    }
} else {
    Log "LM Studio CLI not available. Start the server manually in the LM Studio app."
}

# ── Step 3: Skip web UI if no ports ──────────────────────────────────────────
if (-not $httpPort -and -not $httpsPort) {
    Log "No HTTP/HTTPS ports — skipping web UI."
    $displayHost = $hostIp
    if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
        $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
        if (-not $displayHost) { $displayHost = "127.0.0.1" }
    }
    $state = @{
        installed = $true; service_name = $LMSTUDIO_SERVICE_NAME
        install_dir = $installDir; host = $hostIp
        http_port = $LMSTUDIO_INTERNAL_PORT
        http_url = "http://${displayHost}:${LMSTUDIO_INTERNAL_PORT}"
        deploy_mode = "os"; running = $true
    }
    $state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8
    exit 0
}

# ── Step 4: Python + venv ────────────────────────────────────────────────────
Log "Resolving Python..."
$pythonCmd = $null
foreach ($py in @("python3", "python", "py")) {
    try { $ver = & $py --version 2>&1; if ($ver -match "Python 3") { $pythonCmd = $py; break } } catch {}
}
if (-not $pythonCmd) {
    Log "Installing Python..."
    try { winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements } catch {}
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $pythonCmd = "python"
}
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { & $pythonCmd -m venv $venvDir }
& $venvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $venvPython -m pip install flask requests --quiet 2>&1

# ── Step 5: Copy web UI files ────────────────────────────────────────────────
$scriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonDir = Join-Path $scriptRoot "LMStudio\common"
if (Test-Path $commonDir) {
    Copy-Item -Path "$commonDir\*" -Destination $installDir -Recurse -Force
}

# ── Step 6: Startup script ───────────────────────────────────────────────────
$webPort = $httpPort
$startScript = Join-Path $installDir "start-lmstudio-webui.py"
$pyLines = @(
    "#!/usr/bin/env python3",
    "import os, sys, ssl, threading, time",
    "",
    "LMSTUDIO_INTERNAL = 'http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}'",
    "HTTP_PORT_STR = os.environ.get('LMSTUDIO_WEB_PORT', '${webPort}').strip()",
    "HTTPS_PORT = os.environ.get('LMSTUDIO_HTTPS_PORT', '${httpsPort}').strip()",
    "CERT_FILE = os.environ.get('LMSTUDIO_CERT_FILE', '')",
    "KEY_FILE = os.environ.get('LMSTUDIO_KEY_FILE', '')",
    "",
    "def run_https(app, port, certfile, keyfile):",
    "    try:",
    "        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)",
    "        ctx.minimum_version = ssl.TLSVersion.TLSv1_2",
    "        ctx.load_cert_chain(os.path.normpath(certfile), os.path.normpath(keyfile))",
    "        from werkzeug.serving import make_server",
    "        server = make_server('0.0.0.0', port, app, ssl_context=ctx, threaded=True)",
    "        print(f'LM Studio HTTPS on https://0.0.0.0:{port}')",
    "        server.serve_forever()",
    "    except Exception as e:",
    "        print(f'HTTPS failed: {e}')",
    "",
    "if __name__ == '__main__':",
    "    os.environ['LMSTUDIO_API_BASE'] = LMSTUDIO_INTERNAL",
    "    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
    "    from lmstudio_web import app",
    "    http_port = int(HTTP_PORT_STR) if HTTP_PORT_STR and HTTP_PORT_STR.isdigit() and int(HTTP_PORT_STR) > 0 else 0",
    "    has_https = HTTPS_PORT and HTTPS_PORT.isdigit() and int(HTTPS_PORT) > 0 and CERT_FILE and KEY_FILE and os.path.isfile(os.path.normpath(CERT_FILE)) and os.path.isfile(os.path.normpath(KEY_FILE))",
    "    if has_https and http_port > 0:",
    "        t = threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), os.path.normpath(CERT_FILE), os.path.normpath(KEY_FILE)), daemon=True)",
    "        t.start()",
    "        print(f'LM Studio Web UI on http://0.0.0.0:{http_port}')",
    "        app.run(host='0.0.0.0', port=http_port)",
    "    elif has_https:",
    "        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)",
    "        ctx.minimum_version = ssl.TLSVersion.TLSv1_2",
    "        ctx.load_cert_chain(os.path.normpath(CERT_FILE), os.path.normpath(KEY_FILE))",
    "        print(f'LM Studio Web UI on https://0.0.0.0:{HTTPS_PORT} (HTTPS only)')",
    "        app.run(host='0.0.0.0', port=int(HTTPS_PORT), ssl_context=ctx)",
    "    elif http_port > 0:",
    "        print(f'LM Studio Web UI on http://0.0.0.0:{http_port}')",
    "        app.run(host='0.0.0.0', port=http_port)",
    "    else:",
    "        print('No HTTP or HTTPS port configured.')"
)
$pyLines -join "`n" | Set-Content -Path $startScript -Encoding UTF8

# ── Step 7: SSL cert ────────────────────────────────────────────────────────
$certFile = Join-Path $certDir "lmstudio.crt"
$keyFile  = Join-Path $certDir "lmstudio.key"
if ($httpsPort -and $httpsPort -ne "0" -and -not (Test-Path $certFile)) {
    $cn = $domain; if (-not $cn) { $cn = $hostIp }; if (-not $cn -or $cn -eq "0.0.0.0") { $cn = "localhost" }
    $opensslPath = Get-Command "openssl" -ErrorAction SilentlyContinue
    if ($opensslPath) {
        & openssl req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days 3650 -subj "/CN=$cn/O=ServerInstaller/C=US" 2>&1
    }
}

# ── Step 8: Scheduled Task ──────────────────────────────────────────────────
$taskName = $LMSTUDIO_SERVICE_NAME
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$action = New-ScheduledTaskAction -Execute $venvPython -Argument "`"$startScript`"" -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$env:LMSTUDIO_WEB_PORT = $webPort
$env:LMSTUDIO_HTTPS_PORT = $httpsPort
$env:LMSTUDIO_CERT_FILE = $certFile
$env:LMSTUDIO_KEY_FILE = $keyFile
$env:LMSTUDIO_API_BASE = "http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

# ── Step 9: Firewall ────────────────────────────────────────────────────────
if ($httpPort) { try { New-NetFirewallRule -DisplayName "LMStudio HTTP $httpPort" -Direction Inbound -LocalPort $httpPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {} }
if ($httpsPort) { try { New-NetFirewallRule -DisplayName "LMStudio HTTPS $httpsPort" -Direction Inbound -LocalPort $httpsPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {} }

# ── Step 10: Save state ─────────────────────────────────────────────────────
$displayHost = $hostIp
if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
    $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    if (-not $displayHost) { $displayHost = "127.0.0.1" }
}
$httpUrl = ""; $httpsUrl = ""
if ($httpPort) { $httpUrl = "http://${displayHost}:${httpPort}" }
if ($httpsPort) { $httpsUrl = "https://${displayHost}:${httpsPort}" }

$state = @{
    installed = $true; service_name = $LMSTUDIO_SERVICE_NAME; install_dir = $installDir
    host = $hostIp; domain = $domain; http_port = $httpPort; https_port = $httpsPort
    http_url = $httpUrl; https_url = $httpsUrl; deploy_mode = "os"
    auth_enabled = [bool]$username; auth_username = $username; running = $true; version = ""
    lmstudio_internal = "http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
}
$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

Log ""
Log "================================================================="
Log " LM Studio Installation Complete!"
Log "================================================================="
if ($httpUrl) { Log " Web UI (HTTP):  $httpUrl" }
if ($httpsUrl) { Log " Web UI (HTTPS): $httpsUrl" }
Log " LM Studio API:  http://127.0.0.1:${LMSTUDIO_INTERNAL_PORT}"
Log "================================================================="
