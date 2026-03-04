[CmdletBinding()]
param(
    [string]$DotNetChannel = "8.0",
    [string]$SiteName = "DotNetApp",
    [int]$SitePort = 8080
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from an elevated PowerShell session."
    }
}

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WindowsFeatureSet {
    $featureNames = @(
        "IIS-WebServerRole",
        "IIS-WebServer",
        "IIS-CommonHttpFeatures",
        "IIS-StaticContent",
        "IIS-DefaultDocument",
        "IIS-HttpErrors",
        "IIS-HttpRedirect",
        "IIS-ApplicationDevelopment",
        "IIS-NetFxExtensibility45",
        "IIS-ASPNET45",
        "IIS-HealthAndDiagnostics",
        "IIS-HttpLogging",
        "IIS-Security",
        "IIS-RequestFiltering",
        "IIS-Performance",
        "IIS-WebSockets",
        "IIS-WebServerManagementTools",
        "IIS-ManagementConsole"
    )

    foreach ($featureName in $featureNames) {
        Write-Host "Enabling Windows feature: $featureName"
        Enable-WindowsOptionalFeature -Online -FeatureName $featureName -All -NoRestart | Out-Null
    }
}

function Install-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Arguments
    )

    $targetPath = Join-Path $env:TEMP $FileName
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $targetPath

    try {
        Write-Host "Running installer: $FileName"
        $process = Start-Process -FilePath $targetPath -ArgumentList $Arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Installer $FileName failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        Remove-Item $targetPath -Force -ErrorAction SilentlyContinue
    }
}

function Install-DotNetPrerequisites {
    param([Parameter(Mandatory = $true)][string]$Channel)

    Install-Executable -Url "https://aka.ms/dotnet/$Channel/dotnet-sdk-win-x64.exe" `
        -FileName "dotnet-sdk-win-x64.exe" `
        -Arguments "/install /quiet /norestart"

    Install-Executable -Url "https://aka.ms/dotnet/$Channel/aspnetcore-runtime-win-x64.exe" `
        -FileName "aspnetcore-runtime-win-x64.exe" `
        -Arguments "/install /quiet /norestart"

    Install-Executable -Url "https://aka.ms/dotnet/$Channel/dotnet-hosting-win.exe" `
        -FileName "dotnet-hosting-win.exe" `
        -Arguments "/install /quiet /norestart OPT_NO_ANCM=0"
}

function Ensure-Git {
    if (Test-Command -Name "git") {
        return
    }

    if (-not (Test-Command -Name "winget")) {
        throw "Git is not installed and winget is unavailable. Install Git manually, then rerun the script."
    }

    Write-Host "Installing Git with winget"
    $process = Start-Process -FilePath "winget" `
        -ArgumentList "install --id Git.Git --exact --accept-package-agreements --accept-source-agreements --silent" `
        -Wait -PassThru -NoNewWindow

    if ($process.ExitCode -ne 0) {
        throw "Git installation failed with exit code $($process.ExitCode)."
    }
}

function Get-RepositoryName {
    param([Parameter(Mandatory = $true)][string]$RepositoryUrl)

    $name = Split-Path -Path $RepositoryUrl -Leaf
    if ($name.EndsWith(".git")) {
        $name = $name.Substring(0, $name.Length - 4)
    }

    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Unable to determine a repository name from '$RepositoryUrl'."
    }

    return $name
}

function Find-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$RepositoryPath)

    $project = Get-ChildItem -Path $RepositoryPath -Filter *.csproj -Recurse | Select-Object -First 1
    if (-not $project) {
        throw "No .csproj file was found in $RepositoryPath."
    }

    return $project.FullName
}

function Publish-Project {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectPath,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    & dotnet restore $ProjectPath
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet restore failed."
    }

    & dotnet publish $ProjectPath -c Release -o $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed."
    }
}

function Ensure-WebConfig {
    param(
        [Parameter(Mandatory = $true)][string]$PublishPath,
        [Parameter(Mandatory = $true)][string]$AssemblyName
    )

    $webConfigPath = Join-Path $PublishPath "web.config"
    if (Test-Path $webConfigPath) {
        return
    }

    $content = @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="aspNetCore" path="*" verb="*" modules="AspNetCoreModuleV2" resourceType="Unspecified" />
    </handlers>
    <aspNetCore processPath="dotnet" arguments=".\$AssemblyName.dll" stdoutLogEnabled="false" hostingModel="inprocess" />
  </system.webServer>
</configuration>
"@

    Set-Content -Path $webConfigPath -Value $content -Encoding UTF8
}

function Configure-IisSite {
    param(
        [Parameter(Mandatory = $true)][string]$PublishPath,
        [Parameter(Mandatory = $true)][string]$AppPoolName,
        [Parameter(Mandatory = $true)][string]$WebsiteName,
        [Parameter(Mandatory = $true)][int]$Port
    )

    Import-Module WebAdministration

    if (-not (Test-Path "IIS:\AppPools\$AppPoolName")) {
        New-WebAppPool -Name $AppPoolName | Out-Null
    }

    Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name managedRuntimeVersion -Value ""

    if (Test-Path "IIS:\Sites\$WebsiteName") {
        Stop-Website -Name $WebsiteName
        Remove-Website -Name $WebsiteName
    }

    New-Website -Name $WebsiteName -Port $Port -PhysicalPath $PublishPath -ApplicationPool $AppPoolName | Out-Null
    Start-Website -Name $WebsiteName | Out-Null
}

Assert-Administrator
Install-WindowsFeatureSet
Install-DotNetPrerequisites -Channel $DotNetChannel

$repoUrl = Read-Host "Enter a Git repository URL to deploy (leave blank to skip)"
if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "Setup completed. IIS and .NET prerequisites are installed."
    exit 0
}

Ensure-Git

$repoRoot = Join-Path $PSScriptRoot "repositories"
New-Item -ItemType Directory -Path $repoRoot -Force | Out-Null

$repoName = Get-RepositoryName -RepositoryUrl $repoUrl
$repoPath = Join-Path $repoRoot $repoName

if (Test-Path $repoPath) {
    Write-Host "Repository already exists. Pulling latest changes."
    & git -C $repoPath pull
    if ($LASTEXITCODE -ne 0) {
        throw "git pull failed."
    }
}
else {
    & git clone $repoUrl $repoPath
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed."
    }
}

$projectPath = Find-ProjectPath -RepositoryPath $repoPath
$assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($projectPath)
$publishPath = Join-Path $repoPath "published"

Publish-Project -ProjectPath $projectPath -OutputPath $publishPath
Ensure-WebConfig -PublishPath $publishPath -AssemblyName $assemblyName
Configure-IisSite -PublishPath $publishPath -AppPoolName $SiteName -WebsiteName $SiteName -Port $SitePort

Write-Host "Deployment complete."
Write-Host "IIS site: $SiteName"
Write-Host "URL: http://localhost:$SitePort"
