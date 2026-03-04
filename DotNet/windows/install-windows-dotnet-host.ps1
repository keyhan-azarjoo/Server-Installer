[CmdletBinding()]
param(
    [string]$DotNetChannel,
    [string]$SdkInstallerUrl,
    [string]$AspNetRuntimeUrl,
    [string]$HostingBundleUrl,
    [string]$GitHubToken,
    [string]$SourceValue,
    [string]$DomainName,
    [string]$SiteName = "DotNetApp",
    [int]$SitePort = 80,
    [int]$HttpsPort = 443
)

$ErrorActionPreference = "Stop"
$script:OriginalBoundParameters = @{}
foreach ($entry in $PSBoundParameters.GetEnumerator()) {
    $script:OriginalBoundParameters[$entry.Key] = $entry.Value
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $scriptPath = $PSCommandPath
        if ([string]::IsNullOrWhiteSpace($scriptPath)) {
            throw "Run this script from an elevated PowerShell session."
        }

        $argumentList = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", ('"{0}"' -f $scriptPath)
        )

        foreach ($entry in $script:OriginalBoundParameters.GetEnumerator()) {
            $argumentList += "-$($entry.Key)"

            if ($entry.Value -is [switch]) {
                continue
            }

            $escapedValue = [string]$entry.Value
            $escapedValue = $escapedValue.Replace('"', '\"')
            $argumentList += ('"{0}"' -f $escapedValue)
        }

        Write-Host "Requesting elevation..."
        Start-Process -FilePath "powershell.exe" -ArgumentList $argumentList -Verb RunAs | Out-Null
        exit 0
    }
}

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-IsUrl {
    param([Parameter(Mandatory = $true)][string]$Value)

    return $Value -match '^(https?)://'
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
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName
        if ($feature.State -eq "Enabled") {
            Write-Host "Windows feature already enabled: $featureName"
            continue
        }

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

function Resolve-DotNetChannel {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "Choose a .NET release channel."
        Write-Host "Examples: 8, 9, 10, 10.0, LTS, STS"
        $Value = Read-Host "Enter .NET channel (default: 8.0)"
    }

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "8.0"
    }

    $trimmed = $Value.Trim()
    if ($trimmed -match '^\d+$') {
        return "$trimmed.0"
    }

    return $trimmed
}

function Get-DotNetMajorVersion {
    param([Parameter(Mandatory = $true)][string]$Channel)

    if ($Channel -match '^(\d+)') {
        return $Matches[1]
    }

    throw "Unable to determine a .NET major version from '$Channel'. Use a major version like 8, 9, or 10 when idempotent install checks are required."
}

function Test-DotNetSdkInstalled {
    param([Parameter(Mandatory = $true)][string]$MajorVersion)

    if (-not (Test-Command -Name "dotnet")) {
        return $false
    }

    $sdkList = & dotnet --list-sdks 2>$null
    return [bool]($sdkList | Where-Object { $_ -match "^$([regex]::Escape($MajorVersion))\." })
}

function Test-AspNetRuntimeInstalled {
    param([Parameter(Mandatory = $true)][string]$MajorVersion)

    if (-not (Test-Command -Name "dotnet")) {
        return $false
    }

    $runtimeList = & dotnet --list-runtimes 2>$null
    return [bool]($runtimeList | Where-Object { $_ -match "^Microsoft\.AspNetCore\.App $([regex]::Escape($MajorVersion))\." })
}

function Test-HostingBundleInstalled {
    param([Parameter(Mandatory = $true)][string]$MajorVersion)

    $registryPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($registryPath in $registryPaths) {
        $match = Get-ItemProperty -Path $registryPath -ErrorAction SilentlyContinue |
            Where-Object {
                $_.DisplayName -like "Microsoft ASP.NET Core * Hosting Bundle*" -and
                $_.DisplayVersion -match "^$([regex]::Escape($MajorVersion))\."
            } |
            Select-Object -First 1

        if ($match) {
            return $true
        }
    }

    return $false
}

