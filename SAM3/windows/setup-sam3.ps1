$ErrorActionPreference = "Stop"

# ============================================================
# SAM3 Windows Installer
# Installs SAM3 (Segment Anything Model 3) as a managed service
# Supports: OS service, IIS reverse proxy, Docker
# ============================================================

$SAM3_SERVICE_NAME = "ServerInstaller-SAM3"
$programData = [Environment]::GetFolderPath("CommonApplicationData")
$stateDir = Join-Path $programData "Server-Installer\sam3"
$statePath = Join-Path $stateDir "sam3-state.json"
$installDir = Join-Path $programData "Server-Installer\sam3\app"
$venvDir = Join-Path $installDir "venv"
$modelDir = Join-Path $installDir "models"
$tempVideoDir = Join-Path $installDir "temp\videos"
$certDir = Join-Path $programData "Server-Installer\sam3\certs"
$nginxConfDir = Join-Path $programData "Server-Installer\sam3\nginx"

# Read environment variables
$hostIp = if ($env:SAM3_HOST_IP) { $env:SAM3_HOST_IP.Trim() } else { "" }
$httpPort = if ($env:SAM3_HTTP_PORT) { $env:SAM3_HTTP_PORT.Trim() } else { "" }
$httpsPort = if ($env:SAM3_HTTPS_PORT) { $env:SAM3_HTTPS_PORT.Trim() } else { "" }
$domain = if ($env:SAM3_DOMAIN) { $env:SAM3_DOMAIN.Trim() } else { "" }
$username = if ($env:SAM3_USERNAME) { $env:SAM3_USERNAME.Trim() } else { "" }
$password = if ($env:SAM3_PASSWORD) { $env:SAM3_PASSWORD.Trim() } else { "" }
$useOsAuth = if ($env:SAM3_USE_OS_AUTH) { $env:SAM3_USE_OS_AUTH.Trim().ToLowerInvariant() } else { "" }
$gpuDevice = if ($env:SAM3_GPU_DEVICE) { $env:SAM3_GPU_DEVICE.Trim() } else { "" }
$downloadModel = if ($env:SAM3_DOWNLOAD_MODEL) { $env:SAM3_DOWNLOAD_MODEL.Trim().ToLowerInvariant() } else { "" }
$deployMode = if ($env:SAM3_DEPLOY_MODE) { $env:SAM3_DEPLOY_MODE.Trim().ToLowerInvariant() } else { "" }
$pythonVersion = if ($env:PYTHON_VERSION) { $env:PYTHON_VERSION.Trim() } else { "" }

if (-not $httpPort) { $httpPort = "5000" }
if (-not $httpsPort) { $httpsPort = "5443" }
if (-not $pythonVersion) { $pythonVersion = "3.12" }
if (-not $deployMode) { $deployMode = "os" }

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
New-Item -ItemType Directory -Force -Path $tempVideoDir | Out-Null
New-Item -ItemType Directory -Force -Path $certDir | Out-Null

# ── GPU/TPU Detection ──────────────────────────────────────

function Detect-GPU {
    $gpus = @()
    try {
        $wmiGpus = Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue
        foreach ($gpu in $wmiGpus) {
            $name = $gpu.Name
            $vram = [math]::Round($gpu.AdapterRAM / 1GB, 1)
            $isNvidia = $name -match "NVIDIA|GeForce|RTX|GTX|Quadro|Tesla|A100|H100|DGX"
            $isAmd = $name -match "AMD|Radeon|RX"
            $isIntel = $name -match "Intel.*Arc|Intel.*Xe"
            $type = "cpu"
            if ($isNvidia) { $type = "cuda" }
            elseif ($isAmd) { $type = "rocm" }
            elseif ($isIntel) { $type = "xpu" }
            $gpus += [PSCustomObject]@{
                Name = $name
                VRAM_GB = $vram
                Type = $type
            }
        }
    } catch {}

    # Check for NVIDIA CUDA
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvidiaSmi) {
        try {
            $smiOutput = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
            if ($smiOutput) {
                Write-Host "[INFO] NVIDIA GPU detected via nvidia-smi:" -ForegroundColor Green
                Write-Host "  $smiOutput"
            }
        } catch {}
    }

    return $gpus
}

