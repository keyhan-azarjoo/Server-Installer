$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\S3\windows\modules\common.ps1")
. (Join-Path $PSScriptRoot "..\..\S3\windows\modules\docker.ps1")

$Script:MongoRoot = Join-Path $env:ProgramData "LocalMongoDB"
$Script:MongoLabel = "com.localmongo.installer=true"

function Get-EnvOrDefault([string]$name, [string]$defaultValue) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if ([string]::IsNullOrWhiteSpace($value)) { return $defaultValue }
  return $value.Trim()
}

function Require-NumericPort([string]$name, [string]$value) {
  if ($value -notmatch '^\d+$') {
    Err "$name must be numeric."
    exit 1
  }
  $port = [int]$value
  if ($port -lt 1 -or $port -gt 65535) {
    Err "$name must be between 1 and 65535."
    exit 1
  }
  return $port
}

function Remove-ExistingLocalMongo([string]$dockerCtx) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker --context $dockerCtx rm -f localmongo-https localmongo-web localmongo-mongodb 2>$null | Out-Null
  docker --context $dockerCtx network rm localmongo-net 2>$null | Out-Null
  docker --context $dockerCtx volume rm -f localmongo-data 2>$null | Out-Null
  schtasks /End /TN "LocalMongoDB-Autostart" 1>$null 2>$null | Out-Null
  schtasks /Delete /TN "LocalMongoDB-Autostart" /F 1>$null 2>$null | Out-Null
  if (Test-Path $Script:MongoRoot) {
    Remove-Item -Recurse -Force -Path $Script:MongoRoot -ErrorAction SilentlyContinue
  }
  $ErrorActionPreference = $prev
}

function Register-LocalMongoAutostart([string]$dockerCtx) {
  $taskCommand = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "docker --context ' + $dockerCtx + ' start localmongo-mongodb localmongo-web localmongo-https | Out-Null"'
  schtasks /Delete /TN "LocalMongoDB-Autostart" /F 1>$null 2>$null | Out-Null
  schtasks /Create /TN "LocalMongoDB-Autostart" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $taskCommand /F | Out-Null
}

function Trust-LocalMongoCaddyRoot([string]$rootCertPath) {
  if (-not (Test-Path $rootCertPath)) {
    Warn "Caddy root certificate not found yet: $rootCertPath"
    return
  }
  try {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($rootCertPath)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root","LocalMachine")
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $exists = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
    if (-not $exists) {
      $store.Add($cert)
      Info "Trusted LocalMongoDB HTTPS root certificate in LocalMachine\Root."
    } else {
      Info "LocalMongoDB HTTPS root certificate is already trusted."
    }
    $store.Close()
  } catch {
    Warn "Could not trust LocalMongoDB HTTPS certificate automatically: $($_.Exception.Message)"
  }
}

function Wait-ForMongoHttp([int]$webPort, [int]$httpsPort) {
  $ready = $false
  for ($i = 0; $i -lt 45; $i++) {
    if (Test-TcpPort -targetHost "127.0.0.1" -port $webPort -timeoutMs 1500) {
      $ready = $true
      break
    }
    Start-Sleep -Seconds 2
  }
  if (-not $ready) {
    Err "Mongo web admin container did not open port $webPort."
    exit 1
  }
  if (-not (Wait-TcpPort -targetHost "127.0.0.1" -port $httpsPort -maxSeconds 45)) {
    Err "HTTPS proxy did not open port $httpsPort."
    exit 1
  }
}