function Install-DotNetPrerequisites {
    param(
        [string]$Channel,
        [string]$SdkUrl,
        [string]$RuntimeUrl,
        [string]$HostingUrl
    )

    $majorVersion = Get-DotNetMajorVersion -Channel $Channel

    if ([string]::IsNullOrWhiteSpace($SdkUrl)) {
        $SdkUrl = "https://aka.ms/dotnet/$Channel/dotnet-sdk-win-x64.exe"
    }

    if ([string]::IsNullOrWhiteSpace($RuntimeUrl)) {
        $RuntimeUrl = "https://aka.ms/dotnet/$Channel/aspnetcore-runtime-win-x64.exe"
    }

    if ([string]::IsNullOrWhiteSpace($HostingUrl)) {
        $HostingUrl = "https://aka.ms/dotnet/$Channel/dotnet-hosting-win.exe"
    }

    if (Test-DotNetSdkInstalled -MajorVersion $majorVersion) {
        Write-Host ".NET SDK $majorVersion already installed."
    }
    else {
        Install-Executable -Url $SdkUrl `
            -FileName "dotnet-sdk-win-x64.exe" `
            -Arguments "/install /quiet /norestart"
    }

    if (Test-AspNetRuntimeInstalled -MajorVersion $majorVersion) {
        Write-Host "ASP.NET Core Runtime $majorVersion already installed."
    }
    else {
        Install-Executable -Url $RuntimeUrl `
            -FileName "aspnetcore-runtime-win-x64.exe" `
            -Arguments "/install /quiet /norestart"
    }

    if (Test-HostingBundleInstalled -MajorVersion $majorVersion) {
        Write-Host "ASP.NET Core Hosting Bundle $majorVersion already installed."
    }
    else {
        Install-Executable -Url $HostingUrl `
            -FileName "dotnet-hosting-win.exe" `
            -Arguments "/install /quiet /norestart OPT_NO_ANCM=0"
    }
}

function Get-ArtifactName {
    param([Parameter(Mandatory = $true)][string]$SourcePath)

    $normalizedPath = $SourcePath.TrimEnd('\', '/')
    $name = Split-Path -Path $normalizedPath -Leaf

    if ([string]::IsNullOrWhiteSpace($name)) {
        throw "Unable to determine a folder name from '$SourcePath'."
    }

    if ($name.EndsWith(".zip", [System.StringComparison]::OrdinalIgnoreCase)) {
        $name = $name.Substring(0, $name.Length - 4)
    }

    return $name
}

function Get-DownloadHeaders {
    param([Parameter(Mandatory = $true)][string]$SourceValue)

    $headers = @{}
    if ($SourceValue -match '^https://(github\.com|api\.github\.com|objects\.githubusercontent\.com|raw\.githubusercontent\.com)/') {
        if ([string]::IsNullOrWhiteSpace($script:GitHubToken)) {
            $script:GitHubToken = Read-Host "Enter GitHub token for private artifact access (leave blank for public download)"
        }

        if (-not [string]::IsNullOrWhiteSpace($script:GitHubToken)) {
            $headers["Authorization"] = "Bearer $($script:GitHubToken)"
        }
    }

    return $headers
}

function Expand-DeploymentPackage {
    param(
        [Parameter(Mandatory = $true)][string]$SourceFile,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    if (Test-Path -LiteralPath $TargetPath) {
        Remove-Item -LiteralPath $TargetPath -Recurse -Force
    }

    New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null

    $extension = [System.IO.Path]::GetExtension($SourceFile)
    if ($extension -ieq ".zip") {
        Expand-Archive -LiteralPath $SourceFile -DestinationPath $TargetPath -Force
        return
    }

    throw "Unsupported package format '$extension'. Provide a published .zip package or a local published folder."
}

function Stop-IisDeploymentLocking {
    param([Parameter(Mandatory = $true)][string]$WebsiteName)

    Import-Module WebAdministration

    if (Test-Path "IIS:\Sites\$WebsiteName") {
        $site = Get-Website -Name $WebsiteName -ErrorAction SilentlyContinue
        if ($site -and $site.State -eq "Started") {
            Stop-Website -Name $WebsiteName | Out-Null
        }
    }

    if (Test-Path "IIS:\AppPools\$WebsiteName") {
        $appPool = Get-ChildItem "IIS:\AppPools\$WebsiteName" -ErrorAction SilentlyContinue
        if ($appPool -and $appPool.State -eq "Started") {
            Stop-WebAppPool -Name $WebsiteName | Out-Null
        }
    }
}

function Remove-DeploymentPath {
    param(
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [Parameter(Mandatory = $true)][string]$WebsiteName
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return
    }

    Stop-IisDeploymentLocking -WebsiteName $WebsiteName
    Start-Sleep -Seconds 2

    try {
        Remove-Item -LiteralPath $TargetPath -Recurse -Force
    }
    catch {
        throw "Failed to remove existing deployment path '$TargetPath'. IIS files may still be locked. Stop the related site or worker process and retry. $($_.Exception.Message)"
    }
}

function Find-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $project = Get-ChildItem -Path $RootPath -Filter *.csproj -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($project) {
        return $project.FullName
    }

    return $null
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

function Publish-LocalSource {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$TargetRoot
    )

    $projectPath = Find-ProjectPath -RootPath $SourceRoot
    if (-not $projectPath) {
        return $null
    }

    $publishPath = Join-Path $TargetRoot "published"
    if (Test-Path -LiteralPath $publishPath) {
        Remove-Item -LiteralPath $publishPath -Recurse -Force
    }

    New-Item -ItemType Directory -Path $publishPath -Force | Out-Null
    Write-Host "Publishing local source project: $projectPath"
    & dotnet publish $projectPath -c Release -o $publishPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed."
    }

    return [string]$publishPath
}

