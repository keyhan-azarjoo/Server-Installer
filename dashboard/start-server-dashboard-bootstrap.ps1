$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VerbosePreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Test-IsAdministrator {
  if (-not $IsWindows) {
    return $true
  }
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($IsWindows -and -not (Test-IsAdministrator)) {
  $argParts = @(
    "-NoProfile",
    "-ExecutionPolicy Bypass",
    ('-File "' + $PSCommandPath + '"')
  )
  foreach ($arg in @($args)) {
    if (-not [string]::IsNullOrWhiteSpace($arg)) {
      $escapedArg = $arg.Replace('"', '\"')
      $argParts += ('"' + $escapedArg + '"')
    }
  }
  $argLine = $argParts -join " "
  $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argLine -Verb RunAs -Wait -PassThru
  exit $proc.ExitCode
}

$enableHttps = $env:DASHBOARD_HTTPS
if ([string]::IsNullOrWhiteSpace($enableHttps)) {
  $enableHttps = "1"
}
$enableHttps = $enableHttps.ToLowerInvariant() -in @("1", "true", "yes", "y", "on")

function Get-CommandPath([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Stop-ExistingDashboardProcesses {
  if (-not $IsWindows) {
    return
  }

  try {
    schtasks /End /TN "ServerInstallerDashboard" *> $null
  } catch {
  }

  try {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.CommandLine -and (
        $_.CommandLine -match 'server_installer_dashboard\.py' -or
        $_.CommandLine -match 'start-server-dashboard\.py.+--run-server'
      )
    }
    foreach ($proc in $procs) {
      try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
      } catch {
      }
    }
  } catch {
  }

  Start-Sleep -Seconds 2
}

function Get-RequiredServerInstallerFiles {
  $manifestCandidates = @(
    (Join-Path $PSScriptRoot "download-manifest.txt")
  )
  if ($env:SERVER_INSTALLER_LOCAL_ROOT) {
    $manifestCandidates += (Join-Path $env:SERVER_INSTALLER_LOCAL_ROOT "dashboard\download-manifest.txt")
  }

  foreach ($manifestPath in ($manifestCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $manifestPath)) {
      continue
    }

    $files = Get-Content -LiteralPath $manifestPath | Where-Object {
      $_ -and $_.Trim() -and -not $_.Trim().StartsWith("#")
    } | ForEach-Object { $_.Trim() }
    if ($files.Count -gt 0) {
      return @($files)
    }
  }

  return @(
    "dashboard/download-manifest.txt",
    "dashboard/start-server-dashboard.py",
    "dashboard/server_installer_dashboard.py",
    "dashboard/windows_dashboard_service.py",
    "dashboard/file_manager.py",
    "dashboard/ssl_manager.py",
    "dashboard/ui_assets.py",
    "dashboard/ui/core.js",
    "dashboard/ui/utils.js",
    "dashboard/ui/actions.js",
    "dashboard/ui/components.js",
    "dashboard/ui/app.js",
    "Python/windows/setup-python.ps1",
    "Mongo/windows/setup-mongodb.ps1",
    "DotNet/windows/install-windows-dotnet-host.ps1",
    "DotNet/windows/modules/common.ps1",
    "DotNet/windows/modules/iis-mode.ps1",
    "DotNet/windows/modules/docker-mode.ps1",
    "S3/windows/setup-storage.ps1",
    "S3/windows/modules/common.ps1",
    "S3/windows/modules/minio.ps1",
    "S3/windows/modules/cleanup.ps1",
    "S3/windows/modules/iis.ps1",
    "S3/windows/modules/docker.ps1",
    "S3/windows/modules/main.ps1",
    "Proxy/linux-macos/setup-proxy.sh",
    "Proxy/windows/setup-proxy.ps1",
    "Proxy/common/add-user.sh",
    "Proxy/common/backup-config.sh",
    "Proxy/common/delete-user.sh",
    "Proxy/common/list-users.sh",
    "Proxy/common/status.sh",
    "Proxy/common/uninstall.sh",
    "Proxy/common/view-users.sh",
    "Proxy/panel/install-panel.sh",
    "Proxy/panel/proxy-panel.py",
    "Proxy/panel/proxy-panel.service",
    "Proxy/panel/static/app.js",
    "Proxy/panel/static/style.css",
    "Proxy/panel/templates/dashboard.html",
    "Proxy/panel/templates/login.html",
    "Proxy/layers/layer3-basic/install.sh",
    "Proxy/layers/layer4-nginx/install.sh",
    "Proxy/layers/layer6-stunnel/install.sh",
    "Proxy/layers/layer7-iran-optimized/add-user.sh",
    "Proxy/layers/layer7-iran-optimized/delete-user.sh",
    "Proxy/layers/layer7-iran-optimized/install.sh",
    "Proxy/layers/layer7-real-domain/add-user.sh",
    "Proxy/layers/layer7-real-domain/delete-user.sh",
    "Proxy/layers/layer7-real-domain/install.sh",
    "Proxy/layers/layer7-v2ray-vless/add-user.sh",
    "Proxy/layers/layer7-v2ray-vless/delete-user.sh",
    "Proxy/layers/layer7-v2ray-vless/install.sh",
    "Proxy/layers/layer7-v2ray-vmess/add-user.sh",
    "Proxy/layers/layer7-v2ray-vmess/delete-user.sh",
    "Proxy/layers/layer7-v2ray-vmess/install.sh"
  )
}