$detectedGpus = Detect-GPU
$selectedDevice = "cpu"
if ($gpuDevice -and $gpuDevice -ne "auto") {
    $selectedDevice = $gpuDevice
} elseif ($detectedGpus.Count -gt 0) {
    $nvidiaGpu = $detectedGpus | Where-Object { $_.Type -eq "cuda" } | Select-Object -First 1
    if ($nvidiaGpu) {
        $selectedDevice = "cuda"
        Write-Host "[INFO] Auto-selected NVIDIA GPU: $($nvidiaGpu.Name) ($($nvidiaGpu.VRAM_GB) GB)" -ForegroundColor Green
    } else {
        $amdGpu = $detectedGpus | Where-Object { $_.Type -eq "rocm" } | Select-Object -First 1
        if ($amdGpu) {
            $selectedDevice = "rocm"
            Write-Host "[INFO] Auto-selected AMD GPU: $($amdGpu.Name)" -ForegroundColor Green
        }
    }
}

Write-Host "[INFO] SAM3 will use device: $selectedDevice" -ForegroundColor Cyan

# ── Python Resolution ──────────────────────────────────────

function Resolve-Python {
    param([string]$Version)
    foreach ($cmdName in @("python.exe", "python3.exe")) {
        $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $output = & $cmd.Source -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
                if ($output -and $LASTEXITCODE -eq 0) {
                    $lines = @($output | Where-Object { $_ -and $_.Trim() })
                    if ($lines.Count -ge 1 -and $lines[1].StartsWith("$Version.")) {
                        return $lines[0].Trim()
                    }
                }
            } catch {}
        }
    }
    # Try py launcher
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $output = & $py.Source "-$Version" -c "import sys; print(sys.executable)" 2>$null
            if ($output -and $LASTEXITCODE -eq 0) {
                return ($output | Select-Object -First 1).Trim()
            }
        } catch {}
    }
    return $null
}

$pythonExe = Resolve-Python -Version $pythonVersion
if (-not $pythonExe) {
    Write-Host "[WARN] Python $pythonVersion not found, trying system python3..." -ForegroundColor Yellow
    $cmd = Get-Command python3.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue }
    if ($cmd) { $pythonExe = $cmd.Source }
}
if (-not $pythonExe) {
    throw "Python is not installed. Install Python $pythonVersion first using the Python service page."
}
Write-Host "[INFO] Using Python: $pythonExe"

# ── Copy SAM3 Application Files ────────────────────────────

$scriptRoot = Split-Path -Parent $PSScriptRoot
$commonDir = Join-Path $scriptRoot "common"

Write-Host "[INFO] Copying SAM3 application files..."
foreach ($subdir in @("core", "web\templates", "web\static\js", "web\static\css")) {
    $target = Join-Path $installDir $subdir
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}

$filesToCopy = @(
    "app.py", "requirements.txt",
    "core\detector.py", "core\video_processor.py", "core\tracker.py",
    "core\exporter.py", "core\utils.py", "core\__init__.py",
    "web\templates\index.html",
    "web\static\js\dashboard.js",
    "web\static\css\dashboard.css"
)

foreach ($file in $filesToCopy) {
    $src = Join-Path $commonDir $file
    $dst = Join-Path $installDir $file
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
    } else {
        Write-Host "[WARN] Missing source file: $file" -ForegroundColor Yellow
    }
}

# ── Create Virtual Environment & Install Dependencies ──────

if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
    Write-Host "[INFO] Creating virtual environment..."
    & $pythonExe -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment." }
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

Write-Host "[INFO] Upgrading pip..."
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] pip upgrade had issues" -ForegroundColor Yellow }

# Install PyTorch based on GPU selection
Write-Host "[INFO] Installing PyTorch for device: $selectedDevice..."
if ($selectedDevice -eq "cuda") {
    & $venvPip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
} elseif ($selectedDevice -eq "rocm") {
    & $venvPip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.0
} else {
    & $venvPip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
}
if ($LASTEXITCODE -ne 0) { throw "Failed to install PyTorch." }

Write-Host "[INFO] Installing SAM3 requirements..."
$reqFile = Join-Path $installDir "requirements.txt"
& $venvPip install -r $reqFile
if ($LASTEXITCODE -ne 0) { throw "Failed to install SAM3 requirements." }

# Install CLIP (required separately)
Write-Host "[INFO] Installing CLIP..."
& $venvPip install "git+https://github.com/ultralytics/CLIP.git"
if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] CLIP installation had issues - exemplar detection may not work" -ForegroundColor Yellow }

# ── SSL Certificates ───────────────────────────────────────

$certFile = Join-Path $certDir "sam3.crt"
$keyFile = Join-Path $certDir "sam3.key"

