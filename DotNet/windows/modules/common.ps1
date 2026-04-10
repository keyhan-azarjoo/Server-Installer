Set-StrictMode -Version Latest

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-DotNetExecutablePath {
    $dotnetCommand = Get-Command "dotnet" -ErrorAction SilentlyContinue
    if ($dotnetCommand -and $dotnetCommand.Source) {
        return $dotnetCommand.Source
    }

    foreach ($candidate in @(
        (Join-Path $env:ProgramFiles "dotnet\dotnet.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "dotnet\dotnet.exe"),
        "C:\Program Files\dotnet\dotnet.exe",
        "C:\Program Files (x86)\dotnet\dotnet.exe"
    )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Assert-Administrator {
    param([hashtable]$OriginalBoundParameters)

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        return
    }

    $scriptPath = $PSCommandPath
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        throw "Run this script from an elevated PowerShell session."
    }

    $argumentList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $scriptPath)
    )

    foreach ($entry in $OriginalBoundParameters.GetEnumerator()) {
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

function Test-IsUrl {
    param([Parameter(Mandatory = $true)][string]$Value)

    return $Value -match '^(https?)://'
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

    throw "Unable to determine a .NET major version from '$Channel'."
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

function Test-DotNetSdkInstalled {
    param([Parameter(Mandatory = $true)][string]$MajorVersion)

    $dotnetExe = Get-DotNetExecutablePath
    if (-not $dotnetExe) {
        return $false
    }

    $sdkList = & $dotnetExe --list-sdks 2>$null
    return [bool]($sdkList | Where-Object { $_ -match "^$([regex]::Escape($MajorVersion))\." })
}

function Test-AspNetRuntimeInstalled {
    param([Parameter(Mandatory = $true)][string]$MajorVersion)

    $dotnetExe = Get-DotNetExecutablePath
    if (-not $dotnetExe) {
        return $false
    }

    $runtimeList = & $dotnetExe --list-runtimes 2>$null
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
                $_.PSObject.Properties.Match("DisplayName").Count -gt 0 -and
                $_.PSObject.Properties.Match("DisplayVersion").Count -gt 0 -and
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
        [Parameter(Mandatory = $true)][string]$Channel,
        [string]$SdkUrl,
        [string]$RuntimeUrl,
        [string]$HostingUrl,
        [switch]$SkipHostingBundle
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
        Install-Executable -Url $SdkUrl -FileName "dotnet-sdk-win-x64.exe" -Arguments "/install /quiet /norestart"
    }

    if (Test-AspNetRuntimeInstalled -MajorVersion $majorVersion) {
        Write-Host "ASP.NET Core Runtime $majorVersion already installed."
    }
    else {
        Install-Executable -Url $RuntimeUrl -FileName "aspnetcore-runtime-win-x64.exe" -Arguments "/install /quiet /norestart"
    }

    if ($SkipHostingBundle) {
        Write-Host "Skipping ASP.NET Core Hosting Bundle install."
    }
    else {
        if (Test-HostingBundleInstalled -MajorVersion $majorVersion) {
            Write-Host "ASP.NET Core Hosting Bundle $majorVersion already installed."
        }
        else {
            Install-Executable -Url $HostingUrl -FileName "dotnet-hosting-win.exe" -Arguments "/install /quiet /norestart OPT_NO_ANCM=0"
        }
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
    param(
        [Parameter(Mandatory = $true)][string]$SourceValue,
        [string]$GitHubToken
    )

    $headers = @{}
    if ($SourceValue -match '^https://(github\.com|api\.github\.com|objects\.githubusercontent\.com|raw\.githubusercontent\.com)/') {
        if ([string]::IsNullOrWhiteSpace($GitHubToken)) {
            if ($env:SERVER_INSTALLER_NONINTERACTIVE -eq "1") {
                Write-Host "No GitHub token provided in non-interactive mode; continuing as public download."
            }
            else {
                $GitHubToken = Read-Host "Enter GitHub token for private artifact access (leave blank for public download)"
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($GitHubToken)) {
            $headers["Authorization"] = "Bearer $GitHubToken"
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
    if ([System.IO.Path]::GetExtension($SourceFile) -ieq ".zip") {
        Expand-Archive -LiteralPath $SourceFile -DestinationPath $TargetPath -Force
        return
    }

    throw "Unsupported package format. Provide a .zip package or a local folder."
}

function Find-ProjectPath {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $project = Get-ChildItem -Path $RootPath -Filter *.csproj -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $project) { return $null }
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

function Copy-FolderContent {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    if (Test-Path -LiteralPath $TargetPath) {
        Remove-Item -LiteralPath $TargetPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null
    Copy-Item -Path (Join-Path $SourcePath '*') -Destination $TargetPath -Recurse -Force
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

    if (Test-Path -LiteralPath $TargetRoot) {
        Remove-Item -LiteralPath $TargetRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null

    Write-Host "Publishing local source project: $projectPath"
    & dotnet publish $projectPath -c Release -o $TargetRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "dotnet publish failed."
    }

    return [string]$TargetRoot
}

function Prepare-DeploymentContent {
    param(
        [Parameter(Mandatory = $true)][string]$SourceValue,
        [Parameter(Mandatory = $true)][string]$StagingRoot,
        [string]$GitHubToken
    )

    if (Test-Path -LiteralPath $StagingRoot) {
        Remove-Item -LiteralPath $StagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null

    if (Test-Path -LiteralPath $SourceValue -PathType Container) {
        $resolvedSource = (Resolve-Path -LiteralPath $SourceValue).Path
        $publishedPath = Find-PublishedAppPath -RootPath $resolvedSource
        if ($publishedPath) {
            Write-Host "Found published application under: $publishedPath"
            Copy-FolderContent -SourcePath $publishedPath -TargetPath $StagingRoot
            return [string]$StagingRoot
        }

        $publishedOutput = Publish-LocalSource -SourceRoot $resolvedSource -TargetRoot $StagingRoot
        if ($publishedOutput) {
            return [string]$publishedOutput
        }

        Copy-FolderContent -SourcePath $resolvedSource -TargetPath $StagingRoot
        return [string]$StagingRoot
    }

    if (Test-Path -LiteralPath $SourceValue -PathType Leaf) {
        if ([System.IO.Path]::GetExtension($SourceValue) -ieq ".zip") {
            Expand-DeploymentPackage -SourceFile (Resolve-Path -LiteralPath $SourceValue).Path -TargetPath $StagingRoot
            return [string]$StagingRoot
        }
        throw "Local file sources must be .zip packages."
    }

    if (-not (Test-IsUrl -Value $SourceValue)) {
        throw "The source path '$SourceValue' does not exist."
    }

    if ($SourceValue -match '^https://github\.com/[^/]+/[^/]+/?($|tree/|blob/)') {
        throw "Provide a build artifact URL, not a GitHub repository page."
    }

    $downloadPath = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName() + ".zip")
    $headers = Get-DownloadHeaders -SourceValue $SourceValue -GitHubToken $GitHubToken

    try {
        Write-Host "Downloading deployment package: $SourceValue"
        if ($headers.Count -gt 0) {
            Invoke-WebRequest -Uri $SourceValue -OutFile $downloadPath -Headers $headers
        }
        else {
            Invoke-WebRequest -Uri $SourceValue -OutFile $downloadPath
        }
        Expand-DeploymentPackage -SourceFile $downloadPath -TargetPath $StagingRoot
    }
    finally {
        Remove-Item -LiteralPath $downloadPath -Force -ErrorAction SilentlyContinue
    }

    return [string]$StagingRoot
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
        throw "No runnable application DLL was found."
    }

    return $dll.FullName
}

function Test-IsPrivateIPv4 {
    param([Parameter(Mandatory = $true)][string]$IPAddress)

    if ($IPAddress -match '^10\.') { return $true }
    if ($IPAddress -match '^192\.168\.') { return $true }
    if ($IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.') { return $true }
    return $false
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
                if ($_.IPAddress -match '^192\.168\.') { return 0 }
                if ($_.IPAddress -match '^10\.') { return 1 }
                if ($_.IPAddress -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.') { return 2 }
                return 3
            }
        }, @{
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
                $ipInterface = $interfaceMap[$_.InterfaceIndex]
                if ($ipInterface) { return $ipInterface.InterfaceMetric }
                return 9999
            }
        }, SkipAsSource
}

function Get-StaticIPAddress {
    $candidateIps = Get-PreferredIPv4Addresses
    $publicIp = $candidateIps |
        Where-Object { -not (Test-IsPrivateIPv4 -IPAddress $_.IPAddress) } |
        Select-Object -First 1

    if ($publicIp) {
        return $publicIp.IPAddress
    }

    return $null
}

function Get-LocalIPAddress {
    $candidateIps = Get-PreferredIPv4Addresses
    $privateIp = $candidateIps |
        Where-Object { Test-IsPrivateIPv4 -IPAddress $_.IPAddress } |
        Select-Object -First 1

    if ($privateIp) {
        return $privateIp.IPAddress
    }

    return $null
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
