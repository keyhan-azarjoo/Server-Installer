# ─────────────────────────────────────────────────────────────────────────────
# Ollama Installer for Windows
# Installs Ollama LLM server + Web UI proxy with HTTPS, auth, and auto-start
# ─────────────────────────────────────────────────────────────────────────────
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ── Configuration ────────────────────────────────────────────────────────────
$OLLAMA_SERVICE_NAME = "ServerInstaller-Ollama"
$programData         = [Environment]::GetFolderPath("CommonApplicationData")
if ($env:SERVER_INSTALLER_DATA_DIR) { $baseStateDir = $env:SERVER_INSTALLER_DATA_DIR } else { $baseStateDir = Join-Path $programData "Server-Installer" }
$stateDir            = Join-Path $baseStateDir "ollama"
$statePath           = Join-Path $stateDir "ollama-state.json"
$installDir          = Join-Path $stateDir "app"
$venvDir             = Join-Path $installDir "venv"
$certDir             = Join-Path $stateDir "certs"
$logFile             = Join-Path $stateDir "ollama.log"

if ($env:OLLAMA_HTTP_PORT)  { $httpPort  = $env:OLLAMA_HTTP_PORT }  else { $httpPort  = "11434" }
if ($env:OLLAMA_HTTPS_PORT) { $httpsPort = $env:OLLAMA_HTTPS_PORT } else { $httpsPort = "" }
if ($env:OLLAMA_HOST_IP)    { $hostIp    = $env:OLLAMA_HOST_IP }    else { $hostIp    = "0.0.0.0" }
if ($env:OLLAMA_DOMAIN)     { $domain    = $env:OLLAMA_DOMAIN }     else { $domain    = "" }
if ($env:OLLAMA_USERNAME)   { $username  = $env:OLLAMA_USERNAME }   else { $username  = "" }
if ($env:OLLAMA_PASSWORD)   { $password  = $env:OLLAMA_PASSWORD }   else { $password  = "" }
$webUiPort  = 3080  # Web UI proxy port

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
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $ollamaPath = Get-Command "ollama" -ErrorAction SilentlyContinue
        if ($ollamaPath) {
            Log "Ollama installed successfully: $($ollamaPath.Source)"
        } else {
            Log "WARNING: Ollama installed but not found in PATH. Trying default location..."
            $defaultOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
            if (Test-Path $defaultOllama) {
                $env:Path += ";$(Split-Path $defaultOllama)"
                Log "Found at: $defaultOllama"
            }
        }
    } catch {
        Log "ERROR: Failed to download Ollama: $_"
        Log "Please install Ollama manually from https://ollama.com/download"
        exit 1
    }
} else {
    Log "Ollama already installed: $($ollamaPath.Source)"
}

# ── Step 2: Start Ollama service ─────────────────────────────────────────────
Log "Ensuring Ollama service is running..."
$env:OLLAMA_HOST = "${hostIp}:${httpPort}"
try {
    $ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $ollamaProcess) {
        Log "Starting Ollama server on ${hostIp}:${httpPort}..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    } else {
        Log "Ollama is already running (PID: $($ollamaProcess.Id))"
    }
} catch {
    Log "WARNING: Could not start Ollama: $_"
}

# ── Step 3: Resolve Python for Web UI ────────────────────────────────────────
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
        Log "ERROR: Could not install Python. Please install Python 3.10+ manually."
        exit 1
    }
}
Log "Using Python: $pythonCmd"

# ── Step 4: Setup Web UI virtual environment ─────────────────────────────────
Log "Setting up Web UI virtual environment..."
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonCmd -m venv $venvDir
}
& $venvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $venvPython -m pip install flask requests --quiet 2>&1

# ── Step 5: Copy Web UI files ────────────────────────────────────────────────
Log "Copying Web UI files..."
$scriptRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$commonDir = Join-Path $scriptRoot "Ollama\common"
if (Test-Path $commonDir) {
    Copy-Item -Path "$commonDir\*" -Destination $installDir -Recurse -Force
    Log "Web UI files copied to $installDir"
} else {
    Log "WARNING: Common directory not found at $commonDir"
}

