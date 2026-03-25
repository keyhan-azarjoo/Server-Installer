Set-StrictMode -Version Latest

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
        $appPoolState = Get-WebAppPoolState -Name $WebsiteName -ErrorAction SilentlyContinue
        if ($null -ne $appPoolState -and $appPoolState.Value -eq "Started") {
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
        Write-Host "Initial file removal failed. Stopping IIS core services and retrying."

        Stop-Service W3SVC -Force -ErrorAction SilentlyContinue
        Stop-Service WAS -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2

        try {
            Remove-Item -LiteralPath $TargetPath -Recurse -Force
        }
        catch {
            Start-Service WAS -ErrorAction SilentlyContinue
            Start-Service W3SVC -ErrorAction SilentlyContinue
            throw "Failed to remove existing deployment path '$TargetPath'. Files are still locked. $($_.Exception.Message)"
        }

        Start-Service WAS -ErrorAction SilentlyContinue
        Start-Service W3SVC -ErrorAction SilentlyContinue
    }
}

function Remove-ConflictingBinding {
    param(
        [Parameter(Mandatory = $true)][string]$WebsiteName,
        [Parameter(Mandatory = $true)][string]$Protocol,
        [Parameter(Mandatory = $true)][int]$Port,
        [string]$HostHeader
    )

    Import-Module WebAdministration

    $targetBindingInformation = "*:${Port}:$HostHeader"
    $conflictingSites = Get-Website | Where-Object {
        $_.Name -ne $WebsiteName -and
        ($_.Bindings.Collection | Where-Object {
            $_.protocol -eq $Protocol -and $_.bindingInformation -eq $targetBindingInformation
        })
    }

    foreach ($site in $conflictingSites) {
        Write-Host "Removing conflicting $Protocol binding from IIS site '$($site.Name)' on port $Port."
        Stop-Website -Name $site.Name -ErrorAction SilentlyContinue | Out-Null
        Remove-WebBinding -Name $site.Name -Protocol $Protocol -Port $Port -HostHeader $HostHeader | Out-Null
    }
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
        return New-SelfSignedCertificate -Subject "CN=$HostName" -CertStoreLocation "Cert:\LocalMachine\My" -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(3)
    }

    return New-SelfSignedCertificate -DnsName $HostName -CertStoreLocation "Cert:\LocalMachine\My" -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(3)
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

    Remove-ConflictingBinding -WebsiteName $WebsiteName -Protocol "http" -Port $resolvedHttpPort -HostHeader $hostHeader
    Remove-ConflictingBinding -WebsiteName $WebsiteName -Protocol "https" -Port $resolvedHttpsPort -HostHeader $hostHeader

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

    $remainingHttpConflict = Get-Website | Where-Object {
        $_.Name -ne $WebsiteName -and
        ($_.Bindings.Collection | Where-Object {
            $_.protocol -eq "http" -and $_.bindingInformation -eq "*:${resolvedHttpPort}:$hostHeader"
        })
    } | Select-Object -First 1
    if ($remainingHttpConflict) {
        throw "HTTP port $resolvedHttpPort is still occupied by IIS site '$($remainingHttpConflict.Name)'."
    }

    $remainingHttpsConflict = Get-Website | Where-Object {
        $_.Name -ne $WebsiteName -and
        ($_.Bindings.Collection | Where-Object {
            $_.protocol -eq "https" -and $_.bindingInformation -eq "*:${resolvedHttpsPort}:$hostHeader"
        })
    } | Select-Object -First 1
    if ($remainingHttpsConflict) {
        throw "HTTPS port $resolvedHttpsPort is still occupied by IIS site '$($remainingHttpsConflict.Name)'."
    }

    New-Website -Name $WebsiteName -Port $resolvedHttpPort -PhysicalPath $PublishPath -ApplicationPool $AppPoolName -HostHeader $hostHeader | Out-Null
    if (-not (Get-WebBinding -Name $WebsiteName -Protocol "https" -ErrorAction SilentlyContinue)) {
        New-WebBinding -Name $WebsiteName -Protocol "https" -Port $resolvedHttpsPort -HostHeader $hostHeader -SslFlags $sslFlags | Out-Null
    }

    Push-Location IIS:\SslBindings
    try {
        $bindingPath = if ($sslFlags -eq 1) { "0.0.0.0!$resolvedHttpsPort!$hostHeader" } else { "0.0.0.0!$resolvedHttpsPort" }
        if (Test-Path $bindingPath) {
            Remove-Item $bindingPath -Force
        }
        Get-Item "Cert:\LocalMachine\My\$($Certificate.Thumbprint)" | New-Item $bindingPath -SslFlags $sslFlags | Out-Null
    }
    finally {
        Pop-Location
    }

    Grant-IisFolderAccess -PublishPath $PublishPath -AppPoolName $AppPoolName

    $appPoolState = Get-WebAppPoolState -Name $AppPoolName -ErrorAction SilentlyContinue
    if ($null -ne $appPoolState -and $appPoolState.Value -ne "Started") {
        Start-WebAppPool -Name $AppPoolName | Out-Null
    }

    Start-Website -Name $WebsiteName | Out-Null
    Start-Sleep -Seconds 2

    if (-not (Test-LocalHttpsEndpoint -Port $resolvedHttpsPort)) {
        $currentPoolState = Get-WebAppPoolState -Name $AppPoolName -ErrorAction SilentlyContinue
        $poolState = if ($null -ne $currentPoolState) { $currentPoolState.Value } else { "Unknown" }
        throw "IIS site started, but HTTPS health check failed on port $resolvedHttpsPort (app pool state: $poolState)."
    }

    return @{
        HttpPort = $resolvedHttpPort
        HttpsPort = $resolvedHttpsPort
    }
}

