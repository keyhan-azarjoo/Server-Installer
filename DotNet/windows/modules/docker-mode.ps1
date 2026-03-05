Set-StrictMode -Version Latest

function Enable-WindowsOptionalFeatureIfAvailable {
    param([Parameter(Mandatory = $true)][string]$FeatureName)

    $feature = Get-WindowsOptionalFeature -Online -FeatureName $FeatureName -ErrorAction SilentlyContinue
    if (-not $feature) {
        return @{
            Available = $false
            RestartNeeded = $false
        }
    }

    if ($feature.State -eq "Enabled") {
        Write-Host "Windows feature already enabled: $FeatureName"
        return @{
            Available = $true
            RestartNeeded = $false
        }
    }

    Write-Host "Enabling Windows feature: $FeatureName"
    $result = Enable-WindowsOptionalFeature -Online -FeatureName $FeatureName -All -NoRestart
    $needsRestart = $result -and ($result.RestartNeeded -eq $true)
    return @{
        Available = $true
        RestartNeeded = $needsRestart
    }
}

function Ensure-WindowsContainerRuntimeReady {
    $restartNeeded = $false
    $containersFeature = Enable-WindowsOptionalFeatureIfAvailable -FeatureName "Containers"
    if (-not $containersFeature.Available) {
        throw "Windows Containers feature is unavailable on this host."
    }
    if ($containersFeature.RestartNeeded) {
        $restartNeeded = $true
    }

    $hypervResult = Enable-WindowsOptionalFeatureIfAvailable -FeatureName "Microsoft-Hyper-V-All"
    if (-not $hypervResult.Available) {
        $hypervResult = Enable-WindowsOptionalFeatureIfAvailable -FeatureName "Microsoft-Hyper-V"
    }
    if ($hypervResult.Available -and $hypervResult.RestartNeeded) {
        $restartNeeded = $true
    }

    foreach ($serviceName in @("hns", "vmcompute")) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne "Running") {
            Start-Service -Name $serviceName -ErrorAction SilentlyContinue
        }
    }

    if ($restartNeeded) {
        throw "Windows container features were enabled/updated. Restart the machine and rerun deployment."
    }
}

function Get-DockerEngineOsType {
    if (-not (Test-Command -Name "docker")) {
        return $null
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $dockerOsType = (& docker info --format "{{.OSType}}" 2>$null | Select-Object -First 1)
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ([string]::IsNullOrWhiteSpace($dockerOsType)) {
        return $null
    }

    return $dockerOsType.Trim().ToLowerInvariant()
}

function Test-DockerDesktopInstalled {
    $desktopPaths = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LocalAppData "Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    foreach ($desktopPath in $desktopPaths) {
        if (Test-Path -LiteralPath $desktopPath) {
            return $true
        }
    }

    if (Get-Command "com.docker.cli" -ErrorAction SilentlyContinue) {
        return $true
    }

    return $false
}

function Install-DockerDesktop {
    if (Test-Command -Name "winget") {
        Write-Host "Installing Docker Desktop with winget"
        $process = Start-Process -FilePath "winget" -ArgumentList "install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements --silent" -Wait -PassThru -NoNewWindow
        if ($process.ExitCode -eq 0) {
            return
        }

        Write-Host "winget install failed with exit code $($process.ExitCode). Trying direct installer download."
    }

    $installerPath = Join-Path $env:TEMP "DockerDesktopInstaller.exe"
    $installerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    try {
        Write-Host "Downloading Docker Desktop installer"
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

        $argumentSets = @(
            "install --quiet --accept-license --always-run-service",
            "install --quiet"
        )

        foreach ($arguments in $argumentSets) {
            Write-Host "Installing Docker Desktop from downloaded installer ($arguments)"
            $installerProcess = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
            if ($installerProcess.ExitCode -eq 0) {
                return
            }

            if (Test-DockerDesktopInstalled) {
                Write-Host "Docker Desktop appears installed despite installer exit code $($installerProcess.ExitCode)."
                return
            }
        }

        throw "Docker Desktop installer failed. Check Docker Desktop install logs under %LocalAppData%\\Docker."
    }
    catch {
        if (Test-DockerDesktopInstalled) {
            Write-Host "Docker Desktop appears installed despite installer error."
            return
        }

        throw
    }
    finally {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    }
}

