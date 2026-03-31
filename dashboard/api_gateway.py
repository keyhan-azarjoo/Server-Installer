"""
API Gateway endpoints for service-level operations.

Provides proxy/gateway APIs for S3 (MinIO), MongoDB, Proxy panel,
SAM3 object detection, and Ollama LLM services.
"""
import json
import os
import ssl
import subprocess
import traceback
import urllib.request
import urllib.parse
import urllib.error
from http import HTTPStatus
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# SSL context that accepts self-signed certificates for internal service calls
_internal_ssl_ctx = ssl.create_default_context()
_internal_ssl_ctx.check_hostname = False
_internal_ssl_ctx.verify_mode = ssl.CERT_NONE


def _json_request(url, method="GET", data=None, headers=None, timeout=15):
    """Make an HTTP request and return parsed JSON."""
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        ctx = _internal_ssl_ctx if url.startswith("https://") else None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            return json.loads(err_body)
        except Exception:
            return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _raw_request(url, method="GET", data=None, headers=None, timeout=30):
    """Make HTTP request, return (status_code, headers_dict, body_bytes)."""
    hdrs = {}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        ctx = _internal_ssl_ctx if url.startswith("https://") else None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {}, e.read()
    except Exception as e:
        return 500, {}, json.dumps({"error": str(e)}).encode()


# ─────────────────────────────────────────────────────────────────────────────
# S3 / MinIO Gateway
# ─────────────────────────────────────────────────────────────────────────────

def _get_s3_config():
    """Read S3/MinIO install state and return (endpoint, access_key, secret_key)."""
    # Windows state file
    state_file = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "LocalS3" / "storage-server" / "install-state.json"
    # Linux state file
    linux_state = Path("/opt/locals3/install-state.json")
    cfg = {}
    for f in (state_file, linux_state):
        if f.exists():
            try:
                cfg = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                break
            except Exception:
                pass
    host = cfg.get("display_host") or cfg.get("selected_host") or cfg.get("lan_ip") or "127.0.0.1"
    api_port = cfg.get("api_port") or cfg.get("minio_api_port") or "9000"
    access_key = cfg.get("root_user") or cfg.get("access_key") or "admin"
    secret_key = cfg.get("root_password") or cfg.get("secret_key") or ""
    endpoint = f"http://{host}:{api_port}"
    return endpoint, access_key, secret_key


