import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

from constants import (
    ROOT,
    WEBSITE_STATE_FILE,
)
from utils import _read_json_file, command_exists, run_capture
from system_info import choose_service_host
from website_manager import _website_state_payload


def _safe_service_name(name):
    value = (name or "").strip()
    if not value:
        return ""
    if not re.match(r"^[A-Za-z0-9_.@-]+$", value):
        return ""
    return value


def get_windows_native_mongo_info():
    if os.name != "nt":
        return {}
    ps = (
        # Scan all LocalMongoDB-* instance directories for install-info.json, pick newest
        "$pd=$env:ProgramData; "
        "$metas=@(); "
        "Get-ChildItem -Path $pd -Filter 'LocalMongoDB-*' -Directory -ErrorAction SilentlyContinue | ForEach-Object { "
        "  $f=Join-Path $_.FullName 'install-info.json'; "
        "  if(Test-Path $f){ $metas+=[PSCustomObject]@{Path=$f;Modified=(Get-Item $f -ErrorAction SilentlyContinue).LastWriteTime} } "
        "}; "
        # Also check legacy path without instance suffix
        "$legacyMeta=Join-Path (Join-Path $pd 'LocalMongoDB') 'install-info.json'; "
        "if(Test-Path $legacyMeta){ $metas+=[PSCustomObject]@{Path=$legacyMeta;Modified=(Get-Item $legacyMeta -ErrorAction SilentlyContinue).LastWriteTime} }; "
        "$meta=if($metas.Count -gt 0){ ($metas | Sort-Object Modified -Descending | Select-Object -First 1).Path } else { $null }; "
        "$obj=[ordered]@{installed=$false;version='';connection='';port='';host='';mode='';web_version='';auth_enabled=$false;status='';admin_user='';admin_password=''}; "
        "if($meta){ "
        "  try { "
        "    $m=Get-Content -LiteralPath $meta -Raw | ConvertFrom-Json; "
        "    if($m.version){$obj.version=[string]$m.version}; "
        "    if($m.connection_string){$obj.connection=[string]$m.connection_string}; "
        "    if($m.mongo_port){$obj.port=[string]$m.mongo_port}; "
        "    if($m.host){$obj.host=[string]$m.host}; "
        "    if($m.mode){$obj.mode=[string]$m.mode}; "
        "    if($m.web_version){$obj.web_version=[string]$m.web_version}; "
        "    if($null -ne $m.auth_enabled){$obj.auth_enabled=[bool]$m.auth_enabled}; "
        "    if($m.admin_user){$obj.admin_user=[string]$m.admin_user}; "
        "    if($m.admin_password){$obj.admin_password=[string]$m.admin_password}; "
        "    $obj.installed=$true; "
        "  } catch {} "
        "  $svcName=if($m -and $m.service_name){ [string]$m.service_name } else { 'LocalMongoDB' }; "
        "  $svc=Get-Service -Name $svcName -ErrorAction SilentlyContinue; "
        "  if($svc){ $obj.installed=$true; $obj.status=[string]$svc.Status }; "
        "  $cfgDir=Split-Path $meta; "
        "  $cfg=Join-Path $cfgDir 'config\\mongod.cfg'; "
        "  if((-not $obj.port) -and (Test-Path $cfg)){ "
        "    $match=Select-String -Path $cfg -Pattern '^\\s*port\\s*:\\s*(\\d+)' -AllMatches -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "    if($match){$obj.port=[string]$match.Matches[0].Groups[1].Value} "
        "  } "
        "  if((-not $obj.version) -and (Test-Path (Join-Path $cfgDir 'mongodb\\bin\\mongod.exe'))){ "
        "    try { "
        "      $ver=& (Join-Path $cfgDir 'mongodb\\bin\\mongod.exe') --version 2>$null | Out-String; "
        "      if($ver -match 'db version v([0-9A-Za-z\\.\\-]+)'){ $obj.version=$matches[1] } "
        "    } catch {} "
        "  } "
        "} "
        "$obj | ConvertTo-Json -Depth 3"
    )
    rc, out = run_capture(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        timeout=20,
    )
    if rc != 0 or not out:
        return {}
    try:
        data = json.loads(out)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def find_windows_mongosh_exe():
    if os.name != "nt":
        return ""
    candidates = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "LocalMongoDB" / "mongosh" / "bin" / "mongosh.exe",
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "LocalMongoDB" / "mongodb" / "bin" / "mongosh.exe",
    ]
    for base in filter(None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), r"C:\Program Files"]):
        root = Path(base) / "MongoDB"
        if root.exists():
            candidates.extend(root.rglob("mongosh.exe"))
    for path in candidates:
        try:
            if path and Path(path).exists():
                return str(Path(path))
        except Exception:
            continue
    rc, out = run_capture(["where", "mongosh"], timeout=10)
    if rc == 0 and out:
        for line in out.splitlines():
            p = line.strip().strip('"')
            if p.lower().endswith("mongosh.exe") and Path(p).exists():
                return p
    return ""


