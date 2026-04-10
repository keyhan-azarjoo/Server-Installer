# .NET Deployment Manual

This folder contains the Windows and Linux installers for deploying published .NET applications.

Folder layout:

```text
DotNet/
├── linux
└── windows
```

## Included Installers

- `windows/install-windows-dotnet-host.ps1`
- `windows/start-server-dashboard.ps1`
- `linux/install-linux-dotnet-runner.sh`
- `linux/start-server-dashboard.sh`

## Manual Docker API Example

If you already have a published Linux build and want to run it manually with Docker and Nginx, this structure works:

```text
C:\keyhan\API\weighingSystemApi\
├── dockerfiles
└── linux   (contains Api.dll and published app files)
```

### Step 1: Go to `dockerfiles`

```powershell
cd C:\keyhan\API\weighingSystemApi\dockerfiles
```

### Step 2: Create `Dockerfile`

```powershell
notepad Dockerfile
```

Paste:

```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:9.0

WORKDIR /app
COPY ../linux .

EXPOSE 8080

ENTRYPOINT ["dotnet", "Api.dll"]
```

Save the file without a `.txt` extension.

### Step 3: Create `nginx.conf`

```powershell
notepad nginx.conf
```

Paste:

```nginx
events {}

http {
    server {
        listen 80;

        location / {
            proxy_pass http://api:8080;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }

    server {
        listen 443 ssl;

        ssl_certificate /etc/nginx/certs/cert.pem;
        ssl_certificate_key /etc/nginx/certs/key.pem;

        location / {
            proxy_pass http://api:8080;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### Step 4: Create `docker-compose.yml`

```powershell
notepad docker-compose.yml
```

Paste:

```yaml
services:
  api:
    build:
      context: ..
      dockerfile: dockerfiles/Dockerfile
    container_name: myapi
    environment:
      - ASPNETCORE_URLS=http://+:8080
    expose:
      - "8080"
    restart: always

  nginx:
    image: nginx:latest
    container_name: nginx
    ports:
      - "8585:80"
      - "8586:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - api
```

### Step 5: Create `certs`

If you need to generate the self-signed certificate again:

```powershell
mkdir certs
docker run --rm -v ${PWD}/certs:/certs alpine sh -c "apk add --no-cache openssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /certs/key.pem -out /certs/cert.pem -subj '/CN=192.168.1.182'"
```

### Step 6: Build and run

```powershell
docker compose up -d --build
```

### Step 7: Verify containers

```powershell
docker ps
```

You should see both `myapi` and `nginx`.

### Step 8: Test the app

HTTP:

```text
http://192.168.1.182:8585/weatherforecast
```

HTTPS:

```text
https://192.168.1.182:8586/weatherforecast
```

## Notes

- A `404` on `/` is normal if your API does not expose a root endpoint. Test a real route such as `/weatherforecast`.
- A browser warning on HTTPS is normal because the certificate is self-signed.
- The request flow is: browser -> Nginx -> `http://api:8080` -> .NET API.
- You can reuse the same pattern for other published .NET APIs by changing the folder names, DLL name, exposed routes, and ports.
