[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DashboardArgs
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoBase = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
$RequestedPythonVersion = "3.12"
$PythonSetupRelativePath = "Python/windows/setup-python.ps1"
$DashboardBootstrapRelativePath = "dashboard/start-server-dashboard-bootstrap.ps1"
$ProgramDataRoot = Join-Path $env:ProgramData "Server-Installer"
$DashboardStatePath = Join-Path $ProgramDataRoot "dashboard\service-state.json"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Restart-Elevated {
    $argLine = Get-InvocationArgumentLine -ScriptPath $PSCommandPath -Arguments $DashboardArgs
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argLine -Verb RunAs -Wait -PassThru
    exit $proc.ExitCode
}

function Quote-PowerShellArgument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return '"' + $Value.Replace('"', '\"') + '"'
}

function Get-InvocationArgumentLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments
    )

    $parts = @(
        "-NoProfile",
        "-ExecutionPolicy Bypass",
        ('-File ' + (Quote-PowerShellArgument -Value $ScriptPath))
    )
    foreach ($arg in @($Arguments)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$arg)) {
            $parts += (Quote-PowerShellArgument -Value ([string]$arg))
        }
    }
    return ($parts -join " ")
}

function Get-PythonInfoFromPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable
    )

    if (-not (Test-Path -LiteralPath $Executable)) {
        return $null
    }

    try {
        $output = & $Executable -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
    } catch {
        return $null
    }

    if (-not $output -or $LASTEXITCODE -ne 0) {
        return $null
    }

    $lines = @($output | Where-Object { $_ -and $_.Trim() })
    if ($lines.Count -lt 2) {
        return $null
    }

    return [PSCustomObject]@{
        Executable = $lines[0].Trim()
        Version = $lines[1].Trim()
    }
}

function Get-PythonInfo {
    $versionPrefix = "$RequestedPythonVersion."

    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $output = & $py.Source "-$RequestedPythonVersion" -c "import sys; print(sys.executable); print(sys.version.split()[0])" 2>$null
            if ($output -and $LASTEXITCODE -eq 0) {
                $lines = @($output | Where-Object { $_ -and $_.Trim() })
                if ($lines.Count -ge 2) {
                    $info = [PSCustomObject]@{
                        Executable = $lines[0].Trim()
                        Version = $lines[1].Trim()
                    }
                    if ($info.Version -eq $RequestedPythonVersion -or $info.Version.StartsWith($versionPrefix)) {
                        return $info
                    }
                }
            }
        } catch {
        }
    }

    $candidates = @()
    foreach ($commandName in @("python.exe", "python3.exe")) {
        $cmd = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            $candidates += $cmd.Source
        }
    }

    $roots = @(
        $env:ProgramFiles,
        $env:ProgramW6432,
        ${env:ProgramFiles(x86)},
        $env:LocalAppData,
        "C:\Program Files",
        "C:\Program Files (x86)"
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($root in $roots) {
        foreach ($pattern in @("Python312\python.exe", "Programs\Python\Python312\python.exe")) {
            $candidates += (Join-Path $root $pattern)
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $info = Get-PythonInfoFromPath -Executable $candidate
        if (-not $info) {
            continue
        }
        if ($info.Version -eq $RequestedPythonVersion -or $info.Version.StartsWith($versionPrefix)) {
            return $info
        }
    }

    return $null
}

function Get-OrDownloadFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $localPath = Join-Path $PSScriptRoot ($RelativePath -replace '/', '\')
    if (Test-Path -LiteralPath $localPath) {
        return $localPath
    }

    $cacheRoot = Join-Path $env:TEMP "server-installer-bootstrap"
    $targetPath = Join-Path $cacheRoot ($RelativePath -replace '/', '\')
    $targetDir = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Invoke-WebRequest -Uri "$RepoBase/$RelativePath" -OutFile $targetPath
    return $targetPath
}

function Ensure-Python {
    $pythonInfo = Get-PythonInfo
    if ($pythonInfo) {
        return $pythonInfo
    }

    Write-Host "Python $RequestedPythonVersion not found. Installing the minimum required runtime..."
    $pythonSetupScript = Get-OrDownloadFile -RelativePath $PythonSetupRelativePath
    $env:PYTHON_VERSION = $RequestedPythonVersion
    $env:PYTHON_INSTALL_JUPYTER = "0"

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $pythonSetupScript
    if ($LASTEXITCODE -ne 0) {
        throw "Python setup failed."
    }

    $pythonInfo = Get-PythonInfo
    if (-not $pythonInfo) {
        throw "Python $RequestedPythonVersion was not found after install."
    }

    return $pythonInfo
}

function Get-LocalIPv4Addresses {
    $ips = @()
    try {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Select-Object -ExpandProperty IPAddress -Unique
    } catch {
        $ips = @()
    }
    return @($ips)
}

function Get-PublicIPv4Address {
    foreach ($endpoint in @(
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com"
    )) {
        try {
            $value = (Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 5).Content
            $value = [string]$value
            $value = $value.Trim()
            if ($value -match '^\d{1,3}(\.\d{1,3}){3}$') {
                return $value
            }
        } catch {
        }
    }
    return $null
}

function Show-DashboardUrls {
    $port = 8090
    $serviceName = "ServerInstallerDashboard"

    if (Test-Path -LiteralPath $DashboardStatePath) {
        try {
            $state = Get-Content -LiteralPath $DashboardStatePath -Raw | ConvertFrom-Json
            if ($state.port) {
                $port = [int]$state.port
            }
        } catch {
        }
    }

    $urls = [System.Collections.Generic.List[string]]::new()
    $urls.Add("https://127.0.0.1:$port")
    foreach ($ip in (Get-LocalIPv4Addresses)) {
        $candidate = "https://$ip`:$port"
        if (-not $urls.Contains($candidate)) {
            $urls.Add($candidate)
        }
    }
    $publicIp = Get-PublicIPv4Address

    Write-Host ""
    Write-Host "Dashboard URLs:"
    foreach ($url in $urls) {
        Write-Host "- $url"
    }
    if ($publicIp) {
        Write-Host "Public IP:"
        Write-Host "- $publicIp"
    }
    Write-Host "Service name:"
    Write-Host "- $serviceName"
}

function Invoke-DashboardBootstrap {
    $bootstrapPath = Get-OrDownloadFile -RelativePath $DashboardBootstrapRelativePath

    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "dashboard\start-server-dashboard-bootstrap.ps1")) {
        $env:SERVER_INSTALLER_LOCAL_ROOT = $PSScriptRoot
    } else {
        Remove-Item Env:SERVER_INSTALLER_LOCAL_ROOT -ErrorAction SilentlyContinue
    }

    $env:DASHBOARD_HTTPS = "1"
    $env:SERVER_INSTALLER_FORCE_DOWNLOAD = "1"
    Write-Host "Repairing dashboard startup and launching the dashboard..."
    & $bootstrapPath @DashboardArgs
    return $LASTEXITCODE
}

if (-not (Test-IsAdministrator)) {
    Restart-Elevated
}

$null = Ensure-Python
$exitCode = Invoke-DashboardBootstrap
Show-DashboardUrls
exit $exitCode
