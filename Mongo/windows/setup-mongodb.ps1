$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\S3\windows\modules\common.ps1")
. (Join-Path $PSScriptRoot "..\..\S3\windows\modules\docker.ps1")

$Script:MongoRoot = Join-Path $env:ProgramData "LocalMongoDB"
$Script:MongoLabel = "com.localmongo.installer=true"
$Script:NativeMongoServiceName = "LocalMongoDB"

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
  if (-not (Wait-TcpPort -targetHost "127.0.0.1" -port $webPort -maxSeconds 45)) {
    Err "Mongo web admin container did not open TCP port $webPort."
    exit 1
  }

  $webReady = $false
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$webPort/" -Method GET -MaximumRedirection 0 -TimeoutSec 5 -UseBasicParsing
      if ($resp.StatusCode -in 200, 301, 302, 401, 403) {
        $webReady = $true
        break
      }
    } catch {
      $code = $null
      try { $code = [int]$_.Exception.Response.StatusCode } catch {}
      if ($code -in 200, 301, 302, 401, 403) {
        $webReady = $true
        break
      }
    }
    Start-Sleep -Seconds 2
  }
  if (-not $webReady) {
    Err "Mongo web admin UI did not become ready."
    exit 1
  }

  if (-not (Wait-TcpPort -targetHost "127.0.0.1" -port $httpsPort -maxSeconds 45)) {
    Err "HTTPS proxy did not open port $httpsPort."
    exit 1
  }

  $httpsReady = $false
  for ($i = 0; $i -lt 30; $i++) {
    try {
      [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
      $resp = Invoke-WebRequest -Uri "https://127.0.0.1:$httpsPort/" -Method GET -MaximumRedirection 0 -TimeoutSec 5 -UseBasicParsing
      if ($resp.StatusCode -in 200, 301, 302, 401, 403) {
        $httpsReady = $true
        break
      }
    } catch {
      $code = $null
      try { $code = [int]$_.Exception.Response.StatusCode } catch {}
      if ($code -in 200, 301, 302, 401, 403) {
        $httpsReady = $true
        break
      }
    } finally {
      [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $null
    }
    Start-Sleep -Seconds 2
  }
  if (-not $httpsReady) {
    Err "Local HTTPS endpoint did not become ready."
    exit 1
  }
}

function Get-DockerOsType {
  param([string]$dockerCtx)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $osType = (& docker --context $dockerCtx info --format "{{.OSType}}" 2>$null | Out-String).Trim().ToLowerInvariant()
  $ErrorActionPreference = $prev
  return $osType
}

function Get-DockerContextNames {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $contexts = @(& docker context ls --format "{{.Name}}" 2>$null)
  $ErrorActionPreference = $prev
  return @($contexts | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
}

function Resolve-DockerContext([string[]]$preferredContexts) {
  $seen = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)
  $candidates = New-Object System.Collections.Generic.List[string]

  foreach ($ctx in @($preferredContexts + (Get-DockerContextNames) + @("desktop-linux", "default"))) {
    $trimmed = "$ctx".Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
    if ($seen.Add($trimmed)) {
      $candidates.Add($trimmed) | Out-Null
    }
  }

  foreach ($ctx in $candidates) {
    $osType = Get-DockerOsType -dockerCtx $ctx
    if ($osType -eq "linux") {
      return $ctx
    }
  }

  foreach ($ctx in $candidates) {
    $osType = Get-DockerOsType -dockerCtx $ctx
    if ($osType) {
      return $ctx
    }
  }

  if ($candidates.Count -gt 0) {
    return $candidates[0]
  }
  return "default"
}

function Find-DockerDesktopCli {
  $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
  if ($dockerCommand -and $dockerCommand.Source) {
    $dockerExeDir = Split-Path -Path $dockerCommand.Source -Parent
    $derivedCandidates = @(
      (Join-Path $dockerExeDir "..\..\DockerCli.exe"),
      (Join-Path $dockerExeDir "..\DockerCli.exe"),
      (Join-Path $dockerExeDir "com.docker.cli.exe")
    )
    foreach ($candidate in $derivedCandidates) {
      try {
        $resolved = [System.IO.Path]::GetFullPath($candidate)
      } catch {
        $resolved = $candidate
      }
      if (Test-Path $resolved) {
        return $resolved
      }
    }
  }

  foreach ($regPath in @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop"
  )) {
    try {
      $installLocation = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstallLocation
      if (-not [string]::IsNullOrWhiteSpace($installLocation)) {
        foreach ($candidate in @(
          (Join-Path $installLocation "DockerCli.exe"),
          (Join-Path $installLocation "resources\DockerCli.exe"),
          (Join-Path $installLocation "resources\bin\com.docker.cli.exe")
        )) {
          if (Test-Path $candidate) {
            return $candidate
          }
        }
      }
    } catch {}
  }

  $roots = @(
    $env:ProgramW6432,
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)},
    (Join-Path $env:SystemDrive "Program Files"),
    (Join-Path $env:SystemDrive "Program Files (x86)"),
    $env:LocalAppData
  ) | Where-Object { $_ } | Select-Object -Unique

  $relativeCandidates = @(
    "Docker\Docker\DockerCli.exe",
    "Docker\Docker\resources\DockerCli.exe",
    "Docker\Docker\resources\bin\com.docker.cli.exe",
    "Programs\Docker\Docker\DockerCli.exe",
    "Programs\Docker\Docker\resources\DockerCli.exe",
    "Programs\Docker\Docker\resources\bin\com.docker.cli.exe"
  )

  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($root in $roots) {
    foreach ($relative in $relativeCandidates) {
      $candidates.Add((Join-Path $root $relative)) | Out-Null
    }
  }

  foreach ($path in $candidates) {
    if (Test-Path $path) {
      return $path
    }
  }

  foreach ($root in $roots) {
    if (-not (Test-Path $root)) { continue }
    $found = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -in @("DockerCli.exe", "com.docker.cli.exe") } |
      Select-Object -First 1
    if ($found -and $found.FullName) {
      return $found.FullName
    }
  }

  foreach ($name in @("DockerCli.exe", "com.docker.cli.exe")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
      return $cmd.Source
    }
  }

  return $null
}