if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
    Write-Host "[INFO] Generating self-signed SSL certificate..."
    $opensslExe = Get-Command openssl.exe -ErrorAction SilentlyContinue
    if ($opensslExe) {
        $certCN = $domain
        if (-not $certCN) { $certCN = $hostIp }
        if (-not $certCN) { $certCN = 'localhost' }
        $subj = "/CN=$certCN/O=ServerInstaller/C=US"
        & $opensslExe.Source req -x509 -nodes -newkey rsa:2048 -keyout $keyFile -out $certFile -days 3650 -subj $subj 2>$null
    } else {
        Write-Host "[WARN] OpenSSL not found. HTTPS will use system-generated certificates." -ForegroundColor Yellow
    }
}

# ── Model Download ─────────────────────────────────────────

$modelPath = Join-Path $modelDir "sam3.pt"
if ($downloadModel -in @("1", "true", "yes", "y", "on")) {
    if (-not (Test-Path $modelPath)) {
        Write-Host "[INFO] Downloading SAM3 model (sam3.pt ~3.4 GB)... This may take a while." -ForegroundColor Cyan
        try {
            # Download using ultralytics built-in download
            & $venvPython -c "from ultralytics import SAM; model = SAM('sam3.pt')" 2>$null
            # Move the downloaded model to our model directory
            $defaultModelPath = Join-Path $installDir "sam3.pt"
            if (Test-Path $defaultModelPath) {
                Move-Item -Path $defaultModelPath -Destination $modelPath -Force
            }
            Write-Host "[INFO] SAM3 model downloaded successfully." -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Model download failed: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "[INFO] You can download the model manually later from the dashboard." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] SAM3 model already exists at: $modelPath"
    }
}

# ── Create Startup Script ──────────────────────────────────

$startupScript = Join-Path $installDir "start-sam3.py"
$startupContent = @"
import os, sys, ssl, functools, threading
from flask import request, Response

os.environ.setdefault('SAM3_MODEL_PATH', os.path.join(os.path.dirname(__file__), 'models', 'sam3.pt'))
os.environ.setdefault('SAM3_DEVICE', '$selectedDevice')
os.environ.setdefault('SAM3_HOST', '0.0.0.0')
os.environ.setdefault('SAM3_PORT', '$httpPort')

sys.path.insert(0, os.path.dirname(__file__))

SAM3_USERNAME = os.environ.get('SAM3_USERNAME', '$username')
SAM3_PASSWORD = os.environ.get('SAM3_PASSWORD', '$password')
SAM3_USE_OS_AUTH = os.environ.get('SAM3_USE_OS_AUTH', '$useOsAuth')
SAM3_HTTPS_PORT = os.environ.get('SAM3_HTTPS_PORT', '$httpsPort')
SAM3_CERT_FILE = os.environ.get('SAM3_CERT_FILE', r'$certFile')
SAM3_KEY_FILE = os.environ.get('SAM3_KEY_FILE', r'$keyFile')

from app import app

def check_auth(u, p):
    if SAM3_USE_OS_AUTH in ('1', 'true', 'yes'):
        try:
            import ctypes
            advapi32 = ctypes.windll.advapi32
            token = ctypes.c_void_p()
            result = advapi32.LogonUserW(u, None, p, 2, 0, ctypes.byref(token))
            if token.value:
                ctypes.windll.kernel32.CloseHandle(token)
            return bool(result)
        except Exception:
            return False
    return u == SAM3_USERNAME and p == SAM3_PASSWORD

def authenticate():
    return Response('Authentication required', 401, {'WWW-Authenticate': 'Basic realm="SAM3"'})

def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not SAM3_USERNAME and SAM3_USE_OS_AUTH not in ('1', 'true', 'yes'):
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

for rule in list(app.url_map.iter_rules()):
    endpoint = app.view_functions.get(rule.endpoint)
    if endpoint and rule.endpoint != 'static':
        app.view_functions[rule.endpoint] = requires_auth(endpoint)

def run_https(app, host, port, certfile, keyfile):
    try:
        certfile = os.path.normpath(certfile)
        keyfile = os.path.normpath(keyfile)
        print(f'SAM3 HTTPS: loading cert={certfile} key={keyfile}')
        if not os.path.isfile(certfile):
            print(f'SAM3 HTTPS ERROR: cert file not found: {certfile}')
            return
        if not os.path.isfile(keyfile):
            print(f'SAM3 HTTPS ERROR: key file not found: {keyfile}')
            return
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile, keyfile)
        from werkzeug.serving import make_server
        server = make_server(host, port, app, ssl_context=ctx, threaded=True)
        print(f'SAM3 HTTPS running on https://{host}:{port}')
        server.serve_forever()
    except Exception as e:
        import traceback
        print(f'SAM3 HTTPS server failed: {e}')
        traceback.print_exc()

