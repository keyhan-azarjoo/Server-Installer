[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LocalPath,
    [Parameter(Mandatory = $true)][string]$RemoteHost,
    [Parameter(Mandatory = $true)][string]$RemoteUser,
    [string]$RemoteInstallerPath = "C:\Windows\Temp\install-windows-dotnet-host.ps1",
    [string]$RemoteModuleDirectory = "C:\Windows\Temp",
    [string]$RemotePackageDirectory = "C:\Windows\Temp\Server-Installer",
    [string]$DotNetChannel = "8.0",
    [string]$DomainName,
    [string]$SiteName = "DotNetApp",
    [int]$SitePort = 80,
    [int]$HttpsPort = 443
)


$ErrorActionPreference = "Stop"

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-Tooling {
    foreach ($tool in @("ssh", "scp", "dotnet")) {
        if (-not (Test-Command -Name $tool)) {
            throw "Required command not found: $tool"
        }
    }
}

function Find-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $project = Get-ChildItem -Path $RootPath -Filter *.csproj -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1

    return $project.FullName
}

function Find-PublishedAppPath {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $runtimeConfig = Get-ChildItem -Path $RootPath -Filter *.runtimeconfig.json -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/](ref|refs)[\\/]' } |
        Sort-Object @{
            Expression = {
                $score = 0
                if ($_.FullName -match '[\\/](publish|published)[\\/]') { $score += 100 }
                if ($_.FullName -match '[\\/]Release[\\/]') { $score += 50 }
                if ($_.FullName -match '[\\/]Debug[\\/]') { $score -= 25 }
                $score
            }
            Descending = $true
        }, FullName |
        Select-Object -First 1

    if (-not $runtimeConfig) {
        return $null
    }

    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($runtimeConfig.BaseName)
    $dllPath = Join-Path $runtimeConfig.DirectoryName "$baseName.dll"
    if (Test-Path -LiteralPath $dllPath) {
        return $runtimeConfig.DirectoryName
    }

    return $null
}

function Resolve-LocalDeploymentFolder {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "Local path not found: $PathValue"
    }

    if (Test-Path -LiteralPath $PathValue -PathType Leaf) {
        if ([System.IO.Path]::GetExtension($PathValue) -ieq ".zip") {
            return (Resolve-Path -LiteralPath $PathValue).Path
        }

        throw "Local file must be a .zip package."
    }

    $resolvedPath = (Resolve-Path -LiteralPath $PathValue).Path
    $publishedPath = Find-PublishedAppPath -RootPath $resolvedPath
    if ($publishedPath) {
        return $publishedPath
    }

    $projectPath = Find-ProjectPath -RootPath $resolvedPath
    if (-not $projectPath) {
        throw "No published app or .csproj was found under $resolvedPath."
    }

    $publishRoot = Join-Path $env:TEMP ("iis-installer-publish-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null

    Write-Host "Publishing local source project: $projectPath"
    & dotnet publish $projectPath -c Release -o $publishRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed."
    }

    return $publishRoot
}

function Ensure-ZipPackage {
    param([Parameter(Mandatory = $true)][string]$PathValue)

    if (Test-Path -LiteralPath $PathValue -PathType Leaf) {
        return (Resolve-Path -LiteralPath $PathValue).Path
    }

    $folderName = Split-Path -Path $PathValue -Leaf
    if ([string]::IsNullOrWhiteSpace($folderName)) {
        $folderName = "published-app"
    }

    $zipPath = Join-Path $env:TEMP ($folderName + "-" + [System.Guid]::NewGuid().ToString("N") + ".zip")
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path (Join-Path $PathValue '*') -DestinationPath $zipPath -Force
    return $zipPath
}

function Quote-RemoteArg {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

Assert-Tooling

$localDeploySource = Resolve-LocalDeploymentFolder -PathValue $LocalPath
$packagePath = Ensure-ZipPackage -PathValue $localDeploySource

$installerLocalPath = Join-Path $PSScriptRoot "install-windows-dotnet-host.ps1"
if (-not (Test-Path -LiteralPath $installerLocalPath)) {
    throw "Installer script not found: $installerLocalPath"
}

$moduleLocalPath = Join-Path $PSScriptRoot "modules"
if (-not (Test-Path -LiteralPath $moduleLocalPath)) {
    throw "Module directory not found: $moduleLocalPath"
}

$packageFileName = Split-Path -Path $packagePath -Leaf
$remotePackagePath = "$RemotePackageDirectory\$packageFileName"
$remoteTarget = "$RemoteUser@$RemoteHost"

& ssh $remoteTarget "powershell -NoProfile -ExecutionPolicy Bypass -Command `"New-Item -ItemType Directory -Path $(Quote-RemoteArg $RemotePackageDirectory) -Force | Out-Null; New-Item -ItemType Directory -Path $(Quote-RemoteArg $RemoteModuleDirectory) -Force | Out-Null`""
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create remote directories."
}

& scp $installerLocalPath "${remoteTarget}:$RemoteInstallerPath"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy installer script to remote host."
}

& scp -r $moduleLocalPath "${remoteTarget}:$RemoteModuleDirectory"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy module scripts to remote host."
}

& scp $packagePath "${remoteTarget}:$remotePackagePath"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy deployment package to remote host."
}

$remoteCommand = @(
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-RemoteArg $RemoteInstallerPath),
    "-DeploymentMode", "IIS",
    "-DotNetChannel", (Quote-RemoteArg $DotNetChannel),
    "-SourceValue", (Quote-RemoteArg $remotePackagePath),
    "-SiteName", (Quote-RemoteArg $SiteName),
    "-SitePort", $SitePort,
    "-HttpsPort", $HttpsPort
)

if (-not [string]::IsNullOrWhiteSpace($DomainName)) {
    $remoteCommand += @("-DomainName", (Quote-RemoteArg $DomainName))
}

$remoteCommandText = ($remoteCommand -join ' ')
Write-Host "Running remote installer on $RemoteHost"
& ssh $remoteTarget $remoteCommandText
if ($LASTEXITCODE -ne 0) {
    throw "Remote installer failed."
}