function Switch-DockerToLinuxContainers {
  $dockerCli = Find-DockerDesktopCli
  if (-not $dockerCli) {
    Warn "Docker Desktop switch CLI not found. Expected one of the standard Docker Desktop CLI paths."
    return $false
  }
  Info "Docker is running Windows containers. Switching Docker Desktop to Linux containers using: $dockerCli"
  foreach ($args in @(
    @("-SwitchLinuxEngine"),
    @("-SwitchDaemon")
  )) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $exitCode = 1
    try {
      $proc = Start-Process -FilePath $dockerCli -ArgumentList $args -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
      $exitCode = $proc.ExitCode
    } catch {
      try {
        & $dockerCli @args 2>$null | Out-Null
        $exitCode = $LASTEXITCODE
      } catch {
        $exitCode = 1
      }
    }
    $ErrorActionPreference = $prev
    if ($exitCode -eq 0) {
      for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Seconds 5
        try {
          if (Test-DockerEngine) {
            $dockerCtx = Resolve-DockerContext @((Get-ActiveDockerContext), "desktop-linux", "default")
            $osType = Get-DockerOsType -dockerCtx $dockerCtx
            if ($osType -eq "linux") {
              return $true
            }
          }
        } catch {}
      }
    }
  }
  return $false
}

function Ensure-DockerLinuxEngine([string]$dockerCtx) {
  $resolvedCtx = Resolve-DockerContext @($dockerCtx, (Get-ActiveDockerContext))
  $osType = Get-DockerOsType -dockerCtx $resolvedCtx
  if ($osType -eq "linux") {
    if ($resolvedCtx -ne $dockerCtx) {
      Info "Using Docker context: $resolvedCtx"
    }
    Info "Docker engine mode: linux"
    return $resolvedCtx
  }
  if ($osType -eq "windows") {
    $switched = Switch-DockerToLinuxContainers
    if ($switched) {
      $resolvedCtx = Resolve-DockerContext @((Get-ActiveDockerContext), "desktop-linux", $dockerCtx)
      $osType = Get-DockerOsType -dockerCtx $resolvedCtx
      if ($osType -eq "linux") {
        if ($resolvedCtx -ne $dockerCtx) {
          Info "Using Docker context: $resolvedCtx"
        }
        Info "Docker engine mode: linux"
        return $resolvedCtx
      }
    }
    Err "Docker Desktop is running Windows containers. MongoDB installer requires Linux containers."
    Warn "Open Docker Desktop and switch to Linux containers, then rerun MongoDB install."
    exit 1
  }
  Warn "Could not determine Docker engine mode reliably (reported '$osType'). Continuing."
  return $resolvedCtx
}

