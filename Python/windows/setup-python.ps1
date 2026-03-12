$ErrorActionPreference = "Stop"

function Resolve-PythonFromLauncher {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $py) {
        return $null
    }

    $output = & $py.Source "-$Version" -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
    if (-not $output -or $LASTEXITCODE -ne 0) {
        return $null
    }

    $lines = @($output | Where-Object { $_ -and $_.Trim() })
    if ($lines.Count -lt 1) {
        return $null
    }

    return [PSCustomObject]@{
        Executable = $lines[0].Trim()
        Version = if ($lines.Count -gt 1) { $lines[1].Trim() } else { "" }
    }
}

function Install-PythonWithWinget {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget.exe is required to install Python automatically."
    }

    $packageId = "Python.Python.$Version"
    Write-Host "Installing $packageId via winget..."
    & $winget.Source install --id $packageId --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget install failed for $packageId."
    }
}

function Ensure-Pip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    & $PythonExe -m ensurepip --upgrade 2>$null | Out-Null
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }
}

$requestedVersion = ($env:PYTHON_VERSION | ForEach-Object { $_.Trim() })
if (-not $requestedVersion) {
    $requestedVersion = "3.12"
}

$installJupyter = (($env:PYTHON_INSTALL_JUPYTER | ForEach-Object { $_.Trim().ToLowerInvariant() }) -in @("1", "true", "yes", "y", "on"))
$jupyterPort = ($env:PYTHON_JUPYTER_PORT | ForEach-Object { $_.Trim() })
$hostIp = ($env:PYTHON_HOST_IP | ForEach-Object { $_.Trim() })
$programData = [Environment]::GetFolderPath("CommonApplicationData")
$stateDir = Join-Path $programData "Server-Installer\python"
$statePath = Join-Path $stateDir "python-state.json"

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

$pythonInfo = Resolve-PythonFromLauncher -Version $requestedVersion
if (-not $pythonInfo) {
    Install-PythonWithWinget -Version $requestedVersion
    Start-Sleep -Seconds 3
    $pythonInfo = Resolve-PythonFromLauncher -Version $requestedVersion
}

if (-not $pythonInfo) {
    throw "Python $requestedVersion was not found after install."
}

Ensure-Pip -PythonExe $pythonInfo.Executable

if ($installJupyter) {
    Write-Host "Installing JupyterLab and Notebook..."
    & $pythonInfo.Executable -m pip install --upgrade jupyterlab notebook
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Jupyter packages."
    }
}

$scriptsDir = Join-Path (Split-Path -Parent $pythonInfo.Executable) "Scripts"
$state = [ordered]@{
    requested_version = $requestedVersion
    python_version = $pythonInfo.Version
    python_executable = $pythonInfo.Executable
    scripts_dir = $scriptsDir
    jupyter_installed = $installJupyter
    jupyter_port = if ($jupyterPort) { $jupyterPort } else { "8888" }
    host = $hostIp
    updated_at = (Get-Date).ToString("o")
}

$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8
Write-Host "Python ready: $($pythonInfo.Executable)"
if ($installJupyter) {
    Write-Host "Jupyter packages installed."
}