function Main {
  Relaunch-Elevated
  Info "===== Local MongoDB Installer (Windows / Docker) ====="

  $hostValue = Get-EnvOrDefault "LOCALMONGO_HOST" ""
  $hostIp = Get-EnvOrDefault "LOCALMONGO_HOST_IP" ""
  if ([string]::IsNullOrWhiteSpace($hostValue)) {
    $hostValue = if ($hostIp) { $hostIp } else { (Get-LanIPv4) }
  }
  if ([string]::IsNullOrWhiteSpace($hostValue)) {
    $hostValue = "localhost"
  }

  $httpsPort = Require-NumericPort "LOCALMONGO_HTTPS_PORT" (Get-EnvOrDefault "LOCALMONGO_HTTPS_PORT" "9445")
  $mongoPort = Require-NumericPort "LOCALMONGO_MONGO_PORT" (Get-EnvOrDefault "LOCALMONGO_MONGO_PORT" "27017")
  $webPort = Require-NumericPort "LOCALMONGO_WEB_PORT" (Get-EnvOrDefault "LOCALMONGO_WEB_PORT" "8081")

  if ($httpsPort -eq $mongoPort -or $httpsPort -eq $webPort -or $mongoPort -eq $webPort) {
    Err "HTTPS, MongoDB, and Web UI ports must be different."
    exit 1
  }

  $mongoUser = Get-EnvOrDefault "LOCALMONGO_ADMIN_USER" "admin"
  $mongoPassword = Get-EnvOrDefault "LOCALMONGO_ADMIN_PASSWORD" "StrongPassword123"
  $uiUser = Get-EnvOrDefault "LOCALMONGO_UI_USER" $mongoUser
  $uiPassword = Get-EnvOrDefault "LOCALMONGO_UI_PASSWORD" $mongoPassword

  Ensure-DockerInstalled
  Wait-DockerEngine
  Sanitize-DockerEnv
  $dockerCtx = Get-ActiveDockerContext
  Info "Using Docker context: $dockerCtx"
  Info "Clearing previous LocalMongoDB containers, volume, and config..."
  Remove-ExistingLocalMongo -dockerCtx $dockerCtx

  foreach ($pair in @(
    @{ Name = "HTTPS"; Port = $httpsPort },
    @{ Name = "MongoDB"; Port = $mongoPort },
    @{ Name = "Web UI"; Port = $webPort }
  )) {
    if (-not (Port-Free $pair.Port)) {
      Warn "$($pair.Name) port $($pair.Port) is still in use after cleanup."
      $listeners = Get-PortListeners $pair.Port
      if ($listeners.Count -gt 0) {
        $listeners | Format-Table -AutoSize | Out-String | Write-Host
      }
      exit 1
    }
  }

  $siteDir = Join-Path $Script:MongoRoot "caddy-site"
  $dataDir = Join-Path $Script:MongoRoot "caddy-data"
  $configDir = Join-Path $Script:MongoRoot "caddy-config"
  New-Item -ItemType Directory -Force -Path $Script:MongoRoot, $siteDir, $dataDir, $configDir | Out-Null

  $addresses = @("https://localhost:$httpsPort")
  if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") {
    $addresses += "https://${hostValue}:$httpsPort"
  }
  $caddyfile = @"
{
  auto_https disable_redirects
}