function Resolve-DeploymentSource {
    param(
        [Parameter(Mandatory = $true)][string]$SourceValue,
        [Parameter(Mandatory = $true)][string]$TargetRoot,
        [Parameter(Mandatory = $true)][string]$WebsiteName
    )

    $targetName = Get-ArtifactName -SourcePath $SourceValue
    $targetPath = Join-Path $TargetRoot $targetName

    if (Test-Path -LiteralPath $SourceValue -PathType Container) {
        $resolvedSource = (Resolve-Path -LiteralPath $SourceValue).Path
        $existingPublishedPath = Find-PublishedAppPath -RootPath $resolvedSource
        if ($existingPublishedPath) {
            Write-Host "Found published application under: $existingPublishedPath"

            Remove-DeploymentPath -TargetPath $targetPath -WebsiteName $WebsiteName

            Copy-Item -LiteralPath $existingPublishedPath -Destination $targetPath -Recurse -Force
            return [string]$targetPath
        }

        $publishedPath = Publish-LocalSource -SourceRoot $resolvedSource -TargetRoot $targetPath
        if ($publishedPath) {
            return [string]$publishedPath
        }

        Remove-DeploymentPath -TargetPath $targetPath -WebsiteName $WebsiteName

        Copy-Item -LiteralPath $resolvedSource -Destination $targetPath -Recurse -Force
        return [string]$targetPath
    }

    if (Test-Path -LiteralPath $SourceValue -PathType Leaf) {
        Expand-DeploymentPackage -SourceFile (Resolve-Path -LiteralPath $SourceValue).Path -TargetPath $targetPath
        return [string]$targetPath
    }

    if (-not (Test-IsUrl -Value $SourceValue)) {
        throw "The source path '$SourceValue' does not exist. Provide a valid local published folder, a local .zip package, or a downloadable artifact URL."
    }

    if ($SourceValue -match '^https://github\.com/[^/]+/[^/]+/?($|tree/|blob/)') {
        throw "Provide a build artifact URL, not a GitHub repository page. Build the app first, package the published output, then use the artifact URL."
    }

    $downloadPath = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName() + ".zip")
    $headers = Get-DownloadHeaders -SourceValue $SourceValue

    try {
        Write-Host "Downloading deployment package: $SourceValue"
        if ($headers.Count -gt 0) {
            Invoke-WebRequest -Uri $SourceValue -OutFile $downloadPath -Headers $headers
        }
        else {
            Invoke-WebRequest -Uri $SourceValue -OutFile $downloadPath
        }

        Expand-DeploymentPackage -SourceFile $downloadPath -TargetPath $targetPath
    }
    finally {
        Remove-Item -LiteralPath $downloadPath -Force -ErrorAction SilentlyContinue
    }

    return [string]$targetPath
}

