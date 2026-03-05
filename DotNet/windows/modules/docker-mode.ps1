Set-StrictMode -Version Latest

function Ensure-WindowsContainersFeature {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName "Containers" -ErrorAction SilentlyContinue
    if (-not $feature) {
        return
    }

    if ($feature.State -eq "Enabled") {
        Write-Host "Windows Containers feature already enabled."
        return
    }

    Write-Host "Enabling Windows Containers feature"
    Enable-WindowsOptionalFeature -Online -FeatureName "Containers" -All -NoRestart | Out-Null
}

function Install-DockerWithMicrosoftScript {
    Ensure-WindowsContainersFeature
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