function Ensure-FirewallPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Protocol,
        [Parameter(Mandatory = $true)][string]$SiteName
    )

    $ruleName = "IIS $SiteName $Protocol $Port"
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Firewall rule already exists: $ruleName"
        return
    }

    Write-Host "Opening Windows Firewall inbound TCP $Port for $Protocol..."
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
}

function Invoke-IisDeployment {
    param(
        [Parameter(Mandatory = $true)][string]$ContentPath,
        [Parameter(Mandatory = $true)][string]$PackageName,
        [Parameter(Mandatory = $true)][string]$SiteName,
        [Parameter(Mandatory = $true)][int]$HttpPort,
        [Parameter(Mandatory = $true)][int]$HttpsPort,
        [string]$DomainName
    )

    $resolvedHost = Resolve-HostName -DomainName $DomainName
    $certificate = Ensure-ServerCertificate -HostName $resolvedHost
    $deploymentRoot = Join-Path $env:SystemDrive "inetpub\wwwroot"
    $targetPath = Join-Path $deploymentRoot $PackageName

    New-Item -ItemType Directory -Path $deploymentRoot -Force | Out-Null
    Remove-DeploymentPath -TargetPath $targetPath -WebsiteName $SiteName
    Copy-FolderContent -SourcePath $ContentPath -TargetPath $targetPath

    $assemblyPath = Find-ApplicationAssembly -DeploymentPath $targetPath
    $assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($assemblyPath)
    $publishPath = Split-Path -Path $assemblyPath -Parent

    Ensure-WebConfig -PublishPath $publishPath -AssemblyName $assemblyName
    $binding = Configure-IisSite -PublishPath $publishPath -AppPoolName $SiteName -WebsiteName $SiteName -HttpPort $HttpPort -HttpsPortNumber $HttpsPort -DomainName $DomainName -Certificate $certificate

    Ensure-FirewallPort -Port $binding.HttpPort -Protocol "HTTP" -SiteName $SiteName
    Ensure-FirewallPort -Port $binding.HttpsPort -Protocol "HTTPS" -SiteName $SiteName

    return @{
        Host = $resolvedHost
        HttpPort = $binding.HttpPort
        HttpsPort = $binding.HttpsPort
        Path = $targetPath
    }
}