# ── Step 6: Generate startup script ──────────────────────────────────────────
Log "Creating startup script..."
$startScript = Join-Path $installDir "start-ollama-webui.py"
@"
#!/usr/bin/env python3
import os, sys, subprocess, threading, time

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "0.0.0.0:${httpPort}")
WEB_UI_PORT = int(os.environ.get("OLLAMA_WEBUI_PORT", "${webUiPort}"))

# Ensure Ollama is running
def ensure_ollama():
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:${httpPort}/api/tags", timeout=3)
    except Exception:
        print("[Startup] Starting Ollama server...")
        subprocess.Popen(["ollama", "serve"], env={**os.environ, "OLLAMA_HOST": OLLAMA_HOST})
        time.sleep(5)

if __name__ == "__main__":
    ensure_ollama()
    sys.path.insert(0, os.path.dirname(__file__))
    from ollama_web import app
    app.run(host="0.0.0.0", port=WEB_UI_PORT)
"@ | Set-Content -Path $startScript -Encoding UTF8

# ── Step 7: Generate self-signed SSL cert ────────────────────────────────────
if ($httpsPort -and $httpsPort -ne "0") {
    $certFile = Join-Path $certDir "ollama.crt"
    $keyFile  = Join-Path $certDir "ollama.key"
    if (-not (Test-Path $certFile)) {
        Log "Generating self-signed SSL certificate..."
        $cn = $domain
        if (-not $cn) { $cn = $hostIp }
        $opensslPath = Get-Command "openssl" -ErrorAction SilentlyContinue
        if ($opensslPath) {
            & openssl req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days 3650 -subj "/CN=$cn/O=ServerInstaller/C=US" 2>&1
            Log "SSL certificate created."
        } else {
            Log "openssl not found — skipping SSL cert generation."
        }
    }
}

# ── Step 8: Register as Windows Scheduled Task ───────────────────────────────
Log "Registering auto-start task..."
$taskName = $OLLAMA_SERVICE_NAME
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

$action = New-ScheduledTaskAction `
    -Execute $venvPython `
    -Argument "`"$startScript`"" `
    -WorkingDirectory $installDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval ([TimeSpan]::FromMinutes(1))

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Log "Task '$taskName' registered and started."

# ── Step 9: Open firewall ports ──────────────────────────────────────────────
Log "Configuring firewall..."
foreach ($p in @($httpPort, $webUiPort)) {
    try {
        New-NetFirewallRule -DisplayName "Ollama $p" -Direction Inbound -LocalPort $p -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    } catch {}
}
if ($httpsPort -and $httpsPort -ne "0") {
    try {
        New-NetFirewallRule -DisplayName "Ollama HTTPS $httpsPort" -Direction Inbound -LocalPort $httpsPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
    } catch {}
}

# ── Step 10: Save state ──────────────────────────────────────────────────────
$displayHost = $hostIp
if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
    $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    if (-not $displayHost) { $displayHost = "127.0.0.1" }
}

$state = @{
    installed         = $true
    service_name      = $OLLAMA_SERVICE_NAME
    install_dir       = $installDir
    venv_dir          = $venvDir
    host              = $hostIp
    domain            = $domain
    http_port         = $httpPort
    https_port        = $httpsPort
    webui_port        = "$webUiPort"
    http_url          = "http://${displayHost}:${httpPort}"
    webui_url         = "http://${displayHost}:${webUiPort}"
    https_url         = ""
    deploy_mode       = "os"
    auth_enabled      = [bool]$username
    auth_username     = $username
    running           = $true
    version           = ""
}
try { $state.version = (& ollama --version 2>&1) -replace "ollama version ", "" } catch {}
if ($httpsPort) { $state.https_url = "https://${displayHost}:${httpsPort}" }

$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

# ── Done ─────────────────────────────────────────────────────────────────────
Log ""
Log "================================================================="
Log " Ollama Installation Complete!"
Log "================================================================="
Log " Ollama API:  http://${displayHost}:${httpPort}"
Log " Web UI:      http://${displayHost}:${webUiPort}"
if ($httpsPort) { Log " HTTPS:       https://${displayHost}:${httpsPort}" }
Log " Service:     $OLLAMA_SERVICE_NAME"
Log " State:       $statePath"
Log "================================================================="
Log ""
Log "Quick start: ollama pull llama3.2"
Log "Then chat:   ollama run llama3.2"
