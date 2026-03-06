[CmdletBinding()]
param(
    [string]$BindHost = "auto",
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"

function Get-PreferredIPv4Address {
    $defaultRoute = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object -Property RouteMetric, InterfaceMetric |
        Select-Object -First 1

    $candidateIps = @()
    if ($defaultRoute) {
        $candidateIps = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $defaultRoute.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Sort-Object -Property @{ Expression = { if ($_.PrefixOrigin -eq "Manual") { 0 } else { 1 } } }, SkipAsSource
    }

    if (-not $candidateIps -or $candidateIps.Count -eq 0) {
        $candidateIps = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.PrefixOrigin -ne "WellKnown"
            } |
            Sort-Object -Property @{ Expression = { if ($_.PrefixOrigin -eq "Manual") { 0 } else { 1 } } }, InterfaceMetric, SkipAsSource
    }

    $ipFromNetAdapter = $candidateIps | Select-Object -First 1
    if ($ipFromNetAdapter -and -not [string]::IsNullOrWhiteSpace($ipFromNetAdapter.IPAddress)) {
        return $ipFromNetAdapter.IPAddress
    }

    try {
        $socket = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Dgram, [System.Net.Sockets.ProtocolType]::Udp)
        $socket.Connect("8.8.8.8", 53)
        $localIp = $socket.LocalEndPoint.Address.ToString()
        $socket.Close()
        if (-not [string]::IsNullOrWhiteSpace($localIp)) {
            return $localIp
        }
    }
    catch {
    }

    return "127.0.0.1"
}

if ([string]::IsNullOrWhiteSpace($BindHost) -or $BindHost -eq "auto" -or $BindHost -eq "0.0.0.0") {
    $displayHost = Get-PreferredIPv4Address
    $BindHost = "0.0.0.0"
}
else {
    $displayHost = $BindHost
}

function Ensure-ServerInstallerFiles {
    $repoRootCandidate = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $localDashboard = Join-Path $repoRootCandidate "dashboard\server_installer_dashboard.py"
    $localComponents = Join-Path $repoRootCandidate "dashboard\ui\components.js"
    $localApp = Join-Path $repoRootCandidate "dashboard\ui\app.js"
    if ((Test-Path -LiteralPath $localDashboard) -and (Test-Path -LiteralPath $localComponents) -and (Test-Path -LiteralPath $localApp)) {
        Write-Host "Using local repository dashboard files."
        return $repoRootCandidate
    }

    $installRoot = Join-Path $env:ProgramData "Server-Installer"
    $baseUrl = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"

    $requiredFiles = @(
        "dashboard/server_installer_dashboard.py",
        "dashboard/ui/components.js",
        "dashboard/ui/app.js"
    )

    foreach ($relativePath in $requiredFiles) {
        $targetPath = Join-Path $installRoot ($relativePath -replace '/', '\')
        $targetDirectory = Split-Path -Path $targetPath -Parent
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

        $uri = "$baseUrl/$relativePath"
        $tempPath = "$targetPath.download"
        try {
            Write-Host "Syncing required file: $relativePath"
            Invoke-WebRequest -Uri $uri -OutFile $tempPath
            Move-Item -Force -Path $tempPath -Destination $targetPath
        }
        catch {
            if (Test-Path -LiteralPath $tempPath) {
                Remove-Item -Force -LiteralPath $tempPath -ErrorAction SilentlyContinue
            }
            if (-not (Test-Path -LiteralPath $targetPath)) {
                throw "Failed to download required file: $relativePath. $($_.Exception.Message)"
            }
            Write-Warning "Using cached file for $relativePath. $($_.Exception.Message)"
        }
    }

    return $installRoot
}

$installRoot = Ensure-ServerInstallerFiles
$dashboardScript = Join-Path $installRoot "dashboard\server_installer_dashboard.py"

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    $pythonCommand = "py"
    $pythonArgsPrefix = @("-3")
}
else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python 3 is required. Install Python and rerun."
    }
    $pythonCommand = "python"
    $pythonArgsPrefix = @()
}

$argsList = @()
$argsList += $pythonArgsPrefix
$argsList += $dashboardScript
$argsList += @("--host", $BindHost)
$argsList += @("--port", "$Port")

Write-Host "Starting dashboard..."
Write-Host "Local URL: http://127.0.0.1:$Port"
Write-Host "Server URL: http://$displayHost`:$Port"
Push-Location $installRoot
try {
    & $pythonCommand @argsList
}
finally {
    Pop-Location
}
