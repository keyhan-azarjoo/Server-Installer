[CmdletBinding()]
param(
    [ValidateSet("IIS", "Docker")]
    [string]$DeploymentMode,
    [string]$DotNetChannel,
    [string]$SdkInstallerUrl,
    [string]$AspNetRuntimeUrl,
    [string]$HostingBundleUrl,
    [string]$GitHubToken,
    [string]$SourceValue,
    [string]$DomainName,
    [string]$SiteName = "DotNetApp",
    [int]$SitePort = 80,
    [int]$HttpsPort = 443,
    [int]$DockerHostPort = 8080
)

$ErrorActionPreference = "Stop"
$originalBoundParameters = @{}
foreach ($entry in $PSBoundParameters.GetEnumerator()) {
    $originalBoundParameters[$entry.Key] = $entry.Value
}

$moduleRoot = Join-Path $PSScriptRoot "modules"
function Ensure-LocalWindowsModules {
    param([Parameter(Mandatory = $true)][string]$ModuleRoot)

    $requiredFiles = @("common.ps1", "iis-mode.ps1", "docker-mode.ps1")
    $missingFiles = $requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $ModuleRoot $_)) }
    if ($missingFiles.Count -eq 0) {
        return
    }

    New-Item -ItemType Directory -Path $ModuleRoot -Force | Out-Null
    $baseUrl = "https://raw.githubusercontent.com/keyhan-azarjoo/IIS-Installer/main/DotNet/windows/modules"

    foreach ($fileName in $missingFiles) {
        $targetPath = Join-Path $ModuleRoot $fileName
        $uri = "$baseUrl/$fileName"
        Write-Host "Downloading Windows module: $fileName"
        Invoke-WebRequest -Uri $uri -OutFile $targetPath
    }
}

Ensure-LocalWindowsModules -ModuleRoot $moduleRoot
. (Join-Path $moduleRoot "common.ps1")
. (Join-Path $moduleRoot "iis-mode.ps1")
. (Join-Path $moduleRoot "docker-mode.ps1")

Assert-Administrator -OriginalBoundParameters $originalBoundParameters

if ([string]::IsNullOrWhiteSpace($DeploymentMode)) {
    Write-Host "Choose deployment mode."
    Write-Host "1. IIS"
    Write-Host "2. Docker"
    $modeSelection = Read-Host "Select deployment mode (default: 1)"
    if ($modeSelection -eq "2") {
        $DeploymentMode = "Docker"
    }
    else {
        $DeploymentMode = "IIS"
    }
}

$DotNetChannel = Resolve-DotNetChannel -Value $DotNetChannel
$sourceValue = if (-not [string]::IsNullOrWhiteSpace($SourceValue)) { $SourceValue } else { Read-Host "Enter a build artifact URL, a local source folder, a local published folder, or a local published .zip path to deploy (leave blank to skip)" }
if ([string]::IsNullOrWhiteSpace($sourceValue)) {
    Write-Host "Setup completed. No deployment source was provided."
    exit 0
}

$domainName = if (-not [string]::IsNullOrWhiteSpace($DomainName)) { $DomainName } else { Read-Host "Enter a domain name for the site (leave blank to auto-detect the best IP address)" }

if ($DeploymentMode -eq "IIS") {
    Install-WindowsFeatureSet
    Install-DotNetPrerequisites -Channel $DotNetChannel -SdkUrl $SdkInstallerUrl -RuntimeUrl $AspNetRuntimeUrl -HostingUrl $HostingBundleUrl
}
else {
    Install-DotNetPrerequisites -Channel $DotNetChannel -SdkUrl $SdkInstallerUrl -RuntimeUrl $AspNetRuntimeUrl -HostingUrl $HostingBundleUrl -SkipHostingBundle
}

$stagingRoot = Join-Path $env:TEMP ("iis-installer-stage-" + [System.Guid]::NewGuid().ToString("N"))
$contentPath = Prepare-DeploymentContent -SourceValue $sourceValue -StagingRoot $stagingRoot -GitHubToken $GitHubToken
$packageName = Get-ArtifactName -SourcePath $sourceValue

try {
    switch ($DeploymentMode) {
        "IIS" {
            $result = Invoke-IisDeployment -ContentPath $contentPath -PackageName $packageName -SiteName $SiteName -HttpPort $SitePort -HttpsPort $HttpsPort -DomainName $domainName
            Write-Host "Deployment mode: IIS"
            Write-Host "Deployment complete."
            Write-Host "Site path: $($result.Path)"
            Write-Host "Preferred host: $($result.Host)"
            Write-Host "HTTP URL: http://$($result.Host):$($result.HttpPort)"
            Write-Host "HTTPS URL: https://$($result.Host):$($result.HttpsPort)"
        }
        "Docker" {
            $result = Invoke-DockerDeployment -ContentPath $contentPath -PackageName $packageName -SiteName $SiteName -DotNetChannel $DotNetChannel -HostPort $DockerHostPort -DomainName $domainName
            Write-Host "Deployment mode: Docker"
            Write-Host "Deployment complete."
            Write-Host "Container path: $($result.Path)"
            Write-Host "Container name: $($result.Container)"
            Write-Host "HTTP URL: http://$($result.Host):$($result.HttpPort)"
            Write-Host "HTTPS is not configured automatically in Docker mode."
        }
    }
}
finally {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}
