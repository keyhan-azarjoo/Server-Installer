# IIS / .NET App Installer

This repository includes two OS-specific installers under `DotNet`:

- `DotNet/windows/install-windows-dotnet-host.ps1`
- `DotNet/linux/install-linux-dotnet-runner.sh`

These installers deploy only from prebuilt published output.

## Windows

Fetch and run the PowerShell script from an elevated terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/keyhan-azarjoo/IIS-Installer/main/DotNet/windows/install-windows-dotnet-host.ps1" -OutFile ".\install-windows-dotnet-host.ps1"
.\install-windows-dotnet-host.ps1
```

Repository folder:

```text
https://github.com/keyhan-azarjoo/IIS-Installer/tree/main/DotNet/windows
```

What it does:

- Enables IIS and required modules, including WebSockets.
- Prompts for the .NET release channel and installs the matching .NET SDK, ASP.NET Core Runtime, and Hosting Bundle.
- Prompts for a build artifact URL, a local source folder, a local published folder, or a local published `.zip`.
- If a local source folder contains a `.csproj`, it runs `dotnet publish -c Release` first and deploys that build output.
- Prompts for an optional domain name.
- If no domain is provided, it tries to use the public IP first and falls back to the local LAN IP.
- Creates both HTTP and HTTPS IIS bindings and generates a self-signed certificate when needed.
- Skips IIS features and .NET installers that are already present.

Defaults:

- .NET channel prompt accepts `8`, `9`, `10`, `10.0`, `LTS`, `STS`, or a direct value supported by Microsoft `aka.ms` channel links. Default: `8.0`
- HTTP port: `80`
- HTTPS port: `443`
- IIS site name: `DotNetApp`

Example with custom values:

```powershell
.\install-windows-dotnet-host.ps1 -DotNetChannel 10 -SiteName MyApi -SitePort 8080 -HttpsPort 8443
```

## Linux

Fetch and run the shell script as root:

```bash
curl -fsSL "https://raw.githubusercontent.com/keyhan-azarjoo/IIS-Installer/main/DotNet/linux/install-linux-dotnet-runner.sh" -o ./install-linux-dotnet-runner.sh
chmod +x ./install-linux-dotnet-runner.sh
sudo ./install-linux-dotnet-runner.sh
```

Repository folders:

```text
Windows: https://github.com/keyhan-azarjoo/IIS-Installer/tree/main/DotNet/windows
Linux:   https://github.com/keyhan-azarjoo/IIS-Installer/tree/main/DotNet/linux
```

What it does:

- Prompts for the .NET release channel, then installs `curl`, `unzip`, `tar`, `openssl`, `nginx`, and the .NET SDK / ASP.NET Core Runtime.
- Prompts for a build artifact URL, a local source folder, a local published folder, or a local published `.zip` / `.tar.gz`.
- If a local source folder contains a `.csproj`, it runs `dotnet publish -c Release` first and deploys that build output.
- Prompts for an optional domain name.
- If no domain is provided, it tries to use the public IP first and falls back to the local LAN IP.
- Runs the app on local Kestrel and places Nginx in front of it for HTTP and HTTPS.
- Generates a self-signed certificate when needed.
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
- The Windows flow is intended for ASP.NET Core web apps hosted behind IIS.
- The Linux flow runs the app behind Nginx with HTTP and HTTPS termination.
- The generated certificates are self-signed. Browsers will warn until you replace them with a trusted certificate.