function Find-ApplicationAssembly {
    param([Parameter(Mandatory = $true)][string]$DeploymentPath)

    $runtimeConfig = Get-ChildItem -Path $DeploymentPath -Filter *.runtimeconfig.json -Recurse |
        Where-Object { $_.FullName -notmatch '[\\/](ref|refs)[\\/]' } |
        Select-Object -First 1

    if ($runtimeConfig) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($runtimeConfig.BaseName)
        $dllPath = Join-Path $runtimeConfig.DirectoryName "$baseName.dll"
        if (Test-Path -LiteralPath $dllPath) {
            return $dllPath
        }
    }

    $dll = Get-ChildItem -Path $DeploymentPath -Filter *.dll -Recurse |
        Where-Object { $_.FullName -notmatch '[\\/](ref|refs)[\\/]' } |
        Select-Object -First 1

    if (-not $dll) {
        throw "No runnable application DLL was found. Provide a published framework-dependent build package or folder."
    }

    return $dll.FullName
}

function Get-LocalIPAddress {
    $candidateIps = Get-PreferredIPv4Addresses
    $privateIp = $candidateIps |
        Where-Object { Test-IsPrivateIPv4 -IPAddress $_.IPAddress } |
        Select-Object -First 1

    return $privateIp.IPAddress
}

function Get-PreferredIPv4Addresses {
    $interfaceMap = @{}
    Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object {
        $interfaceMap[$_.InterfaceIndex] = $_
    }

    $adapterMap = @{}
    Get-NetAdapter -ErrorAction SilentlyContinue | ForEach-Object {
        $adapterMap[$_.InterfaceIndex] = $_
    }

    return Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.ValidLifetime -gt 0
        } |
        Sort-Object @{
            Expression = {
                $adapter = $adapterMap[$_.InterfaceIndex]
                if (-not $adapter) { return 2 }

                $name = "$($adapter.Name) $($adapter.InterfaceDescription)"
                if ($name -match '(?i)\b(ethernet|gigabit|lan)\b') { return 0 }
                if ($name -match '(?i)\b(wi-?fi|wireless|wlan)\b') { return 1 }
                return 2
            }
        }, @{
            Expression = {
                if ($_.IPAddress -match '^192\.168\.') { return 0 }
                if ($_.IPAddress -match '^10\.') { return 1 }
                if ($_.IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.') { return 2 }
                return 3
            }
        }, @{
            Expression = {
                $ipInterface = $interfaceMap[$_.InterfaceIndex]
                if ($ipInterface) { return $ipInterface.InterfaceMetric }
                return 9999
            }
        }, SkipAsSource
}

function Test-IsPrivateIPv4 {
    param([Parameter(Mandatory = $true)][string]$IPAddress)

    if ($IPAddress -match '^10\.') {
        return $true
    }

    if ($IPAddress -match '^192\.168\.') {
        return $true
    }

    if ($IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.') {
        return $true
    }

    return $false
}

function Get-StaticIPAddress {
    $candidateIps = Get-PreferredIPv4Addresses
    $publicIp = $candidateIps |
        Where-Object { -not (Test-IsPrivateIPv4 -IPAddress $_.IPAddress) } |
        Select-Object -First 1

    return $publicIp.IPAddress
}

function Resolve-HostName {
    param([string]$DomainName)

    if (-not [string]::IsNullOrWhiteSpace($DomainName)) {
        return $DomainName.Trim()
    }

    $staticIp = Get-StaticIPAddress
    if (-not [string]::IsNullOrWhiteSpace($staticIp)) {
        return $staticIp
    }

    $localIp = Get-LocalIPAddress
    if (-not [string]::IsNullOrWhiteSpace($localIp)) {
        return $localIp
    }

    return "localhost"
}

