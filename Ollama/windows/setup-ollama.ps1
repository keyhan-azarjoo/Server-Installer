# ─────────────────────────────────────────────────────────────────────────────
# Ollama Installer for Windows
# Installs Ollama LLM server + Web UI on user-selected IP:Port
# ─────────────────────────────────────────────────────────────────────────────
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ── Configuration ────────────────────────────────────────────────────────────
$OLLAMA_SERVICE_NAME = "ServerInstaller-Ollama"
$OLLAMA_INTERNAL_PORT = "11434"  # Ollama always runs internally on this
$programData         = [Environment]::GetFolderPath("CommonApplicationData")
if ($env:SERVER_INSTALLER_DATA_DIR) { $baseStateDir = $env:SERVER_INSTALLER_DATA_DIR } else { $baseStateDir = Join-Path $programData "Server-Installer" }
$stateDir            = Join-Path $baseStateDir "ollama"
$statePath           = Join-Path $stateDir "ollama-state.json"
$installDir          = Join-Path $stateDir "app"
$venvDir             = Join-Path $installDir "venv"
$certDir             = Join-Path $stateDir "certs"
$logFile             = Join-Path $stateDir "ollama.log"

if ($env:OLLAMA_HTTP_PORT)  { $httpPort  = $env:OLLAMA_HTTP_PORT }  else { $httpPort  = "" }
if ($env:OLLAMA_HTTPS_PORT) { $httpsPort = $env:OLLAMA_HTTPS_PORT } else { $httpsPort = "" }
if ($env:OLLAMA_HOST_IP)    { $hostIp    = $env:OLLAMA_HOST_IP }    else { $hostIp    = "0.0.0.0" }
if ($env:OLLAMA_DOMAIN)     { $domain    = $env:OLLAMA_DOMAIN }     else { $domain    = "" }
if ($env:OLLAMA_USERNAME)   { $username  = $env:OLLAMA_USERNAME }   else { $username  = "" }
if ($env:OLLAMA_PASSWORD)   { $password  = $env:OLLAMA_PASSWORD }   else { $password  = "" }

function Log($msg) { Write-Host "[Ollama] $msg" }

# ── Create directories ───────────────────────────────────────────────────────
Log "Creating directories..."
foreach ($d in @($stateDir, $installDir, $certDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ── Step 1: Install Ollama binary ────────────────────────────────────────────
Log "Checking for Ollama..."
$ollamaPath = Get-Command "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaPath) {
    Log "Ollama not found. Downloading installer..."
    $installerUrl = "https://ollama.com/download/OllamaSetup.exe"
    $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        Log "Running Ollama installer (silent)..."
        Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait -NoNewWindow
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $ollamaPath = Get-Command "ollama" -ErrorAction SilentlyContinue
        if ($ollamaPath) {
            Log "Ollama installed successfully: $($ollamaPath.Source)"
        } else {
            $defaultOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
            if (Test-Path $defaultOllama) {
                $env:Path += ";$(Split-Path $defaultOllama)"
                Log "Found at: $defaultOllama"
            }
        }
    } catch {
        Log "ERROR: Failed to download Ollama: $_"
        exit 1
    }
} else {
    Log "Ollama already installed: $($ollamaPath.Source)"
}

# ── Step 2: Start Ollama on internal port ────────────────────────────────────
Log "Starting Ollama on internal port $OLLAMA_INTERNAL_PORT..."
$env:OLLAMA_HOST = "127.0.0.1:${OLLAMA_INTERNAL_PORT}"
$env:OLLAMA_ORIGINS = "*"
try {
    $ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $ollamaProcess) {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
        Log "Ollama started on 127.0.0.1:${OLLAMA_INTERNAL_PORT}"
    } else {
        Log "Ollama already running (PID: $($ollamaProcess.Id))"
    }
} catch {
    Log "WARNING: Could not start Ollama: $_"
}

# ── Step 3: Skip web UI if no ports configured ──────────────────────────────
if (-not $httpPort -and -not $httpsPort) {
    Log "No HTTP/HTTPS ports configured — skipping web UI setup."
    Log "Ollama API available at http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"

    # Save state
    $displayHost = $hostIp
    if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
        $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
        if (-not $displayHost) { $displayHost = "127.0.0.1" }
    }
    $state = @{
        installed = $true; service_name = $OLLAMA_SERVICE_NAME
        install_dir = $installDir; host = $hostIp
        http_port = $OLLAMA_INTERNAL_PORT
        http_url = "http://${displayHost}:${OLLAMA_INTERNAL_PORT}"
        deploy_mode = "os"; running = $true; version = ""
    }
    try { $state.version = (& ollama --version 2>&1) -replace "ollama version ", "" } catch {}
    $state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8
    exit 0
}