function Get-LocalMongoMetadataPath {
  return (Join-Path $Script:MongoRoot "install-info.json")
}

function Get-MongodVersion([string]$mongodExe) {
  if (-not (Test-Path $mongodExe)) {
    return ""
  }
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $out = (& $mongodExe --version 2>$null | Out-String)
  $ErrorActionPreference = $prev
  if ($out -match 'db version v([0-9][0-9A-Za-z\.\-]+)') {
    return $matches[1]
  }
  return ""
}

function Find-MongodExe {
  $cmd = Get-Command "mongod.exe" -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
    return $cmd.Source
  }

  $candidates = @(
    (Join-Path $Script:MongoRoot "mongodb\bin\mongod.exe")
  )

  foreach ($base in @($env:ProgramFiles, $env:ProgramW6432, (Join-Path $env:SystemDrive "Program Files"))) {
    if ([string]::IsNullOrWhiteSpace($base)) { continue }
    $mongoServerRoot = Join-Path $base "MongoDB\Server"
    if (-not (Test-Path $mongoServerRoot)) { continue }
    $serverDirs = Get-ChildItem -Path $mongoServerRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    foreach ($dir in $serverDirs) {
      $candidates += (Join-Path $dir.FullName "bin\mongod.exe")
    }
  }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  return $null
}

function Install-MongoViaWinget {
  if (-not (Has-Cmd "winget")) {
    return $null
  }

  Info "Attempting MongoDB install via winget..."
  foreach ($pkg in @("MongoDB.Server", "MongoDB.DatabaseServer")) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      & winget install -e --id $pkg --accept-source-agreements --accept-package-agreements --silent --disable-interactivity 2>$null | Out-Null
    } catch {}
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($exitCode -eq 0) {
      $mongod = Find-MongodExe
      if ($mongod) {
        return $mongod
      }
    }
  }

  return $null
}

function Install-MongoFromZip {
  $downloadRoot = Join-Path $Script:MongoRoot "downloads"
  $extractRoot = Join-Path $downloadRoot "extract"
  $nativeRoot = Join-Path $Script:MongoRoot "mongodb"
  $version = Get-EnvOrDefault "LOCALMONGO_VERSION" "7.0.14"
  $zipPath = Join-Path $downloadRoot "mongodb-windows.zip"
  $customUrl = Get-EnvOrDefault "LOCALMONGO_DOWNLOAD_URL" ""
  $urls = @()

  if ($customUrl) {
    $urls += $customUrl
  } else {
    $urls += @(
      "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-$version.zip",
      "https://downloads.mongodb.org/windows/mongodb-windows-x86_64-$version.zip",
      "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-2012plus-$version.zip",
      "https://downloads.mongodb.org/windows/mongodb-windows-x86_64-2012plus-$version.zip"
    )
  }

  if (-not (Test-Path $zipPath) -or ((Get-Item $zipPath).Length -lt 104857600)) {
    Info "Downloading MongoDB archive..."
    $ok = Download-FileFast -urls $urls -outFile $zipPath
    if (-not $ok) {
      Err "Failed to download MongoDB for Windows."
      Warn "Set LOCALMONGO_DOWNLOAD_URL to a valid MongoDB Windows ZIP if your environment blocks the default URLs."
      exit 1
    }
  } else {
    Info "Using cached MongoDB archive: $zipPath"
  }

  if (Test-Path $extractRoot) {
    Remove-Item -Recurse -Force -Path $extractRoot -ErrorAction SilentlyContinue
  }
  if (Test-Path $nativeRoot) {
    Remove-Item -Recurse -Force -Path $nativeRoot -ErrorAction SilentlyContinue
  }
  New-Item -ItemType Directory -Force -Path $extractRoot, $nativeRoot | Out-Null

  Info "Extracting MongoDB archive..."
  Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force
  $mongod = Get-ChildItem -Path $extractRoot -Recurse -Filter "mongod.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $mongod) {
    Err "Downloaded MongoDB archive does not contain mongod.exe."
    exit 1
  }

  $installRoot = Split-Path -Path $mongod.FullName -Parent | Split-Path -Parent
  Copy-Item -Path (Join-Path $installRoot "*") -Destination $nativeRoot -Recurse -Force

  $nativeMongod = Join-Path $nativeRoot "bin\mongod.exe"
  if (-not (Test-Path $nativeMongod)) {
    Err "MongoDB extraction completed but mongod.exe is missing from the expected path."
    exit 1
  }

  return $nativeMongod
}

