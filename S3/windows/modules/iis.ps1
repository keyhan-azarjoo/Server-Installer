function Ensure-IISInstalled {
  Info "Checking/Installing IIS prerequisites..."

  function Ensure-FeatureLocal([string]$name) {
    $f = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction SilentlyContinue
    if ($f -and $f.State -eq "Enabled") { return }
    Info "Enabling Windows feature: $name"
    $enabled = $false
    try {
      Enable-WindowsOptionalFeature -Online -FeatureName $name -All -NoRestart -ErrorAction Stop | Out-Null
      $enabled = $true
    } catch {
      Warn "PowerShell feature enable failed for $name. Trying DISM..."
    }
    if (-not $enabled) {
      dism /online /enable-feature /featurename:$name /all /norestart | Out-Null
    }
    $verify = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction SilentlyContinue
    if (-not $verify -or $verify.State -ne "Enabled") {
      Err "Failed to enable required Windows feature: $name"
      exit 1
    }
  }

  function Is-AppInstalledLocal([string]$displayNamePattern) {
    $paths = @(
      "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
      "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($p in $paths) {
      $apps = Get-ItemProperty -Path $p -ErrorAction SilentlyContinue
      if ($apps | Where-Object { $_.DisplayName -match $displayNamePattern }) { return $true }
    }
    return $false
  }

  function Install-MsiFromUrlsLocal([string[]]$urls, [string]$outFile) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outFile) | Out-Null
    foreach ($url in $urls) {
      try {
        Info "Downloading: $url"
        Invoke-WebRequest -Uri $url -OutFile $outFile
        if ((Test-Path $outFile) -and ((Get-Item $outFile).Length -gt 1000000)) {
          Info "Installing: $outFile"
          Start-Process -FilePath "msiexec.exe" -ArgumentList @("/i","`"$outFile`"","/qn","/norestart") -Wait
          return $true
        }
      } catch {
        Warn "Failed from URL: $url"
      }
    }
    return $false
  }

  $features = @(
    "IIS-WebServerRole","IIS-WebServer","IIS-CommonHttpFeatures","IIS-DefaultDocument",
    "IIS-StaticContent","IIS-HttpErrors","IIS-HttpRedirect","IIS-ApplicationDevelopment",
    "IIS-ISAPIExtensions","IIS-ISAPIFilter","IIS-ManagementConsole","IIS-WebSockets"
  )
  foreach ($f in $features) { Ensure-FeatureLocal $f }

  $dlDir = Join-Path $env:ProgramData "LocalS3\downloads"
  $rewriteMsi = Join-Path $dlDir "rewrite_amd64_en-US.msi"
  $arrMsi = Join-Path $dlDir "requestRouter_x64.msi"

  if (-not (Is-AppInstalledLocal "IIS URL Rewrite")) {
    Info "IIS URL Rewrite not found. Installing..."
    $rewriteUrls = @(
      "https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi",
      "https://www.iis.net/downloads/microsoft/url-rewrite"
    )
    if (-not (Install-MsiFromUrlsLocal -urls $rewriteUrls -outFile $rewriteMsi)) {
      Err "Failed to install IIS URL Rewrite automatically."
      exit 1
    }
  } else {
    Info "IIS URL Rewrite already installed."
  }

  if (-not (Is-AppInstalledLocal "Application Request Routing")) {
    Info "IIS ARR not found. Installing..."
    $arrUrls = @(
      "https://go.microsoft.com/fwlink/?LinkID=615136",
      "https://www.iis.net/downloads/microsoft/application-request-routing"
    )
    if (-not (Install-MsiFromUrlsLocal -urls $arrUrls -outFile $arrMsi)) {
      Err "Failed to install IIS ARR automatically."
      exit 1
    }
  } else {
    Info "IIS ARR already installed."
  }

  Info "IIS prerequisites installed successfully."
}

function Ensure-HttpSysUrlSegmentLimit([int]$minimumLength = 4096) {
  $regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\HTTP\Parameters"
  $currentValue = $null
  try {
    $currentValue = (Get-ItemProperty -Path $regPath -Name "UrlSegmentMaxLength" -ErrorAction SilentlyContinue).UrlSegmentMaxLength
  } catch {}

  $effectiveValue = if ($null -eq $currentValue) { 260 } else { [int]$currentValue }
  if ($effectiveValue -ge $minimumLength) {
    Info "HTTP.sys UrlSegmentMaxLength is already $effectiveValue."
    return
  }

  Warn "Windows HTTP.sys UrlSegmentMaxLength is $effectiveValue, which is too small for MinIO shared-file URLs."
  Info "Raising HTTP.sys UrlSegmentMaxLength to $minimumLength..."
  New-Item -Path $regPath -Force | Out-Null
  New-ItemProperty -Path $regPath -Name "UrlSegmentMaxLength" -PropertyType DWord -Value $minimumLength -Force | Out-Null
  Mark-RestartRequired "HTTP.sys UrlSegmentMaxLength increased to support long MinIO shared-file URLs"
}


function Ensure-IISProxyMode([string]$domain,[string]$siteRoot,[string]$certPath,[string]$keyPath,[int]$httpsPort,[int]$targetPort,[int]$consoleHttpsPort,[int]$uiPort,[string]$lanIp) {
  Import-Module WebAdministration
  $Script:IISCertIncludesIpSan = $false
  $Script:IISCertThumb = ""
  $siteName = "LocalS3"
  New-Item -ItemType Directory -Force -Path $siteRoot | Out-Null

  # Determine the IP to bind IIS on: use the user-selected IP ($domain when it is an IPv4
  # literal) so IIS only answers on that interface. Fall back to the detected LAN IP, or $null
  # (all interfaces) if neither is available.
  $bindIp = if (Test-IPv4Literal $domain) { $domain } elseif ($lanIp) { $lanIp } else { $null }
  if (Test-Path "IIS:\Sites\$siteName") {
    try { Stop-Website -Name $siteName -ErrorAction SilentlyContinue } catch {}
  }
  try { Stop-WebAppPool -Name "DefaultAppPool" -ErrorAction SilentlyContinue | Out-Null } catch {}
  Start-Sleep -Seconds 2
  $webConfig = @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.web>
    <httpRuntime maxUrlLength="16384" maxQueryStringLength="16384" />
  </system.web>
  <system.webServer>
    <security>
      <requestFiltering allowDoubleEscaping="true">
        <requestLimits maxAllowedContentLength="4294967295" maxUrl="16384" maxQueryString="16384" />
      </requestFiltering>
    </security>
    <rewrite>
      <rules>
        <rule name="MinIOConsoleProxy" stopProcessing="true">
          <match url="(.*)" />
          <conditions>
            <add input="{SERVER_PORT}" pattern="^$consoleHttpsPort$" />
          </conditions>
          <serverVariables>
            <set name="HTTP_HOST" value="{HTTP_HOST}" />
            <set name="HTTP_X_REAL_IP" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_SCHEME" value="https" />
            <set name="HTTP_X_FORWARDED_SSL" value="on" />
            <set name="HTTP_X_FORWARDED_PORT" value="{SERVER_PORT}" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
            <set name="HTTP_UPGRADE" value="{HTTP_UPGRADE}" />
            <set name="HTTP_CONNECTION" value="{HTTP_CONNECTION}" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:$uiPort/{R:1}" />
        </rule>
        <rule name="MinIOApiProxy" stopProcessing="true">
          <match url="(.*)" />
          <serverVariables>
            <set name="HTTP_HOST" value="{HTTP_HOST}" />
            <set name="HTTP_X_REAL_IP" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_SCHEME" value="https" />
            <set name="HTTP_X_FORWARDED_SSL" value="on" />
            <set name="HTTP_X_FORWARDED_PORT" value="{SERVER_PORT}" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
          </serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:$targetPort/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"@
  $webConfigPath = Join-Path $siteRoot "web.config"
  $webConfigTmp = "$webConfigPath.tmp"
  $webConfigWritten = $false
  for ($attempt = 1; $attempt -le 8; $attempt++) {
    try {
      [System.IO.File]::WriteAllText($webConfigTmp, $webConfig, (New-Object System.Text.UTF8Encoding($false)))
      Move-Item -Path $webConfigTmp -Destination $webConfigPath -Force
      $webConfigWritten = $true
      break
    } catch {
      Remove-Item -Path $webConfigTmp -Force -ErrorAction SilentlyContinue
      if ($attempt -lt 8) {
        Start-Sleep -Milliseconds 750
      }
    }
  }
  if (-not $webConfigWritten) {
    Err "Failed to update IIS web.config at $webConfigPath because the file remained locked."
    Warn "Stop the existing LocalS3 IIS site/app pool, then rerun the installer."
    exit 1
  }

  try {
    Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/proxy" -Name "enabled" -Value "True" -ErrorAction Stop | Out-Null
    Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/proxy" -Name "preserveHostHeader" -Value "True" -ErrorAction Stop | Out-Null
    Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/proxy" -Name "reverseRewriteHostInResponseHeaders" -Value "False" -ErrorAction Stop | Out-Null
    try {
      Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/proxy" -Name "maxResponseBufferSize" -Value 0 -ErrorAction Stop | Out-Null
    } catch {}
    try {
      Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/proxy" -Name "allowSslOffloading" -Value "True" -ErrorAction Stop | Out-Null
    } catch {
      Warn "ARR property 'allowSslOffloading' is not available on this IIS version. Continuing."
    }
  } catch {
    Err "IIS reverse proxy is not available (ARR/URL Rewrite missing)."
    Warn "Install these IIS extensions, then rerun in IIS mode:"
    Write-Host "  - URL Rewrite"
    Write-Host "  - Application Request Routing (ARR)"
    exit 1
  }

  try {
    $allowedVars = Get-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/rewrite/allowedServerVariables" -Name "." -ErrorAction Stop
    foreach ($varName in @("HTTP_HOST","HTTP_X_REAL_IP","HTTP_X_FORWARDED_PROTO","HTTP_X_FORWARDED_SCHEME","HTTP_X_FORWARDED_SSL","HTTP_X_FORWARDED_PORT","HTTP_X_FORWARDED_HOST","HTTP_X_FORWARDED_FOR","HTTP_UPGRADE","HTTP_CONNECTION")) {
      $alreadyAllowed = $false
      if ($allowedVars -and $allowedVars.Collection) {
        $alreadyAllowed = $null -ne ($allowedVars.Collection | Where-Object { $_.Attributes["name"].Value -eq $varName } | Select-Object -First 1)
      }
      if (-not $alreadyAllowed) {
        Add-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter "system.webServer/rewrite/allowedServerVariables" -Name "." -Value @{ name = $varName } -ErrorAction Stop | Out-Null
      }
    }
  } catch {
    Warn "Could not update IIS Rewrite allowed server variables automatically. If proxy requests fail, allow HTTP_X_FORWARDED_PROTO/HOST/FOR and HTTP_UPGRADE/CONNECTION in IIS Rewrite settings."
  }

  # Remove legacy LocalS3 certs before generating a fresh trust chain.
  # Older versions stored a self-signed localhost leaf in Root, which can cause Go to
  # pick the wrong authority and fail with "crypto/rsa: verification error".
  Get-ChildItem Cert:\LocalMachine\My | Where-Object {
    $_.FriendlyName -in @("LocalS3-HTTPS","LocalS3 HTTPS","LocalS3 Root CA") -or
    ($_.Subject -eq "CN=localhost" -and $_.Issuer -eq $_.Subject)
  } | Remove-Item -Force -ErrorAction SilentlyContinue
  Get-ChildItem Cert:\LocalMachine\Root | Where-Object {
    $_.FriendlyName -in @("LocalS3-HTTPS","LocalS3 HTTPS","LocalS3 Root CA") -or
    ($_.Subject -eq "CN=localhost" -and $_.Issuer -eq $_.Subject)
  } | Remove-Item -Force -ErrorAction SilentlyContinue
  # Clean up ALL netsh SSL bindings for this port (both SNI hostnameport and non-SNI ipport).
  # Stale bindings from prior installs keep pointing to the old cert even after IIS site removal.
  netsh http delete sslcert hostnameport="localhost:$httpsPort"   2>$null | Out-Null
  netsh http delete sslcert hostnameport="127.0.0.1:$httpsPort"  2>$null | Out-Null
  if ($domain -and $domain -ne "localhost") {
    netsh http delete sslcert hostnameport="${domain}:$httpsPort" 2>$null | Out-Null
  }
  netsh http delete sslcert ipport="0.0.0.0:$httpsPort"          2>$null | Out-Null
  netsh http delete sslcert ipport="127.0.0.1:$httpsPort"        2>$null | Out-Null
  if ($lanIp) { netsh http delete sslcert ipport="${lanIp}:${httpsPort}" 2>$null | Out-Null }
  if ($bindIp -and $bindIp -ne $lanIp) { netsh http delete sslcert ipport="${bindIp}:${httpsPort}" 2>$null | Out-Null }
  netsh http delete sslcert hostnameport="localhost:$consoleHttpsPort"   2>$null | Out-Null
  netsh http delete sslcert hostnameport="127.0.0.1:$consoleHttpsPort"  2>$null | Out-Null
  if ($domain -and $domain -ne "localhost") {
    netsh http delete sslcert hostnameport="${domain}:$consoleHttpsPort" 2>$null | Out-Null
  }
  netsh http delete sslcert ipport="0.0.0.0:$consoleHttpsPort"          2>$null | Out-Null
  netsh http delete sslcert ipport="127.0.0.1:$consoleHttpsPort"        2>$null | Out-Null
  if ($lanIp) { netsh http delete sslcert ipport="${lanIp}:${consoleHttpsPort}" 2>$null | Out-Null }
  if ($bindIp -and $bindIp -ne $lanIp) { netsh http delete sslcert ipport="${bindIp}:${consoleHttpsPort}" 2>$null | Out-Null }

  # Build SAN: always include localhost + 127.0.0.1, plus domain and LAN IP if present
  $sanExt = "2.5.29.17={text}DNS=localhost&IPAddress=127.0.0.1"
  if ($domain -and $domain -ne "localhost") {
    if (Test-IPv4Literal $domain) { $sanExt += "&IPAddress=$domain" } else { $sanExt += "&DNS=$domain" }
  }
  if ($lanIp) { $sanExt += "&IPAddress=$lanIp" }

  $rootCa = $null
  $cert = $null
  $rootPath = Join-Path $env:TEMP "locals3-root-ca.cer"
  $rootBcExt = "2.5.29.19={critical}{text}ca=true&pathlength=1"
  $leafBcExt = "2.5.29.19={critical}{text}ca=false"
  $serverAuthExt = "2.5.29.37={text}1.3.6.1.5.5.7.3.1"

  try {
    $rootCa = New-SelfSignedCertificate -Subject "CN=LocalS3 Root CA" `
      -FriendlyName "LocalS3 Root CA" `
      -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
      -KeyExportPolicy Exportable `
      -KeyUsage CertSign, CRLSign, DigitalSignature `
      -TextExtension @($rootBcExt) `
      -CertStoreLocation "Cert:\LocalMachine\My" `
      -NotAfter (Get-Date).AddYears(5)
    if (-not $rootCa) { throw "Root CA certificate was not created." }

    $rootExport = Export-Certificate -Cert "Cert:\LocalMachine\My\$($rootCa.Thumbprint)" -FilePath $rootPath -Force
    Import-Certificate -FilePath $rootExport.FullName -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null

    $leafExtensions = @($sanExt, $leafBcExt, $serverAuthExt)
    $cert = New-SelfSignedCertificate -Subject "CN=localhost" `
      -FriendlyName "LocalS3 HTTPS" `
      -Signer $rootCa `
      -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
      -KeyExportPolicy Exportable `
      -KeyUsage DigitalSignature, KeyEncipherment `
      -TextExtension $leafExtensions `
      -CertStoreLocation "Cert:\LocalMachine\My" `
      -NotAfter (Get-Date).AddYears(3)
    if (-not $cert) { throw "Leaf certificate was not created." }

    $Script:IISCertIncludesIpSan = $true
    Info "Generated LocalS3 root CA and server certificate."
  } catch {
    Err "Failed to generate IIS HTTPS certificates: $($_.Exception.Message)"
    Warn "Open certlm.msc and remove old 'LocalS3 Root CA' / 'localhost' certificates if this keeps failing."
    exit 1
  } finally {
    Remove-Item -Path $rootPath -Force -ErrorAction SilentlyContinue
  }

  $thumb = $cert.Thumbprint
  $Script:IISCertThumb = $thumb
  Export-Certificate -Cert "Cert:\LocalMachine\My\$thumb" -FilePath $certPath -Force | Out-Null

  foreach ($legacySite in @("LocalS3", "LocalS3-IIS", "LocalS3-Console")) {
    if (Test-Path "IIS:\Sites\$legacySite") {
      Remove-Website -Name $legacySite
    }
  }
  New-Website -Name $siteName -PhysicalPath $siteRoot -Port 80 -Force | Out-Null
  # Stop and remove all bindings (including the default HTTP port-80) before adding only HTTPS.
  # Leaving the port-80 binding causes a conflict with Default Web Site, which prevents startup.
  Stop-Website -Name $siteName -ErrorAction SilentlyContinue
  Get-WebBinding -Name $siteName | Remove-WebBinding -ErrorAction SilentlyContinue
  # Use non-SNI binding (SslFlags=0, no HostHeader) so HTTP.SYS uses per-IP (ipport) cert entries.
  # SNI (SslFlags=1) uses hostnameport entries that can silently fail to update across reinstalls.
  #
  # When the user selected a specific IP, bind to 127.0.0.1 (for local health checks / IIS
  # proxy back-channel) PLUS the selected IP (for external client access). This prevents IIS
  # from answering on other interfaces such as a static WAN IP the user did not choose.
  # When no specific IP is known, fall back to the wildcard "*" (original behaviour).
  if ($bindIp) {
    # API port: loopback for internal health checks + selected IP for external access
    New-WebBinding -Name $siteName -Protocol "https" -Port $httpsPort -IPAddress "127.0.0.1" -HostHeader "" -SslFlags 0 | Out-Null
    $loopApiB = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "127.0.0.1:${httpsPort}:" } | Select-Object -First 1
    if ($loopApiB) { try { $loopApiB.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (loopback API): $($_.Exception.Message)" } }
    New-WebBinding -Name $siteName -Protocol "https" -Port $httpsPort -IPAddress $bindIp -HostHeader "" -SslFlags 0 | Out-Null
    $extApiB = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "${bindIp}:${httpsPort}:" } | Select-Object -First 1
    if ($extApiB) { try { $extApiB.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (API IP): $($_.Exception.Message)" } }
    # Console port: loopback for internal health checks + selected IP for external access
    New-WebBinding -Name $siteName -Protocol "https" -Port $consoleHttpsPort -IPAddress "127.0.0.1" -HostHeader "" -SslFlags 0 | Out-Null
    $loopConB = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "127.0.0.1:${consoleHttpsPort}:" } | Select-Object -First 1
    if ($loopConB) { try { $loopConB.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (loopback console): $($_.Exception.Message)" } }
    New-WebBinding -Name $siteName -Protocol "https" -Port $consoleHttpsPort -IPAddress $bindIp -HostHeader "" -SslFlags 0 | Out-Null
    $extConB = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "${bindIp}:${consoleHttpsPort}:" } | Select-Object -First 1
    if ($extConB) { try { $extConB.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (console IP): $($_.Exception.Message)" } }
  } else {
    # No specific IP selected — bind to all interfaces
    New-WebBinding -Name $siteName -Protocol "https" -Port $httpsPort -IPAddress "*" -HostHeader "" -SslFlags 0 | Out-Null
    $mainBind = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "*:${httpsPort}:" } | Select-Object -First 1
    if ($mainBind) { try { $mainBind.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (main): $($_.Exception.Message)" } }
    New-WebBinding -Name $siteName -Protocol "https" -Port $consoleHttpsPort -IPAddress "*" -HostHeader "" -SslFlags 0 | Out-Null
    $consoleBind = Get-WebBinding -Name $siteName -Protocol "https" | Where-Object { $_.bindingInformation -eq "*:${consoleHttpsPort}:" } | Select-Object -First 1
    if ($consoleBind) { try { $consoleBind.AddSslCertificate($thumb, "My") } catch { Warn "AddSslCertificate (console): $($_.Exception.Message)" } }
  }

  $ErrorActionPreference = "Continue"
  Start-Service W3SVC 2>$null | Out-Null
  Start-WebAppPool -Name "DefaultAppPool" -ErrorAction SilentlyContinue | Out-Null
  try { Start-Website -Name $siteName } catch { Warn "Start-Website error: $($_.Exception.Message)" }
  $ErrorActionPreference = "Stop"

  if (-not (Wait-TcpPort -targetHost "127.0.0.1" -port $httpsPort -maxSeconds 30)) {
    Err "IIS HTTPS listener on port $httpsPort is not reachable."
    Warn "IIS site state:"
    Get-Website -Name $siteName | Format-List * | Out-String | Write-Host
    Warn "Check if another app is blocking port $httpsPort."
    exit 1
  }
  if (-not (Wait-TcpPort -targetHost "127.0.0.1" -port $consoleHttpsPort -maxSeconds 30)) {
    Err "IIS console listener on port $consoleHttpsPort is not reachable."
    Warn "IIS site state:"
    Get-Website -Name $siteName | Format-List * | Out-String | Write-Host
    Warn "Check if another app is blocking port $consoleHttpsPort."
    exit 1
  }

  if ($domain -ne "localhost") { Ensure-HostsEntry -domain $domain }
  if ($bindIp) {
    Ensure-FirewallPort -port $httpsPort
    Ensure-FirewallPort -port $consoleHttpsPort
  } elseif ($lanIp) {
    Ensure-FirewallPort -port $httpsPort
    Ensure-FirewallPort -port $consoleHttpsPort
  }

  $proxyUri = if ($httpsPort -eq 443) { "https://$domain/" } else { "https://${domain}:$httpsPort/" }
  $consoleProxyUri = if ($consoleHttpsPort -eq 443) { "https://$domain/" } else { "https://${domain}:$consoleHttpsPort/" }
  if (-not (Test-HttpReachable -uri $proxyUri)) {
    Warn "IIS HTTPS endpoint probe failed: $proxyUri"
    Warn "Check IIS logs/Event Viewer and confirm URL Rewrite + ARR are installed and enabled."
    Warn "If the browser shows HTTP 500, inspect the LocalS3 IIS site and ARR proxy settings."
  }
  if (-not (Test-HttpReachable -uri $consoleProxyUri)) {
    Warn "IIS console HTTPS endpoint probe failed: $consoleProxyUri"
    Warn "Check IIS logs/Event Viewer and confirm URL Rewrite + ARR are installed and enabled."
  }
}

function Install-IISMode {
  $root = Join-Path $env:ProgramData "LocalS3\storage-server"
  $certDir = Join-Path $root "nginx\certs"
  $siteRoot = Join-Path $root "iis-site"
  New-Item -ItemType Directory -Force -Path $certDir,$siteRoot | Out-Null

  $domain = Resolve-InstallHost "Enter local domain/URL for HTTPS (default: localhost)"
  Info "Using local domain: $domain"
  $browserSessionDuration = Resolve-BrowserSessionDuration
  Info "Web session/share-link max duration: $browserSessionDuration"
  $enableLan = $true
  Info "LAN access: enabled"
  $lanIp = $null
  if ($enableLan) {
    $lanIp = Get-LanIPv4
    if ($lanIp) { Info "Detected LAN IP: $lanIp" } else { Warn "Could not detect LAN IP automatically." }
  }

  $busyDefaults = @()
  foreach ($p in @(443,9000,9001)) {
    if (-not (Port-Free $p)) { $busyDefaults += $p }
  }
  if ($busyDefaults.Count -gt 0 -and (Has-ExistingLocalS3IISInstall)) {
    Warn ("Some default ports are busy (" + ($busyDefaults -join ", ") + ") and an existing LocalS3 IIS installation was detected.")
    if (Test-ServerInstallerNonInteractive) {
      Info "Non-interactive mode detected. Reinstalling LocalS3 IIS automatically."
      $ans = "y"
    } else {
      $ans = (Read-Host "Delete previous LocalS3 IIS install and reinstall now? (Y/n)").Trim().ToLowerInvariant()
    }
    if ($ans -eq "" -or $ans -eq "y" -or $ans -eq "yes") {
      Remove-ExistingLocalS3IISInstall -root $root
    } else {
      Warn "Keeping existing LocalS3 install. Installer will use alternate/custom ports as needed."
    }
  }

  $httpsPort = Resolve-RequiredConfiguredPort -envName "LOCALS3_HTTPS_PORT" -label "S3 HTTPS" -requireIisBinding
  if ($httpsPort -eq 443) {
    Err "LOCALS3_HTTPS_PORT cannot be 443. Choose a unique port from the dashboard."
    exit 1
  }

  $apiPort = Resolve-RequiredConfiguredPort -envName "LOCALS3_API_PORT" -label "MinIO API"
  $uiPort = Resolve-RequiredConfiguredPort -envName "LOCALS3_UI_PORT" -label "MinIO Console UI"
  # Console HTTPS proxy port: try httpsPort+1000 range (e.g. 8443→9443)
  # Exclude $httpsPort so the API and console bindings do not collide.
  $consoleCandidates = @(9443,10443,11443,12443,13443) | Where-Object { $_ -ne $httpsPort }
  $consoleHttpsPort = Resolve-RequiredConfiguredPort -envName "LOCALS3_CONSOLE_PORT" -label "MinIO Console" -requireIisBinding
  Assert-UniqueConfiguredPorts @{
    "LOCALS3_HTTPS_PORT" = $httpsPort
    "LOCALS3_API_PORT" = $apiPort
    "LOCALS3_UI_PORT" = $uiPort
    "LOCALS3_CONSOLE_PORT" = $consoleHttpsPort
  }

  Run-PreflightChecks -DataPath $root

  $displayHost = if ($domain -eq "localhost" -and $lanIp) { $lanIp } else { $domain }
  $publicUrl = if ($httpsPort -eq 443) { "https://$displayHost" } else { "https://${displayHost}:$httpsPort" }
  # If the selected host is localhost but LAN access is enabled, do not force a browser
  # redirect target. That allows users opening the console by LAN IP to stay on that IP.
  $consoleBrowserUrl = if ($consoleHttpsPort -eq 443) { "https://$domain" } else { "https://${domain}:$consoleHttpsPort" }
  $consoleRedirectUrl = if ($domain -eq "localhost" -and $lanIp) { "" } else { $consoleBrowserUrl }

  Ensure-IISInstalled
  Ensure-HttpSysUrlSegmentLimit
  if (Finish-Or-Restart) {
    return
  }
  Ensure-MinIONative -root $root -apiPort $apiPort -uiPort $uiPort -publicUrl $publicUrl -consoleBrowserUrl $consoleRedirectUrl -browserSessionDuration $browserSessionDuration
  $crt = Join-Path $certDir "localhost.crt"
  $key = Join-Path $certDir "localhost.key"
  Ensure-IISProxyMode -domain $domain -siteRoot $siteRoot -certPath $crt -keyPath $key -httpsPort $httpsPort -targetPort $apiPort -consoleHttpsPort $consoleHttpsPort -uiPort $uiPort -lanIp $lanIp

  # Auto-configure buckets, CORS, service accounts
  Configure-MinIOFeatures -ApiPort $apiPort -UiPort $uiPort

  Write-Host ""
  Write-Host "===== INSTALLATION COMPLETE (IIS MODE) ====="
  Write-Host ""
  Write-Host "URLs:"
  Write-Host "  MinIO Console:          $consoleBrowserUrl"
  Write-Host "  S3 API / Share links:   $publicUrl"
  if ($enableLan -and $lanIp) {
    Write-Host "  LAN Console:            https://${lanIp}:$consoleHttpsPort"
    Write-Host "  LAN S3 API:             https://${lanIp}:$httpsPort"
    Write-Host "  For DNS: map $domain -> $lanIp"
  }
  Write-Host ""
  Write-Host "Login:"
  Write-Host "  Username : $Script:ActiveAccessKey"
  Write-Host "  Password : $Script:ActiveSecretKey"
  Write-Host ""
  Write-Host "Pre-configured buckets:"
  Write-Host "  images    (public-read + CORS enabled)"
  Write-Host "  documents"
  Write-Host "  backups"
  Write-Host ""
  Write-Host "Read-only service account (for apps / SDKs):"
  Write-Host "  Access key : readonly-app"
  Write-Host "  Secret key : ReadOnly#App2024!"
}


function Resolve-HttpsPortForIIS {
  if ($env:LOCALS3_HTTPS_PORT -and (-not [string]::IsNullOrWhiteSpace($env:LOCALS3_HTTPS_PORT))) {
    $raw = $env:LOCALS3_HTTPS_PORT.Trim()
    $port = 0
    if (-not [int]::TryParse($raw, [ref]$port)) {
      Err "LOCALS3_HTTPS_PORT must be numeric."
      exit 1
    }
    if ($port -lt 1 -or $port -gt 65535) {
      Err "LOCALS3_HTTPS_PORT must be between 1 and 65535."
      exit 1
    }
    if ((-not (Port-Free $port)) -and (-not (Test-LocalS3ManagedPort $port))) {
      Err "Requested HTTPS port $port is already in use."
      exit 1
    }
    if (-not (Test-IISBindingPortAvailable -port $port -protocol "https" -excludeSite "LocalS3")) {
      Err "Requested HTTPS port $port is already bound in IIS."
      exit 1
    }
    return $port
  }

  if ((Port-Free 443) -and (Test-IISBindingPortAvailable -port 443 -protocol "https" -excludeSite "LocalS3")) {
    return 443
  }

  Warn "Port 443 is already in use or reserved by an existing IIS binding."
  $candidates = @(8443,9443,10443,11443,12443) | Where-Object {
    (Port-Free $_) -and (Test-IISBindingPortAvailable -port $_ -protocol "https" -excludeSite "LocalS3")
  }
  $picked = Pick-Port $candidates
  if ($picked) { return [int]$picked }

  Err "No available IIS HTTPS port was found in the default range (8443, 9443, 10443, 11443, 12443)."
  exit 1
}

function Resolve-EnvPort {
  param(
    [string]$envName,
    [string]$label,
    [switch]$requireIisBinding
  )
  $raw = ""
  try { $raw = (Get-Item -Path "env:$envName" -ErrorAction SilentlyContinue).Value } catch {}
  if (-not $raw -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
  $raw = $raw.Trim()
  $port = 0
  if (-not [int]::TryParse($raw, [ref]$port)) {
    Err "$envName must be numeric."
    exit 1
  }
  if ($port -lt 1 -or $port -gt 65535) {
    Err "$envName must be between 1 and 65535."
    exit 1
  }
  if ((-not (Port-Free $port)) -and (-not (Test-LocalS3ManagedPort $port))) {
    Err "Requested $label port $port is already in use."
    exit 1
  }
  if ($requireIisBinding -and (-not (Test-IISBindingPortAvailable -port $port -protocol "https" -excludeSite "LocalS3"))) {
    Err "Requested $label port $port is already bound in IIS."
    exit 1
  }
  return $port
}

function Resolve-RequiredConfiguredPort {
  param(
    [string]$envName,
    [string]$label,
    [switch]$requireIisBinding
  )
  $raw = ""
  try { $raw = (Get-Item -Path "env:$envName" -ErrorAction SilentlyContinue).Value } catch {}
  if (-not $raw -or [string]::IsNullOrWhiteSpace($raw)) {
    Err "$envName is required. Enter all S3 ports in the dashboard before starting."
    exit 1
  }
  $raw = $raw.Trim()
  $port = 0
  if (-not [int]::TryParse($raw, [ref]$port)) {
    Err "$envName must be numeric."
    exit 1
  }
  if ($port -lt 1 -or $port -gt 65535) {
    Err "$envName must be between 1 and 65535."
    exit 1
  }
  if ((-not (Port-Free $port)) -and (-not (Test-LocalS3ManagedPort $port))) {
    Err "Requested $label port $port is already in use."
    exit 1
  }
  if ($requireIisBinding -and (-not (Test-IISBindingPortAvailable -port $port -protocol "https" -excludeSite "LocalS3"))) {
    Err "Requested $label port $port is already bound in IIS."
    exit 1
  }
  return $port
}

function Assert-UniqueConfiguredPorts([hashtable]$ports) {
  $seen = @{}
  foreach ($name in $ports.Keys) {
    $value = [int]$ports[$name]
    if ($seen.ContainsKey($value)) {
      Err "Ports must be unique. '$name' conflicts with '$($seen[$value])' on port $value."
      exit 1
    }
    $seen[$value] = $name
  }
}

function Test-IISBindingPortAvailable([int]$port, [string]$protocol, [string]$excludeSite = "") {
  try {
    Import-Module WebAdministration -ErrorAction SilentlyContinue
    $bindings = Get-WebBinding -Protocol $protocol -ErrorAction SilentlyContinue
    foreach ($binding in $bindings) {
      $siteName = $binding.ItemXPath -replace '^.*/sites/site\[@name=''([^'']+)''\].*$', '$1'
      if ($excludeSite -and $siteName -eq $excludeSite) { continue }
      if ($siteName -in @("LocalS3", "LocalS3-IIS", "LocalS3-Console")) { continue }
      $parts = $binding.bindingInformation.Split(':')
      if ($parts.Count -lt 2) { continue }
      $bindingPort = 0
      if (-not [int]::TryParse($parts[1], [ref]$bindingPort)) { continue }
      if ($bindingPort -eq $port) {
        return $false
      }
    }
  } catch {}
  return $true
}

function Invoke-LocalS3IISSetup {
  Install-IISMode
}