function Ensure-ServerCertificate {
    param([Parameter(Mandatory = $true)][string]$HostName)

    $existing = Get-ChildItem -Path Cert:\LocalMachine\My |
        Where-Object {
            $_.Subject -match "CN=$([regex]::Escape($HostName))($|,)" -and
            $_.NotAfter -gt (Get-Date)
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if ($existing) {
        return $existing
    }

    if ($HostName -match '^\d{1,3}(\.\d{1,3}){3}$') {
        return New-SelfSignedCertificate `
            -Subject "CN=$HostName" `
            -CertStoreLocation "Cert:\LocalMachine\My" `
            -KeyAlgorithm RSA `
            -KeyLength 2048 `
            -HashAlgorithm SHA256 `
            -NotAfter (Get-Date).AddYears(3)
    }

    return New-SelfSignedCertificate `
        -DnsName $HostName `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(3)
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

function Grant-IisFolderAccess {
    param(
        [Parameter(Mandatory = $true)][string]$PublishPath,
        [Parameter(Mandatory = $true)][string]$AppPoolName
    )

    $appPoolIdentity = "IIS AppPool\$AppPoolName"
    $grantRule = "{0}:(OI)(CI)(RX)" -f $appPoolIdentity
    $iisUsersRule = "IIS_IUSRS:(OI)(CI)(RX)"

    & icacls $PublishPath /grant $grantRule /grant $iisUsersRule /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to grant IIS access to '$PublishPath'."
    }
}

function Test-LocalHttpsEndpoint {
    param([Parameter(Mandatory = $true)][int]$Port)

    $previousCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

    try {
        $request = [System.Net.HttpWebRequest]::Create("https://localhost:$Port/")
        $request.Method = "GET"
        $request.Timeout = 10000
        $request.ReadWriteTimeout = 10000

        try {
            $response = $request.GetResponse()
            $response.Close()
            return $true
        }
        catch [System.Net.WebException] {
            $webResponse = $_.Exception.Response
            if ($webResponse) {
                $statusCode = [int]$webResponse.StatusCode
                $webResponse.Close()

                # 404/401/etc. still proves the app and IIS pipeline are responding.
                if ($statusCode -ne 503) {
                    return $true
                }
            }

            return $false
        }
    }
    finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $previousCallback
    }
}

function Configure-IisSite {
    param(
        [Parameter(Mandatory = $true)][string]$PublishPath,
        [Parameter(Mandatory = $true)][string]$AppPoolName,
        [Parameter(Mandatory = $true)][string]$WebsiteName,
        [Parameter(Mandatory = $true)][int]$HttpPort,
        [Parameter(Mandatory = $true)][int]$HttpsPortNumber,
        [string]$DomainName,
        [Parameter(Mandatory = $true)][System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )

    Import-Module WebAdministration

    $hostHeader = ""
    $sslFlags = 0
    if (-not [string]::IsNullOrWhiteSpace($DomainName)) {
        $hostHeader = $DomainName.Trim()
        $sslFlags = 1
    }

    $resolvedHttpPort = $HttpPort
    $resolvedHttpsPort = $HttpsPortNumber

    if ([string]::IsNullOrWhiteSpace($hostHeader)) {
        $httpConflict = Get-Website |
            Where-Object {
                $_.Name -ne $WebsiteName -and
                $_.Bindings.Collection.bindingInformation -contains "*:${HttpPort}:"
            } |
            Select-Object -First 1

        if ($httpConflict) {
            $resolvedHttpPort = 8080
            Write-Host "HTTP port $HttpPort is already used by IIS site '$($httpConflict.Name)'. Using port $resolvedHttpPort instead."
        }

        $httpsConflict = Get-WebBinding -Protocol "https" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ItemXPath -ne $null -and
                $_.bindingInformation -eq "*:${HttpsPortNumber}:"
            } |
            Select-Object -First 1

        if ($httpsConflict) {
            $resolvedHttpsPort = 8443
            Write-Host "HTTPS port $HttpsPortNumber is already used by another IIS binding. Using port $resolvedHttpsPort instead."
        }
    }

    if (-not (Test-Path "IIS:\AppPools\$AppPoolName")) {
        New-WebAppPool -Name $AppPoolName | Out-Null
    }

    Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name managedRuntimeVersion -Value ""
    Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name autoStart -Value $true
    Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name startMode -Value "AlwaysRunning"
    Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name processModel.loadUserProfile -Value $true

    if (Test-Path "IIS:\Sites\$WebsiteName") {
        Stop-Website -Name $WebsiteName -ErrorAction SilentlyContinue
        Remove-Website -Name $WebsiteName
    }

    New-Website -Name $WebsiteName -Port $resolvedHttpPort -PhysicalPath $PublishPath -ApplicationPool $AppPoolName -HostHeader $hostHeader | Out-Null

    if (-not (Get-WebBinding -Name $WebsiteName -Protocol "https" -ErrorAction SilentlyContinue)) {
        New-WebBinding -Name $WebsiteName -Protocol "https" -Port $resolvedHttpsPort -HostHeader $hostHeader -SslFlags $sslFlags | Out-Null
    }

    Push-Location IIS:\SslBindings
    try {
        if ($sslFlags -eq 1) {
            $bindingPath = "0.0.0.0!$resolvedHttpsPort!$hostHeader"
        }
        else {
            $bindingPath = "0.0.0.0!$resolvedHttpsPort"
        }

        if (Test-Path $bindingPath) {
            Remove-Item $bindingPath -Force
        }

        Get-Item "Cert:\LocalMachine\My\$($Certificate.Thumbprint)" | New-Item $bindingPath -SslFlags $sslFlags | Out-Null
    }
    finally {
        Pop-Location
    }

    Grant-IisFolderAccess -PublishPath $PublishPath -AppPoolName $AppPoolName

    $appPool = Get-ChildItem "IIS:\AppPools\$AppPoolName" -ErrorAction SilentlyContinue
    if ($appPool -and $appPool.State -ne "Started") {
        Start-WebAppPool -Name $AppPoolName | Out-Null
    }

    Start-Website -Name $WebsiteName | Out-Null

    Start-Sleep -Seconds 2
    if (-not (Test-LocalHttpsEndpoint -Port $resolvedHttpsPort)) {
        $currentPool = Get-ChildItem "IIS:\AppPools\$AppPoolName" -ErrorAction SilentlyContinue
        $poolState = if ($currentPool) { $currentPool.State } else { "Unknown" }
        throw "IIS site started, but HTTPS health check failed on port $resolvedHttpsPort (app pool state: $poolState). Check Application Event Log and stdout logs for app startup errors."
    }

    return @{
        HttpPort = $resolvedHttpPort
        HttpsPort = $resolvedHttpsPort
    }
}

