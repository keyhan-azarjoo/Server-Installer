[CmdletBinding()]
param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"

function Ensure-ServerInstallerFiles {
    $installRoot = Join-Path $env:ProgramData "Server-Installer"
    $baseUrl = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"

    $requiredFiles = @(
        "dashboard/server_installer_dashboard.py",
        "DotNet/windows/install-windows-dotnet-host.ps1",
        "DotNet/windows/modules/common.ps1",
        "DotNet/windows/modules/iis-mode.ps1",
        "DotNet/windows/modules/docker-mode.ps1",
        "DotNet/linux/install-linux-dotnet-runner.sh"
    )

    foreach ($relativePath in $requiredFiles) {
        $targetPath = Join-Path $installRoot ($relativePath -replace '/', '\')
        $targetDirectory = Split-Path -Path $targetPath -Parent
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

        if (-not (Test-Path -LiteralPath $targetPath)) {
            $uri = "$baseUrl/$relativePath"
            Write-Host "Downloading required file: $relativePath"
            Invoke-WebRequest -Uri $uri -OutFile $targetPath
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

Write-Host "Starting dashboard on http://$BindHost`:$Port"
Push-Location $installRoot
try {
    & $pythonCommand @argsList
}
finally {
    Pop-Location
}
