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
  $principal = New-ScheduledTaskPrincipal -UserId $activeUser -LogonType InteractiveToken -RunLevel Highest
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
  Fail "WSL is not available on this machine."
}

$wslHelp = Get-WslHelpText

Info "Checking WSL distro '$distro'..."
if (-not (Test-WslDistroAvailable $distro $wslHelp)) {
  if (-not (Test-WslSupportsOption "--install" $wslHelp)) {
    Fail "WSL distro '$distro' is not installed, and this Windows build does not support 'wsl --install'. Install Ubuntu manually or upgrade WSL/Windows, then rerun the Proxy installer."
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