Assert-Administrator
$DotNetChannel = Resolve-DotNetChannel -Value $DotNetChannel
Install-WindowsFeatureSet
Install-DotNetPrerequisites -Channel $DotNetChannel -SdkUrl $SdkInstallerUrl -RuntimeUrl $AspNetRuntimeUrl -HostingUrl $HostingBundleUrl

$sourceValue = if (-not [string]::IsNullOrWhiteSpace($SourceValue)) { $SourceValue } else { Read-Host "Enter a build artifact URL, a local source folder, a local published folder, or a local published .zip path to deploy (leave blank to skip)" }
if ([string]::IsNullOrWhiteSpace($sourceValue)) {
    Write-Host "Setup completed. IIS and .NET prerequisites are installed."
    exit 0
}

$domainName = if (-not [string]::IsNullOrWhiteSpace($DomainName)) { $DomainName } else { Read-Host "Enter a domain name for the site (leave blank to auto-detect the best IP address)" }
$resolvedHost = Resolve-HostName -DomainName $domainName
$certificate = Ensure-ServerCertificate -HostName $resolvedHost

$deploymentRoot = Join-Path $env:SystemDrive "inetpub\wwwroot"
New-Item -ItemType Directory -Path $deploymentRoot -Force | Out-Null

$deploymentPath = Resolve-DeploymentSource -SourceValue $sourceValue -TargetRoot $deploymentRoot -WebsiteName $SiteName
$assemblyPath = Find-ApplicationAssembly -DeploymentPath $deploymentPath
$assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($assemblyPath)
$publishPath = Split-Path -Path $assemblyPath -Parent

Ensure-WebConfig -PublishPath $publishPath -AssemblyName $assemblyName
$siteBinding = Configure-IisSite `
    -PublishPath $publishPath `
    -AppPoolName $SiteName `
    -WebsiteName $SiteName `
    -HttpPort $SitePort `
    -HttpsPortNumber $HttpsPort `
    -DomainName $domainName `
    -Certificate $certificate

Write-Host "Deployment complete."
Write-Host "Preferred host: $resolvedHost"
Write-Host "HTTP URL: http://${resolvedHost}:$($siteBinding.HttpPort)"
Write-Host "HTTPS URL: https://${resolvedHost}:$($siteBinding.HttpsPort)"
