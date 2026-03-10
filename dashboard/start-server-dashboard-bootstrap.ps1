$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$enableHttps = $env:DASHBOARD_HTTPS
if ([string]::IsNullOrWhiteSpace($enableHttps)) {
  $enableHttps = "0"
}
$enableHttps = $enableHttps.ToLowerInvariant() -in @("1", "true", "yes", "y", "on")

function Get-CommandPath([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Test-RepoLayout([string]$Path) {
  if (-not $Path) { return $false }
  $dashboardRoot = Join-Path $Path "dashboard"
  return (Test-Path (Join-Path $dashboardRoot "start-server-dashboard.py")) -and
         (Test-Path (Join-Path $dashboardRoot "server_installer_dashboard.py"))
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

$root = Join-Path $env:ProgramData "Server-Installer"
New-Item -ItemType Directory -Force -Path $root | Out-Null
$pyDir = Join-Path $root "python"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$repo = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
$dashboard = Join-Path $root "start-server-dashboard.py"
$localRoot = $env:SERVER_INSTALLER_LOCAL_ROOT

Write-Host "[INFO] Downloading dashboard launcher..."
if (Test-RepoLayout $localRoot) {
  Copy-Item -Path (Join-Path $localRoot "dashboard\start-server-dashboard.py") -Destination $dashboard -Force
} else {
  Invoke-WebRequest -Uri "$repo/dashboard/start-server-dashboard.py" -OutFile $dashboard
}
Repair-DashboardLauncher -Path $dashboard

$python = Get-CommandPath "python"
if (-not $python) { $python = Get-CommandPath "py" }

if (-not $python) {
  Write-Host "[INFO] Python not found. Bootstrapping embeddable Python..."
  $pyVer = "3.14.2"
  $pyZip = Join-Path $root "python-embed.zip"
  $pyUrl = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embeddable-amd64.zip"
  Invoke-WebRequest -Uri $pyUrl -OutFile $pyZip
  if (Test-Path $pyDir) { Remove-Item -Recurse -Force $pyDir }
  New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
  Expand-Archive -Path $pyZip -DestinationPath $pyDir -Force
  $python = Join-Path $pyDir "python.exe"
}

Write-Host "[INFO] Starting dashboard..."
if ($enableHttps) {
  $certDir = Join-Path $root "certs"
  New-Item -ItemType Directory -Force -Path $certDir | Out-Null
  $certPath = Join-Path $certDir "dashboard.crt"
  $keyPath = Join-Path $certDir "dashboard.key"

  Write-Host "[INFO] Generating HTTPS certificate chain..."
  Ensure-DashboardCaCertificate -CertPath $certPath -KeyPath $keyPath

  $env:DASHBOARD_HTTPS = "1"
  $env:DASHBOARD_CERT = $certPath
  $env:DASHBOARD_KEY = $keyPath
} else {
  Remove-Item Env:\DASHBOARD_HTTPS -ErrorAction SilentlyContinue
  Remove-Item Env:\DASHBOARD_CERT -ErrorAction SilentlyContinue
  Remove-Item Env:\DASHBOARD_KEY -ErrorAction SilentlyContinue
}
& $python $dashboard
