$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-CommandPath([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

$root = Join-Path $env:ProgramData "Server-Installer"
New-Item -ItemType Directory -Force -Path $root | Out-Null
$pyDir = Join-Path $root "python"
New-Item -ItemType Directory -Force -Path $root | Out-Null

$repo = "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main"
$dashboard = Join-Path $root "start-server-dashboard.py"

Write-Host "[INFO] Downloading dashboard launcher..."
Invoke-WebRequest -Uri "$repo/dashboard/start-server-dashboard.py" -OutFile $dashboard

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

$certDir = Join-Path $root "certs"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null
$certPath = Join-Path $certDir "dashboard.crt"
$keyPath = Join-Path $certDir "dashboard.key"

if (!(Test-Path $certPath) -or !(Test-Path $keyPath)) {
  Write-Host "[INFO] Generating HTTPS certificate..."
  $rsa = [System.Security.Cryptography.RSA]::Create(2048)
  $req = New-Object System.Security.Cryptography.X509Certificates.CertificateRequest(
    "CN=ServerInstallerDashboard",
    $rsa,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256,
    [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
  )
  $cert = $req.CreateSelfSigned([DateTimeOffset]::Now.AddDays(-1), [DateTimeOffset]::Now.AddYears(5))
  $certPem = "-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String(
    $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert),
    [System.Base64FormattingOptions]::InsertLineBreaks
  ) + "`n-----END CERTIFICATE-----"
  $keyPem = "-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String(
    $rsa.ExportPkcs8PrivateKey(),
    [System.Base64FormattingOptions]::InsertLineBreaks
  ) + "`n-----END PRIVATE KEY-----"
  Set-Content -Path $certPath -Value $certPem -Encoding ascii
  Set-Content -Path $keyPath -Value $keyPem -Encoding ascii
}

Write-Host "[INFO] Starting dashboard..."
$env:DASHBOARD_HTTPS = "1"
$env:DASHBOARD_CERT = $certPath
$env:DASHBOARD_KEY = $keyPath
& $python $dashboard