if __name__ == '__main__':
    host = os.environ.get('SAM3_HOST', '0.0.0.0')
    http_port = int(os.environ.get('SAM3_PORT', $httpPort))

    https_port = SAM3_HTTPS_PORT.strip()
    cert_path = os.path.normpath(SAM3_CERT_FILE) if SAM3_CERT_FILE else ''
    key_path = os.path.normpath(SAM3_KEY_FILE) if SAM3_KEY_FILE else ''
    if https_port and https_port.isdigit() and os.path.isfile(cert_path) and os.path.isfile(key_path):
        https_thread = threading.Thread(
            target=run_https,
            args=(app, host, int(https_port), cert_path, key_path),
            daemon=True,
        )
        https_thread.start()
        print(f'SAM3 starting HTTP on http://{host}:{http_port} and HTTPS on https://{host}:{https_port}')
    else:
        if https_port and https_port.isdigit():
            print(f'SAM3 HTTPS: cert not found at {cert_path} or {key_path} - HTTPS disabled')
        print(f'SAM3 starting on http://{host}:{http_port}')

    app.run(host=host, port=http_port, debug=False, threaded=True)
"@
Set-Content -Path $startupScript -Value $startupContent -Encoding UTF8

# app.py now natively reads SAM3_MODEL_PATH and SAM3_DEVICE env vars - no patching needed

# ── Create Windows Service (NSSM or native) ───────────────

