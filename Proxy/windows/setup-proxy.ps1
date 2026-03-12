$ErrorActionPreference = "Stop"

function Info([string]$message) { Write-Host "[INFO] $message" }
function Warn([string]$message) { Write-Warning $message }
function Fail([string]$message) { throw $message }

function Resolve-ScriptPath {
  $candidates = @(
    $PSCommandPath,
    $MyInvocation.PSCommandPath,
    $MyInvocation.MyCommand.Path
  )

  foreach ($candidate in $candidates) {
    if (-not [string]::IsNullOrWhiteSpace($candidate)) {
      try {
        return [System.IO.Path]::GetFullPath($candidate)
      } catch {
      }
    }
  }

  Fail "Could not determine the Proxy installer script path."
}

$scriptPath = Resolve-ScriptPath

function Test-IsAdmin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($id)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-IsLocalSystem {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  return $id.User -and $id.User.Value -eq "S-1-5-18"
}

function Get-ActiveInteractiveUser {
  try {
    $explorers = Get-Process explorer -IncludeUserName -ErrorAction SilentlyContinue |
      Where-Object { $_.UserName } |
      Sort-Object SessionId
    foreach ($proc in $explorers) {
      if ($proc.SessionId -ge 1) {
        return $proc.UserName
      }
    }
  } catch {
  }

  try {
    $query = (& query user 2>$null) -split "`r?`n"
    foreach ($line in $query) {
      if ($line -match '^\s*>?(?<user>\S+)\s+\S+\s+\d+\s+Active\b') {
        $user = $matches['user'].Trim()
        if ($user) { return $user }
      }
    }
  } catch {
  }

  return ""
}

function ConvertTo-SingleQuotedPs([string]$value) {
  if ($null -eq $value) { $value = "" }
  return "'" + ($value -replace "'", "''") + "'"
}

