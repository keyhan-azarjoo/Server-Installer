# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Windows
# Installs OpenClaw agent + Web UI on user-selected IP:Port
# ─────────────────────────────────────────────────────────────────────────────
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$SERVICE_NAME = "ServerInstaller-OpenClaw"
$programData = [Environment]::GetFolderPath("CommonApplicationData")
if ($env:SERVER_INSTALLER_DATA_DIR) { $baseStateDir = $env:SERVER_INSTALLER_DATA_DIR } else { $baseStateDir = Join-Path $programData "Server-Installer" }
$stateDir   = Join-Path $baseStateDir "openclaw"
$statePath  = Join-Path $stateDir "openclaw-state.json"
$installDir = Join-Path $stateDir "app"
$venvDir    = Join-Path $installDir "venv"
$certDir    = Join-Path $stateDir "certs"
$logFile    = Join-Path $stateDir "openclaw.log"

if ($env:OPENCLAW_HTTP_PORT)  { $httpPort  = $env:OPENCLAW_HTTP_PORT }  else { $httpPort  = "" }
if ($env:OPENCLAW_HTTPS_PORT) { $httpsPort = $env:OPENCLAW_HTTPS_PORT } else { $httpsPort = "" }
if ($env:OPENCLAW_HOST_IP)    { $hostIp    = $env:OPENCLAW_HOST_IP }    else { $hostIp    = "0.0.0.0" }
if ($env:OPENCLAW_DOMAIN)     { $domain    = $env:OPENCLAW_DOMAIN }     else { $domain    = "" }
if ($env:OPENCLAW_USERNAME)   { $username  = $env:OPENCLAW_USERNAME }   else { $username  = "" }
if ($env:OPENCLAW_PASSWORD)   { $password  = $env:OPENCLAW_PASSWORD }   else { $password  = "" }

function Log($msg) { Write-Host "[OpenClaw] $msg" }