if ($deployMode -eq "os") {
    Write-Host "[INFO] Setting up SAM3 as Windows service..."

    # Use NSSM if available, otherwise create a scheduled task
    $nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($nssm) {
        & $nssm.Source stop $SAM3_SERVICE_NAME 2>$null | Out-Null
        & $nssm.Source remove $SAM3_SERVICE_NAME confirm 2>$null | Out-Null
        & $nssm.Source install $SAM3_SERVICE_NAME $venvPython $startupScript
        & $nssm.Source set $SAM3_SERVICE_NAME AppDirectory $installDir
        & $nssm.Source set $SAM3_SERVICE_NAME Description "SAM3 AI Object Detection Service"
        & $nssm.Source set $SAM3_SERVICE_NAME Start SERVICE_AUTO_START
        & $nssm.Source set $SAM3_SERVICE_NAME AppEnvironmentExtra "SAM3_MODEL_PATH=$modelPath" "SAM3_DEVICE=$selectedDevice" "SAM3_HOST=0.0.0.0" "SAM3_PORT=$httpPort"
        if ($username) {
            & $nssm.Source set $SAM3_SERVICE_NAME AppEnvironmentExtra+ "SAM3_USERNAME=$username" "SAM3_PASSWORD=$password" "SAM3_USE_OS_AUTH=$useOsAuth"
        }
        & $nssm.Source start $SAM3_SERVICE_NAME
        Write-Host "[INFO] SAM3 Windows service created and started via NSSM."
    } else {
        # Fallback: create a scheduled task that auto-starts
        $taskName = $SAM3_SERVICE_NAME
        $action = New-ScheduledTaskAction -Execute $venvPython -Argument "`"$startupScript`"" -WorkingDirectory $installDir
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "SAM3 AI Object Detection Service" -RunLevel Highest -User "SYSTEM" | Out-Null
        Start-ScheduledTask -TaskName $taskName
        Write-Host "[INFO] SAM3 scheduled task created and started."
    }
}

# ── IIS Reverse Proxy (if mode=iis) ───────────────────────

if ($deployMode -eq "iis") {
    Write-Host "[INFO] Configuring IIS reverse proxy for SAM3..."
    Import-Module WebAdministration -ErrorAction SilentlyContinue

    $siteName = "SAM3"
    $appPoolName = "SAM3Pool"

    # Ensure IIS features
    $features = @("IIS-WebServerRole", "IIS-WebServer", "IIS-CommonHttpFeatures", "IIS-RequestFiltering", "IIS-HttpRedirect", "IIS-ApplicationInit")
    foreach ($feature in $features) {
        Enable-WindowsOptionalFeature -Online -FeatureName $feature -NoRestart -ErrorAction SilentlyContinue | Out-Null
    }

    # Install URL Rewrite and ARR if not present
    Write-Host "[INFO] IIS reverse proxy will forward to http://localhost:$httpPort"

    # Create IIS site with reverse proxy config
    if (Get-IISAppPool -Name $appPoolName -ErrorAction SilentlyContinue) {
        Remove-WebAppPool -Name $appPoolName -ErrorAction SilentlyContinue
    }
    New-WebAppPool -Name $appPoolName -Force | Out-Null

    if (Get-Website -Name $siteName -ErrorAction SilentlyContinue) {
        Remove-Website -Name $siteName -ErrorAction SilentlyContinue
    }

    $iisDir = Join-Path $programData "Server-Installer\sam3\iis-root"
    New-Item -ItemType Directory -Force -Path $iisDir | Out-Null

    # Create web.config for reverse proxy
    $webConfig = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <system.webServer>
        <rewrite>
            <rules>
                <rule name="SAM3 Reverse Proxy" stopProcessing="true">
                    <match url="(.*)" />
                    <action type="Rewrite" url="http://localhost:$httpPort/{R:1}" />
                </rule>
            </rules>
        </rewrite>
    </system.webServer>
</configuration>
"@
    Set-Content -Path (Join-Path $iisDir "web.config") -Value $webConfig -Encoding UTF8

    New-Website -Name $siteName -ApplicationPool $appPoolName -PhysicalPath $iisDir -Port ([int]$httpsPort) -Ssl -Force | Out-Null

    # Add HTTPS binding with certificate
    if (Test-Path $certFile) {
        $cert = Import-PfxCertificate -FilePath $certFile -CertStoreLocation Cert:\LocalMachine\My -ErrorAction SilentlyContinue
        if ($cert) {
            New-WebBinding -Name $siteName -Protocol "https" -Port ([int]$httpsPort) -SslFlags 0 -ErrorAction SilentlyContinue
        }
    }

    Write-Host "[INFO] IIS reverse proxy configured for SAM3 on port $httpsPort"
}

# ── Open Firewall Ports ────────────────────────────────────

Write-Host "[INFO] Configuring firewall rules..."
New-NetFirewallRule -DisplayName "SAM3 HTTP" -Direction Inbound -Protocol TCP -LocalPort ([int]$httpPort) -Action Allow -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "SAM3 HTTPS" -Direction Inbound -Protocol TCP -LocalPort ([int]$httpsPort) -Action Allow -ErrorAction SilentlyContinue | Out-Null

# ── Detect Host IP ─────────────────────────────────────────

if (-not $hostIp) {
    $hostIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.IPAddress -ne "127.0.0.1" } | Select-Object -First 1).IPAddress
}
if (-not $hostIp) { $hostIp = "127.0.0.1" }

# ── Write State File ──────────────────────────────────────

$gpuInfo = @()
foreach ($gpu in $detectedGpus) {
    $gpuInfo += @{ name = $gpu.Name; vram_gb = $gpu.VRAM_GB; type = $gpu.Type }
}

$state = [ordered]@{
    service_name = $SAM3_SERVICE_NAME
    install_dir = $installDir
    venv_dir = $venvDir
    python_executable = $venvPython
    model_path = $modelPath
    model_downloaded = (Test-Path $modelPath)
    device = $selectedDevice
    detected_gpus = $gpuInfo
    host = $hostIp
    domain = $domain
    http_port = $httpPort
    https_port = $httpsPort
    http_url = "http://${hostIp}:${httpPort}"
    https_url = "https://${hostIp}:${httpsPort}"
    deploy_mode = $deployMode
    auth_enabled = [bool]($username -or ($useOsAuth -in @("1", "true", "yes")))
    auth_username = $username
    use_os_auth = ($useOsAuth -in @("1", "true", "yes"))
    cert_path = $certFile
    key_path = $keyFile
    running = $true
    updated_at = (Get-Date).ToString("o")
}

$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8

Write-Host ""
Write-Host "============================================================"
Write-Host "SAM3 Installation Complete" -ForegroundColor Green
Write-Host "============================================================"
Write-Host "Device: $selectedDevice"
Write-Host "HTTP:   http://${hostIp}:${httpPort}"
Write-Host "HTTPS:  https://${hostIp}:${httpsPort}"
Write-Host "Mode:   $deployMode"
if (Test-Path $modelPath) {
    Write-Host "Model:  Ready"
} else {
    Write-Host "Model:  Not downloaded (download from dashboard)"
}
Write-Host "============================================================"