$($addresses -join ", ") {
  tls internal
  reverse_proxy localmongo-web:8081
  encode gzip
}
"@
  $caddyfilePath = Join-Path $siteDir "Caddyfile"
  [System.IO.File]::WriteAllText($caddyfilePath, $caddyfile, (New-Object System.Text.UTF8Encoding($false)))

  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker --context $dockerCtx network create localmongo-net 2>$null | Out-Null
  docker --context $dockerCtx volume create localmongo-data 2>$null | Out-Null

  docker --context $dockerCtx run -d `
    --name localmongo-mongodb `
    --label $Script:MongoLabel `
    --label "com.localmongo.role=mongodb" `
    --restart unless-stopped `
    --network localmongo-net `
    -p "${mongoPort}:27017" `
    -e "MONGO_INITDB_ROOT_USERNAME=$mongoUser" `
    -e "MONGO_INITDB_ROOT_PASSWORD=$mongoPassword" `
    -v "localmongo-data:/data/db" `
    mongo:7 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    $ErrorActionPreference = $prev
    Err "Failed to start MongoDB container."
    exit 1
  }

  docker --context $dockerCtx run -d `
    --name localmongo-web `
    --label $Script:MongoLabel `
    --label "com.localmongo.role=web" `
    --restart unless-stopped `
    --network localmongo-net `
    -p "127.0.0.1:${webPort}:8081" `
    -e "ME_CONFIG_MONGODB_SERVER=localmongo-mongodb" `
    -e "ME_CONFIG_MONGODB_PORT=27017" `
    -e "ME_CONFIG_MONGODB_ENABLE_ADMIN=true" `
    -e "ME_CONFIG_MONGODB_AUTH_DATABASE=admin" `
    -e "ME_CONFIG_MONGODB_ADMINUSERNAME=$mongoUser" `
    -e "ME_CONFIG_MONGODB_ADMINPASSWORD=$mongoPassword" `
    -e "ME_CONFIG_BASICAUTH_USERNAME=$uiUser" `
    -e "ME_CONFIG_BASICAUTH_PASSWORD=$uiPassword" `
    mongo-express:latest | Out-Null
  if ($LASTEXITCODE -ne 0) {
    $ErrorActionPreference = $prev
    Err "Failed to start Mongo web admin container."
    exit 1
  }

  docker --context $dockerCtx run -d `
    --name localmongo-https `
    --label $Script:MongoLabel `
    --label "com.localmongo.role=https" `
    --restart unless-stopped `
    --network localmongo-net `
    -p "${httpsPort}:${httpsPort}" `
    -v "${caddyfilePath}:/etc/caddy/Caddyfile:ro" `
    -v "${dataDir}:/data" `
    -v "${configDir}:/config" `
    caddy:2-alpine | Out-Null
  $ErrorActionPreference = $prev
  if ($LASTEXITCODE -ne 0) {
    Err "Failed to start HTTPS proxy container."
    exit 1
  }

  Wait-ForMongoHttp -webPort $webPort -httpsPort $httpsPort

  $rootCert = Join-Path $dataDir "caddy\pki\authorities\local\root.crt"
  if (-not (Test-Path $rootCert)) {
    $rootCert = Join-Path $dataDir "pki\authorities\local\root.crt"
  }
  Trust-LocalMongoCaddyRoot -rootCertPath $rootCert

  if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    Ensure-HostsEntry -domain $hostValue
  }

  Ensure-FirewallPort -port $httpsPort
  Ensure-FirewallPort -port $mongoPort
  Register-LocalMongoAutostart -dockerCtx $dockerCtx

  $httpsUrl = "https://localhost:$httpsPort"
  $lanUrl = ""
  if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") {
    $lanUrl = "https://${hostValue}:$httpsPort"
  }
  $mongoUrl = "mongodb://${hostValue}:$mongoPort/"
  $localMongoUrl = "mongodb://localhost:$mongoPort/"

  Write-Host ""
  Write-Host "===== INSTALLATION COMPLETE ====="
  Write-Host "Compass-style web UI (HTTPS): $httpsUrl"
  if ($lanUrl) { Write-Host "Compass-style web UI (Host):  $lanUrl" }
  Write-Host "Direct web UI (HTTP localhost): http://127.0.0.1:$webPort"
  Write-Host "MongoDB connection:            $localMongoUrl"
  if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") {
    Write-Host "MongoDB connection (Host):     $mongoUrl"
  }
  Write-Host "MongoDB root user:             $mongoUser"
  Write-Host "MongoDB root password:         $mongoPassword"
  Write-Host "Web UI username:               $uiUser"
  Write-Host "Web UI password:               $uiPassword"
  Write-Host "Service:                       LocalMongoDB-Autostart (enabled)"
  Write-Host ""
  Write-Host "You can manage databases, collections, users, and access through the web UI using the MongoDB admin credentials above."
}

Main
