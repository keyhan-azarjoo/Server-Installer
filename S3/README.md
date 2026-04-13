# Local S3 Storage (MinIO + Nginx HTTPS)

Automated local S3-compatible storage setup using:
- MinIO (object storage)
- HTTPS reverse proxy
- Windows mode selection:
  - IIS mode (native MinIO + IIS reverse proxy)
  - Docker mode (MinIO + Nginx containers)
- Linux/macOS: native install (no Docker)

This project includes:
- `windows/setup-storage.ps1` for Windows (IIS or Docker)
- `windows/installers/install-iis-prereqs.ps1` for IIS prerequisites
- `linux-macos/setup-storage.sh` for Linux/macOS (native only)

## Features

- HTTPS-enabled local endpoint
- Domain/URL input (for example: `mystorage.local`)
- Optional LAN access for other computers
- Automatic container cleanup prompt for previously created servers
- Port conflict handling (prefers `443`, can fall back to `8443/9443/10443`)
- Self-signed certificate generation and local trust attempt

## Windows Usage

Installer asks:
- `1) IIS`
- `2) Docker`

If you select Docker mode, Docker Desktop must already be installed.

Docker Desktop is a required prerequisite.  
Install it manually first (do not install from terminal commands):

- Official page: `https://www.docker.com/products/docker-desktop/`
- Direct Windows installer: `https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe`

After installing Docker Desktop, open it once and wait for **Engine running**.

Run in **PowerShell as Administrator**:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
```

Then run the installer from this repo:

```powershell
.\windows\setup-storage.ps1
```

Script reference:

`https://github.com/keyhan-azarjoo/S3/blob/main/windows/setup-storage.ps1`

One-line run from GitHub (PowerShell, simpler bootstrap):

```powershell
$script = Join-Path $env:TEMP 'setup-storage.ps1'; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/keyhan-azarjoo/S3/main/windows/setup-storage.ps1' -OutFile $script; & $script
```

## Linux/macOS Usage

```bash
chmod +x linux-macos/setup-storage.sh
sudo ./linux-macos/setup-storage.sh
```
Linux/macOS installer is native (no Docker required).

One-line run from GitHub (Linux/macOS, same command for both):

```bash
script="/tmp/setup-storage.sh"; curl -fsSL "https://raw.githubusercontent.com/keyhan-azarjoo/S3/main/linux-macos/setup-storage.sh" -o "$script" && chmod +x "$script" && sudo "$script"
```

The same command above works on both Linux and macOS.

## Access URLs

After installation, script output shows:
- MinIO Console HTTPS: `https://<domain>` or `https://<domain>:<console-port>`
- S3 API HTTPS: `https://<domain>:<api-port>` (or `https://<domain>` when `443` is used)
- LAN Console URL: `https://<server-lan-ip>` or `https://<server-lan-ip>:<console-port>` (if enabled)
- LAN S3 API URL: `https://<server-lan-ip>:<api-port>` (if enabled)
- MinIO Console direct URL: `http://localhost:<minio-ui-port>`
- MinIO API direct URL: `http://localhost:<minio-api-port>`

Default login:
- Username: `admin`
- Password: `StrongPassword123`

## DNS / Domain Notes

If domain works on server but not on other computers, set DNS properly:
- Add router/internal DNS record: `<domain> -> <server-lan-ip>`
- Or add hosts entry on each client (if you choose per-client setup)

Without DNS mapping, use IP URL directly.

## Manual Docker Setup

Deploy MinIO with native HTTPS (no Nginx reverse proxy). This avoids UI
breakage and provides the full MinIO Console with Users, Access Keys, and
Policies.

Replace `192.168.1.182` with your server's LAN IP throughout.

### Directory Structure

```text
C:\LocalS3\
 +-- docker-compose.yml
 +-- data\
 `-- certs\
     +-- openssl.cnf
     +-- public.crt
     `-- private.key
```

### Step 0: Clean (if re-deploying)

```powershell
cd C:\LocalS3
docker compose down -v
Remove-Item -Recurse -Force data, certs -ErrorAction Ignore
```

### Step 1: Create structure

```powershell
mkdir data
mkdir certs
```

### Step 2: Create SSL certificate config

Create `certs/openssl.cnf` (SAN is required for MinIO HTTPS):

```ini
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = 192.168.1.182

[v3_req]
subjectAltName = @alt_names

[alt_names]
IP.1 = 192.168.1.182
```

### Step 3: Generate SSL certificate

```powershell
docker run --rm -v ${PWD}/certs:/certs alpine sh -c "apk add --no-cache openssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /certs/private.key -out /certs/public.crt -config /certs/openssl.cnf"
```

Verify you have `certs/private.key` and `certs/public.crt`.

### Step 4: Create `docker-compose.yml`

```yaml
version: "3.9"

services:
  minio:
    image: minio/minio:RELEASE.2023-10-25T06-33-25Z
    container_name: minio
    restart: unless-stopped

    command: server /data --console-address ":9001"

    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: admin123

      # Required for correct share/presigned URLs
      MINIO_SERVER_URL: https://192.168.1.182:9000
      MINIO_BROWSER_REDIRECT_URL: https://192.168.1.182:9001

    volumes:
      - ./data:/data
      - ./certs/public.crt:/root/.minio/certs/public.crt
      - ./certs/private.key:/root/.minio/certs/private.key

    ports:
      - "9000:9000"
      - "9001:9001"
```

### Step 5: Run

```powershell
docker compose up -d
```

### Step 6: Access

MinIO Console:

```text
https://192.168.1.182:9001
```

S3 API:

```text
https://192.168.1.182:9000
```

Login: `admin / admin123`

Browser warning is normal (self-signed certificate).

You should see the full MinIO console with sidebar: `Buckets`, `Identity`, `Users`, `Access Keys`, `Policies`.

## Troubleshooting

```powershell
docker logs minio
```

## Technical Notes

- MinIO serves HTTPS natively using certificates mounted into `/root/.minio/certs/`.
- No Nginx reverse proxy is needed, which avoids console UI breakage.
- The SAN entry in `openssl.cnf` is required; MinIO rejects certificates
  without a Subject Alternative Name.
- `MINIO_SERVER_URL` and `MINIO_BROWSER_REDIRECT_URL` ensure share links and
  console redirects use the correct host and port.

## Architecture

```text
Browser -> https://192.168.1.182:9001 -> MinIO Console
App/SDK -> https://192.168.1.182:9000 -> MinIO S3 API -> MinIO Storage
```

## Known Notes

- If Docker Compose fails with `invalid proto:`, installer automatically falls back to `docker run`.
- If `443` is busy, installer can clean previous managed containers or use alternate HTTPS port.