def get_windows_native_mongo_uri(loopback=True, username=None, password=None):
    info = get_windows_native_mongo_info() if os.name == "nt" else {}
    port = str(info.get("port") or "27017").strip()
    configured_host = str(info.get("host") or "").strip()
    host = "127.0.0.1" if loopback else (configured_host or choose_service_host())
    if str(info.get("auth_enabled") or "").lower() in ("true", "1") or bool(info.get("auth_enabled")):
        user = str(username or "admin").strip() or "admin"
        secret = "" if password is None else str(password)
        if not secret:
            secret = "StrongPassword123"
        return (
            f"mongodb://{quote(user)}:{quote(secret)}"
            f"@{host}:{port}/admin?authSource=admin"
        )
    return f"mongodb://{host}:{port}/admin"


def run_windows_mongosh_json(body_js, timeout=40, username=None, password=None):
    if os.name != "nt":
        return False, {"error": "Windows native Mongo UI is only available on Windows."}
    mongosh = find_windows_mongosh_exe()
    if not mongosh:
        return False, {"error": "mongosh.exe not found. Re-run the Windows MongoDB installer."}
    uri = get_windows_native_mongo_uri(loopback=True, username=username, password=password)
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", str(ROOT))))
    temp_dir.mkdir(parents=True, exist_ok=True)
    script_path = temp_dir / f"codex-mongo-native-{secrets.token_hex(8)}.js"
    begin = "__CODEX_MONGO_JSON_BEGIN__"
    end = "__CODEX_MONGO_JSON_END__"
    wrapper = f"""
try {{
  const __result = (() => {{
{body_js}
  }})();
  print("{begin}");
  print(EJSON.stringify({{ ok: true, result: __result }}, null, 2));
  print("{end}");
}} catch (e) {{
  print("{begin}");
  print(EJSON.stringify({{ ok: false, error: String((e && (e.stack || e.message)) || e) }}, null, 2));
  print("{end}");
  quit(1);
}}
"""
    script_path.write_text(wrapper, encoding="utf-8")
    try:
        rc, out = run_capture([mongosh, uri, "--quiet", "--file", str(script_path)], timeout=timeout)
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
    text = out or ""
    start = text.find(begin)
    stop = text.find(end, start + len(begin)) if start >= 0 else -1
    if start < 0 or stop < 0:
        return False, {"error": (text.strip() or "mongosh did not return JSON output.")}
    payload_text = text[start + len(begin):stop].strip()
    try:
        payload = json.loads(payload_text)
    except Exception as ex:
        return False, {"error": f"Failed to parse mongosh output: {ex}", "raw": payload_text}
    if rc != 0 and payload.get("ok") is not True:
        return False, payload
    if payload.get("ok") is not True:
        return False, payload
    return True, payload.get("result")


def mongo_native_overview(username=None, password=None):
    body_js = """
const adminDb = db.getSiblingDB('admin');
const build = adminDb.runCommand({ buildInfo: 1 }) || {};
const list = adminDb.adminCommand({ listDatabases: 1, nameOnly: true }) || {};
return {
  version: build.version || "",
  databases: (list.databases || []).map((x) => ({
    name: x.name || "",
    sizeOnDisk: x.sizeOnDisk || 0,
    empty: !!x.empty
  }))
};
"""
    return run_windows_mongosh_json(body_js, timeout=40, username=username, password=password)


def mongo_native_collections(db_name, username=None, password=None):
    db_name = str(db_name or "").strip()
    if not db_name:
        return False, {"error": "Database name is required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
return {{
  database: {json.dumps(db_name)},
  collections: (targetDb.getCollectionInfos() || []).map((c) => ({{
    name: c.name || "",
    type: c.type || "collection"
  }}))
}};
"""
    return run_windows_mongosh_json(body_js, timeout=40, username=username, password=password)


def mongo_native_documents(db_name, collection_name, limit=50, username=None, password=None):
    db_name = str(db_name or "").strip()
    collection_name = str(collection_name or "").strip()
    try:
        limit = max(1, min(200, int(limit)))
    except Exception:
        limit = 50
    if not db_name or not collection_name:
        return False, {"error": "Database and collection are required."}
    body_js = f"""
const targetDb = db.getSiblingDB({json.dumps(db_name)});
const docs = targetDb.getCollection({json.dumps(collection_name)}).find({{}}, {{}}).limit({limit}).toArray();
return {{
  database: {json.dumps(db_name)},
  collection: {json.dumps(collection_name)},
  limit: {limit},
  documents: docs
}};
"""
    return run_windows_mongosh_json(body_js, timeout=50, username=username, password=password)


def mongo_native_run_script(db_name, script_text, username=None, password=None):
    db_name = str(db_name or "admin").strip() or "admin"
    script_text = str(script_text or "").strip()
    if not script_text:
        return False, {"error": "Script is required."}
    body_js = f"""
const db = globalThis.db.getSiblingDB({json.dumps(db_name)});
{script_text}
"""
    return run_windows_mongosh_json(body_js, timeout=60, username=username, password=password)


def _resolve_service_host(service_name, fallback):
    """Return the user-selected host stored in website state for *service_name*,
    falling back to *fallback* when no stored host is available."""
    payload = _website_state_payload(service_name)
    stored = str(payload.get("host") or "").strip()
    if stored and stored not in ("localhost", "127.0.0.1"):
        return stored
    return fallback