foreach ($d in @($stateDir, $installDir, $certDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ── Step 1: Resolve Python ───────────────────────────────────────────────────
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

# ── Step 2: Create venv and install OpenClaw ─────────────────────────────────
Log "Setting up virtual environment..."
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { & $pythonCmd -m venv $venvDir }
& $venvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
Log "Installing OpenClaw and dependencies..."
& $venvPython -m pip install openclaw flask requests --quiet 2>&1
Log "OpenClaw installed."

# ── Step 3: Copy web UI files ────────────────────────────────────────────────
$scriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonDir = Join-Path $scriptRoot "OpenClaw\common"
if (Test-Path $commonDir) {
    Copy-Item -Path "$commonDir\*" -Destination $installDir -Recurse -Force
}

# ── Step 4: Skip web UI if no ports ──────────────────────────────────────────
if (-not $httpPort -and -not $httpsPort) {
    Log "No HTTP/HTTPS ports — OpenClaw installed as CLI only."
    Log "Run: openclaw --help"
    $displayHost = $hostIp
    if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
        $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
        if (-not $displayHost) { $displayHost = "127.0.0.1" }
    }
    $state = @{ installed = $true; service_name = $SERVICE_NAME; install_dir = $installDir; host = $hostIp; deploy_mode = "os"; running = $false }
    $state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8
    exit 0
}

# ── Step 5: Startup script ───────────────────────────────────────────────────
$webPort = $httpPort
if (-not $webPort) { $webPort = $httpsPort }
$startScript = Join-Path $installDir "start-openclaw-webui.py"
$pyLines = @(
    "#!/usr/bin/env python3",
    "import os, sys, ssl, threading",
    "",
    "WEB_PORT = int(os.environ.get('OPENCLAW_WEB_PORT', '${webPort}'))",
    "HTTPS_PORT = os.environ.get('OPENCLAW_HTTPS_PORT', '${httpsPort}').strip()",
    "CERT_FILE = os.environ.get('OPENCLAW_CERT_FILE', '')",
    "KEY_FILE = os.environ.get('OPENCLAW_KEY_FILE', '')",
    "",
    "def run_https(app, port, certfile, keyfile):",
    "    try:",
    "        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)",
    "        ctx.minimum_version = ssl.TLSVersion.TLSv1_2",
    "        ctx.load_cert_chain(os.path.normpath(certfile), os.path.normpath(keyfile))",
    "        from werkzeug.serving import make_server",
    "        server = make_server('0.0.0.0', port, app, ssl_context=ctx, threaded=True)",
    "        print(f'OpenClaw HTTPS on https://0.0.0.0:{port}')",
    "        server.serve_forever()",
    "    except Exception as e:",
    "        print(f'HTTPS failed: {e}')",
    "",
    "if __name__ == '__main__':",
    "    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
    "    from openclaw_web import app",
    "    if HTTPS_PORT and HTTPS_PORT.isdigit() and CERT_FILE and KEY_FILE:",
    "        cf = os.path.normpath(CERT_FILE)",
    "        kf = os.path.normpath(KEY_FILE)",
    "        if os.path.isfile(cf) and os.path.isfile(kf):",
    "            t = threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), cf, kf), daemon=True)",
    "            t.start()",
    "    print(f'OpenClaw Web UI on http://0.0.0.0:{WEB_PORT}')",
    "    app.run(host='0.0.0.0', port=WEB_PORT)"
)
$pyLines -join "`n" | Set-Content -Path $startScript -Encoding UTF8

# ── Step 6: SSL cert ────────────────────────────────────────────────────────
$certFile = Join-Path $certDir "openclaw.crt"
$keyFile  = Join-Path $certDir "openclaw.key"
if ($httpsPort -and $httpsPort -ne "0" -and -not (Test-Path $certFile)) {
    $cn = $domain; if (-not $cn) { $cn = $hostIp }; if (-not $cn -or $cn -eq "0.0.0.0") { $cn = "localhost" }
    $opensslPath = Get-Command "openssl" -ErrorAction SilentlyContinue
    if ($opensslPath) {
        & openssl req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days 3650 -subj "/CN=$cn/O=ServerInstaller/C=US" 2>&1
    }
}

# ── Step 7: Scheduled Task ──────────────────────────────────────────────────
$taskName = $SERVICE_NAME
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$action = New-ScheduledTaskAction -Execute $venvPython -Argument "`"$startScript`"" -WorkingDirectory $installDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
$env:OPENCLAW_WEB_PORT = $webPort
$env:OPENCLAW_HTTPS_PORT = $httpsPort
$env:OPENCLAW_CERT_FILE = $certFile
$env:OPENCLAW_KEY_FILE = $keyFile
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

# ── Step 8: Firewall ────────────────────────────────────────────────────────
if ($httpPort) { try { New-NetFirewallRule -DisplayName "OpenClaw HTTP $httpPort" -Direction Inbound -LocalPort $httpPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {} }
if ($httpsPort) { try { New-NetFirewallRule -DisplayName "OpenClaw HTTPS $httpsPort" -Direction Inbound -LocalPort $httpsPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {} }

# ── Step 9: Save state ──────────────────────────────────────────────────────
$displayHost = $hostIp
if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
    $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    if (-not $displayHost) { $displayHost = "127.0.0.1" }
}
$httpUrl = ""; $httpsUrl = ""
if ($httpPort) { $httpUrl = "http://${displayHost}:${httpPort}" }
if ($httpsPort) { $httpsUrl = "https://${displayHost}:${httpsPort}" }

$state = @{
    installed = $true; service_name = $SERVICE_NAME; install_dir = $installDir
    host = $hostIp; domain = $domain; http_port = $httpPort; https_port = $httpsPort
    http_url = $httpUrl; https_url = $httpsUrl; deploy_mode = "os"
    auth_enabled = [bool]$username; auth_username = $username; running = $true
}
$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

Log ""
Log "================================================================="
Log " OpenClaw Installation Complete!"
Log "================================================================="
if ($httpUrl) { Log " Web UI (HTTP):  $httpUrl" }
if ($httpsUrl) { Log " Web UI (HTTPS): $httpsUrl" }
Log " CLI:            openclaw --help"
Log "================================================================="