def _mc_cmd(args, timeout=30):
    """Run MinIO client (mc) command and return (ok, output_text)."""
    mc_paths = []
    if os.name == "nt":
        mc_paths = [
            str(Path(os.environ.get("ProgramData", "C:/ProgramData")) / "LocalS3" / "mc.exe"),
            "mc.exe", "mc",
        ]
    else:
        mc_paths = ["/usr/local/bin/mc", "/opt/locals3/mc", "mc"]
    mc_bin = None
    for p in mc_paths:
        try:
            r = subprocess.run([p, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                mc_bin = p
                break
        except Exception:
            continue
    if not mc_bin:
        return False, "MinIO client (mc) not found on this server."
    try:
        # Ensure alias is configured
        endpoint, access_key, secret_key = _get_s3_config()
        subprocess.run(
            [mc_bin, "alias", "set", "local", endpoint, access_key, secret_key],
            capture_output=True, timeout=10,
        )
        result = subprocess.run(
            [mc_bin] + args,
            capture_output=True, timeout=timeout, text=True,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, str(e)


def s3_list_buckets():
    """List all S3 buckets."""
    ok, output = _mc_cmd(["ls", "local", "--json"])
    if not ok:
        # Fallback: try direct MinIO API
        endpoint, access_key, secret_key = _get_s3_config()
        try:
            req = urllib.request.Request(f"{endpoint}/minio/health/live", method="GET")
            with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
                pass
        except Exception:
            return {"ok": False, "error": f"Cannot reach MinIO. {output}"}
        return {"ok": False, "error": output}
    buckets = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
            if item.get("type") == "folder" or item.get("key", "").endswith("/"):
                name = item.get("key", "").rstrip("/")
                if name:
                    buckets.append({
                        "name": name,
                        "creation_date": item.get("lastModified", ""),
                    })
        except Exception:
            continue
    return {"ok": True, "buckets": buckets}


def s3_create_bucket(name):
    """Create a new S3 bucket."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "Bucket name is required."}
    ok, output = _mc_cmd(["mb", f"local/{name}"])
    return {"ok": ok, "message": output}


def s3_delete_bucket(name):
    """Delete a bucket."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "Bucket name is required."}
    ok, output = _mc_cmd(["rb", f"local/{name}"])
    return {"ok": ok, "message": output}


def s3_list_objects(bucket, prefix=""):
    """List objects in a bucket."""
    bucket = str(bucket or "").strip()
    if not bucket:
        return {"ok": False, "error": "Bucket name is required."}
    path = f"local/{bucket}"
    if prefix:
        path += f"/{prefix}"
    ok, output = _mc_cmd(["ls", path, "--json"])
    if not ok:
        return {"ok": False, "error": output}
    objects = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
            objects.append({
                "key": item.get("key", ""),
                "size": item.get("size", 0),
                "last_modified": item.get("lastModified", ""),
                "type": "folder" if item.get("key", "").endswith("/") else "file",
            })
        except Exception:
            continue
    return {"ok": True, "objects": objects}


def s3_delete_object(bucket, key):
    """Delete an object from a bucket."""
    bucket = str(bucket or "").strip()
    key = str(key or "").strip()
    if not bucket or not key:
        return {"ok": False, "error": "Bucket and key are required."}
    ok, output = _mc_cmd(["rm", f"local/{bucket}/{key}"])
    return {"ok": ok, "message": output}


def s3_presign(bucket, key, expires=3600):
    """Generate a pre-signed URL."""
    bucket = str(bucket or "").strip()
    key = str(key or "").strip()
    if not bucket or not key:
        return {"ok": False, "error": "Bucket and key are required."}
    try:
        expires = max(60, min(604800, int(expires)))
    except Exception:
        expires = 3600
    ok, output = _mc_cmd(["share", "download", f"local/{bucket}/{key}", f"--expire={expires}s"])
    if ok:
        # Extract URL from output
        url = ""
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("http"):
                url = line
                break
        return {"ok": True, "url": url, "expires_in": expires}
    return {"ok": False, "error": output}


def s3_info():
    """Get S3 service connection info."""
    endpoint, access_key, _ = _get_s3_config()
    healthy = False
    try:
        req = urllib.request.Request(f"{endpoint}/minio/health/live", method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
            healthy = resp.status == 200
    except Exception:
        pass
    return {
        "ok": True,
        "endpoint": endpoint,
        "access_key": access_key,
        "region": "us-east-1",
        "healthy": healthy,
    }


def s3_health():
    """Health check for S3 service."""
    endpoint, _, _ = _get_s3_config()
    try:
        req = urllib.request.Request(f"{endpoint}/minio/health/live", method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
            return {"ok": True, "status": "healthy"}
    except Exception as e:
        return {"ok": False, "status": "unhealthy", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB Gateway (extends existing native endpoints)
# ─────────────────────────────────────────────────────────────────────────────

def _mongosh_json(body_js, db_name="admin", timeout=40, username=None, password=None):
    """Run mongosh and return parsed JSON result. Mirrors the existing pattern."""
    # Import from the main module at runtime to avoid circular imports
    try:
        from server_installer_dashboard import run_windows_mongosh_json
        return run_windows_mongosh_json(body_js, timeout=timeout, username=username, password=password)
    except ImportError:
        pass
    # Fallback: try running mongosh directly
    shell_paths = []
    if os.name == "nt":
        shell_paths = ["mongosh.exe", "mongosh", "mongo.exe", "mongo"]
    else:
        shell_paths = ["/usr/bin/mongosh", "/usr/local/bin/mongosh", "mongosh", "mongo"]
    shell_bin = None
    for p in shell_paths:
        try:
            r = subprocess.run([p, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                shell_bin = p
                break
        except Exception:
            continue
    if not shell_bin:
        return False, {"error": "mongosh not found."}
    wrapped = f"try {{ const __r = (function() {{ {body_js} }})(); printjson(__r); }} catch(e) {{ printjson({{error: e.message}}); }}"
    cmd = [shell_bin, "--quiet", "--eval", wrapped]
    if username:
        cmd.extend(["-u", username])
    if password:
        cmd.extend(["-p", password])
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
        output = (result.stdout or "").strip()
        if output:
            return True, json.loads(output)
        return False, {"error": result.stderr or "No output from mongosh."}
    except json.JSONDecodeError:
        return False, {"error": "Invalid JSON from mongosh."}
    except Exception as e:
        return False, {"error": str(e)}


def mongo_list_databases(username=None, password=None):
    """List all MongoDB databases."""
    body_js = """
const adminDb = db.getSiblingDB('admin');
const list = adminDb.adminCommand({ listDatabases: 1 }) || {};
return {
  databases: (list.databases || []).map((x) => ({
    name: x.name || "",
    sizeOnDisk: x.sizeOnDisk || 0,
    empty: !!x.empty
  }))
};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok and isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_create_database(name, username=None, password=None):
    """Create a database by inserting into an init collection."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "Database name is required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(name)});
targetDb.createCollection("_init");
return {{ message: "Database created", database: {json.dumps(name)} }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok:
        return {"ok": True, "message": f"Database '{name}' created."}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_drop_database(name, username=None, password=None):
    """Drop a database."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "Database name is required."}
    if name in ("admin", "local", "config"):
        return {"ok": False, "error": f"Cannot drop system database '{name}'."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(name)});
targetDb.dropDatabase();
return {{ message: "Database dropped", database: {json.dumps(name)} }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok:
        return {"ok": True, "message": f"Database '{name}' dropped."}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_create_collection(db_name, col_name, username=None, password=None):
    """Create a collection."""
    db_name = str(db_name or "").strip()
    col_name = str(col_name or "").strip()
    if not db_name or not col_name:
        return {"ok": False, "error": "Database and collection name are required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
targetDb.createCollection({json.dumps(col_name)});
return {{ message: "Collection created", database: {json.dumps(db_name)}, collection: {json.dumps(col_name)} }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok:
        return {"ok": True, "message": f"Collection '{col_name}' created in '{db_name}'."}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_drop_collection(db_name, col_name, username=None, password=None):
    """Drop a collection."""
    db_name = str(db_name or "").strip()
    col_name = str(col_name or "").strip()
    if not db_name or not col_name:
        return {"ok": False, "error": "Database and collection name are required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
targetDb.getCollection({json.dumps(col_name)}).drop();
return {{ message: "Collection dropped", database: {json.dumps(db_name)}, collection: {json.dumps(col_name)} }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok:
        return {"ok": True, "message": f"Collection '{col_name}' dropped from '{db_name}'."}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_insert_documents(db_name, col_name, documents, username=None, password=None):
    """Insert documents into a collection."""
    db_name = str(db_name or "").strip()
    col_name = str(col_name or "").strip()
    if not db_name or not col_name:
        return {"ok": False, "error": "Database and collection are required."}
    if not documents or not isinstance(documents, list):
        return {"ok": False, "error": "documents must be a non-empty array."}
    docs_json = json.dumps(documents)
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
const result = targetDb.getCollection({json.dumps(col_name)}).insertMany({docs_json});
return {{ inserted_count: result.insertedIds ? Object.keys(result.insertedIds).length : 0, inserted_ids: result.insertedIds || {{}} }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok and isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_update_documents(db_name, col_name, filter_doc, update_doc, username=None, password=None):
    """Update documents matching a filter."""
    db_name = str(db_name or "").strip()
    col_name = str(col_name or "").strip()
    if not db_name or not col_name:
        return {"ok": False, "error": "Database and collection are required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
const result = targetDb.getCollection({json.dumps(col_name)}).updateMany({json.dumps(filter_doc)}, {json.dumps(update_doc)});
return {{ matched_count: result.matchedCount || 0, modified_count: result.modifiedCount || 0 }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok and isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_delete_documents(db_name, col_name, filter_doc, username=None, password=None):
    """Delete documents matching a filter."""
    db_name = str(db_name or "").strip()
    col_name = str(col_name or "").strip()
    if not db_name or not col_name:
        return {"ok": False, "error": "Database and collection are required."}
    if not filter_doc:
        return {"ok": False, "error": "Filter is required for delete operations."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
const result = targetDb.getCollection({json.dumps(col_name)}).deleteMany({json.dumps(filter_doc)});
return {{ deleted_count: result.deletedCount || 0 }};
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok and isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": False, "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


def mongo_health(username=None, password=None):
    """Health check for MongoDB."""
    body_js = """
const result = db.adminCommand({ ping: 1 });
const status = db.adminCommand({ serverStatus: 1 });
return { status: "healthy", connections: (status.connections || {}).current || 0 };
"""
    ok, payload = _mongosh_json(body_js, username=username, password=password)
    if ok and isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": False, "status": "unhealthy", "error": payload.get("error", "Failed") if isinstance(payload, dict) else str(payload)}


# ─────────────────────────────────────────────────────────────────────────────
# Proxy Gateway
# ─────────────────────────────────────────────────────────────────────────────

def _get_proxy_panel_url():
    """Read the proxy panel URL from state files."""
    state_paths = [
        Path(os.environ.get("ProgramData", "C:/ProgramData")) / "ServerInstaller" / "proxy-state.json",
        Path("/opt/server-installer/proxy-state.json"),
        Path("/etc/server-installer/proxy-state.json"),
    ]
    for p in state_paths:
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                url = str(state.get("panel_url") or "").strip()
                if url:
                    return url
            except Exception:
                pass
    return ""


def proxy_list_users():
    """List proxy users through the panel API."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured. Install the proxy first."}
    result = _json_request(f"{panel_url}/api/users", timeout=10)
    if isinstance(result, list):
        return {"ok": True, "users": result}
    if isinstance(result, dict) and "error" not in result:
        return {"ok": True, "users": result.get("users", result)}
    return {"ok": False, "error": result.get("error", "Failed to list users")}


def proxy_add_user(username, password=None):
    """Add a proxy user."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    data = {"username": username}
    if password:
        data["password"] = password
    result = _json_request(f"{panel_url}/api/users", method="POST", data=data)
    return {"ok": "error" not in result, "message": result.get("message", str(result))}


def proxy_delete_user(username):
    """Remove a proxy user."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/users/{urllib.parse.quote(username)}", method="DELETE")
    return {"ok": "error" not in result, "message": result.get("message", "User deleted")}


def proxy_update_password(username, password):
    """Update a user's password."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(
        f"{panel_url}/api/users/{urllib.parse.quote(username)}/password",
        method="POST", data={"password": password},
    )
    return {"ok": "error" not in result, "message": result.get("message", "Password updated")}


def proxy_info():
    """Get proxy system info."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/system/info", timeout=10)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}


def proxy_status():
    """Get proxy service statuses."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/system/status", timeout=10)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "services": result}


def proxy_restart_service():
    """Restart the proxy service."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/service/restart", method="POST")
    return {"ok": "error" not in result, "message": result.get("message", "Service restarted")}


def proxy_switch_layer(layer):
    """Switch proxy layer."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/layer/switch", method="POST", data={"layer": layer})
    return {"ok": "error" not in result, "message": result.get("message", "Layer switched")}


def proxy_user_config(username):
    """Get user connection config."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "error": "Proxy panel URL not configured."}
    result = _json_request(f"{panel_url}/api/users/{urllib.parse.quote(username)}/config", timeout=10)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "config": result}


def proxy_health():
    """Health check for proxy panel."""
    panel_url = _get_proxy_panel_url()
    if not panel_url:
        return {"ok": False, "status": "not_installed"}
    try:
        req = urllib.request.Request(f"{panel_url}/api/system/info", method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
            return {"ok": True, "status": "healthy"}
    except Exception as e:
        return {"ok": False, "status": "unhealthy", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# SAM3 Gateway
# ─────────────────────────────────────────────────────────────────────────────

def _get_sam3_url():
    """Get SAM3 service URL from state files."""
    state_paths = [
        Path(os.environ.get("ProgramData", "C:/ProgramData")) / "ServerInstaller" / "sam3-state.json",
        Path("/opt/server-installer/sam3/state.json"),
        Path("/etc/server-installer/sam3-state.json"),
    ]
    for p in state_paths:
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                # Prefer HTTPS URL when available
                for key in ("https_url", "http_url"):
                    url = str(state.get(key) or "").strip()
                    if url:
                        return url
                host = str(state.get("host") or "127.0.0.1").strip()
                https_port = str(state.get("https_port") or "").strip()
                http_port = str(state.get("http_port") or "5000").strip()
                if https_port:
                    return f"https://{host}:{https_port}"
                if http_port:
                    return f"http://{host}:{http_port}"
            except Exception:
                pass
    return ""


def sam3_detect(image_data, prompt="", threshold=0.3, content_type="image/jpeg"):
    """Run object detection on an image."""
    sam3_url = _get_sam3_url()
    if not sam3_url:
        return {"ok": False, "error": "SAM3 is not installed or not running."}
    import io
    boundary = "----SAM3Boundary"
    body = io.BytesIO()

    def add_field(name, value):
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(f"{value}\r\n".encode())

    def add_file(name, filename, data, ct):
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        body.write(f"Content-Type: {ct}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")

    add_file("image", "image.jpg", image_data, content_type)
    if prompt:
        add_field("text_prompt", prompt)
    add_field("confidence", str(threshold))
    body.write(f"--{boundary}--\r\n".encode())

    data = body.getvalue()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    status, _, resp_body = _raw_request(f"{sam3_url}/detect", method="POST", data=data, headers=headers, timeout=60)
    try:
        result = json.loads(resp_body.decode("utf-8", errors="replace"))
        result["ok"] = status == 200
        return result
    except Exception:
        return {"ok": False, "error": f"SAM3 returned status {status}"}


def sam3_model_info():
    """Get SAM3 model info."""
    sam3_url = _get_sam3_url()
    if not sam3_url:
        return {"ok": False, "error": "SAM3 is not installed or not running."}
    result = _json_request(f"{sam3_url}/model-info", timeout=10)
    if "error" not in result:
        result["ok"] = True
    else:
        result["ok"] = False
    return result


def sam3_health():
    """Health check for SAM3."""
    sam3_url = _get_sam3_url()
    if not sam3_url:
        return {"ok": False, "status": "not_installed"}
    try:
        req = urllib.request.Request(sam3_url, method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
            return {"ok": True, "status": "healthy"}
    except Exception as e:
        return {"ok": False, "status": "unhealthy", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Ollama Gateway
# ─────────────────────────────────────────────────────────────────────────────

def _get_ollama_urls():
    """Get Ollama service URLs — returns (primary_url, internal_url).
    primary_url = user-facing URL (HTTPS web UI or HTTP)
    internal_url = direct Ollama API (http://127.0.0.1:11434) if available
    """
    internal = ""
    # Check environment variable first
    url = os.environ.get("OLLAMA_HOST", "").strip()
    if url:
        if not url.startswith("http"):
            url = f"http://{url}"
        return url, ""
    # Check state files
    state_paths = [
        Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Server-Installer" / "ollama" / "ollama-state.json",
        Path(os.path.expanduser("~")) / ".server-installer" / "ollama" / "ollama-state.json",
        Path("/opt/server-installer/ollama/ollama-state.json"),
    ]
    for p in state_paths:
        if p.exists():
            try:
                state = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                internal = str(state.get("ollama_internal") or "").strip()
                # Prefer HTTPS URL when available
                https_url = str(state.get("https_url") or "").strip()
                if https_url:
                    return https_url, internal
                for key in ("http_url", "url", "endpoint"):
                    val = str(state.get(key) or "").strip()
                    if val:
                        return val, internal
                host = str(state.get("host") or "").strip()
                https_port = str(state.get("https_port") or "").strip()
                http_port = str(state.get("http_port") or state.get("port") or "").strip()
                if https_port:
                    h = host if host and host not in ("0.0.0.0", "*") else "127.0.0.1"
                    return f"https://{h}:{https_port}", internal
                if http_port:
                    h = host if host and host not in ("0.0.0.0", "*") else "127.0.0.1"
                    return f"http://{h}:{http_port}", internal
            except Exception:
                pass
    return "http://127.0.0.1:11434", ""


def _get_ollama_url():
    """Get primary Ollama service URL."""
    url, _ = _get_ollama_urls()
    return url


def _ollama_api_request(api_path, method="GET", data=None, timeout=15):
    """Make Ollama API request, trying primary URL then internal URL with path fallbacks."""
    primary, internal = _get_ollama_urls()
    # Try primary URL with standard path
    result = _json_request(f"{primary}{api_path}", method=method, data=data, timeout=timeout)
    if "error" not in result:
        return result
    err = str(result.get("error", ""))
    # If 404, try web UI alternative paths (e.g. /api/pull -> /api/models/pull)
    if "404" in err:
        alt_map = {"/api/pull": "/api/models/pull", "/api/delete": "/api/models/delete",
                   "/api/show": "/api/models/info", "/api/copy": "/api/models/copy"}
        alt = alt_map.get(api_path)
        if alt:
            result2 = _json_request(f"{primary}{alt}", method=method, data=data, timeout=timeout)
            if "error" not in result2:
                return result2
    # If primary failed and we have an internal URL, try that
    if internal:
        result3 = _json_request(f"{internal}{api_path}", method=method, data=data, timeout=timeout)
        if "error" not in result3:
            return result3
    return result


def ollama_list_models():
    """List downloaded Ollama models."""
    url = _get_ollama_url()
    result = _json_request(f"{url}/api/tags", timeout=10)
    if "models" in result:
        return {"ok": True, "models": result["models"]}
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "models": []}


def ollama_pull_model(name, stream=False):
    """Pull/download a model."""
    result = _ollama_api_request("/api/pull", method="POST", data={"name": name, "stream": False}, timeout=300)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "status": result.get("status", "success")}


def ollama_delete_model(name):
    """Delete a model."""
    result = _ollama_api_request("/api/delete", method="DELETE", data={"name": name}, timeout=30)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "status": "deleted"}


def ollama_show_model(name):
    """Show model details."""
    result = _ollama_api_request("/api/show", method="POST", data={"name": name}, timeout=15)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}


def ollama_chat(model, messages, stream=False):
    """Chat with a model."""
    url = _get_ollama_url()
    result = _json_request(
        f"{url}/api/chat", method="POST",
        data={"model": model, "messages": messages, "stream": False},
        timeout=120,
    )
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}