function Sync-ServerInstallerFiles([string]$SourceRoot, [string]$DestinationRoot, [string]$RepoBase) {
  $requiredFiles = Get-RequiredServerInstallerFiles
  $totalFiles = $requiredFiles.Count
  $index = 0
  $forceDownload = (($env:SERVER_INSTALLER_FORCE_DOWNLOAD | ForEach-Object { $_.Trim().ToLowerInvariant() }) -in @("1", "true", "yes", "y", "on"))
  $repoDisplayBase = $RepoBase -replace '^https://raw\.githubusercontent\.com/', 'https://github.com/' -replace '/main$', '/blob/main'

  foreach ($relativePath in $requiredFiles) {
    $index++
    $percent = if ($totalFiles -gt 0) { [int](($index / $totalFiles) * 100) } else { 0 }
    Write-Progress -Activity "Downloading Server Installer files" -Status "[$index/$totalFiles] $relativePath" -PercentComplete $percent
    $displayUrl = "$repoDisplayBase/$relativePath"
    Write-Host ("Syncing required file: {0}" -f $relativePath)
    Write-Host ("Downloading: {0}" -f $displayUrl)
    $targetPath = Join-Path $DestinationRoot ($relativePath -replace '/', '\')
    $targetDirectory = Split-Path -Path $targetPath -Parent
    New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
    $tempPath = "$targetPath.download"
    try {
      if ((-not $forceDownload) -and $SourceRoot -and (Test-Path -LiteralPath (Join-Path $SourceRoot ($relativePath -replace '/', '\')))) {
        $sourcePath = Join-Path $SourceRoot ($relativePath -replace '/', '\')
        Copy-Item -LiteralPath $sourcePath -Destination $tempPath -Force
      } else {
        Invoke-WebRequest -Uri "$RepoBase/$relativePath" -OutFile $tempPath -ErrorAction Stop
      }
      if (Test-Path -LiteralPath $targetPath) {
        Remove-Item -LiteralPath $targetPath -Force
      }
      Move-Item -Path $tempPath -Destination $targetPath -Force
    } catch {
      Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
      Write-Host ("Failed file: {0}" -f $relativePath)
      Write-Host ("Failed URL: {0}" -f $displayUrl)
      Write-Host ("           ERROR: {0}" -f $_.Exception.Message)
      Write-Progress -Activity "Downloading Server Installer files" -Completed
      throw
    }
  }

  Write-Progress -Activity "Downloading Server Installer files" -Completed
}

function Get-LocalIPv4Addresses {
  $ips = @()
  try {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object {
        $_.IPAddress -and
        $_.IPAddress -ne "127.0.0.1" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown"
      } |
      Select-Object -ExpandProperty IPAddress -Unique
  } catch {
    $ips = @()
  }
  return @($ips)
}

function ConvertTo-DerLength([int]$Length) {
  if ($Length -lt 128) {
    return [byte[]]@([byte]$Length)
  }

  $bytes = New-Object System.Collections.Generic.List[byte]
  $remaining = $Length
  while ($remaining -gt 0) {
    $bytes.Insert(0, [byte]($remaining -band 0xFF))
    $remaining = [Math]::Floor($remaining / 256)
  }

  $result = New-Object System.Collections.Generic.List[byte]
  $result.Add([byte](0x80 -bor $bytes.Count))
  $result.AddRange([byte[]]$bytes.ToArray())
  return $result.ToArray()
}

function ConvertTo-DerInteger([byte[]]$Bytes) {
  if (-not $Bytes -or $Bytes.Length -eq 0) {
    $Bytes = [byte[]]@(0)
  }

  $offset = 0
  while ($offset -lt ($Bytes.Length - 1) -and $Bytes[$offset] -eq 0) {
    $offset++
  }

  if ($offset -gt 0) {
    $Bytes = $Bytes[$offset..($Bytes.Length - 1)]
  }

  if ($Bytes[0] -band 0x80) {
    $Bytes = [byte[]]@(0) + $Bytes
  }

  $result = New-Object System.Collections.Generic.List[byte]
  $result.Add(0x02)
  $result.AddRange([byte[]](ConvertTo-DerLength $Bytes.Length))
  $result.AddRange([byte[]]$Bytes)
  return $result.ToArray()
}

function ConvertTo-RsaPrivateKeyPem([System.Security.Cryptography.RSA]$Rsa) {
  $params = $Rsa.ExportParameters($true)
  $body = New-Object System.Collections.Generic.List[byte]
  $body.AddRange([byte[]](ConvertTo-DerInteger ([byte[]]@(0))))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.Modulus))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.Exponent))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.D))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.P))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.Q))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.DP))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.DQ))
  $body.AddRange([byte[]](ConvertTo-DerInteger $params.InverseQ))

  $sequence = New-Object System.Collections.Generic.List[byte]
  $sequence.Add(0x30)
  $sequence.AddRange([byte[]](ConvertTo-DerLength $body.Count))
  $sequence.AddRange([byte[]]$body.ToArray())

  return "-----BEGIN RSA PRIVATE KEY-----`n" + [Convert]::ToBase64String(
    $sequence.ToArray(),
    [System.Base64FormattingOptions]::InsertLineBreaks
  ) + "`n-----END RSA PRIVATE KEY-----"
}

