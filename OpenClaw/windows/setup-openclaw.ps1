# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Installer for Windows
# Installs real OpenClaw AI Agent platform via Node.js + npm
# ─────────────────────────────────────────────────────────────────────────────
param()
$ErrorActionPreference = "Stop"

$SERVICE_NAME = "ServerInstaller-OpenClaw"
$programData = [Environment]::GetFolderPath("CommonApplicationData")
if ($env:SERVER_INSTALLER_DATA_DIR) { $baseStateDir = $env:SERVER_INSTALLER_DATA_DIR } else { $baseStateDir = Join-Path $programData "Server-Installer" }
$stateDir   = Join-Path $baseStateDir "openclaw"
$statePath  = Join-Path $stateDir "openclaw-state.json"
$logFile    = Join-Path $stateDir "openclaw.log"

if ($env:OPENCLAW_HTTP_PORT)  { $httpPort  = $env:OPENCLAW_HTTP_PORT }  else { $httpPort  = "18789" }
if ($env:OPENCLAW_HTTPS_PORT) { $httpsPort = $env:OPENCLAW_HTTPS_PORT } else { $httpsPort = "" }
if ($env:OPENCLAW_HOST_IP)    { $hostIp    = $env:OPENCLAW_HOST_IP }    else { $hostIp    = "0.0.0.0" }
if ($env:OPENCLAW_DOMAIN)     { $domain    = $env:OPENCLAW_DOMAIN }     else { $domain    = "" }
if ($env:OPENCLAW_USERNAME)   { $username  = $env:OPENCLAW_USERNAME }   else { $username  = "" }
if ($env:OPENCLAW_PASSWORD)   { $password  = $env:OPENCLAW_PASSWORD }   else { $password  = "" }

function Log($msg) { Write-Host "[OpenClaw] $msg" }