def ollama_generate(model, prompt, stream=False):
    """Generate text completion."""
    url = _get_ollama_url()
    result = _json_request(
        f"{url}/api/generate", method="POST",
        data={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}


def ollama_embeddings(model, prompt):
    """Generate embeddings."""
    url = _get_ollama_url()
    result = _json_request(
        f"{url}/api/embeddings", method="POST",
        data={"model": model, "prompt": prompt},
        timeout=60,
    )
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}


def ollama_running_models():
    """List currently loaded models."""
    url = _get_ollama_url()
    result = _json_request(f"{url}/api/ps", timeout=10)
    if "models" in result:
        return {"ok": True, "models": result["models"]}
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "models": []}


def ollama_copy_model(source, destination):
    """Copy/alias a model."""
    result = _ollama_api_request("/api/copy", method="POST",
        data={"source": source, "destination": destination}, timeout=30)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "status": "copied"}


def ollama_create_model(name, modelfile):
    """Create a model from a Modelfile."""
    url = _get_ollama_url()
    result = _json_request(
        f"{url}/api/create", method="POST",
        data={"name": name, "modelfile": modelfile, "stream": False},
        timeout=300,
    )
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "status": result.get("status", "success")}


def ollama_health():
    """Health check for Ollama."""
    url = _get_ollama_url()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5, context=_internal_ssl_ctx if req.full_url.startswith("https://") else None) as resp:
            return {"ok": True, "status": "healthy"}
    except Exception as e:
        return {"ok": False, "status": "unhealthy", "error": str(e)}