function Switch-DockerEngineToLinux {
    if ((Get-DockerEngineOsType) -eq "linux") {
        return $true
    }

    $waitForLinuxEngine = {
        param(
            [int]$TimeoutSeconds = 20,
            [string]$Stage = "switch"
        )

        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        $lastReportedOsType = $null
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 2
            $engineOsType = Get-DockerEngineOsType
            if ($engineOsType -eq "linux") {
                return $true
            }

            if ($engineOsType -ne $lastReportedOsType) {
                if ([string]::IsNullOrWhiteSpace($engineOsType)) {
                    Write-Host "Waiting for Docker engine to become available ($Stage)..."
                }
                else {
                    Write-Host "Docker engine currently reports '$engineOsType' ($Stage), waiting for 'linux'..."
                }
                $lastReportedOsType = $engineOsType
            }
        }

        return $false
    }

    $dockerDesktopCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LocalAppData "Docker\Docker\Docker Desktop.exe")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

    $desktopRunning = [bool](Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)
    if (-not $desktopRunning) {
        foreach ($desktopPath in $dockerDesktopCandidates) {
            if (-not (Test-Path -LiteralPath $desktopPath)) {
                continue
            }

            Write-Host "Starting Docker Desktop"
            Start-Process -FilePath $desktopPath -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
            break
        }
    }

    $dockerCliCandidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\DockerCli.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\DockerCli.exe"),
        (Join-Path $env:LocalAppData "Docker\Docker\DockerCli.exe")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

    $dockerCliCommand = Get-Command "com.docker.cli" -ErrorAction SilentlyContinue
    if ($dockerCliCommand) {
        $dockerCliCandidates += $dockerCliCommand.Source
        $dockerCliCandidates = $dockerCliCandidates | Select-Object -Unique
    }

    $dockerCliCandidates = $dockerCliCandidates | Select-Object -First 2
    foreach ($dockerCliPath in $dockerCliCandidates) {
        foreach ($arg in @("-SwitchLinuxEngine", "-SwitchDaemon")) {
            Write-Host "Switching Docker engine to Linux containers using $arg"
            $switchProcess = Start-Process -FilePath $dockerCliPath -ArgumentList $arg -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue
            if ($switchProcess) {
                $switchProcess.WaitForExit()
            }

            if (& $waitForLinuxEngine -Stage "DockerCli $arg") {
                return $true
            }

            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                & $dockerCliPath $arg *> $null
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }

            if (& $waitForLinuxEngine -Stage "DockerCli direct $arg") {
                return $true
            }
        }
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $contextNames = & docker context ls --format "{{.Name}}" 2>$null
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($LASTEXITCODE -eq 0 -and $contextNames) {
        foreach ($contextName in @("desktop-linux", "default")) {
            if ($contextNames -contains $contextName) {
                Write-Host "Switching Docker context to '$contextName'"
                $previousErrorActionPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = "Continue"
                    & docker context use $contextName 2>$null | Out-Null
                }
                finally {
                    $ErrorActionPreference = $previousErrorActionPreference
                }
                if ($LASTEXITCODE -eq 0 -and (& $waitForLinuxEngine -Stage "docker context $contextName")) {
                    return $true
                }
            }
        }
    }

    return $false
}

function Install-DockerWithMicrosoftScript {
    $installScriptPath = Join-Path $env:TEMP "install-docker-ce.ps1"
    $installScriptUrl = "https://raw.githubusercontent.com/microsoft/Windows-Containers/Main/helpful_tools/Install-DockerCE/install-docker-ce.ps1"

    try {
        Write-Host "Downloading Microsoft Windows Containers Docker install script"
        Invoke-WebRequest -UseBasicParsing -Uri $installScriptUrl -OutFile $installScriptPath

        Write-Host "Installing Docker with Microsoft Windows Containers script"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installScriptPath | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Microsoft Docker install script failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Remove-Item -LiteralPath $installScriptPath -Force -ErrorAction SilentlyContinue
    }

    $dockerService = Get-Service -Name docker -ErrorAction SilentlyContinue
    if ($dockerService -and $dockerService.Status -ne "Running") {
        Start-Service docker
    }

    if (-not (Test-Command -Name "docker")) {
        throw "Docker installation completed, but the docker CLI is still unavailable. A restart may be required."
    }
}

function Ensure-DockerInstalled {
    if (Test-Command -Name "docker") {
        return
    }

    if (Test-Command -Name "winget") {
        Write-Host "Installing Docker Desktop with winget"
        $process = Start-Process -FilePath "winget" -ArgumentList "install --id Docker.DockerDesktop --exact --accept-package-agreements --accept-source-agreements --silent" -Wait -PassThru -NoNewWindow
        if ($process.ExitCode -ne 0) {
            throw "Docker installation failed with exit code $($process.ExitCode)."
        }
        return
    }

    Install-DockerWithMicrosoftScript
}

