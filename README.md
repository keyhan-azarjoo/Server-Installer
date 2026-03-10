# Server / .NET App Installer

This repository includes OS-specific installers under `DotNet`:

- `DotNet/windows/install-windows-dotnet-host.ps1`
- `DotNet/windows/start-server-dashboard.ps1`
- `DotNet/windows/modules/common.ps1`
- `DotNet/windows/modules/iis-mode.ps1`
- `DotNet/windows/modules/docker-mode.ps1`
- `DotNet/linux/install-linux-dotnet-runner.sh`
- `DotNet/linux/start-server-dashboard.sh`
- `dashboard/server_installer_dashboard.py`
- `dashboard/start-server-dashboard.py`

These installers deploy only from prebuilt published output.

## Windows

Run higher-level dashboard mode (cross-platform, single URL):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '$ProgressPreference="SilentlyContinue"; Invoke-WebRequest -Uri "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main/dashboard/bootstrap.ps1" -OutFile ".\\bootstrap.ps1"; powershell -NoProfile -ExecutionPolicy Bypass -File .\\bootstrap.ps1'
```

Dashboard URLs:
- `http://127.0.0.1:8090`
- `http://<server-ip>:8090`

If you download only the main Windows script, it will automatically download its required module files into a local `modules` folder the first time it runs.

Repository folder:

```text
https://github.com/keyhan-azarjoo/Server-Installer/tree/main/DotNet/windows
```

What it does:

- Prompts for `IIS` or `Docker` deployment mode.
- Prompts for the .NET release channel.
- Prompts for a build artifact URL, a local source folder, a local published folder, or a local published `.zip`.
- If a local source folder contains a `.csproj`, it runs `dotnet publish -c Release` first and deploys that build output.
- Prompts for an optional domain name.
- If no domain is provided, it auto-detects a reachable public/static IP when available; otherwise it uses the local LAN IP.

In `IIS` mode:

- Enables IIS and required modules, including WebSockets.
- Installs the matching .NET SDK, ASP.NET Core Runtime, and Hosting Bundle.
- Creates both HTTP and HTTPS IIS bindings and generates a self-signed certificate when needed.
- Deploys site files under `C:\inetpub\wwwroot\<site-or-package-name>`.
- Skips IIS features and .NET installers that are already present.

In `Docker` mode:

- Uses the same source detection and local publish flow.
- Installs Docker Desktop if Docker is missing and `winget` is available.
- Builds a container image from the prepared app files.
- Runs the container on HTTP only by default.
- Stores the Docker build context under `C:\ProgramData\Server-Installer\docker\<site-or-package-name>`.

Defaults:

- .NET channel prompt accepts `8`, `9`, `10`, `10.0`, `LTS`, `STS`, or a direct value supported by Microsoft `aka.ms` channel links. Default: `8.0`
- HTTP port: `80`
- HTTPS port: `443`
- IIS site name: `DotNetApp`

Example with custom values:

```powershell
.\install-windows-dotnet-host.ps1 -DeploymentMode IIS -DotNetChannel 10 -SiteName MyApi -SitePort 8080 -HttpsPort 8443
```

Example in Docker mode:

```powershell
.\install-windows-dotnet-host.ps1 -DeploymentMode Docker -DotNetChannel 10 -SiteName MyApi -DockerHostPort 8080
```

## Linux

Run dashboard mode:

```bash
curl -fsSL "https://raw.githubusercontent.com/keyhan-azarjoo/Server-Installer/main/dashboard/start-server-dashboard.py" -o ./start-server-dashboard.py && python3 ./start-server-dashboard.py
```

Repository folders:

```text
Windows: https://github.com/keyhan-azarjoo/Server-Installer/tree/main/DotNet/windows
Linux:   https://github.com/keyhan-azarjoo/Server-Installer/tree/main/DotNet/linux
```

What it does:

- Prompts for the .NET release channel, then installs `curl`, `unzip`, `tar`, `openssl`, `nginx`, and the .NET SDK / ASP.NET Core Runtime.
- Prompts for a build artifact URL, a local source folder, a local published folder, or a local published `.zip` / `.tar.gz`.
- If a local source folder contains a `.csproj`, it runs `dotnet publish -c Release` first and deploys that build output.
- Prompts for an optional domain name.
- If no domain is provided, it auto-detects a reachable public/static IP when available; otherwise it uses the local LAN IP.
- Runs the app on local Kestrel and places Nginx in front of it for HTTP and HTTPS.
- Generates a self-signed certificate when needed.
- Deploys site files under `/var/www/<service-or-package-name>`.
- Skips Linux packages and .NET installers that are already present.

Defaults:

- .NET channel prompt accepts `8`, `9`, `10`, `10.0`, `LTS`, `STS`, or another valid `dotnet-install` channel value. Default: `8.0`
- Kestrel port: `5000`
- HTTP port: `80`
- HTTPS port: `443`
- Service name: `dotnet-app`

Example with custom values:

```bash
sudo DOTNET_CHANNEL=10 SERVICE_NAME=my-api SERVICE_PORT=5050 HTTP_PORT=8080 HTTPS_PORT=8443 ./install-linux-dotnet-runner.sh
```

## Build The App First

Build the app on your build machine or CI machine, package the published output, then give the installer the artifact URL or local package path.

Example publish commands:

```bash
dotnet publish -c Release -r win-x64 --self-contained false -o ./publish/win-x64
dotnet publish -c Release -r linux-x64 --self-contained false -o ./publish/linux-x64
dotnet publish -c Release -r osx-x64 --self-contained false -o ./publish/osx-x64
dotnet publish -c Release -r osx-arm64 --self-contained false -o ./publish/osx-arm64
```

Then package the published output:

```bash
cd ./publish
zip -r win-x64.zip ./win-x64
tar -czf linux-x64.tar.gz ./linux-x64
tar -czf osx-arm64.tar.gz ./osx-arm64
```

If the artifact is private on GitHub, the installers will prompt for a GitHub token so they can download the package.

## Notes

- Remote downloads must already be published build artifacts.
- For local deployment, you can pass either raw source code (with a `.csproj`) or an already published output folder.
- A script already running on a remote server cannot directly read a path from your local computer.
- The Windows flow is intended for ASP.NET Core web apps hosted behind IIS.
- Windows also supports Docker mode as an alternative to IIS.
- The Linux flow runs the app behind Nginx with HTTP and HTTPS termination.
- The generated certificates are self-signed. Browsers will warn until you replace them with a trusted certificate.
- There is no macOS installer in this repository yet.
