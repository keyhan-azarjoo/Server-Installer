[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DashboardArgs
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VerbosePreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoBase = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
$RequestedPythonVersion = "3.12"
$PythonSetupRelativePath = "Python/windows/setup-python.ps1"
$DashboardBootstrapRelativePath = "dashboard/start-server-dashboard-bootstrap.ps1"

function Get-InstallerRoot {
    $override = [string]$env:SERVER_INSTALLER_DATA_DIR
    if (-not [string]::IsNullOrWhiteSpace($override)) {
        return $override
    }

    $launchDir = [string]$env:SERVER_INSTALLER_LAUNCH_DIR
    if ([string]::IsNullOrWhiteSpace($launchDir)) {
        $launchDir = (Get-Location).Path
    }

    $launchDir = [System.IO.Path]::GetFullPath($launchDir)
    if ([System.IO.Path]::GetFileName($launchDir).Equals("Server-Installer", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $launchDir
    }

    return (Join-Path $launchDir "Server-Installer")
}

$InstallerRoot = Get-InstallerRoot
$DashboardStatePath = Join-Path $InstallerRoot "dashboard\service-state.json"
$env:SERVER_INSTALLER_LAUNCH_DIR = Split-Path -Parent $InstallerRoot
$env:SERVER_INSTALLER_DATA_DIR = $InstallerRoot

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
    function Test-WindowsServicePythonReady {
        param(
            [Parameter(Mandatory = $true)]
            [string]$PythonExe
        )

        if (-not $IsWindows) {
            return $true
        }

        if (-not (Test-Path -LiteralPath $PythonExe)) {
            return $false
        }

        $pythonDir = Split-Path -Parent $PythonExe
        $pythonServiceExe = Join-Path $pythonDir "pythonservice.exe"
        if (-not (Test-Path -LiteralPath $pythonServiceExe)) {
            return $false
        }

        try {
            & $PythonExe -c "import win32serviceutil, win32service; print('pywin32-ok')" 2>$null | Out-Null
            return ($LASTEXITCODE -eq 0)
        } catch {
            return $false
        }
    }

    $pythonSetupScript = Get-OrDownloadFile -RelativePath $PythonSetupRelativePath
    $env:PYTHON_VERSION = $RequestedPythonVersion
    $env:PYTHON_INSTALL_JUPYTER = "0"

    $pythonInfo = Get-PythonInfo
    if (-not $pythonInfo) {
        Write-Host "Python $RequestedPythonVersion not found. Installing the minimum required runtime..."
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $pythonSetupScript
            if ($LASTEXITCODE -ne 0) {
                throw "Python setup failed with exit code $LASTEXITCODE."
            }
        } catch {
            Write-Warning ("Python setup failed. Falling back to dashboard bootstrap runtime. Details: {0}" -f $_.Exception.Message)
            return $null
        }
        $pythonInfo = Get-PythonInfo
        if (-not $pythonInfo) {
            Write-Warning "Python $RequestedPythonVersion was not found after install. Falling back to dashboard bootstrap runtime."
            return $null
        }
        return $pythonInfo
    }

    # Python exists, but may be missing the Windows service deps (pywin32/pythonservice.exe). Repair in-place.
    if (-not (Test-WindowsServicePythonReady -PythonExe $pythonInfo.Executable)) {
        Write-Host "Python $RequestedPythonVersion found, but Windows service dependencies are missing. Repairing..."
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $pythonSetupScript
            if ($LASTEXITCODE -ne 0) {
                throw "Python repair failed with exit code $LASTEXITCODE."
            }
        } catch {
            Write-Warning ("Python repair failed. Continuing with the existing interpreter and dashboard fallback logic. Details: {0}" -f $_.Exception.Message)
            return $pythonInfo
        }

        $pythonInfo = Get-PythonInfo
        if (-not $pythonInfo) {
            Write-Warning "Python $RequestedPythonVersion was not found after repair. Falling back to dashboard bootstrap runtime."
            return $null
        }
    }

    return $pythonInfo
}

function Get-LocalIPv4Addresses {
    $ips = @()
    $virtualAliasPattern = 'vEthernet|WSL|Hyper-V|VirtualBox|VMware|Loopback|Bluetooth|Tailscale|ZeroTier|Docker|Container|Npcap'

    try {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown" -and
                ($_.InterfaceAlias -notmatch $virtualAliasPattern)
            } |
            Select-Object -ExpandProperty IPAddress -Unique
    } catch {
        $ips = @()
    }

    if (-not $ips -or $ips.Count -eq 0) {
        try {
            $ips = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
                ForEach-Object { $_.GetIPProperties().UnicastAddresses } |
                Where-Object {
                    $_ -and $_.Address -and
                    $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork
                } |
                ForEach-Object { $_.Address.IPAddressToString } |
                Where-Object { $_ -and $_ -ne "127.0.0.1" -and $_ -notlike "169.254.*" } |
                Select-Object -Unique
        } catch {
            $ips = @()
        }
    }

    if (-not $ips -or $ips.Count -eq 0) {
        try {
            $ips = ipconfig |
                Select-String -Pattern 'IPv4 Address' |
                ForEach-Object {
                    $m = [regex]::Match($_.Line, '(\d{1,3}(\.\d{1,3}){3})')
                    if ($m.Success) { $m.Groups[1].Value } else { $null }
                } |
                Where-Object { $_ -and $_ -ne "127.0.0.1" -and $_ -notlike "169.254.*" } |
                Select-Object -Unique
        } catch {
            $ips = @()
        }
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
    $env:SERVER_INSTALLER_WINDOWS_DIRECT = "1"
    Write-Host "Repairing dashboard startup and launching the dashboard..."
    & $bootstrapPath @DashboardArgs
    return $LASTEXITCODE
}

if (-not (Test-IsAdministrator)) {
    Restart-Elevated
}

$pythonInfo = Ensure-Python
if ($pythonInfo -and $pythonInfo.Executable) {
    $env:SERVER_INSTALLER_PYTHON = $pythonInfo.Executable
} else {
    Remove-Item Env:SERVER_INSTALLER_PYTHON -ErrorAction SilentlyContinue
}
$exitCode = Invoke-DashboardBootstrap
Show-DashboardUrls
exit $exitCode