function Get-DockerRuntimeTag {
    param([Parameter(Mandatory = $true)][string]$DotNetChannel)

    $majorVersion = Get-DotNetMajorVersion -Channel $DotNetChannel
    $windowsBuild = [System.Environment]::OSVersion.Version.Build

    if ($windowsBuild -ge 20348) {
        return "$majorVersion.0-nanoserver-ltsc2022"
    }

    if ($windowsBuild -ge 17763) {
        return "$majorVersion.0-nanoserver-1809"
    }

    throw "Unsupported Windows build $windowsBuild for Windows containers. Use Windows Server 2019 / build 17763 or newer."
}

function Write-Dockerfile {
    param(
        [Parameter(Mandatory = $true)][string]$ContentPath,
        [Parameter(Mandatory = $true)][string]$AssemblyName,
        [Parameter(Mandatory = $true)][string]$DotNetChannel
    )

    $dockerfilePath = Join-Path $ContentPath "Dockerfile.generated"
    $runtimeTag = Get-DockerRuntimeTag -DotNetChannel $DotNetChannel
    $content = @"
FROM mcr.microsoft.com/dotnet/aspnet:$runtimeTag
WORKDIR /app
COPY . .
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "$AssemblyName.dll"]
"@
    Set-Content -Path $dockerfilePath -Value $content -Encoding UTF8
    return $dockerfilePath
}

function Invoke-DockerDeployment {
    param(
        [Parameter(Mandatory = $true)][string]$ContentPath,
        [Parameter(Mandatory = $true)][string]$PackageName,
        [Parameter(Mandatory = $true)][string]$SiteName,
        [Parameter(Mandatory = $true)][string]$DotNetChannel,
        [Parameter(Mandatory = $true)][int]$HostPort,
        [string]$DomainName
    )

    Ensure-DockerInstalled
    $engineOsType = Get-DockerEngineOsType
    if ($engineOsType -ne "windows") {
        throw "Docker engine must be set to Windows containers. Current engine: '$engineOsType'. Switch Docker Desktop to Windows containers and rerun."
    }
    Ensure-WindowsContainerRuntimeReady

    $deploymentRoot = Join-Path $env:ProgramData "IIS-Installer\docker"
    $targetPath = Join-Path $deploymentRoot $PackageName
    New-Item -ItemType Directory -Path $deploymentRoot -Force | Out-Null
    Copy-FolderContent -SourcePath $ContentPath -TargetPath $targetPath

    $assemblyPath = Find-ApplicationAssembly -DeploymentPath $targetPath
    $assemblyName = [System.IO.Path]::GetFileNameWithoutExtension($assemblyPath)
    $dockerfilePath = Write-Dockerfile -ContentPath (Split-Path -Path $assemblyPath -Parent) -AssemblyName $assemblyName -DotNetChannel $DotNetChannel

    $imageName = ("{0}:latest" -f ($SiteName.ToLowerInvariant() -replace '[^a-z0-9\-]', '-'))
    $containerName = ($SiteName.ToLowerInvariant() -replace '[^a-z0-9\-]', '-')

    $existingContainer = & docker ps -a --filter "name=^/$containerName$" --format "{{.Names}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query existing Docker containers."
    }

    if ($existingContainer -contains $containerName) {
        & docker rm -f $containerName *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove existing Docker container '$containerName'."
        }
    }

    & docker build -f $dockerfilePath -t $imageName $targetPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "docker build failed."
    }

    # Prefer process isolation first when the image matches the host; fall back to Hyper-V
    # if process isolation is unsupported on the current machine.
    $runAttempts = @("process", "hyperv")

    $runSucceeded = $false
    foreach ($isolation in $runAttempts) {
        $runArgs = @("run", "-d", "--name", $containerName, "-p", "${HostPort}:8080")
        if (-not [string]::IsNullOrWhiteSpace($isolation)) {
            $runArgs += "--isolation=$isolation"
            Write-Host "Starting Docker container with $isolation isolation"
        }
        else {
            Write-Host "Starting Docker container"
        }

        $runArgs += $imageName
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $runOutput = & docker @runArgs 2>&1
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }

        if ($runOutput) {
            $runOutput | Out-Host
        }

        if ($LASTEXITCODE -eq 0) {
            $runSucceeded = $true
            break
        }

        if ($isolation -eq "process") {
            & docker rm -f $containerName *> $null
            Write-Host "Process-isolated Docker run failed. Retrying with Hyper-V isolation."
        }
    }

    if (-not $runSucceeded) {
        throw "docker run failed."
    }

    $resolvedHost = Resolve-HostName -DomainName $DomainName
    return @{
        Host = $resolvedHost
        HttpPort = $HostPort
        Path = $targetPath
        Container = $containerName
    }
}