# ── Step 4: Resolve Python for Web UI ────────────────────────────────────────
Log "Resolving Python..."
$pythonCmd = $null
foreach ($py in @("python3", "python", "py")) {
    try {
        $ver = & $py --version 2>&1
        if ($ver -match "Python 3") { $pythonCmd = $py; break }
    } catch {}
}
if (-not $pythonCmd) {
    Log "Python 3 not found. Installing via winget..."
    try {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $pythonCmd = "python"
    } catch {
        Log "ERROR: Could not install Python."
        exit 1
    }
}
Log "Using Python: $pythonCmd"

# ── Step 5: Setup Web UI venv ────────────────────────────────────────────────
Log "Setting up Web UI virtual environment..."
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonCmd -m venv $venvDir
}
& $venvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $venvPython -m pip install flask requests --quiet 2>&1

# ── Step 6: Copy Web UI files ────────────────────────────────────────────────
Log "Copying Web UI files..."
$scriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonDir = Join-Path $scriptRoot "Ollama\common"
if (Test-Path $commonDir) {
    Copy-Item -Path "$commonDir\*" -Destination $installDir -Recurse -Force
    Log "Web UI files copied to $installDir"
}

# ── Step 7: Generate startup script ──────────────────────────────────────────
Log "Creating startup script..."
$startScript = Join-Path $installDir "start-ollama-webui.py"
$webPort = $httpPort
$pyLines = @(
    "#!/usr/bin/env python3",
    "import os, sys, ssl, subprocess, threading, time",
    "",
    "OLLAMA_INTERNAL = 'http://127.0.0.1:${OLLAMA_INTERNAL_PORT}'",
    "HTTP_PORT_STR = os.environ.get('OLLAMA_WEB_PORT', '${webPort}').strip()",
    "HTTPS_PORT = os.environ.get('OLLAMA_HTTPS_PORT', '${httpsPort}').strip()",
    "CERT_FILE = os.environ.get('OLLAMA_CERT_FILE', '')",
    "KEY_FILE = os.environ.get('OLLAMA_KEY_FILE', '')",
    "",
    "# Ensure Ollama is running internally",
    "def ensure_ollama():",
    "    try:",
    "        import urllib.request",
    "        urllib.request.urlopen(OLLAMA_INTERNAL + '/api/tags', timeout=3)",
    "    except Exception:",
    "        print('[Startup] Starting Ollama server...')",
    "        env = dict(os.environ)",
    "        env['OLLAMA_HOST'] = '127.0.0.1:${OLLAMA_INTERNAL_PORT}'",
    "        env['OLLAMA_ORIGINS'] = '*'",
    "        subprocess.Popen(['ollama', 'serve'], env=env, creationflags=0x00000008)",
    "        time.sleep(5)",
    "",
    "def run_https(app, port, certfile, keyfile):",
    "    try:",
    "        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)",
    "        ctx.minimum_version = ssl.TLSVersion.TLSv1_2",
    "        ctx.load_cert_chain(os.path.normpath(certfile), os.path.normpath(keyfile))",
    "        from werkzeug.serving import make_server",
    "        server = make_server('0.0.0.0', port, app, ssl_context=ctx, threaded=True)",
    "        print(f'Ollama HTTPS on https://0.0.0.0:{port}')",
    "        server.serve_forever()",
    "    except Exception as e:",
    "        print(f'HTTPS failed: {e}')",
    "",
    "if __name__ == '__main__':",
    "    ensure_ollama()",
    "    os.environ['OLLAMA_API_BASE'] = OLLAMA_INTERNAL",
    "    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))",
    "    from ollama_web import app",
    "    http_port = int(HTTP_PORT_STR) if HTTP_PORT_STR and HTTP_PORT_STR.isdigit() and int(HTTP_PORT_STR) > 0 else 0",
    "    has_https = HTTPS_PORT and HTTPS_PORT.isdigit() and int(HTTPS_PORT) > 0 and CERT_FILE and KEY_FILE and os.path.isfile(os.path.normpath(CERT_FILE)) and os.path.isfile(os.path.normpath(KEY_FILE))",
    "    if has_https and http_port > 0:",
    "        t = threading.Thread(target=run_https, args=(app, int(HTTPS_PORT), CERT_FILE, KEY_FILE), daemon=True)",
    "        t.start()",
    "        print(f'Ollama Web UI on http://0.0.0.0:{http_port}')",
    "        app.run(host='0.0.0.0', port=http_port)",
    "    elif has_https:",
    "        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)",
    "        ctx.minimum_version = ssl.TLSVersion.TLSv1_2",
    "        ctx.load_cert_chain(os.path.normpath(CERT_FILE), os.path.normpath(KEY_FILE))",
    "        print(f'Ollama Web UI on https://0.0.0.0:{HTTPS_PORT} (HTTPS only)')",
    "        app.run(host='0.0.0.0', port=int(HTTPS_PORT), ssl_context=ctx)",
    "    elif http_port > 0:",
    "        print(f'Ollama Web UI on http://0.0.0.0:{http_port}')",
    "        app.run(host='0.0.0.0', port=http_port)",
    "    else:",
    "        print('No HTTP or HTTPS port configured.')"
)
$pyLines -join "`n" | Set-Content -Path $startScript -Encoding UTF8

