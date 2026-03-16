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

    try {
        $output = & $py.Source "-$Version" -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
    } catch {
        return $null
    }
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

function Test-PythonExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    if (-not (Test-Path $PythonExe)) {
        return $null
    }

    try {
        $output = & $PythonExe -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
    } catch {
        return $null
    }
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

function Resolve-PythonFromPathOrCommonLocations {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    $versionPrefix = "$Version."
    $candidates = New-Object System.Collections.Generic.List[string]

    foreach ($cmdName in @("python.exe", "python3.exe")) {
        $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            [void]$candidates.Add($cmd.Source)
        }
    }

    $roots = @(
        $env:ProgramFiles,
        $env:ProgramW6432,
        ${env:ProgramFiles(x86)},
        "C:\Program Files",
        "C:\Program Files (x86)",
        $env:LocalAppData
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($root in $roots) {
        foreach ($pattern in @("Python$($Version.Replace('.', ''))\python.exe", "Programs\Python\Python$($Version.Replace('.', ''))\python.exe")) {
            $candidate = Join-Path $root $pattern
            if (Test-Path $candidate) {
                [void]$candidates.Add($candidate)
            }
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $info = Test-PythonExecutable -PythonExe $candidate
        if (-not $info) {
            continue
        }
        if ($info.Version -eq $Version -or $info.Version.StartsWith($versionPrefix)) {
            return $info
        }
    }

    return $null
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

    return [PSCustomObject]@{
        InstallMethod = "winget"
        PackageId = $packageId
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

function Ensure-WindowsServiceDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    & $PythonExe -m pip install --upgrade pywin32
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install pywin32."
    }

    $pythonDir = Split-Path -Parent $PythonExe
    $targetServiceExe = Join-Path $pythonDir "pythonservice.exe"
    if (-not (Test-Path -LiteralPath $targetServiceExe)) {
        $candidatePaths = @(
            (Join-Path $env:APPDATA "Python\Python312\site-packages\win32\pythonservice.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\Lib\site-packages\win32\pythonservice.exe"),
            (Join-Path $pythonDir "Lib\site-packages\win32\pythonservice.exe")
        ) | Select-Object -Unique

        $sourceServiceExe = $candidatePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $sourceServiceExe) {
            throw "pythonservice.exe was not found after installing pywin32."
        }

        Copy-Item -LiteralPath $sourceServiceExe -Destination $targetServiceExe -Force
    }
}

function Ensure-JupyterKernel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    & $PythonExe -m pip install --upgrade ipykernel
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install ipykernel."
    }
    & $PythonExe -m ipykernel install --sys-prefix --name python3 --display-name "Python 3"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register Jupyter kernel."
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

$installMethod = "existing"
$installPackageId = ""
$pythonInfo = Resolve-PythonFromLauncher -Version $requestedVersion
if (-not $pythonInfo) {
    $pythonInfo = Resolve-PythonFromPathOrCommonLocations -Version $requestedVersion
}
if (-not $pythonInfo) {
    $installInfo = Install-PythonWithWinget -Version $requestedVersion
    if ($installInfo) {
        $installMethod = $installInfo.InstallMethod
        $installPackageId = $installInfo.PackageId
    }
    Start-Sleep -Seconds 3
    $pythonInfo = Resolve-PythonFromLauncher -Version $requestedVersion
    if (-not $pythonInfo) {
        $pythonInfo = Resolve-PythonFromPathOrCommonLocations -Version $requestedVersion
    }
}

if (-not $pythonInfo) {
    throw "Python $requestedVersion was not found after install."
}

Ensure-Pip -PythonExe $pythonInfo.Executable
if ($IsWindows) {
    Ensure-WindowsServiceDependencies -PythonExe $pythonInfo.Executable
}

if ($installJupyter) {
    Write-Host "Installing JupyterLab and Notebook..."
    & $pythonInfo.Executable -m pip install --upgrade jupyterlab notebook aiohttp
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Jupyter packages."
    }
    Ensure-JupyterKernel -PythonExe $pythonInfo.Executable
}

$scriptsDir = Join-Path (Split-Path -Parent $pythonInfo.Executable) "Scripts"
$state = [ordered]@{
    requested_version = $requestedVersion
    python_version = $pythonInfo.Version
    python_executable = $pythonInfo.Executable
    python_root = (Split-Path -Parent $pythonInfo.Executable)
    scripts_dir = $scriptsDir
    managed_install = ($installMethod -eq "winget")
    install_method = $installMethod
    install_package_id = $installPackageId
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