foreach ($d in @($stateDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# ── Step 1: Check/Install Node.js ───────────────────────────────────────────
Log "Step 1: Checking Node.js..."
$nodeCmd = $null
try { $nodeVer = & node --version 2>$null; if ($nodeVer) { $nodeCmd = "node"; Log "Node.js $nodeVer found." } } catch {}

if (-not $nodeCmd) {
    Log "Installing Node.js..."
    $nodeUrl = "https://nodejs.org/dist/v22.16.0/node-v22.16.0-x64.msi"
    $nodeMsi = Join-Path $env:TEMP "node-install.msi"
    try {
        Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeMsi -UseBasicParsing
        Start-Process msiexec -ArgumentList "/i `"$nodeMsi`" /qn" -Wait -NoNewWindow
        # Add to PATH
        $env:PATH = "C:\Program Files\nodejs;$env:PATH"
        Remove-Item $nodeMsi -Force -ErrorAction SilentlyContinue
        Log "Node.js installed."
    } catch {
        Log "ERROR: Could not install Node.js. Install manually from https://nodejs.org/"
        exit 1
    }
}

try { $null = & node --version 2>$null } catch { Log "ERROR: node not in PATH."; exit 1 }
try { $null = & npm --version 2>$null } catch { Log "ERROR: npm not in PATH."; exit 1 }
Log "Node.js: $(& node --version)  npm: $(& npm --version)"

# ── Step 2: Install OpenClaw via npm ─────────────────────────────────────────
Log "Step 2: Installing OpenClaw..."
try {
    & npm install -g openclaw@latest 2>&1
    Log "OpenClaw installed."
} catch {
    Log "npm install failed: $_"
}

$openclawBin = $null
foreach ($p in @("openclaw", (Join-Path $env:APPDATA "npm\openclaw.cmd"), "C:\Program Files\nodejs\openclaw.cmd")) {
    try { $null = & $p --version 2>$null; $openclawBin = $p; break } catch {}
}
if (-not $openclawBin) {
    Log "ERROR: openclaw not found after install."
    exit 1
}
Log "OpenClaw binary: $openclawBin"

# ── Step 3: Create Scheduled Task for Gateway ────────────────────────────────
Log "Step 3: Setting up gateway service..."
$taskName = $SERVICE_NAME
$bindArg = "lan"
$taskCmd = "$openclawBin gateway --bind $bindArg --allow-unconfigured --port $httpPort --verbose"

# Remove existing task
try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$taskCmd > `"$logFile`" 2>&1`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
    Log "Scheduled task '$taskName' created."
} catch {
    Log "WARNING: Could not create scheduled task: $_"
}

# Start the task
try {
    Start-ScheduledTask -TaskName $taskName
    Log "Gateway started via scheduled task."
    Start-Sleep -Seconds 5
} catch {
    Log "Starting gateway directly..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c $taskCmd > `"$logFile`" 2>&1" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

# Check if running
$running = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$httpPort/" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    $running = $true
    Log "Gateway responding on port $httpPort."
} catch {
    Log "Gateway not responding yet. Check log: $logFile"
    if (Test-Path $logFile) { Get-Content $logFile -Tail 10 | ForEach-Object { Log "  $_" } }
}

# ── Step 4: Install Ollama & configure as default AI ─────────────────────────
Log "Step 4: Checking Ollama..."
$ollamaExists = $false
try { $null = & ollama --version 2>$null; $ollamaExists = $true } catch {}
if (-not $ollamaExists) {
    Log "Ollama not installed. Install it from the AI/ML page for local LLM support."
}

# Configure OpenClaw to use Ollama as default AI provider
$agentDir = Join-Path $env:USERPROFILE ".openclaw\agents\main\agent"
if (-not (Test-Path $agentDir)) { New-Item -ItemType Directory -Path $agentDir -Force | Out-Null }

# Write auth-profiles.json
$authProfiles = @{
    ollama = @{
        provider = "ollama"
        baseUrl  = "http://127.0.0.1:11434"
        apiKey   = "ollama"
    }
} | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $agentDir "auth-profiles.json") -Value $authProfiles -Encoding UTF8
Log "Auth profiles written."

# Write agent settings — default to Ollama
$ollamaModel = "llama3.2:3b"
if ($ollamaExists) {
    try {
        $modelList = & ollama list 2>$null
        $firstModel = ($modelList -split "`n" | Where-Object { $_ -notmatch "^NAME" } | Select-Object -First 1) -split '\s+' | Select-Object -First 1
        if ($firstModel) { $ollamaModel = $firstModel }
    } catch {}
}
$agentSettings = @{
    model              = "ollama/$ollamaModel"
    provider           = "ollama"
    customInstructions = ""
} | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $agentDir "settings.json") -Value $agentSettings -Encoding UTF8
Log "Agent settings written (model: ollama/$ollamaModel)."

# ── Step 5: Firewall ────────────────────────────────────────────────────────
foreach ($port in @($httpPort, $httpsPort)) {
    if ($port) {
        try {
            New-NetFirewallRule -DisplayName "OpenClaw $port" -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -ErrorAction SilentlyContinue
        } catch {}
    }
}

# ── Step 6: State file ──────────────────────────────────────────────────────
$displayHost = $hostIp
if ($displayHost -eq "0.0.0.0" -or $displayHost -eq "*" -or $displayHost -eq "") {
    try { $displayHost = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.*" } | Select-Object -First 1).IPAddress } catch { $displayHost = "127.0.0.1" }
}
$httpUrl = "http://${displayHost}:${httpPort}"
$httpsUrl = ""
if ($httpsPort) { $httpsUrl = "https://${displayHost}:${httpsPort}" }

$state = @{
    installed       = $true
    service_name    = $SERVICE_NAME
    host            = $hostIp
    domain          = $domain
    http_port       = $httpPort
    https_port      = $httpsPort
    http_url        = $httpUrl
    https_url       = $httpsUrl
    deploy_mode     = "os"
    running         = $running
    openclaw_bin    = $openclawBin
    gateway_port    = $httpPort
}
$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

Log ""
Log "================================================================="
Log " OpenClaw Installation Complete!"
Log "================================================================="
Log " Dashboard:      $httpUrl"
if ($httpsUrl) { Log " HTTPS:          $httpsUrl" }
Log " Gateway:        ws://${displayHost}:${httpPort}"
Log " CLI:            $openclawBin --help"
Log "================================================================="