# ── Step 8: SSL certificate ──────────────────────────────────────────────────
$certFile = Join-Path $certDir "ollama.crt"
$keyFile  = Join-Path $certDir "ollama.key"
if ($httpsPort -and $httpsPort -ne "0") {
    if (-not (Test-Path $certFile)) {
        Log "Generating self-signed SSL certificate..."
        $cn = $domain
        if (-not $cn) { $cn = $hostIp }
        if (-not $cn -or $cn -eq "0.0.0.0") { $cn = "localhost" }
        $opensslPath = Get-Command "openssl" -ErrorAction SilentlyContinue
        if ($opensslPath) {
            & openssl req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days 3650 -subj "/CN=$cn/O=ServerInstaller/C=US" 2>&1
            Log "SSL certificate created."
        } else {
            Log "openssl not found — HTTPS not available."
        }
    }
}

# ── Step 9: Register as Scheduled Task ───────────────────────────────────────
Log "Registering auto-start task..."
$taskName = $OLLAMA_SERVICE_NAME
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

$taskEnvArgs = "`"$startScript`""
$action = New-ScheduledTaskAction `
    -Execute $venvPython `
    -Argument $taskEnvArgs `
    -WorkingDirectory $installDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval ([TimeSpan]::FromMinutes(1))

# Set environment variables for the task
$env:OLLAMA_WEB_PORT = $webPort
$env:OLLAMA_HTTPS_PORT = $httpsPort
$env:OLLAMA_CERT_FILE = $certFile
$env:OLLAMA_KEY_FILE = $keyFile
$env:OLLAMA_API_BASE = "http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Log "Task '$taskName' registered and started."

# ── Step 10: Firewall ────────────────────────────────────────────────────────
Log "Configuring firewall..."
if ($httpPort) {
    try { New-NetFirewallRule -DisplayName "Ollama HTTP $httpPort" -Direction Inbound -LocalPort $httpPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {}
}
if ($httpsPort) {
    try { New-NetFirewallRule -DisplayName "Ollama HTTPS $httpsPort" -Direction Inbound -LocalPort $httpsPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {}
}

# ── Step 11: Save state ──────────────────────────────────────────────────────
$displayHost = $hostIp
if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
    $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    if (-not $displayHost) { $displayHost = "127.0.0.1" }
}

$httpUrl = ""
$httpsUrl = ""
if ($httpPort) { $httpUrl = "http://${displayHost}:${httpPort}" }
if ($httpsPort) { $httpsUrl = "https://${displayHost}:${httpsPort}" }

$state = @{
    installed         = $true
    service_name      = $OLLAMA_SERVICE_NAME
    install_dir       = $installDir
    venv_dir          = $venvDir
    host              = $hostIp
    domain            = $domain
    http_port         = $httpPort
    https_port        = $httpsPort
    http_url          = $httpUrl
    https_url         = $httpsUrl
    deploy_mode       = "os"
    auth_enabled      = [bool]$username
    auth_username     = $username
    running           = $true
    version           = ""
    ollama_internal   = "http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
}
try { $state.version = (& ollama --version 2>&1) -replace "ollama version ", "" } catch {}

$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

# ── Done ─────────────────────────────────────────────────────────────────────
Log ""
Log "================================================================="
Log " Ollama Installation Complete!"
Log "================================================================="
if ($httpUrl) { Log " Web UI (HTTP):  $httpUrl" }
if ($httpsUrl) { Log " Web UI (HTTPS): $httpsUrl" }
Log " Ollama API:     http://127.0.0.1:${OLLAMA_INTERNAL_PORT}"
Log " Service:        $OLLAMA_SERVICE_NAME"
Log "================================================================="
Log ""
Log "Quick start: ollama pull llama3.2"