function Ensure-NativeMongoBinary {
  $mongod = Find-MongodExe
  if ($mongod) {
    Info "Using existing mongod.exe: $mongod"
    return $mongod
  }

  $wingetMongod = Install-MongoViaWinget
  if ($wingetMongod) {
    Info "MongoDB installed via winget."
    return $wingetMongod
  }

  return (Install-MongoFromZip)
}

function Find-MongoshExe {
  $cmd = Get-Command "mongosh.exe" -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
    return $cmd.Source
  }

  foreach ($base in @($env:ProgramFiles, $env:ProgramW6432, (Join-Path $env:SystemDrive "Program Files"))) {
    if ([string]::IsNullOrWhiteSpace($base)) { continue }
    $shellRoot = Join-Path $base "MongoDB"
    if (-not (Test-Path $shellRoot)) { continue }
    $shellExe = Get-ChildItem -Path $shellRoot -Recurse -Filter "mongosh.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($shellExe -and $shellExe.FullName) {
      return $shellExe.FullName
    }
  }

  return $null
}

function Ensure-MongoshExe {
  $mongosh = Find-MongoshExe
  if ($mongosh) {
    return $mongosh
  }

  if (Has-Cmd "winget") {
    Info "Attempting mongosh install via winget..."
    foreach ($pkg in @("MongoDB.Shell", "MongoDB.mongosh")) {
      $prev = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      try {
        & winget install -e --id $pkg --accept-source-agreements --accept-package-agreements --silent --disable-interactivity 2>$null | Out-Null
      } catch {}
      $exitCode = $LASTEXITCODE
      $ErrorActionPreference = $prev
      if ($exitCode -eq 0) {
        $mongosh = Find-MongoshExe
        if ($mongosh) {
          return $mongosh
        }
      }
    }
  }

  $downloadRoot = Join-Path $Script:MongoRoot "downloads"
  $extractRoot = Join-Path $downloadRoot "mongosh-extract"
  $nativeRoot = Join-Path $Script:MongoRoot "mongosh"
  $version = Get-EnvOrDefault "LOCALMONGOSH_VERSION" "2.5.10"
  $zipPath = Join-Path $downloadRoot "mongosh-windows.zip"
  $customUrl = Get-EnvOrDefault "LOCALMONGOSH_DOWNLOAD_URL" ""
  $urls = @()

  if ($customUrl) {
    $urls += $customUrl
  } else {
    $urls += @(
      "https://downloads.mongodb.com/compass/mongosh-$version-win32-x64.zip",
      "https://fastdl.mongodb.org/mongosh/mongosh-$version-win32-x64.zip"
    )
  }

  function Download-MongoshZip([string[]]$downloadUrls, [string]$destinationPath) {
    $outDir = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    foreach ($u in $downloadUrls) {
      try {
        if (Has-Cmd "curl.exe") {
          Info "Downloading with curl (resume supported)..."
          & curl.exe -L --fail --retry 4 --retry-delay 2 --connect-timeout 20 -C - -o $destinationPath $u
          if ($LASTEXITCODE -eq 0 -and (Test-Path $destinationPath) -and ((Get-Item $destinationPath).Length -gt 5242880)) {
            return $true
          }
        }
      } catch {}
      try {
        if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
          Info "Downloading with BITS..."
          Start-BitsTransfer -Source $u -Destination $destinationPath -DisplayName "MongoDBShellInstaller"
          if ((Test-Path $destinationPath) -and ((Get-Item $destinationPath).Length -gt 5242880)) {
            return $true
          }
        }
      } catch {}
      try {
        Info "Downloading with Invoke-WebRequest..."
        Invoke-WebRequest -Uri $u -OutFile $destinationPath
        if ((Test-Path $destinationPath) -and ((Get-Item $destinationPath).Length -gt 5242880)) {
          return $true
        }
      } catch {}
    }
    return $false
  }

  Info "Attempting mongosh ZIP download..."
  New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
  $ok = Download-MongoshZip -downloadUrls $urls -destinationPath $zipPath
  if ($ok) {
    if (Test-Path $extractRoot) {
      Remove-Item -Recurse -Force -Path $extractRoot -ErrorAction SilentlyContinue
    }
    if (Test-Path $nativeRoot) {
      Remove-Item -Recurse -Force -Path $nativeRoot -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $extractRoot, $nativeRoot | Out-Null
    try {
      Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force
      $shellExe = Get-ChildItem -Path $extractRoot -Recurse -Filter "mongosh.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($shellExe -and $shellExe.FullName) {
        $installRoot = Split-Path -Path $shellExe.FullName -Parent | Split-Path -Parent
        Copy-Item -Path (Join-Path $installRoot "*") -Destination $nativeRoot -Recurse -Force
        $localMongosh = Join-Path $nativeRoot "bin\mongosh.exe"
        if (Test-Path $localMongosh) {
          return $localMongosh
        }
      }
    } catch {}
  }

  return $null
}