function Repair-DashboardLauncher([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  $content = Get-Content -LiteralPath $Path -Raw
  $oldBind = @"
def can_bind(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
"@
  $newBind = @"
def can_bind(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
"@

  if ($content.Contains($oldBind)) {
    $content = $content.Replace($oldBind, $newBind)
    Set-Content -LiteralPath $Path -Value $content -Encoding utf8
  }
}

function ConvertTo-CertificatePem([System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert) {
  return "-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String(
    $Cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert),
    [System.Base64FormattingOptions]::InsertLineBreaks
  ) + "`n-----END CERTIFICATE-----"
}

function ConvertTo-PrivateKeyPem([System.Security.Cryptography.X509Certificates.X509Certificate2]$Cert) {
  $rsa = $null
  try {
    $rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($Cert)
  } catch {
    try {
      $rsa = $Cert.PrivateKey
    } catch {
      $rsa = $null
    }
  }
  if (-not $rsa) {
    throw "RSA private key is not available for the generated dashboard certificate."
  }

  try {
    $keyBytes = $rsa.ExportPkcs8PrivateKey()
    return "-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String(
      $keyBytes,
      [System.Base64FormattingOptions]::InsertLineBreaks
    ) + "`n-----END PRIVATE KEY-----"
  } catch {
    try {
      if ($rsa -is [System.Security.Cryptography.RSACng]) {
        $keyBytes = $rsa.Key.Export([System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob)
        return "-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String(
          $keyBytes,
          [System.Base64FormattingOptions]::InsertLineBreaks
        ) + "`n-----END PRIVATE KEY-----"
      }
    } catch {
    }
    return ConvertTo-RsaPrivateKeyPem -Rsa $rsa
  }
}

function Ensure-DashboardCaCertificate([string]$CertPath, [string]$KeyPath) {
  $friendlyNames = @("ServerInstallerDashboard Root CA", "ServerInstallerDashboard HTTPS")
  $rootSubject = "CN=ServerInstallerDashboard Root CA"

  Get-ChildItem Cert:\LocalMachine\My | Where-Object {
    $_.FriendlyName -in $friendlyNames
  } | Remove-Item -Force -ErrorAction SilentlyContinue

  $existingRoot = Get-ChildItem Cert:\LocalMachine\Root | Where-Object {
    $_.FriendlyName -eq "ServerInstallerDashboard Root CA" -and $_.Subject -eq $rootSubject
  } | Select-Object -First 1

  $rootCa = $null
  if ($existingRoot) {
    $rootCa = Get-ChildItem Cert:\LocalMachine\My | Where-Object {
      $_.Thumbprint -eq $existingRoot.Thumbprint
    } | Select-Object -First 1
  }

  if (-not $rootCa) {
    $rootBcExt = "2.5.29.19={critical}{text}ca=true&pathlength=1"
    $rootCa = New-SelfSignedCertificate -Subject $rootSubject `
      -FriendlyName "ServerInstallerDashboard Root CA" `
      -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
      -KeyExportPolicy Exportable `
      -KeyUsage CertSign, CRLSign, DigitalSignature `
      -TextExtension @($rootBcExt) `
      -CertStoreLocation "Cert:\LocalMachine\My" `
      -NotAfter (Get-Date).AddYears(5)

    if (-not $rootCa) {
      throw "Dashboard root CA certificate was not created."
    }

    $rootTmp = Join-Path $env:TEMP "server-installer-dashboard-root-ca.cer"
    try {
      $rootExport = Export-Certificate -Cert "Cert:\LocalMachine\My\$($rootCa.Thumbprint)" -FilePath $rootTmp -Force
      Import-Certificate -FilePath $rootExport.FullName -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null
    } finally {
      Remove-Item -Path $rootTmp -Force -ErrorAction SilentlyContinue
    }
  }

  $dnsSans = @("localhost", $env:COMPUTERNAME) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
  $ipSans = @("127.0.0.1") + (Get-LocalIPv4Addresses)
  $sanParts = @()
  foreach ($dns in $dnsSans) {
    $sanParts += "DNS=$dns"
  }
  foreach ($ip in ($ipSans | Select-Object -Unique)) {
    $sanParts += "IPAddress=$ip"
  }
  $sanExt = "2.5.29.17={text}" + ($sanParts -join "&")
  $leafBcExt = "2.5.29.19={critical}{text}ca=false"
  $serverAuthExt = "2.5.29.37={text}1.3.6.1.5.5.7.3.1"

  $leafCert = New-SelfSignedCertificate -Subject "CN=localhost" `
    -FriendlyName "ServerInstallerDashboard HTTPS" `
    -Signer $rootCa `
    -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
    -KeyExportPolicy Exportable `
    -KeyUsage DigitalSignature, KeyEncipherment `
    -TextExtension @($sanExt, $leafBcExt, $serverAuthExt) `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -NotAfter (Get-Date).AddYears(3)

  if (-not $leafCert) {
    throw "Dashboard HTTPS leaf certificate was not created."
  }

  Set-Content -Path $CertPath -Value (ConvertTo-CertificatePem -Cert $leafCert) -Encoding ascii
  Set-Content -Path $KeyPath -Value (ConvertTo-PrivateKeyPem -Cert $leafCert) -Encoding ascii
}

$root = $env:SERVER_INSTALLER_DATA_DIR
if ([string]::IsNullOrWhiteSpace($root)) {
  $root = Join-Path $env:ProgramData "Server-Installer"
}
$root = [System.IO.Path]::GetFullPath($root)
New-Item -ItemType Directory -Force -Path $root | Out-Null
$pyDir = Join-Path $root "python"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$repo = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
$localSourceRoot = $env:SERVER_INSTALLER_LOCAL_ROOT
$dashboard = Join-Path $root "dashboard\start-server-dashboard.py"

Write-Host "[INFO] Downloading dashboard launcher..."
Stop-ExistingDashboardProcesses
Sync-ServerInstallerFiles -SourceRoot $localSourceRoot -DestinationRoot $root -RepoBase $repo
Repair-DashboardLauncher -Path $dashboard

$python = Get-CommandPath "python"
if (-not $python) { $python = Get-CommandPath "py" }

if (-not $python) {
  Write-Host "[INFO] Python not found. Bootstrapping embeddable Python..."
  $pyVer = "3.14.2"
  $pyZip = Join-Path $root "python-embed.zip"
  $pyUrl = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embeddable-amd64.zip"
  Write-Progress -Activity "Downloading Python runtime" -Status "python-$pyVer-embeddable-amd64.zip" -PercentComplete 0
  Invoke-WebRequest -Uri $pyUrl -OutFile $pyZip
  Write-Progress -Activity "Downloading Python runtime" -Completed
  if (Test-Path $pyDir) { Remove-Item -Recurse -Force $pyDir }
  New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
  Expand-Archive -Path $pyZip -DestinationPath $pyDir -Force
  $python = Join-Path $pyDir "python.exe"
}

$pythonConsoleless = $null
if ($python) {
  try {
    $candidate = Join-Path (Split-Path -Parent $python) "pythonw.exe"
    if (Test-Path -LiteralPath $candidate) {
      $pythonConsoleless = $candidate
    }
  } catch {
    $pythonConsoleless = $null
  }
}
if (-not $pythonConsoleless) {
  $pythonConsoleless = $python
}

Write-Host "[INFO] Starting dashboard..."
$certDir = Join-Path $root "certs"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null
$certPath = Join-Path $certDir "dashboard.crt"
$keyPath = Join-Path $certDir "dashboard.key"

Write-Host "[INFO] Generating HTTPS certificate chain..."
Ensure-DashboardCaCertificate -CertPath $CertPath -KeyPath $KeyPath

$env:DASHBOARD_HTTPS = "1"
$env:DASHBOARD_CERT = $certPath
$env:DASHBOARD_KEY = $keyPath
if ($localSourceRoot) {
  $env:SERVER_INSTALLER_REPO_BASE = "http://127.0.0.1:9"
}
# Use a console-capable interpreter for install/update so failures (e.g., missing pywin32) are visible.
& $python $dashboard @args
