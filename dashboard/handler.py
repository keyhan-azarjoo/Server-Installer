import html
import io
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from file_manager import (
    file_manager_copy_path,
    file_manager_delete_path,
    file_manager_list,
    file_manager_make_directory,
    file_manager_read_file,
    file_manager_rename_path,
    file_manager_save_uploads,
    file_manager_write_file,
    normalize_file_manager_path as _normalize_file_manager_path,
)
try:
    from ssl_manager import (
        ssl_list_certs,
        ssl_delete_cert,
        ssl_cert_info,
        ssl_validate_pair,
        run_ssl_letsencrypt,
        run_ssl_renew_all,
        run_ssl_upload,
        run_ssl_assign,
    )
    _SSL_MANAGER_OK = True
except ImportError:
    _SSL_MANAGER_OK = False
    def ssl_list_certs(): return []
    def ssl_delete_cert(name): return 1, "ssl_manager module not available — run Dashboard Update to install it."
    def ssl_cert_info(cert_pem): return {}
    def ssl_validate_pair(cert_pem, key_pem): return False, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_letsencrypt(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_renew_all(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_upload(form, parts, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."
    def run_ssl_assign(form, live_cb=None): return 1, "ssl_manager module not available — run Dashboard Update."

from constants import (
    BUILD_ID,
    JOBS,
    JOBS_LOCK,
    ROOT,
    SESSIONS,
    SERVER_INSTALLER_DATA,
    _interactive_sessions,
    _interactive_sessions_lock,
)
from utils import _read_json_file, _write_json_file, command_exists, run_process
from cert_manager import (
    _read_installed_commit,
    _fetch_remote_commit_sha,
    run_dashboard_apply_cert,
)
from python_manager import (
    get_python_info,
    resolve_windows_python,
    _hide_detected_python,
)
from website_manager import (
    get_website_info,
    run_website_deploy,
    run_windows_website_iis,
    run_windows_website_service,
    run_unix_website_service,
    run_website_docker,
    run_windows_python_api_service,
    run_unix_python_api_service,
    run_python_api_docker,
    run_python_api_update_source,
    run_windows_python_api_iis,
    run_python_command,
    start_python_jupyter,
    stop_python_jupyter,
)
from system_info import (
    choose_service_host,
    get_docker_info,
    get_windows_s3_docker_support,
)
from port_manager import get_port_usage, manage_firewall_port
from mongo_manager import (
    get_windows_native_mongo_info,
    mongo_native_overview,
    mongo_native_collections,
    mongo_native_documents,
    mongo_native_run_script,
)
from service_manager import (
    get_service_items,
    get_system_status,
    filter_service_items,
    manage_service,
)
from installer_runners import (
    run_windows_installer,
    run_windows_setup_only,
    run_windows_docker_setup_only,
    run_linux_installer,
    run_windows_sam3_installer,
    run_unix_sam3_installer,
    run_sam3_download_model,
    run_sam3_docker,
    run_sam3_stop,
    run_sam3_start,
    run_sam3_delete,
    run_windows_s3_installer,
    run_windows_mongo_installer,
    run_unix_mongo_installer,
    run_mongo_docker,
    run_linux_proxy_installer,
    run_windows_proxy_installer,
    manage_proxy_service,
    run_linux_s3_installer,
    run_linux_s3_docker_installer,
    run_linux_s3_stop,
    run_dashboard_update,
    run_windows_s3_stop,
    run_linux_docker_setup,
    run_linux_docker_deploy,
)
from ai_services import (
    run_ollama_os_install,
    run_ollama_start,
    run_ollama_stop,
    run_ollama_delete,
    run_ollama_docker,
    run_lmstudio_os_install,
    run_lmstudio_start,
    run_lmstudio_stop,
    run_lmstudio_delete,
    run_lmstudio_docker,
    run_openclaw_os_install,
    run_openclaw_start,
    run_openclaw_stop,
    run_openclaw_delete,
    run_openclaw_docker,
    run_tgwui_os_install,
    run_tgwui_docker,
    run_tgwui_delete,
    run_comfyui_os_install,
    run_comfyui_docker,
    run_comfyui_delete,
    run_whisper_os_install,
    run_whisper_docker,
    run_whisper_delete,
    run_piper_os_install,
    run_piper_docker,
    run_piper_delete,
)
from system_admin import (
    is_windows_admin,
    run_system_power,
    save_uploaded_stream,
    save_uploaded_folder,
    save_uploaded_archive_or_file,
    upload_root_dir,
    validate_os_credentials,
    run_windows_interactive_powershell_file,
    get_active_windows_user,
)
from pages import (
    start_live_job,
    page_login,
    page_dashboard,
    page_output,
    page_mongo_native_ui,
)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def is_local_client(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except Exception:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def parse_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def get_mongo_native_credentials(self):
        username = (self.headers.get("X-Mongo-User", "") or "").strip()
        password = self.headers.get("X-Mongo-Password", "")
        return username, password

    def _handle_api_gateway_get(self):
        """Handle GET requests for the API gateway (S3, Mongo, Proxy, SAM3, Ollama)."""
        from api_gateway import (
            s3_list_buckets, s3_list_objects, s3_info, s3_health, s3_presign,
            mongo_list_databases, mongo_health,
            proxy_list_users, proxy_info, proxy_status, proxy_user_config, proxy_health,
            sam3_model_info, sam3_health,
            ollama_list_models, ollama_running_models, ollama_health,
            lmstudio_list_models, lmstudio_health,
        )
        path = self.path.split("?", 1)[0]
        query = {}
        if "?" in self.path:
            query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)

        # S3 routes
        if path == "/api/s3/buckets":
            return s3_list_buckets()
        if path == "/api/s3/objects":
            bucket = (query.get("bucket", [""])[0] or "").strip()
            prefix = (query.get("prefix", [""])[0] or "").strip()
            return s3_list_objects(bucket, prefix)
        if path == "/api/s3/info":
            return s3_info()
        if path == "/api/s3/health":
            return s3_health()

        # MongoDB routes
        if path == "/api/mongo/databases":
            username, password = self.get_mongo_native_credentials()
            return mongo_list_databases(username=username, password=password)
        if path == "/api/mongo/health":
            username, password = self.get_mongo_native_credentials()
            return mongo_health(username=username, password=password)

        # Proxy routes
        if path == "/api/proxy/users":
            return proxy_list_users()
        if path == "/api/proxy/info":
            return proxy_info()
        if path == "/api/proxy/status":
            return proxy_status()
        if path.startswith("/api/proxy/users/") and path.endswith("/config"):
            username = path[len("/api/proxy/users/"):-len("/config")]
            return proxy_user_config(unquote(username))
        if path == "/api/proxy/health":
            return proxy_health()

        # SAM3 routes
        if path == "/api/sam3/model-info":
            return sam3_model_info()
        if path == "/api/sam3/health":
            return sam3_health()

        # Ollama routes
        if path == "/api/ollama/tags" or path == "/api/ollama/models":
            return ollama_list_models()
        if path == "/api/ollama/ps":
            return ollama_running_models()
        if path == "/api/ollama/health":
            return ollama_health()

        # LM Studio routes
        if path == "/api/lmstudio/models":
            return lmstudio_list_models()
        if path == "/api/lmstudio/health":
            return lmstudio_health()

        return None  # Not handled

    def _handle_api_gateway_post(self):
        """Handle POST/PUT/DELETE requests for the API gateway."""
        from api_gateway import (
            s3_create_bucket, s3_delete_bucket, s3_delete_object, s3_presign,
            mongo_create_database, mongo_drop_database, mongo_create_collection,
            mongo_drop_collection, mongo_insert_documents, mongo_update_documents,
            mongo_delete_documents,
            proxy_add_user, proxy_delete_user, proxy_update_password,
            proxy_restart_service, proxy_switch_layer,
            sam3_detect,
            ollama_chat, ollama_generate, ollama_embeddings, ollama_pull_model,
            ollama_delete_model, ollama_show_model, ollama_copy_model, ollama_create_model,
            lmstudio_chat,
        )
        path = self.path.split("?", 1)[0]
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length) if length > 0 else b""

        def _json_body():
            """Parse JSON body or fall back to form data."""
            if "json" in ctype and raw_body:
                try:
                    return json.loads(raw_body.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            # Fall back to URL-encoded form parsing
            if raw_body and "form" in ctype:
                try:
                    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw_body.decode("utf-8", errors="replace"), keep_blank_values=True).items()}
                except Exception:
                    pass
            return {}

        # S3 routes
        if path == "/api/s3/buckets":
            body = _json_body()
            return s3_create_bucket(body.get("name", ""))
        if path.startswith("/api/s3/buckets/"):
            name = path[len("/api/s3/buckets/"):]
            return s3_delete_bucket(name)
        if path.startswith("/api/s3/objects/"):
            # DELETE /api/s3/objects/{bucket}/{key}
            rest = path[len("/api/s3/objects/"):]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                return s3_delete_object(parts[0], parts[1])
            return {"ok": False, "error": "Invalid path. Use /api/s3/objects/{bucket}/{key}"}
        if path == "/api/s3/presign":
            body = _json_body()
            return s3_presign(body.get("bucket", ""), body.get("key", ""), body.get("expires", 3600))

        # MongoDB routes
        if path == "/api/mongo/databases":
            body = _json_body()
            return mongo_create_database(body.get("name", ""))
        if path.startswith("/api/mongo/databases/"):
            name = path[len("/api/mongo/databases/"):]
            username, password = self.get_mongo_native_credentials()
            return mongo_drop_database(name, username=username, password=password)
        if path == "/api/mongo/collections":
            body = _json_body()
            username, password = self.get_mongo_native_credentials()
            return mongo_create_collection(body.get("db", ""), body.get("name", ""), username=username, password=password)
        if path.startswith("/api/mongo/collections/"):
            rest = path[len("/api/mongo/collections/"):]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                username, password = self.get_mongo_native_credentials()
                return mongo_drop_collection(parts[0], parts[1], username=username, password=password)
            return {"ok": False, "error": "Use /api/mongo/collections/{db}/{name}"}
        if path == "/api/mongo/documents":
            body = _json_body()
            username, password = self.get_mongo_native_credentials()
            db_name = body.get("db", "")
            col_name = body.get("collection", "")
            # Determine operation based on body content
            if "documents" in body:
                return mongo_insert_documents(db_name, col_name, body["documents"], username=username, password=password)
            if "update" in body:
                return mongo_update_documents(db_name, col_name, body.get("filter", {}), body["update"], username=username, password=password)
            if "filter" in body and "documents" not in body and "update" not in body:
                return mongo_delete_documents(db_name, col_name, body["filter"], username=username, password=password)
            return {"ok": False, "error": "Provide 'documents' to insert, 'update' to update, or 'filter' to delete."}

        # Proxy routes
        if path == "/api/proxy/users":
            body = _json_body()
            return proxy_add_user(body.get("username", ""), body.get("password"))
        if path.startswith("/api/proxy/users/") and path.endswith("/password"):
            username = path[len("/api/proxy/users/"):-len("/password")]
            body = _json_body()
            return proxy_update_password(unquote(username), body.get("password", ""))
        if path.startswith("/api/proxy/users/"):
            username = path[len("/api/proxy/users/"):]
            return proxy_delete_user(unquote(username))
        if path == "/api/proxy/service/restart":
            return proxy_restart_service()
        if path == "/api/proxy/layer/switch":
            body = _json_body()
            return proxy_switch_layer(body.get("layer", ""))

        # SAM3 routes
        if path == "/api/sam3/detect":
            try:
                parts = self._parse_multipart()
                image_data = b""
                prompt = ""
                threshold = 0.3
                content_type = "image/jpeg"
                for part in parts:
                    if part.get("name") == "image":
                        image_data = part.get("content", b"")
                        if part.get("filename", "").lower().endswith(".png"):
                            content_type = "image/png"
                    elif part.get("name") in ("prompt", "text_prompt"):
                        prompt = part.get("content", b"").decode("utf-8", errors="replace")
                    elif part.get("name") in ("threshold", "confidence"):
                        try:
                            threshold = float(part.get("content", b"0.3").decode())
                        except Exception:
                            pass
                if not image_data:
                    return {"ok": False, "error": "Image file is required."}
                return sam3_detect(image_data, prompt, threshold, content_type)
            except Exception as ex:
                return {"ok": False, "error": str(ex)}

        # Ollama routes
        if path == "/api/ollama/chat":
            body = _json_body()
            return ollama_chat(body.get("model", ""), body.get("messages", []))
        if path == "/api/ollama/generate":
            body = _json_body()
            return ollama_generate(body.get("model", ""), body.get("prompt", ""))
        if path == "/api/ollama/embeddings":
            body = _json_body()
            return ollama_embeddings(body.get("model", ""), body.get("prompt", ""))
        if path == "/api/ollama/pull":
            body = _json_body()
            return ollama_pull_model(body.get("name", ""))
        if path == "/api/ollama/pull/stream":
            from api_gateway import ollama_pull_model_stream
            body = _json_body()
            name = body.get("name", "")
            if not name:
                return {"ok": False, "error": "Model name required"}
            # Stream the response directly
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                for line in ollama_pull_model_stream(name):
                    self.wfile.write(("data: " + line + "\n").encode("utf-8"))
                    self.wfile.flush()
            except Exception as e:
                try:
                    self.wfile.write(("data: " + json.dumps({"error": str(e)}) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
            return "__streamed__"
        if path == "/api/ollama/delete":
            body = _json_body()
            return ollama_delete_model(body.get("name", ""))
        if path == "/api/ollama/show":
            body = _json_body()
            return ollama_show_model(body.get("name", ""))
        if path == "/api/ollama/copy":
            body = _json_body()
            return ollama_copy_model(body.get("source", ""), body.get("destination", ""))
        if path == "/api/ollama/create":
            body = _json_body()
            return ollama_create_model(body.get("name", ""), body.get("modelfile", ""))

        # LM Studio routes
        if path == "/api/lmstudio/chat":
            body = _json_body()
            return lmstudio_chat(body.get("model", ""), body.get("messages", []))

        return None  # Not handled

    def _parse_multipart(self):
        ctype = self.headers.get("Content-Type", "") or ""
        m = re.search(r'boundary="?([^";]+)"?', ctype, flags=re.IGNORECASE)
        if not m:
            raise RuntimeError("Missing multipart boundary.")
        boundary = m.group(1).encode("utf-8")
        length = int(self.headers.get("Content-Length", "0") or "0")
        data = self.rfile.read(length)
        marker = b"--" + boundary
        parts = []
        for chunk in data.split(marker):
            if not chunk or chunk in (b"--\r\n", b"--", b"\r\n"):
                continue
            if chunk.startswith(b"\r\n"):
                chunk = chunk[2:]
            if chunk.endswith(b"--\r\n"):
                chunk = chunk[:-4]
            elif chunk.endswith(b"\r\n"):
                chunk = chunk[:-2]

            header_blob, sep, body = chunk.partition(b"\r\n\r\n")
            if not sep:
                continue
            headers = {}
            for line in header_blob.decode("utf-8", errors="replace").split("\r\n"):
                k, _, v = line.partition(":")
                if _:
                    headers[k.strip().lower()] = v.strip()
            cd = headers.get("content-disposition", "")
            if not cd:
                continue
            name_m = re.search(r'name="([^"]+)"', cd)
            file_m = re.search(r'filename="([^"]*)"', cd)
            if not name_m:
                continue
            parts.append({
                "name": name_m.group(1),
                "filename": file_m.group(1) if file_m else "",
                "content": body,
            })
        return parts

    def parse_request_form(self):
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        if ctype.startswith("multipart/form-data"):
            try:
                parts = self._parse_multipart()
            except Exception as ex:
                raise RuntimeError(f"Failed to parse multipart upload: {ex}") from ex
            result = {}
            if not parts:
                return result
            grouped = {}
            for p in parts:
                grouped.setdefault(p["name"], []).append(p)

            for key, items in grouped.items():
                folder_items = []
                for it in items:
                    filename = it.get("filename", "")
                    content = it.get("content", b"")
                    if filename:
                        fake_item = type("UploadItem", (), {})()
                        fake_item.filename = filename
                        fake_item.file = io.BytesIO(content)
                        if key in ("SourceFolder", "SOURCE_FOLDER", "SourceUpload"):
                            folder_items.append(fake_item)
                        else:
                            saved = save_uploaded_archive_or_file(fake_item)
                            result.setdefault(key, []).append(saved)
                    else:
                        value = content.decode("utf-8", errors="replace").strip()
                        result.setdefault(key, []).append(value)

                if folder_items:
                    if key == "SourceUpload":
                        if len(folder_items) == 1 and ("/" not in (folder_items[0].filename or "").replace("\\", "/")):
                            saved_single = save_uploaded_archive_or_file(folder_items[0])
                            result.setdefault(key, []).append(saved_single)
                        else:
                            saved_folder = save_uploaded_folder(folder_items)
                            result.setdefault(key, []).append(saved_folder)
                    else:
                        saved_folder = save_uploaded_folder(folder_items)
                        result.setdefault(key, []).append(saved_folder)
            return result
        return self.parse_form()

    def parse_upload_source(self):
        ctype = (self.headers.get("Content-Type", "") or "").lower()
        if not ctype.startswith("multipart/form-data"):
            raise RuntimeError("Upload requires multipart/form-data.")

        parts = self._parse_multipart()
        if not parts:
            raise RuntimeError("Upload form is empty.")
        items = [p for p in parts if p.get("name") == "SourceUpload"]
        if not items:
            raise RuntimeError("No upload selected.")
        files = []
        for p in items:
            if p.get("filename"):
                fake_item = type("UploadItem", (), {})()
                fake_item.filename = p.get("filename", "")
                fake_item.file = io.BytesIO(p.get("content", b""))
                files.append(fake_item)

        valid_files = [it for it in files if getattr(it, "filename", None) and getattr(it, "file", None)]
        if not valid_files:
            raise RuntimeError("No upload selected.")

        looks_like_folder = (len(valid_files) > 1) or any(
            ("/" in (it.filename or "").replace("\\", "/")) for it in valid_files
        )
        if looks_like_folder:
            return save_uploaded_folder(valid_files)

        return save_uploaded_archive_or_file(valid_files[0])

    def set_cookie(self, sid):
        self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly")

    def clear_cookie(self):
        self.send_header("Set-Cookie", "sid=; Path=/; HttpOnly; Max-Age=0")

    def get_sid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sid="):
                return part[4:]
        return ""

    def get_session(self):
        sid = self.get_sid()
        session = SESSIONS.get(sid)
        return session if isinstance(session, dict) else {}

    def is_auth(self):
        sid = self.get_sid()
        return bool(sid and sid in SESSIONS)

    def write_html(self, content, status=HTTPStatus.OK, cookie_sid=None, clear_sid=False):
        data = content.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            if cookie_sid:
                self.set_cookie(cookie_sid)
            if clear_sid:
                self.clear_cookie()
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def write_json(self, payload, status=HTTPStatus.OK):
        import json
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def is_fetch(self):
        return self.headers.get("X-Requested-With", "").lower() == "fetch"

    def respond_run_result(self, title, code, output):
        if self.is_fetch():
            self.write_json({"title": title, "exit_code": code, "output": output})
        else:
            self.write_html(page_output(title, output, code))

    def _handle_ws_pty(self):
        """Handle /ws/pty WebSocket PTY upgrade in the threaded HTTP server."""
        import hashlib, base64, struct, threading
        from urllib.parse import urlparse, parse_qs as _pqs

        self.close_connection = True

        if (not self.is_local_client()) and (not self.is_auth()):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Dashboard"')
            self.end_headers()
            return

        parsed = urlparse(self.path)
        params = _pqs(parsed.query, keep_blank_values=True)
        cwd_val = (params.get("cwd", [""])[0] or "").strip() or None
        try:
            cols = max(10, min(512, int(params.get("cols", ["80"])[0] or 80)))
        except Exception:
            cols = 80
        try:
            rows = max(2, min(200, int(params.get("rows", ["24"])[0] or 24)))
        except Exception:
            rows = 24

        ws_key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(
            hashlib.sha1((ws_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()

        rfile = self.rfile
        wfile = self.wfile
        send_lock = threading.Lock()

        def _read_exact(n):
            if n == 0:
                return b""
            buf = b""
            while len(buf) < n:
                try:
                    chunk = rfile.read(n - len(buf))
                except Exception:
                    return None
                if not chunk:
                    return None
                buf += chunk
            return buf

        def ws_recv():
            try:
                h = _read_exact(2)
                if not h:
                    return None
                opcode = h[0] & 0x0F
                masked = bool(h[1] & 0x80)
                length = h[1] & 0x7F
                if length == 126:
                    e = _read_exact(2)
                    if not e:
                        return None
                    length = struct.unpack("!H", e)[0]
                elif length == 127:
                    e = _read_exact(8)
                    if not e:
                        return None
                    length = struct.unpack("!Q", e)[0]
                mask = _read_exact(4) if masked else b"\x00\x00\x00\x00"
                if mask is None:
                    return None
                raw = _read_exact(length)
                if raw is None:
                    return None
                payload = bytearray(raw)
                if masked:
                    for i in range(len(payload)):
                        payload[i] ^= mask[i % 4]
                return opcode, bytes(payload)
            except Exception:
                return None

        def ws_send(opcode, payload):
            if isinstance(payload, str):
                payload = payload.encode("utf-8", errors="replace")
            n = len(payload)
            hdr = bytearray([0x80 | opcode])
            if n < 126:
                hdr.append(n)
            elif n < 65536:
                hdr.append(126)
                hdr.extend(struct.pack("!H", n))
            else:
                hdr.append(127)
                hdr.extend(struct.pack("!Q", n))
            with send_lock:
                try:
                    wfile.write(bytes(hdr) + payload)
                    wfile.flush()
                    return True
                except Exception:
                    return False

        done = threading.Event()

        if os.name == "nt":
            try:
                import winpty as _winpty
            except ImportError:
                ws_send(0x1, "\r\nError: pywinpty not installed.\r\n")
                ws_send(0x8, b"")
                return
            shell = os.environ.get("COMSPEC", "cmd.exe")
            try:
                proc = _winpty.PtyProcess.spawn(shell, dimensions=(rows, cols), cwd=cwd_val)
            except Exception as ex:
                ws_send(0x1, f"\r\nFailed to start terminal: {ex}\r\n")
                ws_send(0x8, b"")
                return

            def _pty_read():
                try:
                    while not done.is_set():
                        try:
                            data = proc.read(4096)
                            if data:
                                ws_send(0x1, data)
                            elif not proc.isalive():
                                break
                        except EOFError:
                            break
                        except Exception:
                            break
                finally:
                    done.set()

            def _ws_read():
                nonlocal cols, rows
                try:
                    while not done.is_set():
                        frame = ws_recv()
                        if frame is None:
                            break
                        op, pl = frame
                        if op == 0x8:
                            break
                        if op == 0x9:
                            ws_send(0xA, pl)
                            continue
                        if op in (0x1, 0x2):
                            text = pl.decode("utf-8", errors="replace") if isinstance(pl, bytes) else pl
                            if text.startswith('{"type":"resize"'):
                                try:
                                    r = json.loads(text)
                                    proc.setwinsize(max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))))
                                except Exception:
                                    pass
                            else:
                                try:
                                    proc.write(text)
                                except Exception:
                                    break
                finally:
                    done.set()

            t1 = threading.Thread(target=_pty_read, daemon=True)
            t2 = threading.Thread(target=_ws_read, daemon=True)
            t1.start()
            t2.start()
            done.wait()
            try:
                proc.terminate()
            except Exception:
                pass
        else:
            try:
                import pty as _pty
                import termios as _termios
                import fcntl as _fcntl
            except ImportError as ex:
                ws_send(0x1, f"\r\nError: {ex}\r\n")
                ws_send(0x8, b"")
                return
            shell = os.environ.get("SHELL", "/bin/bash")
            master_fd = slave_fd = proc = None
            try:
                master_fd, slave_fd = _pty.openpty()
                try:
                    _fcntl.ioctl(slave_fd, _termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                except Exception:
                    pass
                env = {**os.environ, "TERM": "xterm-256color"}
                proc = subprocess.Popen(
                    [shell], stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                    cwd=cwd_val, env=env, close_fds=True, start_new_session=True,
                )
                os.close(slave_fd)
                slave_fd = None
            except Exception as ex:
                for fd in [slave_fd, master_fd]:
                    if fd is not None:
                        try:
                            os.close(fd)
                        except Exception:
                            pass
                ws_send(0x1, f"\r\nFailed to start terminal: {ex}\r\n")
                ws_send(0x8, b"")
                return

            def _pty_read():
                try:
                    while not done.is_set():
                        try:
                            data = os.read(master_fd, 4096)
                            if data:
                                ws_send(0x2, data)
                            else:
                                break
                        except (OSError, IOError):
                            break
                finally:
                    done.set()

            def _ws_read():
                nonlocal cols, rows
                try:
                    while not done.is_set():
                        frame = ws_recv()
                        if frame is None:
                            break
                        op, pl = frame
                        if op == 0x8:
                            break
                        if op == 0x9:
                            ws_send(0xA, pl)
                            continue
                        if op in (0x1, 0x2):
                            if pl.startswith(b'{"type":"resize"'):
                                try:
                                    r = json.loads(pl.decode("utf-8", errors="replace"))
                                    if r.get("type") == "resize":
                                        _fcntl.ioctl(master_fd, _termios.TIOCSWINSZ,
                                                     struct.pack("HHHH", max(2, int(r.get("rows", rows))), max(10, int(r.get("cols", cols))), 0, 0))
                                except Exception:
                                    pass
                            else:
                                try:
                                    os.write(master_fd, pl)
                                except Exception:
                                    break
                finally:
                    done.set()

            t1 = threading.Thread(target=_pty_read, daemon=True)
            t2 = threading.Thread(target=_ws_read, daemon=True)
            t1.start()
            t2.start()
            done.wait()
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                os.close(master_fd)
            except Exception:
                pass

    def do_GET(self):
        if self.path == "/ws/pty" or self.path.startswith("/ws/pty?"):
            conn_hdr = self.headers.get("Connection", "")
            upg_hdr = self.headers.get("Upgrade", "")
            if "upgrade" in conn_hdr.lower() and upg_hdr.lower() == "websocket":
                self._handle_ws_pty()
                return
        if self.path.startswith("/static/"):
            static_rel = self.path.split("?", 1)[0].replace("/static/", "", 1).lstrip("/")
            static_root = (ROOT / "dashboard").resolve()
            static_file = (static_root / static_rel).resolve()
            try:
                static_file.relative_to(static_root)
            except Exception:
                self.write_html("Invalid static path.", HTTPStatus.BAD_REQUEST)
                return
            if (not static_file.exists()) or (not static_file.is_file()):
                self.write_html("Static file not found.", HTTPStatus.NOT_FOUND)
                return
            data = static_file.read_bytes()
            ext = static_file.suffix.lower()
            if ext == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif ext == ".css":
                content_type = "text/css; charset=utf-8"
            elif ext == ".json":
                content_type = "application/json; charset=utf-8"
            else:
                content_type = "text/plain; charset=utf-8"
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return
            return
        if self.path == "/api/status":
            self.write_json({"ok": True}, HTTPStatus.OK)
            return
        if self.path.startswith("/run/openclaw_configure_output"):
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            session_id = (query.get("session_id", [""])[0] or "").strip()
            with _interactive_sessions_lock:
                sess = _interactive_sessions.get(session_id)
            if not sess:
                self.write_json({"ok": False, "error": "Invalid session_id"})
                return
            with sess["buf_lock"]:
                output = "".join(sess["buf"])
                sess["buf"].clear()
            done = sess["done"][0]
            # Clean up finished sessions
            if done:
                with _interactive_sessions_lock:
                    _interactive_sessions.pop(session_id, None)
            self.write_json({"ok": True, "output": output, "done": done})
            return
        if self.path == "/api/website/engines":
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                self.write_json({"ok": True, "engines": _detect_website_engines()}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/system/status"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                scope = (query.get("scope", ["all"])[0] or "all").strip().lower()
                payload = {"ok": True, "status": get_system_status(scope)}
                self.write_json(payload, HTTPStatus.OK)
            except Exception as ex:
                print(f"System status error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/system/services"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                scope = (query.get("scope", ["all"])[0] or "all").strip().lower()
                payload = {"ok": True, "services": filter_service_items(scope)}
                self.write_json(payload, HTTPStatus.OK)
            except Exception as ex:
                print(f"Service list error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/dashboard/version-check"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                installed_sha = _read_installed_commit()
                remote_sha = _fetch_remote_commit_sha(timeout=8)
                if not remote_sha:
                    # Network unavailable — can't determine; return null so button stays hidden
                    self.write_json({"ok": True, "update_available": None,
                                     "installed": installed_sha, "remote": ""}, HTTPStatus.OK)
                    return
                update_available = bool(not installed_sha or remote_sha != installed_sha)
                self.write_json({
                    "ok": True,
                    "update_available": update_available,
                    "installed": installed_sha[:12] if installed_sha else "",
                    "remote": remote_sha[:12],
                }, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/dashboard/cert"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                cfg_data = _dashboard_cert_config()
                mode = cfg_data.get("mode", "self-signed")
                name = cfg_data.get("name", "")
                # Determine which cert file is actually in use
                if mode == "managed" and name:
                    c, k = _get_managed_cert_paths(name)
                else:
                    c = str(DASHBOARD_SELFSIGNED_CERT) if DASHBOARD_SELFSIGNED_CERT.exists() else ""
                    k = str(DASHBOARD_SELFSIGNED_KEY) if DASHBOARD_SELFSIGNED_KEY.exists() else ""
                # Get cert info if available
                cert_info = {}
                if c and Path(c).exists():
                    try:
                        cert_info = ssl_cert_info(Path(c).read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass
                self.write_json({
                    "ok": True,
                    "mode": mode,
                    "name": name,
                    "cert_path": c,
                    "cert_info": cert_info,
                    "managed_certs": ssl_list_certs(),
                }, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/ssl/list"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                certs = ssl_list_certs()
                self.write_json({"ok": True, "certs": certs}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/files/list"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                payload = file_manager_list((query.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/files/download"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = {}
                if "?" in self.path:
                    query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                normalized = _normalize_file_manager_path((query.get("path", [""])[0] or "").strip())
                if not normalized:
                    raise RuntimeError("File path is required.")
                path = Path(normalized)
                if not path.exists() or not path.is_file():
                    raise RuntimeError("File not found.")
                data = path.read_bytes()
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
                self.end_headers()
                self.wfile.write(data)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/mongo/native-ui":
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
                return
            self.write_html(page_mongo_native_ui())
            return
        if self.path.startswith("/api/mongo/native/overview"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_overview(username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        if self.path.startswith("/api/mongo/native/collections"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            db_name = (query.get("db", [""])[0] or "").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_collections(db_name, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        if self.path.startswith("/api/mongo/native/documents"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            db_name = (query.get("db", [""])[0] or "").strip()
            collection_name = (query.get("collection", [""])[0] or "").strip()
            limit = (query.get("limit", ["50"])[0] or "50").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_documents(db_name, collection_name, limit, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok and isinstance(payload, dict):
                payload = {"ok": True, **payload}
            elif not ok and isinstance(payload, dict):
                payload = {"ok": False, **payload}
            else:
                payload = {"ok": ok, "result": payload}
            self.write_json(payload, status)
            return
        # ── API Gateway GET routes ────────────────────────────────────────────
        if self.path.startswith("/api/s3/") or self.path.startswith("/api/mongo/") or self.path.startswith("/api/proxy/") or self.path.startswith("/api/sam3/") or self.path.startswith("/api/ollama/") or self.path.startswith("/api/lmstudio/"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                result = self._handle_api_gateway_get()
                if result is not None:
                    status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                    self.write_json(result, status)
                    return
            except Exception as ex:
                print(f"API gateway GET error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        if self.path in ("/", "/login"):
            if self.is_local_client() or self.is_auth():
                self.write_html(page_dashboard())
            else:
                self.write_html(page_login())
            return
        if self.path == "/logout":
            sid = self.get_sid()
            if sid in SESSIONS:
                SESSIONS.pop(sid, None)
            self.write_html(page_login(), clear_sid=True)
            return
        if self.path.startswith("/job/"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            path_only = self.path.split("?", 1)[0]
            job_id = path_only.split("/job/", 1)[1]
            query = {}
            if "?" in self.path:
                query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
            try:
                offset = int((query.get("offset", ["0"])[0] or "0"))
            except ValueError:
                offset = 0
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    self.write_json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                    return
                full_output = job["output"]
                if offset < 0:
                    offset = 0
                output_chunk = full_output[offset:]
                payload = {
                    "job_id": job_id,
                    "title": job["title"],
                    "output": output_chunk,
                    "next_offset": len(full_output),
                    "done": job["done"],
                    "exit_code": job["exit_code"],
                }
            self.write_json(payload)
            return
        self.write_html("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/login":
            form = self.parse_form()
            user = (form.get("username", [""])[0] or "").strip()
            password = (form.get("password", [""])[0] or "").strip()
            ok, error = validate_os_credentials(user, password)
            if ok:
                sid = secrets.token_hex(16)
                SESSIONS[sid] = {"username": user, "password": password}
                self.write_html(page_dashboard(), cookie_sid=sid)
            else:
                self.write_html(page_login(error), HTTPStatus.UNAUTHORIZED)
            return

        if (not self.is_local_client()) and (not self.is_auth()):
            self.write_html("Unauthorized", HTTPStatus.UNAUTHORIZED)
            return

        if self.path == "/upload/source":
            try:
                saved_path = self.parse_upload_source()
            except Exception as ex:
                print(f"Upload error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
                return
            self.write_json({"ok": True, "path": saved_path})
            return

        if self.path == "/api/system/port":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            port = (form.get("port", [""])[0] or "").strip()
            protocol = (form.get("protocol", ["tcp"])[0] or "tcp").strip()
            ok, message = manage_firewall_port(action, port, protocol)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/system/port_check":
            form = self.parse_request_form()
            port = (form.get("port", [""])[0] or "").strip()
            protocol = (form.get("protocol", ["tcp"])[0] or "tcp").strip()
            result = get_port_usage(port, protocol)
            status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
            self.write_json(result, status)
            return
        if self.path == "/api/system/service":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            name = (form.get("name", [""])[0] or "").strip()
            kind = (form.get("kind", ["service"])[0] or "service").strip()
            detail = (form.get("detail", [""])[0] or "").strip()
            ports_json = (form.get("ports", [""])[0] or "").strip()
            # Collect ports to close BEFORE deletion (service may disappear after)
            ports_to_close = {}
            if action == "delete":
                try:
                    if ports_json:
                        for p in json.loads(ports_json):
                            port = p.get("port")
                            proto = str(p.get("protocol", "tcp") or "tcp").strip().lower()
                            if port and str(port).isdigit():
                                ports_to_close[(int(port), proto)] = True
                except Exception:
                    pass
                for p in _lookup_service_ports(name, kind):
                    port = p.get("port")
                    proto = str(p.get("protocol", "tcp") or "tcp").strip().lower()
                    if port and str(port).isdigit():
                        ports_to_close[(int(port), proto)] = True
            ok, message = manage_service(action, name, kind, detail)
            if ok and action == "delete":
                for (port, proto) in ports_to_close:
                    manage_firewall_port("close", str(port), proto)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/proxy/service":
            form = self.parse_request_form()
            action = (form.get("action", [""])[0] or "").strip()
            name = (form.get("name", [""])[0] or "").strip()
            ok, message = manage_proxy_service(action, name)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": message}, status)
            return
        if self.path == "/api/files/read":
            form = self.parse_request_form()
            try:
                payload = file_manager_read_file((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/files/info"):
            if (not self.is_local_client()) and (not self.is_auth()):
                self.write_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                # Support both POST form data and GET query params
                info_form = self.parse_request_form()
                path_str = (info_form.get("path", [""])[0] or "").strip() if info_form else ""
                if not path_str:
                    query = {}
                    if "?" in self.path:
                        query = parse_qs(self.path.split("?", 1)[1], keep_blank_values=True)
                    path_str = (query.get("path", [""])[0] or "").strip()
                if not path_str:
                    self.write_json({"ok": False, "error": "path is required"}, HTTPStatus.BAD_REQUEST)
                    return
                p = Path(path_str)
                if not p.exists():
                    self.write_json({"ok": False, "error": f"Path does not exist: {path_str}"}, HTTPStatus.NOT_FOUND)
                    return
                st = p.stat()
                is_dir = p.is_dir()
                # For directories count items (non-recursive) and compute recursive size
                item_count = None
                dir_size_bytes = None
                if is_dir:
                    try:
                        items = list(p.iterdir())
                        item_count = len(items)
                    except (PermissionError, OSError):
                        item_count = None
                    try:
                        dir_size_bytes = sum(
                            f.stat().st_size for f in p.rglob("*") if f.is_file()
                        )
                    except (PermissionError, OSError):
                        dir_size_bytes = None
                # Permissions string (rwxrwxrwx style)
                try:
                    import stat as _stat
                    mode = st.st_mode
                    perm_str = _stat.filemode(mode)
                except Exception:
                    perm_str = ""
                # Created time: Windows = st_ctime, Unix = birthtime if available else st_ctime
                created = None
                try:
                    created = int(st.st_birthtime)
                except AttributeError:
                    created = int(st.st_ctime)
                result = {
                    "ok": True,
                    "path": str(p),
                    "name": p.name,
                    "type": "folder" if is_dir else "file",
                    "size_bytes": st.st_size if not is_dir else (dir_size_bytes or 0),
                    "modified": int(st.st_mtime),
                    "created": created,
                    "permissions": perm_str,
                }
                if is_dir:
                    result["item_count"] = item_count
                    result["dir_size_bytes"] = dir_size_bytes
                else:
                    result["extension"] = p.suffix.lstrip(".")
                self.write_json(result, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path == "/api/files/write":
            form = self.parse_request_form()
            try:
                payload = file_manager_write_file(
                    (form.get("path", [""])[0] or "").strip(),
                    form.get("content", [""])[0] or "",
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/mkdir":
            form = self.parse_request_form()
            try:
                payload = file_manager_make_directory((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/delete":
            form = self.parse_request_form()
            try:
                payload = file_manager_delete_path((form.get("path", [""])[0] or "").strip())
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/rename":
            form = self.parse_request_form()
            try:
                payload = file_manager_rename_path(
                    (form.get("source", [""])[0] or "").strip(),
                    (form.get("target", [""])[0] or "").strip(),
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/copy":
            form = self.parse_request_form()
            try:
                payload = file_manager_copy_path(
                    (form.get("source", [""])[0] or "").strip(),
                    (form.get("target_dir", [""])[0] or "").strip(),
                )
                self.write_json({"ok": True, **payload}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/files/upload":
            try:
                parts = self._parse_multipart()
                target_dir = ""
                upload_parts = []
                for part in parts:
                    if part.get("name") == "target":
                        target_dir = part.get("content", b"").decode("utf-8", errors="replace").strip()
                    elif part.get("name") == "files":
                        upload_parts.append(part)
                written = file_manager_save_uploads(upload_parts, target_dir)
                self.write_json({"ok": True, "written": written}, HTTPStatus.OK)
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/mongo/native/command":
            form = self.parse_request_form()
            db_name = (form.get("db", ["admin"])[0] or "admin").strip()
            script_text = (form.get("script", [""])[0] or "").strip()
            username, password = self.get_mongo_native_credentials()
            ok, payload = mongo_native_run_script(db_name, script_text, username=username, password=password)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            if ok:
                self.write_json({"ok": True, "result": payload}, status)
            else:
                if not isinstance(payload, dict):
                    payload = {"error": str(payload)}
                self.write_json({"ok": False, **payload}, status)
            return
        # ── API Gateway POST routes ───────────────────────────────────────────
        if self.path.startswith("/api/s3/") or self.path.startswith("/api/mongo/") or self.path.startswith("/api/proxy/") or self.path.startswith("/api/sam3/") or self.path.startswith("/api/ollama/") or self.path.startswith("/api/lmstudio/"):
            try:
                result = self._handle_api_gateway_post()
                if result == "__streamed__":
                    return  # Already streamed directly
                if result is not None:
                    status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
                    self.write_json(result, status)
                    return
            except Exception as ex:
                print(f"API gateway POST error: {ex}")
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return

        try:
            form = self.parse_request_form()
        except Exception as ex:
            print(f"Form parse error: {ex}")
            traceback.print_exc()
            if self.is_fetch():
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.BAD_REQUEST)
            else:
                self.write_html(f"Invalid request: {html.escape(str(ex))}", HTTPStatus.BAD_REQUEST)
            return

        session = self.get_session()
        if session:
            session_user = str(session.get("username") or "").strip()
            session_password = str(session.get("password") or "")
            if session_user and "SYSTEM_USERNAME" not in form:
                form["SYSTEM_USERNAME"] = [session_user]
            if session_password and "SYSTEM_PASSWORD" not in form:
                form["SYSTEM_PASSWORD"] = [session_password]

        if self.path == "/run/s3_windows":
            title = "S3 Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_windows":
            title = "MongoDB Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_mongo_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_mongo_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_unix":
            title = "MongoDB Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_unix_mongo_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_unix_mongo_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/mongo_docker":
            title = "MongoDB Docker Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_mongo_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_mongo_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/proxy_windows":
            form["SERVER_INSTALLER_DASHBOARD_PORT"] = [str(getattr(self.server, "server_port", ""))]
            title = "Proxy Installer (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_proxy_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_proxy_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/proxy_linux":
            form["SERVER_INSTALLER_DASHBOARD_PORT"] = [str(getattr(self.server, "server_port", ""))]
            title = "Proxy Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_proxy_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_proxy_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_install":
            title = f"Python Installer ({'Windows' if os.name == 'nt' else 'Linux/macOS'})"
            if self.is_fetch():
                runner = (lambda cb: run_windows_python_installer(form, live_cb=cb)) if os.name == "nt" else (lambda cb: run_unix_python_installer(form, live_cb=cb))
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                if os.name == "nt":
                    code, output = run_windows_python_installer(form)
                else:
                    code, output = run_unix_python_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_command":
            title = "Python CMD"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_command(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_command(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_service":
            title = "Python API OS Service"
            runner = (lambda cb: run_windows_python_api_service(form, live_cb=cb)) if os.name == "nt" else (lambda cb: run_unix_python_api_service(form, live_cb=cb))
            if self.is_fetch():
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = runner(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_docker":
            title = "Python API Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_api_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_api_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_update_source":
            title = "Update API Files"
            service_name = (form.get("service_name", [""])[0] or "").strip()
            source_path = (form.get("source_path", [""])[0] or "").strip()
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_python_api_update_source(service_name, source_path, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_python_api_update_source(service_name, source_path)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_api_iis":
            title = "Python API IIS"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_python_api_iis(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_python_api_iis(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_iis":
            title = "Website IIS"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_website_iis(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_website_iis(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_engine_install":
            engine_id = (form.get("ENGINE_ID", [""])[0] or "").strip().lower()
            if not engine_id:
                self.write_json({"ok": False, "error": "ENGINE_ID is required."}, HTTPStatus.BAD_REQUEST)
                return
            title = f"Install {engine_id}"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: _install_website_engine(engine_id, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = _install_website_engine(engine_id)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/website_deploy":
            target = (form.get("WEBSITE_TARGET", ["service"])[0] or "service").strip().lower()
            engine = (form.get("WEBSITE_ENGINE", [""])[0] or "").strip().lower()
            engine_label_map = {"docker": "Docker", "iis": "IIS", "nginx": "Nginx", "nodejs": "Node.js", "kubernetes": "Kubernetes", "pm2": "PM2", "service": "OS Service"}
            title = f"Website Deploy → {engine_label_map.get(engine or target, target)}"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_website_deploy(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_website_deploy(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_jupyter_start":
            title = "Start Jupyter"
            starter = lambda cb: start_python_jupyter(
                host=(form.get("PYTHON_HOST_IP", [""])[0] or "").strip(),
                port=(form.get("PYTHON_JUPYTER_PORT", ["8888"])[0] or "8888").strip(),
                notebook_dir=(form.get("PYTHON_NOTEBOOK_DIR", [""])[0] or "").strip(),
                auth_username=(form.get("SYSTEM_USERNAME", [""])[0] or "").strip(),
                auth_password=(form.get("SYSTEM_PASSWORD", [""])[0] or ""),
                live_cb=cb,
            )
            if self.is_fetch():
                job_id = start_live_job(title, starter)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = starter(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/python_jupyter_stop":
            title = "Stop Jupyter"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: stop_python_jupyter(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = stop_python_jupyter()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_stop":
            title = "S3 Stop (Windows)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_iis":
            title = "S3 Installer (Windows IIS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb, mode="iis"))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form, mode="iis")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_windows_docker":
            title = "S3 Installer (Windows Docker)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_s3_installer(form, live_cb=cb, mode="docker"))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_s3_installer(form, mode="docker")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_linux":
            selected_mode = (form.get("LOCALS3_MODE", ["os"])[0] or "os").strip().lower()
            if selected_mode == "docker":
                title = "Install S3 (Linux Docker)"
                runner = lambda cb, f=form: run_linux_s3_docker_installer(f, live_cb=cb)
            else:
                title = "S3 Installer (Linux/macOS)"
                runner = lambda cb, f=form: run_linux_s3_installer(f, live_cb=cb)
            if self.is_fetch():
                job_id = start_live_job(title, runner)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = runner(None)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/s3_linux_stop":
            title = "S3 Stop (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_s3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_s3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/sam3_windows", "/run/sam3_windows_os", "/run/sam3_windows_iis"):
            mode = "iis" if self.path == "/run/sam3_windows_iis" else "os"
            form["SAM3_DEPLOY_MODE"] = [mode]
            title = f"SAM3 Installer (Windows {mode.upper()})"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_sam3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_sam3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/sam3_linux", "/run/sam3_linux_os"):
            form["SAM3_DEPLOY_MODE"] = ["os"]
            title = "SAM3 Installer (Linux/macOS)"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_unix_sam3_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_unix_sam3_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_download_model":
            title = "SAM3 Model Download"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_download_model(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_download_model(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_docker":
            title = "SAM3 Docker Deploy"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_stop":
            title = "SAM3 Stop"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_stop(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_stop()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_start":
            title = "SAM3 Start"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_start(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_start()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/sam3_delete":
            title = "SAM3 Delete"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_sam3_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_sam3_delete()
                self.respond_run_result(title, code, output)
            return
        # ── Ollama routes ─────────────────────────────────────────────────────
        if self.path in ("/run/ollama_windows_os", "/run/ollama_unix_os", "/run/ollama_windows_iis"):
            title = "Ollama Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ollama_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ollama_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ollama_docker":
            title = "Ollama Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ollama_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ollama_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ollama_pull_model":
            model_name = (form.get("OLLAMA_MODEL_NAME", [""])[0] or "").strip()
            title = "Ollama Pull: " + (model_name or "model")
            def _pull_model(cb):
                output = []
                def log(m):
                    output.append(m)
                    if cb: cb(m + "\n")
                log("=== Pulling Ollama model: " + model_name + " ===")
                # First check if ollama is running
                ollama_bin = shutil.which("ollama")
                if not ollama_bin:
                    log("ERROR: Ollama is not installed. Install it first using the Install card above.")
                    return 1, "\n".join(output)
                # Try to start Ollama if not running
                try:
                    import urllib.request
                    urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
                    log("Ollama server is running.")
                except Exception:
                    log("Ollama server not responding. Trying to start it...")
                    if os.name == "nt":
                        subprocess.Popen([ollama_bin, "serve"], creationflags=0x00000008)
                    else:
                        subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import time
                    for i in range(15):
                        time.sleep(2)
                        try:
                            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
                            log("Ollama server started.")
                            break
                        except Exception:
                            log("Waiting for Ollama to start... (" + str(i+1) + "/15)")
                    else:
                        log("ERROR: Could not start Ollama server. Please start it manually.")
                        return 1, "\n".join(output)
                # Pull the model using ollama CLI (shows progress)
                log("Downloading model: " + model_name)
                code = _run_install_cmd([ollama_bin, "pull", model_name], log, timeout=1800)
                if code == 0:
                    log("\nModel '" + model_name + "' pulled successfully!")
                else:
                    log("\nFailed to pull model '" + model_name + "'")
                return code, "\n".join(output)
            if self.is_fetch():
                job_id = start_live_job(title, _pull_model)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = _pull_model(None)
                self.respond_run_result(title, code, output)
            return
        # ── OpenClaw routes ───────────────────────────────────────────────────
        # ── Delete / Uninstall routes ────────────────────────────────────────
        if self.path == "/run/ollama_delete":
            title = "Uninstall Ollama"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ollama_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ollama_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/lmstudio_delete":
            title = "Uninstall LM Studio"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_lmstudio_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_lmstudio_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/openclaw_set_tokens":
            title = "OpenClaw: Set API Tokens"
            def _set_tokens(cb):
                output = []
                def log(m):
                    output.append(m)
                    if cb: cb(m + "\n")
                ollama_key = (form.get("OLLAMA_API_KEY", [""])[0] or "").strip()
                lmstudio_key = (form.get("LMSTUDIO_API_KEY", [""])[0] or "").strip()
                openai_key = (form.get("OPENAI_API_KEY", [""])[0] or "").strip()
                anthropic_key = (form.get("ANTHROPIC_API_KEY", [""])[0] or "").strip()
                container = "serverinstaller-openclaw"
                log("=== Setting API tokens in OpenClaw container ===")
                # Build env lines and .env content
                env_lines = []
                if ollama_key:
                    env_lines.append(f"OLLAMA_API_KEY={ollama_key}")
                    log(f"Ollama API Key: {ollama_key[:4]}{'*' * max(0, len(ollama_key)-4)}")
                if lmstudio_key:
                    env_lines.append(f"LMSTUDIO_API_KEY={lmstudio_key}")
                    log(f"LM Studio API Key: {lmstudio_key[:4]}{'*' * max(0, len(lmstudio_key)-4)}")
                if openai_key:
                    env_lines.append(f"OPENAI_API_KEY={openai_key}")
                    log(f"OpenAI API Key: {openai_key[:6]}{'*' * 8}")
                if anthropic_key:
                    env_lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
                    log(f"Anthropic API Key: {anthropic_key[:8]}{'*' * 8}")
                if not env_lines:
                    log("No tokens provided.")
                    return 1, "\n".join(output)
                env_content = "\\n".join(env_lines)
                # Write .env files inside the container
                cmds = [
                    f"printf '{env_content}\\n' > /root/.openclaw/.env",
                    f"printf '{env_content}\\n' > /root/.env",
                    f"printf '{env_content}\\n' >> /etc/environment",
                ]
                # Write auth-profiles.json with versioned format
                profiles = {}
                if ollama_key:
                    profiles['"ollama:local"'] = f'{{"type":"api_key","provider":"ollama","key":"{ollama_key}"}}'
                if lmstudio_key:
                    profiles['"lmstudio:local"'] = f'{{"type":"api_key","provider":"lmstudio","key":"{lmstudio_key}"}}'
                if openai_key:
                    profiles['"openai:default"'] = f'{{"type":"api_key","provider":"openai","key":"{openai_key}"}}'
                if anthropic_key:
                    profiles['"anthropic:default"'] = f'{{"type":"api_key","provider":"anthropic","key":"{anthropic_key}"}}'
                profiles_json = ",".join(f"{k}:{v}" for k, v in profiles.items())
                last_good_parts = []
                if ollama_key:
                    last_good_parts.append('"ollama":"ollama:local"')
                if lmstudio_key:
                    last_good_parts.append('"lmstudio":"lmstudio:local"')
                if openai_key:
                    last_good_parts.append('"openai":"openai:default"')
                if anthropic_key:
                    last_good_parts.append('"anthropic":"anthropic:default"')
                last_good_json = ",".join(last_good_parts)
                auth_json = f'{{"version":1,"profiles":{{{profiles_json}}},"lastGood":{{{last_good_json}}}}}'
                cmds.append(f"mkdir -p /root/.openclaw/agents/main/agent")
                cmds.append(f"echo '{auth_json}' > /root/.openclaw/agents/main/agent/auth-profiles.json")
                # Ask the running gateway to reload using the container's normal startup flow.
                cmds.append("kill -USR1 $(pgrep -f 'openclaw gateway' | head -1) 2>/dev/null || true")
                full_cmd = " && ".join(cmds)
                log("Executing in container...")
                code = _run_install_cmd(["docker", "exec", container, "bash", "-c", full_cmd], log, timeout=30)
                if code == 0:
                    log("\nTokens saved! Gateway reloading with updated API keys.")
                    log("Wait a few seconds, then refresh the OpenClaw dashboard.")
                else:
                    log("\nFailed to set tokens. Is the OpenClaw container running?")
                return code, "\n".join(output)
            if self.is_fetch():
                job_id = start_live_job(title, _set_tokens)
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = _set_tokens(None)
                self.respond_run_result(title, code, output)
            return
        # ── OpenClaw interactive configure terminal ─────────────────────────
        if self.path == "/run/openclaw_configure_start":
            import uuid
            session_id = uuid.uuid4().hex
            try:
                proc = subprocess.Popen(
                    ["docker", "exec", "-i", "serverinstaller-openclaw", "openclaw", "configure"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)})
                return
            buf = []
            buf_lock = threading.Lock()
            done_flag = [False]
            def _reader():
                try:
                    while True:
                        chunk = proc.stdout.read(1)
                        if not chunk:
                            break
                        with buf_lock:
                            buf.append(chunk.decode("utf-8", errors="replace"))
                except Exception:
                    pass
                finally:
                    done_flag[0] = True
            t = threading.Thread(target=_reader, daemon=True)
            t.start()
            with _interactive_sessions_lock:
                _interactive_sessions[session_id] = {
                    "proc": proc,
                    "buf": buf,
                    "buf_lock": buf_lock,
                    "done": done_flag,
                }
            self.write_json({"ok": True, "session_id": session_id})
            return
        if self.path == "/run/openclaw_configure_input":
            session_id = (form.get("session_id", [""])[0] or "").strip()
            user_input = form.get("input", [""])[0] or ""
            with _interactive_sessions_lock:
                sess = _interactive_sessions.get(session_id)
            if not sess:
                self.write_json({"ok": False, "error": "Invalid session_id"})
                return
            try:
                sess["proc"].stdin.write((user_input + "\n").encode("utf-8"))
                sess["proc"].stdin.flush()
            except Exception as ex:
                self.write_json({"ok": False, "error": str(ex)})
                return
            self.write_json({"ok": True})
            return
        if self.path == "/run/openclaw_delete":
            title = "Uninstall OpenClaw"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_openclaw_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_openclaw_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/tgwui_delete":
            title = "Uninstall Text Generation WebUI"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_tgwui_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_tgwui_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/comfyui_delete":
            title = "Uninstall ComfyUI"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_comfyui_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_comfyui_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/whisper_delete":
            title = "Uninstall Whisper STT"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_whisper_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_whisper_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/piper_delete":
            title = "Uninstall Piper TTS"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_piper_delete(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_piper_delete()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/openclaw_docker":
            title = "OpenClaw Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_openclaw_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_openclaw_docker(form)
                self.respond_run_result(title, code, output)
            return
        if self.path in ("/run/openclaw_windows_os", "/run/openclaw_unix_os"):
            title = "OpenClaw Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_openclaw_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_openclaw_os_install(form)
                self.respond_run_result(title, code, output)
            return
        # ── LM Studio routes ──────────────────────────────────────────────────
        if self.path in ("/run/lmstudio_windows_os", "/run/lmstudio_unix_os"):
            title = "LM Studio Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_lmstudio_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_lmstudio_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/lmstudio_docker":
            title = "LM Studio Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_lmstudio_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_lmstudio_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Text Generation WebUI routes ──────────────────────────────────────
        if self.path in ("/run/tgwui_windows_os", "/run/tgwui_unix_os"):
            title = "Text Gen WebUI Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_tgwui_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_tgwui_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/tgwui_docker":
            title = "Text Gen WebUI Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_tgwui_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_tgwui_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── ComfyUI routes ────────────────────────────────────────────────────
        if self.path in ("/run/comfyui_windows_os", "/run/comfyui_unix_os", "/run/comfyui_windows_iis"):
            title = "ComfyUI Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_comfyui_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_comfyui_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/comfyui_docker":
            title = "ComfyUI Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_comfyui_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_comfyui_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Whisper routes ────────────────────────────────────────────────────
        if self.path in ("/run/whisper_windows_os", "/run/whisper_unix_os", "/run/whisper_windows_iis"):
            title = "Whisper STT Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_whisper_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_whisper_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/whisper_docker":
            title = "Whisper Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_whisper_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_whisper_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Piper TTS routes ──────────────────────────────────────────────────
        if self.path in ("/run/piper_windows_os", "/run/piper_unix_os", "/run/piper_windows_iis"):
            title = "Piper TTS Install"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_piper_os_install(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_piper_os_install(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/piper_docker":
            title = "Piper TTS Docker"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_piper_docker(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_piper_docker(form)
                self.respond_run_result(title, code, output)
            return
        # ── Generic AI service install routes ─────────────────────────────────
        _ai_generic_map = {
            "vllm": ("vLLM", "vllm/vllm-openai:latest", "8000", "pip install vllm"),
            "llamacpp": ("llama.cpp", "ghcr.io/ggerganov/llama.cpp:server", "8080", "git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && make -j"),
            "deepseek": ("DeepSeek", "ollama/ollama:latest", "11434", "ollama pull deepseek-coder-v2:lite"),
            "localai": ("LocalAI", "localai/localai:latest-aio-cpu", "8080", ""),
            "sdwebui": ("SD WebUI", "universonic/stable-diffusion-webui:latest", "7860", "git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui"),
            "fooocus": ("Fooocus", "ashleykza/fooocus:latest", "7865", "git clone https://github.com/lllyasviel/Fooocus"),
            "coqui": ("Coqui TTS", "ghcr.io/coqui-ai/tts:latest", "5002", "pip install coqui-tts"),
            "bark": ("Bark", "", "5005", "pip install git+https://github.com/suno-ai/bark.git"),
            "rvc": ("RVC", "alexta69/rvc-webui:latest", "7897", "git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI"),
            "openwebui": ("Open WebUI", "ghcr.io/open-webui/open-webui:main", "3000", "pip install open-webui"),
            "chromadb": ("ChromaDB", "chromadb/chroma:latest", "8000", "pip install chromadb"),
            "custom": ("Custom Model", "", "8080", ""),
            # OS Agents
            "openclaw": ("OpenClaw", "openclaw/openclaw:latest", "8080", "pip install openclaw"),
            "openinterpreter": ("Open Interpreter", "openinterpreter/open-interpreter:latest", "8080", "pip install open-interpreter"),
            "openhands": ("OpenHands", "ghcr.io/all-hands-ai/openhands:latest", "3000", ""),
            "autogpt": ("AutoGPT", "", "8000", "pip install autogpt-forge"),
            "crewai": ("CrewAI", "", "8080", "pip install crewai crewai-tools"),
            "metagpt": ("MetaGPT", "", "8080", "pip install metagpt"),
            "langchain": ("LangChain", "", "8000", "pip install langchain langchain-community langserve uvicorn"),
            "langgraph": ("LangGraph", "", "8123", "pip install langgraph langgraph-cli"),
            "llamaindex": ("LlamaIndex", "", "8000", "pip install llama-index"),
            "haystack": ("Haystack", "", "8000", "pip install haystack-ai"),
            "dify": ("Dify", "langgenius/dify-api:latest", "3000", ""),
            "flowise": ("Flowise", "flowiseai/flowise:latest", "3000", "npx flowise start"),
            "n8n": ("n8n", "n8nio/n8n:latest", "5678", "npx n8n start"),
            "activepieces": ("Activepieces", "activepieces/activepieces:latest", "8080", ""),
        }
        for _ai_key, (_ai_name, _ai_image, _ai_port, _ai_pip) in _ai_generic_map.items():
            if self.path in (f"/run/{_ai_key}_windows_os", f"/run/{_ai_key}_unix_os"):
                title = f"{_ai_name} Install"
                def _make_installer(_name, _pip, _port, _key, _form):
                    def _fn(cb):
                        output = []
                        def log(m):
                            output.append(m)
                            if cb: cb(m + "\n")
                        log(f"=== Installing {_name} ===")
                        host_ip = (_form.get(f"{_key.upper()}_HOST_IP", ["0.0.0.0"])[0] or "0.0.0.0").strip()
                        port = (_form.get(f"{_key.upper()}_HTTP_PORT", [_port])[0] or _port).strip()
                        if _pip:
                            code = _run_install_cmd(_pip, log, timeout=600)
                        else:
                            log(f"No automated OS installer for {_name}. Use Docker instead.")
                            code = 1
                        if code == 0:
                            sdir = SERVER_INSTALLER_DATA / _key
                            sdir.mkdir(parents=True, exist_ok=True)
                            app_dir = sdir / "app"
                            app_dir.mkdir(parents=True, exist_ok=True)
                            display_host = host_ip if host_ip not in ("0.0.0.0", "*", "") else choose_service_host()
                            # Create a web wrapper so the service has an accessible URL
                            wrapper = app_dir / "server.py"
                            wrapper.write_text(
                                f'#!/usr/bin/env python3\n'
                                f'"""Auto-generated web wrapper for {_name}."""\n'
                                f'import os, sys, subprocess, json\n'
                                f'from http.server import HTTPServer, SimpleHTTPRequestHandler\n'
                                f'PORT = int(os.environ.get("PORT", "{port}"))\n'
                                f'HOST = os.environ.get("HOST", "0.0.0.0")\n'
                                f'SERVICE = "{_name}"\n'
                                f'KEY = "{_key}"\n\n'
                                f'class Handler(SimpleHTTPRequestHandler):\n'
                                f'    def do_GET(self):\n'
                                f'        if self.path == "/api/health":\n'
                                f'            self.send_response(200)\n'
                                f'            self.send_header("Content-Type", "application/json")\n'
                                f'            self.end_headers()\n'
                                f'            self.wfile.write(json.dumps({{"ok": True, "service": SERVICE, "status": "running"}}).encode())\n'
                                f'            return\n'
                                f'        self.send_response(200)\n'
                                f'        self.send_header("Content-Type", "text/html")\n'
                                f'        self.end_headers()\n'
                                f'        html = f"""<!DOCTYPE html><html><head><meta charset=utf-8><title>{{SERVICE}}</title>\n'
                                f'        <style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:system-ui;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh}}\n'
                                f'        .card{{background:#1e293b;border-radius:16px;padding:48px;max-width:600px;text-align:center;border:1px solid #334155}}\n'
                                f'        h1{{font-size:32px;margin-bottom:16px;color:#60a5fa}}p{{color:#94a3b8;line-height:1.8;margin-bottom:24px}}\n'
                                f'        code{{background:#334155;padding:4px 12px;border-radius:6px;font-size:14px}}\n'
                                f'        a{{color:#60a5fa;text-decoration:none}}</style></head>\n'
                                f'        <body><div class=card><h1>{{SERVICE}}</h1>\n'
                                f'        <p>{{SERVICE}} is installed and running on this server.</p>\n'
                                f'        <p>Use the CLI: <code>{{KEY}}</code></p>\n'
                                f'        <p>API health: <a href=/api/health>/api/health</a></p>\n'
                                f'        </div></body></html>"""\n'
                                f'        self.wfile.write(html.encode())\n\n'
                                f'print(f"{{SERVICE}} web server on http://{{HOST}}:{{PORT}}")\n'
                                f'HTTPServer((HOST, PORT), Handler).serve_forever()\n',
                                encoding="utf-8",
                            )
                            log(f"Created web server wrapper at {wrapper}")
                            # Start the server as a background process
                            log(f"Starting {_name} web server on port {port}...")
                            python_cmd = sys.executable or "python"
                            try:
                                if os.name == "nt":
                                    subprocess.Popen(
                                        [python_cmd, str(wrapper)],
                                        cwd=str(app_dir),
                                        creationflags=0x00000008,  # DETACHED_PROCESS
                                        env={**os.environ, "PORT": port, "HOST": host_ip},
                                    )
                                else:
                                    subprocess.Popen(
                                        [python_cmd, str(wrapper)],
                                        cwd=str(app_dir),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        env={**os.environ, "PORT": port, "HOST": host_ip},
                                    )
                                log(f"{_name} server started.")
                            except Exception as ex:
                                log(f"WARNING: Could not auto-start server: {ex}")
                            # Save state
                            sfile = sdir / f"{_key}-state.json"
                            _write_json_file(sfile, {
                                "installed": True, "service_name": f"serverinstaller-{_key}",
                                "install_dir": str(app_dir), "host": host_ip,
                                "http_port": port, "http_url": f"http://{display_host}:{port}",
                                "deploy_mode": "os", "running": True,
                            })
                            manage_firewall_port("open", port, "tcp")
                            log(f"\n{_name} installed and running!")
                            log(f"URL: http://{display_host}:{port}")
                        return code, "\n".join(output)
                    return _fn
                installer = _make_installer(_ai_name, _ai_pip, _ai_port, _ai_key, form)
                if self.is_fetch():
                    job_id = start_live_job(title, installer)
                    self.write_json({"job_id": job_id, "title": title})
                else:
                    code, output = installer(None)
                    self.respond_run_result(title, code, output)
                return
            if self.path == f"/run/{_ai_key}_docker" and _ai_image:
                title = f"{_ai_name} Docker"
                def _make_docker(_name, _image, _port, _key, _form):
                    def _fn(cb):
                        return _run_ai_docker_generic(
                            _key, _image, _form, _port,
                            _port, _name,
                            SERVER_INSTALLER_DATA / _key / f"{_key}-state.json",
                            SERVER_INSTALLER_DATA / _key,
                            live_cb=cb,
                        )
                    return _fn
                docker_fn = _make_docker(_ai_name, _ai_image, _ai_port, _ai_key, form)
                if self.is_fetch():
                    job_id = start_live_job(title, docker_fn)
                    self.write_json({"job_id": job_id, "title": title})
                else:
                    code, output = docker_fn(None)
                    self.respond_run_result(title, code, output)
                return
        if self.path == "/run/dashboard_update":
            title = "Dashboard Update"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_dashboard_update(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_dashboard_update()
                self.respond_run_result(title, code, output)
            return

        if self.path == "/run/windows":
            title = "Windows Combined Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_iis":
            form["DeploymentMode"] = ["IIS"]
            title = "Windows IIS Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_setup_iis":
            title = "Windows IIS Stack Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_setup_only(form, "iis", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_setup_only(form, "iis")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_setup_docker":
            title = "Windows Docker Stack Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_setup_only(form, "docker", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_setup_only(form, "docker")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_docker_engine":
            title = "Windows Docker Engine Setup"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_docker_setup_only(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_docker_setup_only()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/windows_docker":
            form["DeploymentMode"] = ["Docker"]
            title = "Windows Docker Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_windows_installer(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_windows_installer(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux":
            title = "Linux Combined Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_installer(form, live_cb=cb, require_source=True))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_installer(form, require_source=True)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux_prereq":
            form["SOURCE_VALUE"] = [""]
            title = "Linux Prerequisites Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_installer(form, live_cb=cb, require_source=False))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_installer(form, require_source=False)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux_setup_docker":
            title = "Linux Docker Setup Installer"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_docker_setup(live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_docker_setup()
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/linux_docker":
            title = "Linux Docker Deployment"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_linux_docker_deploy(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_linux_docker_deploy(form)
                self.respond_run_result(title, code, output)
            return

        # ── SSL / Certificate endpoints ────────────────────────────────────────
        if self.path == "/api/ssl/delete":
            name = (form.get("SSL_CERT_NAME", [""])[0] or "").strip()
            ok, msg = ssl_delete_cert(name)
            status = HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST
            self.write_json({"ok": ok, "message": msg}, status)
            return
        if self.path == "/api/ssl/upload":
            # Multipart upload: cert_file, key_file, chain_file, pfx_file + form fields
            try:
                parts = self._parse_multipart()
                form_fields = {}
                file_parts = []
                for part in parts:
                    pname = part.get("name", "")
                    if pname in ("cert_file", "key_file", "chain_file", "pfx_file"):
                        file_parts.append(part)
                    else:
                        form_fields[pname] = [part.get("content", b"").decode("utf-8", errors="replace").strip()]
                # Merge with already-parsed form
                for k, v in form.items():
                    if k not in form_fields:
                        form_fields[k] = v
                code, msg = run_ssl_upload(form_fields, file_parts)
                ok = (code == 0)
                self.write_json({"ok": ok, "message": msg}, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
            except Exception as ex:
                traceback.print_exc()
                self.write_json({"ok": False, "error": str(ex)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path == "/run/ssl_letsencrypt":
            title = "Let's Encrypt Certificate"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_letsencrypt(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_letsencrypt(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ssl_renew":
            title = "Renew SSL Certificates"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_renew_all(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_renew_all(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/ssl_assign":
            title = "Assign Certificate to Service"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_ssl_assign(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_ssl_assign(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/dashboard_apply_cert":
            title = "Apply Dashboard Certificate"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_dashboard_apply_cert(form, live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_dashboard_apply_cert(form)
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/system_restart":
            title = "Restart System"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_system_power("restart", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_system_power("restart")
                self.respond_run_result(title, code, output)
            return
        if self.path == "/run/system_shutdown":
            title = "Shut Down System"
            if self.is_fetch():
                job_id = start_live_job(title, lambda cb: run_system_power("shutdown", live_cb=cb))
                self.write_json({"job_id": job_id, "title": title})
            else:
                code, output = run_system_power("shutdown")
                self.respond_run_result(title, code, output)
            return

        self.write_html("Not found", HTTPStatus.NOT_FOUND)