function Write-NativeMongoConfig([string]$cfgPath, [string[]]$bindIps, [int]$mongoPort, [string]$dataDir, [string]$logPath, [bool]$authEnabled) {
  $config = @"
storage:
  dbPath: "$($dataDir -replace '\\','\\')"
systemLog:
  destination: file
  path: "$($logPath -replace '\\','\\')"
  logAppend: true
net:
  bindIp: "$($bindIps -join ',')"
  port: $mongoPort
"@
  if ($authEnabled) {
    $config += @"
security:
  authorization: enabled
"@
  }
  [System.IO.File]::WriteAllText($cfgPath, $config, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-MongoshWithTimeout([string]$mongoshExe, [string]$uri, [string]$scriptPath, [int]$timeoutSeconds = 45) {
  if ([string]::IsNullOrWhiteSpace($mongoshExe) -or -not (Test-Path $mongoshExe)) {
    return 1
  }
  $outPath = Join-Path $Script:MongoRoot "logs\mongosh-last.log"
  $errPath = Join-Path $Script:MongoRoot "logs\mongosh-last.err.log"
  Remove-Item -Force -Path $outPath, $errPath -ErrorAction SilentlyContinue
  try {
    $proc = Start-Process -FilePath $mongoshExe `
      -ArgumentList @($uri, "--quiet", "--file", $scriptPath) `
      -PassThru `
      -WindowStyle Hidden `
      -RedirectStandardOutput $outPath `
      -RedirectStandardError $errPath
    if (-not $proc.WaitForExit($timeoutSeconds * 1000)) {
      try { $proc.Kill() } catch {}
      Warn "mongosh timed out after $timeoutSeconds seconds."
      return 124
    }
    return $proc.ExitCode
  } catch {
    Warn "mongosh execution failed: $($_.Exception.Message)"
    return 1
  }
}

function Initialize-NativeMongoAuthentication([string]$mongoshExe, [string]$connectHost, [int]$mongoPort, [string]$mongoUser, [string]$mongoPassword) {
  if ([string]::IsNullOrWhiteSpace($mongoshExe) -or -not (Test-Path $mongoshExe)) {
    return $false
  }

  $initScript = Join-Path $Script:MongoRoot "config\init-admin.js"
  $js = @"
const admin = db.getSiblingDB('admin');
const existing = admin.getUser('$mongoUser');
if (!existing) {
  admin.createUser({
    user: '$mongoUser',
    pwd: '$mongoPassword',
    roles: [{ role: 'root', db: 'admin' }]
  });
}
"@
  [System.IO.File]::WriteAllText($initScript, $js, (New-Object System.Text.UTF8Encoding($false)))

  $exitCode = Invoke-MongoshWithTimeout -mongoshExe $mongoshExe -uri "mongodb://$connectHost`:$mongoPort/admin" -scriptPath $initScript -timeoutSeconds 45
  Remove-Item -Force -Path $initScript -ErrorAction SilentlyContinue
  return ($exitCode -eq 0)
}

function Test-NativeMongoAuthentication([string]$mongoshExe, [string]$connectHost, [int]$mongoPort, [string]$mongoUser, [string]$mongoPassword) {
  if ([string]::IsNullOrWhiteSpace($mongoshExe) -or -not (Test-Path $mongoshExe)) {
    return $false
  }
  $testScript = Join-Path $Script:MongoRoot "config\test-auth.js"
  $js = @"
const result = db.runCommand({ ping: 1 });
if (!result || result.ok !== 1) {
  quit(2);
}
"@
  [System.IO.File]::WriteAllText($testScript, $js, (New-Object System.Text.UTF8Encoding($false)))
  $uri = "mongodb://$([uri]::EscapeDataString($mongoUser)):$([uri]::EscapeDataString($mongoPassword))@$connectHost`:$mongoPort/admin?authSource=admin"
  $exitCode = Invoke-MongoshWithTimeout -mongoshExe $mongoshExe -uri $uri -scriptPath $testScript -timeoutSeconds 30
  Remove-Item -Force -Path $testScript -ErrorAction SilentlyContinue
  return ($exitCode -eq 0)
}

function Remove-ExistingNativeLocalMongo {
  $service = Get-Service -Name $Script:NativeMongoServiceName -ErrorAction SilentlyContinue
  if ($service) {
    try {
      if ($service.Status -ne "Stopped") {
        Stop-Service -Name $Script:NativeMongoServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
      }
    } catch {}
    sc.exe delete $Script:NativeMongoServiceName | Out-Null
    Start-Sleep -Seconds 2
  }

  foreach ($path in @(
    (Get-LocalMongoMetadataPath),
    (Join-Path $Script:MongoRoot "config\mongod.cfg")
  )) {
    if (Test-Path $path) {
      Remove-Item -Force -Path $path -ErrorAction SilentlyContinue
    }
  }
}

function Write-LocalMongoMetadata([string]$mode, [string]$mongodExe, [string]$hostValue, [int]$mongoPort, [string]$version, [string]$connectionString, [string]$webVersion, [bool]$authEnabled) {
  $primaryHost = if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") { $hostValue } else { "localhost" }
  $metadata = [ordered]@{
    mode = $mode
    service_name = $Script:NativeMongoServiceName
    mongod_path = $mongodExe
    host = $primaryHost
    mongo_port = $mongoPort
    connection_string = $connectionString
    version = $version
    web_version = $webVersion
    auth_enabled = $authEnabled
  }
  $json = $metadata | ConvertTo-Json -Depth 4
  [System.IO.File]::WriteAllText((Get-LocalMongoMetadataPath), $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Show-NativeMongoLogTail([string]$logPath) {
  if (-not (Test-Path $logPath)) {
    return
  }
  Warn "MongoDB log tail:"
  try {
    Get-Content -Path $logPath -Tail 60 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
  } catch {}
}

function Restart-NativeMongoService([string]$serviceName, [string]$connectHost, [int]$mongoPort, [string]$logPath, [string]$phaseLabel) {
  $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
  if (-not $service) {
    Err "MongoDB service '$serviceName' was not found during $phaseLabel."
    Show-NativeMongoLogTail -logPath $logPath
    exit 1
  }

  try {
    if ($service.Status -ne "Stopped") {
      Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
    }
  } catch {}

  for ($i = 0; $i -lt 30; $i++) {
    try {
      $service.Refresh()
      if ($service.Status -eq "Stopped") { break }
    } catch {}
    Start-Sleep -Seconds 1
  }

  Start-Sleep -Seconds 5

  $lastError = $null
  for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
      if ($attempt -eq 1) {
        Start-Service -Name $serviceName -ErrorAction Stop
      } else {
        sc.exe start $serviceName | Out-Null
      }
      Start-Sleep -Seconds 2
      if (Wait-TcpPort -targetHost $connectHost -port $mongoPort -maxSeconds 45) {
        return
      }
    } catch {
      $lastError = $_.Exception.Message
    }
    Start-Sleep -Seconds 2
  }

  if ($lastError) {
    Err "MongoDB service did not restart cleanly during ${phaseLabel}: $lastError"
  } else {
    Err "MongoDB service did not restart cleanly during $phaseLabel."
  }
  Show-NativeMongoLogTail -logPath $logPath
  exit 1
}

function Install-NativeLocalMongo([string]$hostValue, [int]$mongoPort, [string]$mongoUser, [string]$mongoPassword, [string]$uiUser, [string]$uiPassword) {
  Info "Installing MongoDB as a native Windows service..."
  Remove-ExistingNativeLocalMongo

  if (-not (Port-Free $mongoPort)) {
    Warn "MongoDB port $mongoPort is still in use after cleanup."
    $listeners = Get-PortListeners $mongoPort
    if ($listeners.Count -gt 0) {
      $listeners | Format-Table -AutoSize | Out-String | Write-Host
    }
    exit 1
  }

  $mongodExe = Ensure-NativeMongoBinary
  $version = Get-MongodVersion -mongodExe $mongodExe
  $configDir = Join-Path $Script:MongoRoot "config"
  $dataDir = Join-Path $Script:MongoRoot "data"
  $logDir = Join-Path $Script:MongoRoot "logs"
  $cfgPath = Join-Path $configDir "mongod.cfg"
  $logPath = Join-Path $logDir "mongod.log"
  New-Item -ItemType Directory -Force -Path $Script:MongoRoot, $configDir, $dataDir, $logDir | Out-Null

  $connectHost = if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") { $hostValue } else { "127.0.0.1" }
  $bindIps = @($connectHost)
  Write-NativeMongoConfig -cfgPath $cfgPath -bindIps $bindIps -mongoPort $mongoPort -dataDir $dataDir -logPath $logPath -authEnabled $false

  & $mongodExe --config $cfgPath --install --serviceName $Script:NativeMongoServiceName --serviceDisplayName $Script:NativeMongoServiceName | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Err "Failed to register MongoDB Windows service."
    exit 1
  }

  Set-Service -Name $Script:NativeMongoServiceName -StartupType Automatic
  Start-Service -Name $Script:NativeMongoServiceName
  if (-not (Wait-TcpPort -targetHost $connectHost -port $mongoPort -maxSeconds 45)) {
    Err "MongoDB service did not open TCP port $mongoPort."
    exit 1
  }

  Ensure-FirewallPort -port $mongoPort
  $authEnabled = $false
  $mongoshExe = Ensure-MongoshExe
  if ($mongoshExe) {
    Info "Initializing MongoDB admin user..."
    if (Initialize-NativeMongoAuthentication -mongoshExe $mongoshExe -connectHost $connectHost -mongoPort $mongoPort -mongoUser $mongoUser -mongoPassword $mongoPassword) {
      Write-NativeMongoConfig -cfgPath $cfgPath -bindIps $bindIps -mongoPort $mongoPort -dataDir $dataDir -logPath $logPath -authEnabled $true
      Restart-NativeMongoService -serviceName $Script:NativeMongoServiceName -connectHost $connectHost -mongoPort $mongoPort -logPath $logPath -phaseLabel "enabling authentication"
      if (Test-NativeMongoAuthentication -mongoshExe $mongoshExe -connectHost $connectHost -mongoPort $mongoPort -mongoUser $mongoUser -mongoPassword $mongoPassword) {
        $authEnabled = $true
      } else {
        Warn "MongoDB service restarted, but admin login validation failed. Leaving authentication disabled in installer metadata."
        Write-NativeMongoConfig -cfgPath $cfgPath -bindIps $bindIps -mongoPort $mongoPort -dataDir $dataDir -logPath $logPath -authEnabled $false
        Restart-NativeMongoService -serviceName $Script:NativeMongoServiceName -connectHost $connectHost -mongoPort $mongoPort -logPath $logPath -phaseLabel "reverting authentication"
      }
    } else {
      Warn "Could not initialize MongoDB admin user automatically. Compass authentication will fail until a user is created."
    }
  } else {
    Warn "mongosh is not available, so MongoDB authentication could not be initialized automatically."
  }

  $primaryConnection = if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") { "mongodb://${hostValue}:$mongoPort/" } else { "mongodb://127.0.0.1:$mongoPort/" }
  Write-LocalMongoMetadata -mode "native" -mongodExe $mongodExe -hostValue $hostValue -mongoPort $mongoPort -version $version -connectionString $primaryConnection -webVersion "native-service" -authEnabled $false
  Write-LocalMongoMetadata -mode "native" -mongodExe $mongodExe -hostValue $hostValue -mongoPort $mongoPort -version $version -connectionString $primaryConnection -webVersion "native-service" -authEnabled $authEnabled

  Write-Host ""
  Write-Host "===== INSTALLATION COMPLETE ====="
  Write-Host "MongoDB service:               $($Script:NativeMongoServiceName)"
  if ($hostValue -and $hostValue -ne "localhost" -and $hostValue -ne "127.0.0.1") {
    Write-Host "MongoDB connection:            mongodb://${hostValue}:$mongoPort/"
  } else {
    Write-Host "MongoDB connection:            mongodb://127.0.0.1:$mongoPort/"
  }
  if ($version) {
    Write-Host "MongoDB version:               $version"
  }
  Write-Host "Web version:                   native-service"
  Write-Host "Data path:                     $dataDir"
  Write-Host "Log path:                      $logPath"
  if ($authEnabled) {
    Write-Host "MongoDB root user:             $mongoUser"
    Write-Host "MongoDB root password:         $mongoPassword"
  } else {
    Write-Host "Authentication:                not initialized automatically"
  }
  Write-Host "TLS/SSL:                       disabled in native Windows mode"
  Write-Host "Admin/User fields:             native Windows mode does not deploy the Docker web UI."
  Write-Host ""
  Write-Host "MongoDB is installed as a native Windows service and set to start automatically."
}

function Main {
  Relaunch-Elevated
  $windowsMode = Get-EnvOrDefault "LOCALMONGO_WINDOWS_MODE" "native"
  if ($windowsMode -ne "docker") {
    Info "===== Local MongoDB Installer (Windows / Native) ====="
  } else {
    Info "===== Local MongoDB Installer (Windows / Docker) ====="
  }

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

  if ($windowsMode -ne "docker") {
    Install-NativeLocalMongo -hostValue $hostValue -mongoPort $mongoPort -mongoUser $mongoUser -mongoPassword $mongoPassword -uiUser $uiUser -uiPassword $uiPassword
    return
  }

  Ensure-DockerInstalled
  Wait-DockerEngine
  Sanitize-DockerEnv
  $dockerCtx = Get-ActiveDockerContext
  Info "Using Docker context: $dockerCtx"
  $dockerCtx = Ensure-DockerLinuxEngine -dockerCtx $dockerCtx
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
    --restart always `
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
    --restart always `
    --network localmongo-net `
    -p "127.0.0.1:${webPort}:8081" `
    -e "ME_CONFIG_MONGODB_SERVER=localmongo-mongodb" `
    -e "ME_CONFIG_MONGODB_URL=mongodb://${mongoUser}:${mongoPassword}@localmongo-mongodb:27017/" `
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
    --restart always `
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