function Invoke-AsInteractiveUser {
  $activeUser = Get-ActiveInteractiveUser
  if ([string]::IsNullOrWhiteSpace($activeUser)) {
    Fail "Proxy install requires an active signed-in Windows user session so WSL can be installed and configured."
  }

  $taskName = "ServerInstaller-ProxyBootstrap"
  $runnerRoot = Join-Path $env:ProgramData "Server-Installer\proxy"
  $runnerScript = Join-Path $runnerRoot "proxy-interactive-runner.ps1"
  $runnerLog = Join-Path $runnerRoot "proxy-interactive-runner.log"
  $runnerExit = Join-Path $runnerRoot "proxy-interactive-runner.exit"
  $targetScript = $scriptPath

  New-Item -ItemType Directory -Force -Path $runnerRoot | Out-Null
  Remove-Item $runnerLog, $runnerExit -Force -ErrorAction SilentlyContinue

  $envAssignments = @(
    "PROXY_SKIP_INTERACTIVE_RELAUNCH",
    "PROXY_WSL_DISTRO",
    "PROXY_LAYER",
    "PROXY_DOMAIN",
    "PROXY_EMAIL",
    "PROXY_DUCKDNS_TOKEN",
    "PROXY_PANEL_PORT",
    "PROXY_HOST_IP",
    "SERVER_INSTALLER_DASHBOARD_PORT"
  ) | ForEach-Object {
    '$env:{0} = {1}' -f $_, (ConvertTo-SingleQuotedPs ([Environment]::GetEnvironmentVariable($_)))
  }

  $runnerContent = @(
    '$ErrorActionPreference = ''Stop'''
    ('$logFile = {0}' -f (ConvertTo-SingleQuotedPs $runnerLog))
    ('$exitFile = {0}' -f (ConvertTo-SingleQuotedPs $runnerExit))
    ('$targetScript = {0}' -f (ConvertTo-SingleQuotedPs $targetScript))
    '$null = New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($logFile))'
    'Set-Content -Path $logFile -Value "" -Encoding UTF8'
  ) + $envAssignments + @(
    'try {'
    '  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $targetScript *>&1 | Tee-Object -FilePath $logFile -Append'
    '  $code = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }'
    '} catch {'
    '  ($_ | Out-String) | Tee-Object -FilePath $logFile -Append | Out-Null'
    '  $code = 1'
    '}'
    'Set-Content -Path $exitFile -Value $code -Encoding ASCII'
    'exit $code'
  )
  Set-Content -Path $runnerScript -Value ($runnerContent -join "`r`n") -Encoding UTF8

  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`""
  $principal = New-ScheduledTaskPrincipal -UserId $activeUser -LogonType Interactive -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

  try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName

    $offset = 0
    $deadline = (Get-Date).AddMinutes(30)
    while ((Get-Date) -lt $deadline) {
      if (Test-Path $runnerLog) {
        $content = Get-Content -Path $runnerLog -Raw -ErrorAction SilentlyContinue
        if ($content) {
          $newText = $content.Substring([Math]::Min($offset, $content.Length))
          if ($newText) {
            Write-Host -NoNewline $newText
            $offset = $content.Length
          }
        }
      }
      if (Test-Path $runnerExit) {
        break
      }
      Start-Sleep -Milliseconds 700
    }

    if (-not (Test-Path $runnerExit)) {
      Fail "Timed out waiting for interactive Proxy bootstrap task to finish."
    }

    $exitCode = 1
    try {
      $exitCode = [int](Get-Content -Path $runnerExit -Raw -ErrorAction Stop).Trim()
    } catch {
      $exitCode = 1
    }
    if ($exitCode -ne 0) {
      Fail "Interactive Proxy bootstrap failed."
    }
    return
  } finally {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Remove-Item $runnerScript, $runnerExit -Force -ErrorAction SilentlyContinue
  }
}

function Convert-ToWslPath([string]$windowsPath) {
  $full = [System.IO.Path]::GetFullPath($windowsPath)
  $drive = $full.Substring(0,1).ToLowerInvariant()
  $rest = $full.Substring(2).Replace('\', '/')
  return "/mnt/$drive$rest"
}

function Get-EnvOrDefault([string]$name, [string]$defaultValue) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if ([string]::IsNullOrWhiteSpace($value)) { return $defaultValue }
  return $value.Trim()
}

function Has-Cmd([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Try-EnableDockerCliFromDefaultPath {
  if (Has-Cmd "docker") { return }

  foreach ($dockerBin in @(
    "C:\Program Files\Docker\Docker\resources\bin",
    "C:\Program Files\Docker\Docker",
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\resources\bin"),
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker")
  )) {
    if (-not $dockerBin) { continue }
    $dockerExe = Join-Path $dockerBin "docker.exe"
    if (-not (Test-Path $dockerExe)) { continue }
    if ($env:Path -notlike "*$dockerBin*") {
      $env:Path = "$dockerBin;$env:Path"
    }
    return
  }
}

function Download-FileFast([string[]]$urls, [string]$outFile) {
  $outDir = Split-Path -Parent $outFile
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null

  foreach ($url in $urls) {
    try {
      if (Has-Cmd "curl.exe") {
        & curl.exe -L --fail --retry 4 --retry-delay 2 --connect-timeout 20 -C - -o $outFile $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $outFile) -and ((Get-Item $outFile).Length -gt 104857600)) { return $true }
      }
    } catch {}

    try {
      if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
        Start-BitsTransfer -Source $url -Destination $outFile -DisplayName "ProxyDockerInstaller"
        if ((Test-Path $outFile) -and ((Get-Item $outFile).Length -gt 104857600)) { return $true }
      }
    } catch {}

    try {
      Invoke-WebRequest -Uri $url -OutFile $outFile
      if ((Test-Path $outFile) -and ((Get-Item $outFile).Length -gt 104857600)) { return $true }
    } catch {}
  }

  return $false
}

function Install-DockerDesktopDirect {
  $cacheDir = Join-Path $env:ProgramData "Server-Installer\proxy\downloads"
  $exe = Join-Path $cacheDir "DockerDesktopInstaller.exe"
  $urls = @(
    "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe",
    "https://desktop.docker.com/win/stable/amd64/Docker%20Desktop%20Installer.exe"
  )

  $useCached = $false
  if (Test-Path $exe) {
    $size = (Get-Item $exe).Length
    if ($size -gt 104857600) {
      $useCached = $true
      Info "Using cached Docker installer: $exe"
    }
  }

  if (-not $useCached) {
    Info "Downloading Docker Desktop installer..."
    if (-not (Download-FileFast -urls $urls -outFile $exe)) {
      return $false
    }
  }

  Start-Process -FilePath $exe -ArgumentList @("install", "--quiet", "--accept-license") -Wait
  return $true
}

function Find-DockerDesktopExe {
  foreach ($candidate in @(
    "C:\Program Files\Docker\Docker\Docker Desktop.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe")
  )) {
    if ($candidate -and (Test-Path $candidate)) {
      return $candidate
    }
  }

  foreach ($root in @(
    "C:\Program Files\Docker\Docker",
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker")
  )) {
    if (-not $root -or -not (Test-Path $root)) { continue }
    try {
      $match = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "Docker Desktop.exe" } |
        Select-Object -First 1
      if ($match -and $match.FullName) {
        return $match.FullName
      }
    } catch {}
  }

  return ""
}

function Find-DockerSwitchCli {
  foreach ($name in @("DockerCli.exe", "com.docker.cli.exe", "com.docker.cli")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
      return $cmd.Source
    }
  }

  foreach ($candidate in @(
    "C:\Program Files\Docker\Docker\DockerCli.exe",
    "C:\Program Files\Docker\Docker\com.docker.cli.exe",
    "C:\Program Files\Docker\Docker\resources\bin\com.docker.cli.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\DockerCli.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\com.docker.cli.exe")
  )) {
    if ($candidate -and (Test-Path $candidate)) {
      return $candidate
    }
  }

  return ""
}

function Start-DockerDesktop {
  try {
    $running = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    if ($running) {
      return
    }
  } catch {}

  $exe = Find-DockerDesktopExe
  if ($exe -and (Test-Path $exe)) {
    Info "Starting Docker Desktop..."
    Start-Process $exe | Out-Null
  }
}

function Test-DockerEngine {
  $previous = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  docker info 2>&1 | Out-Null
  $ok = ($LASTEXITCODE -eq 0)
  $ErrorActionPreference = $previous
  return $ok
}

function Get-DockerOsType {
  $previous = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $out = docker info --format "{{.OSType}}" 2>$null
  $exitCode = $LASTEXITCODE
  $ErrorActionPreference = $previous
  if ($exitCode -ne 0) {
    return ""
  }
  return (($out | Out-String).Trim())
}

function Ensure-DockerInstalled {
  Try-EnableDockerCliFromDefaultPath
  if (Has-Cmd "docker") {
    return
  }

  Info "Docker CLI not found. Attempting automatic Docker Desktop installation..."
  if (-not (Install-DockerDesktopDirect)) {
    Fail "Automatic Docker Desktop installation failed."
  }

  Try-EnableDockerCliFromDefaultPath
  if (-not (Has-Cmd "docker")) {
    $dockerExe = Join-Path "C:\Program Files\Docker\Docker\resources\bin" "docker.exe"
    if (Test-Path $dockerExe) {
      $env:Path = "C:\Program Files\Docker\Docker\resources\bin;$env:Path"
    }
  }

  if (-not (Has-Cmd "docker")) {
    Fail "Docker Desktop was installed but docker.exe is still unavailable."
  }
}

function Repair-DockerEngine {
  try {
    $wslOut = wsl --list --quiet 2>$null
    if ($wslOut) {
      $distros = $wslOut | Where-Object { ($_ -replace '[^\x20-\x7E]', '').Trim() -match "docker-desktop" }
      foreach ($distroName in $distros) {
        $trimmed = ($distroName -replace '[^\x20-\x7E]', '').Trim()
        if ($trimmed) {
          wsl --terminate $trimmed 2>$null | Out-Null
        }
      }
    }
  } catch {}

  try {
    Get-Process "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  } catch {}
  Start-Sleep -Seconds 5
  Start-DockerDesktop
}

function Wait-DockerEngine {
  if (Test-DockerEngine) {
    return
  }

  Start-DockerDesktop
  $elapsed = 0
  while ($elapsed -lt 120) {
    Start-Sleep -Seconds 5
    $elapsed += 5
    if (Test-DockerEngine) {
      return
    }
  }

  Warn "Docker Engine did not become ready. Attempting repair..."
  Repair-DockerEngine

  $elapsed = 0
  while ($elapsed -lt 120) {
    Start-Sleep -Seconds 5
    $elapsed += 5
    if (Test-DockerEngine) {
      return
    }
  }

  Fail "Docker Engine is not reachable."
}

function Ensure-DockerLinuxEngine {
  $osType = Get-DockerOsType
  if ($osType -eq "linux") {
    return
  }

  $dockerCli = Find-DockerSwitchCli
  if (-not $dockerCli) {
    Fail "Docker Desktop switch CLI not found."
  }

  Info "Switching Docker Desktop to Linux containers..."
  & $dockerCli -SwitchLinuxEngine 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Fail "Failed to switch Docker Desktop to Linux containers."
  }

  $elapsed = 0
  while ($elapsed -lt 120) {
    Start-Sleep -Seconds 5
    $elapsed += 5
    if ((Get-DockerOsType) -eq "linux") {
      return
    }
  }

  Fail "Docker Desktop did not switch to Linux containers in time."
}

function ConvertTo-SingleQuotedBash([string]$value) {
  if ($null -eq $value) { $value = "" }
  $replacement = [string][char]39 + [string][char]34 + [string][char]39 + [string][char]34 + [string][char]39
  return "'" + $value.Replace("'", $replacement) + "'"
}

function Invoke-Docker([string[]]$Arguments) {
  $output = & docker @Arguments 2>&1
  $exitCode = $LASTEXITCODE
  $text = (($output | ForEach-Object { "$_" }) -join "`n")
  $text = $text.Replace([string][char]0, '').Replace([string][char]0xFEFF, '').Trim()
  return [pscustomobject]@{
    ExitCode = $exitCode
    Output = $text
  }
}

