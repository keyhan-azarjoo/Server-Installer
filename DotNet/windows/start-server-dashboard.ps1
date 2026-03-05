[CmdletBinding()]
param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8090
)

$ErrorActionPreference = "Stop"

$dashboardScript = Join-Path $PSScriptRoot "..\..\dashboard\server_installer_dashboard.py"
$dashboardScript = [System.IO.Path]::GetFullPath($dashboardScript)

if (-not (Test-Path -LiteralPath $dashboardScript)) {
    throw "Dashboard script not found: $dashboardScript"
}

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
& $pythonCommand @argsList
