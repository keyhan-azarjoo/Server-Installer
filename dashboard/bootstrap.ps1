$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-CommandPath([string]$name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
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
  try {
    $keyBytes = $rsa.ExportPkcs8PrivateKey()
    $keyPem = "-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String(
      $keyBytes,
      [System.Base64FormattingOptions]::InsertLineBreaks
    ) + "`n-----END PRIVATE KEY-----"
  } catch {
    try {
      if ($rsa -is [System.Security.Cryptography.RSACng]) {
        $keyBytes = $rsa.Key.Export([System.Security.Cryptography.CngKeyBlobFormat]::Pkcs8PrivateBlob)
        $keyPem = "-----BEGIN PRIVATE KEY-----`n" + [Convert]::ToBase64String(
          $keyBytes,
          [System.Base64FormattingOptions]::InsertLineBreaks
        ) + "`n-----END PRIVATE KEY-----"
      } else {
        throw "RSA provider does not support CNG export."
      }
    } catch {
      $keyPem = ConvertTo-RsaPrivateKeyPem -Rsa $rsa
    }
  }
  Set-Content -Path $certPath -Value $certPem -Encoding ascii
  Set-Content -Path $keyPath -Value $keyPem -Encoding ascii
}

Write-Host "[INFO] Starting dashboard..."
$env:DASHBOARD_HTTPS = "1"
$env:DASHBOARD_CERT = $certPath
$env:DASHBOARD_KEY = $keyPath
& $python $dashboard