function Invoke-DockerOrFail([string[]]$Arguments, [string]$failureMessage) {
  $result = Invoke-Docker $Arguments
  if ($result.ExitCode -ne 0) {
    $detail = if ($result.Output) { "`n$result.Output" } else { "" }
    Fail "$failureMessage$detail"
  }
  return $result.Output
}

function Get-ProxyDockerAdminPassword([string]$stateFile) {
  if (Test-Path $stateFile) {
    try {
      $existing = Get-Content -Path $stateFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
      if ($existing -and $existing.admin_password) {
        return "$($existing.admin_password)"
      }
    } catch {}
  }

  $alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*-_=+"
  $chars = 1..24 | ForEach-Object { $alphabet[(Get-Random -Minimum 0 -Maximum $alphabet.Length)] }
  return (-join $chars)
}

function Get-DockerContainerStatus([string]$name) {
  $status = Invoke-Docker @("container", "inspect", "--format", "{{.State.Status}}", $name)
  if ($status.ExitCode -ne 0) {
    return ""
  }
  return $status.Output.Trim()
}

function Ensure-ProxyDockerImage([string]$imageName) {
  $inspect = Invoke-Docker @("image", "inspect", $imageName)
  if ($inspect.ExitCode -eq 0) {
    return
  }

  $bootstrapName = "server-installer-proxy-bootstrap"
  Invoke-Docker @("rm", "-f", $bootstrapName) | Out-Null

  Info "Preparing Ubuntu image for Docker-based Proxy install..."
  Invoke-DockerOrFail @("run", "-d", "--name", $bootstrapName, "ubuntu:24.04", "sleep", "infinity") "Failed to start Docker bootstrap container."

  try {
    $bootstrapCommand = @"
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y systemd systemd-sysv dbus sudo curl ca-certificates gnupg lsb-release python3 openssl openssh-server iptables iproute2 procps ufw cron vnstat net-tools iputils-ping nginx stunnel4 jq
mkdir -p /run/sshd
systemd-machine-id-setup >/dev/null 2>&1 || true
apt-get clean
rm -rf /var/lib/apt/lists/*
"@
    Invoke-DockerOrFail @("exec", $bootstrapName, "bash", "-lc", $bootstrapCommand) "Failed to prepare Ubuntu image for Proxy Docker fallback."
    Invoke-DockerOrFail @("commit", $bootstrapName, $imageName) "Failed to save prepared Proxy Docker image."
  } finally {
    Invoke-Docker @("rm", "-f", $bootstrapName) | Out-Null
  }
}

function Wait-ProxyDockerSystemd([string]$containerName) {
  $probe = @'
for i in $(seq 1 90); do
  state=$(systemctl is-system-running 2>/dev/null || true)
  if [ "$state" = "running" ] || [ "$state" = "degraded" ]; then
    exit 0
  fi
  sleep 2
done
exit 1
'@
  Invoke-DockerOrFail @("exec", $containerName, "bash", "-lc", $probe) "Proxy Docker container did not finish booting systemd."
}

function Ensure-ProxyDockerContainer([string]$containerName, [string]$imageName, [string]$proxyRootWindows, [int]$panelPort) {
  $status = Get-DockerContainerStatus $containerName
  if ($status -eq "running") {
    return
  }

  if ($status) {
    Invoke-DockerOrFail @("start", $containerName) "Failed to start Proxy Docker container."
    return
  }

  $mountSpec = "${proxyRootWindows}:/srv/proxy:ro"
  $arguments = @(
    "run", "-d",
    "--name", $containerName,
    "--hostname", "server-installer-proxy",
    "--privileged",
    "--cgroupns=host",
    "--restart", "unless-stopped",
    "--tmpfs", "/run",
    "--tmpfs", "/run/lock",
    "-v", "/sys/fs/cgroup:/sys/fs/cgroup:rw",
    "-v", $mountSpec,
    "-p", "22:22",
    "-p", "80:80",
    "-p", "443:443",
    "-p", "${panelPort}:8443",
    $imageName,
    "/sbin/init"
  )
  Invoke-DockerOrFail $arguments "Failed to create Proxy Docker container."
}

function Install-ProxyViaDocker([string]$proxyRootWindows, [string]$stateFile, [string]$layer, [string]$domain, [string]$email, [string]$duckdns, [string]$panelPort, [string]$panelHost) {
  Ensure-DockerInstalled
  Wait-DockerEngine
  Ensure-DockerLinuxEngine

  $containerName = "server-installer-proxy"
  $imageName = "server-installer/proxy-base:24.04"
  $adminPassword = Get-ProxyDockerAdminPassword $stateFile
  $rootCredential = ConvertTo-SingleQuotedBash ("root:" + $adminPassword)
  $layerQuoted = ConvertTo-SingleQuotedBash $layer
  $domainQuoted = ConvertTo-SingleQuotedBash $domain
  $emailQuoted = ConvertTo-SingleQuotedBash $email
  $duckdnsQuoted = ConvertTo-SingleQuotedBash $duckdns
  $panelPortQuoted = ConvertTo-SingleQuotedBash $panelPort
  $panelHostQuoted = ConvertTo-SingleQuotedBash $panelHost
  $dashboardPortQuoted = ConvertTo-SingleQuotedBash ([Environment]::GetEnvironmentVariable("SERVER_INSTALLER_DASHBOARD_PORT"))

  Ensure-ProxyDockerImage -imageName $imageName
  Ensure-ProxyDockerContainer -containerName $containerName -imageName $imageName -proxyRootWindows $proxyRootWindows -panelPort ([int]$panelPort)
  Wait-ProxyDockerSystemd -containerName $containerName

  $installCommand = @"
set -e
export DEBIAN_FRONTEND=noninteractive
printf '%s\n' $rootCredential | chpasswd
mkdir -p /run/sshd
export PROXY_REPO_ROOT='/srv/proxy'
export PROXY_LAYER=$layerQuoted
export PROXY_DOMAIN=$domainQuoted
export PROXY_EMAIL=$emailQuoted
export PROXY_DUCKDNS_TOKEN=$duckdnsQuoted
export PROXY_PANEL_PORT=$panelPortQuoted
export PROXY_HOST_IP=$panelHostQuoted
export SERVER_INSTALLER_DASHBOARD_PORT=$dashboardPortQuoted
bash /srv/proxy/linux-macos/setup-proxy.sh
"@
  Invoke-DockerOrFail @("exec", $containerName, "bash", "-lc", $installCommand) "Docker-based Proxy installation failed."

  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stateFile) | Out-Null
  @{
    runtime = "docker"
    container = $containerName
    layer = $layer
    host = $panelHost
    url = "https://${panelHost}:$panelPort"
    port = $panelPort
    admin_username = "root"
    admin_password = $adminPassword
    installed_at = (Get-Date).ToString("s")
  } | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

  Info "Proxy installation completed inside Docker."
  Info "Proxy dashboard: https://${panelHost}:$panelPort"
  Info "Proxy dashboard login: root / $adminPassword"
}

function Invoke-Wsl([string[]]$Arguments) {
  $output = & wsl.exe @Arguments 2>&1
  $exitCode = $LASTEXITCODE
  $text = (($output | ForEach-Object { "$_" }) -join "`n")
  $text = $text.Replace([string][char]0, '').Replace([string][char]0xFEFF, '').Trim()
  return [pscustomobject]@{
    ExitCode = $exitCode
    Output = $text
  }
}

function Invoke-WslOrFail([string[]]$Arguments, [string]$failureMessage) {
  $result = Invoke-Wsl $Arguments
  if ($result.ExitCode -ne 0) {
    $detail = if ($result.Output) { "`n$result.Output" } else { "" }
    Fail "$failureMessage$detail"
  }
  return $result.Output
}

function Get-WslHelpText() {
  return (Invoke-Wsl @("--help")).Output
}

function Test-WslSupportsOption([string]$option, [string]$helpText) {
  return $helpText -match [Regex]::Escape($option)
}

function Test-WslDistroAvailable([string]$name, [string]$helpText) {
  if (Test-WslSupportsOption "--list" $helpText -or Test-WslSupportsOption "-l," $helpText) {
    $result = Invoke-Wsl @("-l", "-q")
    if ($result.ExitCode -eq 0) {
      return ($result.Output -split "`r?`n" | Where-Object { $_.Trim() -eq $name }).Count -gt 0
    }
  }

  $probe = Invoke-Wsl @("-d", $name, "-e", "/bin/true")
  return $probe.ExitCode -eq 0
}

if (-not (Test-IsAdmin)) {
  Fail "This installer must run as Administrator."
}

if ((Test-IsLocalSystem) -and [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("PROXY_SKIP_INTERACTIVE_RELAUNCH"))) {
  Info "Proxy installer is running as LocalSystem. Relaunching under the active desktop user for WSL operations..."
  Invoke-AsInteractiveUser
  exit 0
}

$scriptRoot = Split-Path -Parent $scriptPath
$proxyRoot = Split-Path -Parent $scriptRoot
$linuxInstallerWindows = Join-Path $proxyRoot "linux-macos\setup-proxy.sh"
$linuxInstallerWsl = Convert-ToWslPath $linuxInstallerWindows
$repoRootWsl = Convert-ToWslPath $proxyRoot
$stateDir = Join-Path $env:ProgramData "Server-Installer\proxy"
$stateFile = Join-Path $stateDir "proxy-wsl.json"
$distro = Get-EnvOrDefault "PROXY_WSL_DISTRO" "Ubuntu"
$layer = Get-EnvOrDefault "PROXY_LAYER" "layer3-basic"
$domain = Get-EnvOrDefault "PROXY_DOMAIN" ""
$email = Get-EnvOrDefault "PROXY_EMAIL" ""
$duckdns = Get-EnvOrDefault "PROXY_DUCKDNS_TOKEN" ""
$panelPort = Get-EnvOrDefault "PROXY_PANEL_PORT" "8443"
$panelHost = Get-EnvOrDefault "PROXY_HOST_IP" "127.0.0.1"

if ($panelPort -notmatch '^\d+$') {
  Fail "PROXY_PANEL_PORT must be numeric."
}

$panelPortNumber = [int]$panelPort
if ($panelPortNumber -lt 1 -or $panelPortNumber -gt 65535) {
  Fail "PROXY_PANEL_PORT must be between 1 and 65535."
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  Warn "WSL is not available on this machine. Falling back to Docker-based Linux runtime."
  Install-ProxyViaDocker -proxyRootWindows $proxyRoot -stateFile $stateFile -layer $layer -domain $domain -email $email -duckdns $duckdns -panelPort $panelPort -panelHost $panelHost
  exit 0
}

$wslHelp = Get-WslHelpText

Info "Checking WSL distro '$distro'..."
if (-not (Test-WslDistroAvailable $distro $wslHelp)) {
  Warn "WSL distro '$distro' is not installed. Trying Docker-based Linux runtime first."
  try {
    Install-ProxyViaDocker -proxyRootWindows $proxyRoot -stateFile $stateFile -layer $layer -domain $domain -email $email -duckdns $duckdns -panelPort $panelPort -panelHost $panelHost
    exit 0
  } catch {
    if (-not (Test-WslSupportsOption "--install" $wslHelp)) {
      throw
    }
    Warn "Docker fallback failed. Falling back to WSL distro installation."
  }

  Info "Installing WSL distro '$distro'..."
  Invoke-WslOrFail @("--install", "-d", $distro) "Failed to start WSL distro installation."
  throw "WSL distro installation started. Reboot if Windows requests it, then rerun the Proxy installer."
}

Info "Enabling systemd inside WSL..."
$enableSystemd = @"
set -e
mkdir -p /etc
python3 - <<'PY'
from pathlib import Path
path = Path('/etc/wsl.conf')
text = path.read_text(encoding='utf-8') if path.exists() else ''
if '[boot]' in text and 'systemd=true' in text:
    raise SystemExit(0)
lines = [line.rstrip() for line in text.splitlines() if line.strip()]
if '[boot]' not in lines:
    lines.extend(['[boot]', 'systemd=true'])
elif 'systemd=true' not in lines:
    idx = lines.index('[boot]')
    lines.insert(idx + 1, 'systemd=true')
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
"@
Invoke-WslOrFail @("-d", $distro, "--user", "root", "--", "bash", "-lc", $enableSystemd) "Failed to update /etc/wsl.conf inside WSL."

if (Test-WslSupportsOption "--shutdown" $wslHelp) {
  Invoke-WslOrFail @("--shutdown") "Failed to restart WSL after enabling systemd."
  Start-Sleep -Seconds 3
} else {
  Warn "This WSL build does not support 'wsl --shutdown'. A Windows reboot may be required before systemd becomes active."
}

$initProcess = Invoke-WslOrFail @("-d", $distro, "--user", "root", "--", "bash", "-lc", "ps -p 1 -o comm= 2>/dev/null || true") "Failed to verify WSL init system."
if (($initProcess | Out-String).Trim() -ne "systemd") {
  Fail "systemd is not active in WSL distro '$distro'. The Proxy installer requires a newer WSL release with systemd support. Update WSL/Windows, reboot, and rerun the installer."
}

Info "Running Linux proxy installer inside WSL..."
$installCommand = @"
set -e
export PROXY_REPO_ROOT='$repoRootWsl'
export PROXY_LAYER='$layer'
export PROXY_DOMAIN='$domain'
export PROXY_EMAIL='$email'
export PROXY_DUCKDNS_TOKEN='$duckdns'
export PROXY_PANEL_PORT='$panelPort'
export PROXY_HOST_IP='$panelHost'
bash '$linuxInstallerWsl'
"@
Invoke-WslOrFail @("-d", $distro, "--user", "root", "--", "bash", "-lc", $installCommand) "Linux proxy installer failed inside WSL."

Info "Configuring WSL keepalive + autostart task..."
$keepAliveInstall = @"
cat >/usr/local/bin/server-installer-proxy-keepalive.sh <<'EOF'
#!/usr/bin/env bash
set -e
mkdir -p /var/run/server-installer
if [ -f /var/run/server-installer/proxy-keepalive.pid ] && kill -0 \$(cat /var/run/server-installer/proxy-keepalive.pid) 2>/dev/null; then
  :
else
  nohup bash -lc 'while true; do sleep 3600; done' >/var/log/proxy-wsl-keepalive.log 2>&1 &
  echo \$! >/var/run/server-installer/proxy-keepalive.pid
fi
systemctl start proxy-panel >/dev/null 2>&1 || true
systemctl start xray >/dev/null 2>&1 || true
systemctl start stunnel4 >/dev/null 2>&1 || true
systemctl start nginx >/dev/null 2>&1 || true
service ssh start >/dev/null 2>&1 || true
EOF
chmod +x /usr/local/bin/server-installer-proxy-keepalive.sh
/usr/local/bin/server-installer-proxy-keepalive.sh
"@
Invoke-WslOrFail @("-d", $distro, "--user", "root", "--", "bash", "-lc", $keepAliveInstall) "Failed to configure Proxy keepalive inside WSL."

$taskName = "ServerInstaller-ProxyWSL"
$taskCommand = "wsl.exe -d $distro --user root -- bash -lc '/usr/local/bin/server-installer-proxy-keepalive.sh'"
schtasks /Delete /TN $taskName /F 1>$null 2>$null | Out-Null
schtasks /Create /TN $taskName /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $taskCommand /F | Out-Null

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
@{
  distro = $distro
  layer = $layer
  host = $panelHost
  url = "https://${panelHost}:$panelPort"
  port = $panelPort
  installed_at = (Get-Date).ToString("s")
} | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

Info "Proxy installation completed."
Info "Proxy dashboard: https://${panelHost}:$panelPort"
