import secrets
import threading
import time

from constants import BUILD_ID, JOBS, JOBS_LOCK
from ui_assets import (
    DASHBOARD_UI_SCRIPTS,
    render_dashboard_page,
    render_login_page,
    render_mongo_native_ui,
    render_output_page,
)

def start_live_job(title, runner):
    job_id = secrets.token_hex(12)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "title": title,
            "output": f"[{time.strftime('%H:%M:%S')}] Job accepted: {title}\n",
            "done": False,
            "exit_code": None,
            "created": time.time(),
        }

    def append_out(text):
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["output"] += text

    def heartbeat():
        last_len = -1
        unchanged_ticks = 0
        while True:
            time.sleep(5)
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return
                if job["done"]:
                    return
                current_len = len(job["output"])
                if current_len == last_len:
                    unchanged_ticks += 1
                    if unchanged_ticks >= 6:
                        job["output"] += f"[{time.strftime('%H:%M:%S')}] still running...\n"
                        unchanged_ticks = 0
                else:
                    unchanged_ticks = 0
                last_len = len(job["output"])

    def worker():
        try:
            code, output = runner(append_out)
            with JOBS_LOCK:
                if job_id in JOBS:
                    current_output = JOBS[job_id]["output"]
                    if output and not current_output.endswith(output):
                        JOBS[job_id]["output"] += output
                    JOBS[job_id]["exit_code"] = code
                    JOBS[job_id]["done"] = True
        except Exception as ex:
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["output"] += f"\nUnhandled error: {ex}\n"
                    JOBS[job_id]["exit_code"] = 1
                    JOBS[job_id]["done"] = True

    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    return job_id


def page_login(message=""):
    return render_login_page(message)


def page_dashboard_mui(message="", system_name=""):
    s3_docker = get_windows_s3_docker_support() if (system_name or platform.system()).lower() == "windows" else {"supported": True, "reason": ""}
    config = {
        "os": (system_name or platform.system()).lower(),
        "os_label": platform.system(),
        "message": message or "",
        "s3_windows_docker_supported": bool(s3_docker.get("supported", True)),
        "s3_windows_docker_reason": str(s3_docker.get("reason") or ""),
    }
    return render_dashboard_page(config, DASHBOARD_UI_SCRIPTS, dashboard_root=ROOT / "dashboard")


def page_dashboard(message=""):
    system_name = platform.system().lower()
    return page_dashboard_mui(message, system_name)


def page_output(title, output, code):
    return render_output_page(title, output, code)


def page_mongo_native_ui():
    info = get_windows_native_mongo_info() if os.name == "nt" else {}
    connection = str(info.get("connection") or "")
    version = str(info.get("version") or "")
    web_version = str(info.get("web_version") or "native-service")
    auth_enabled = bool(info.get("auth_enabled"))
    host = choose_service_host()
    port = str(info.get("port") or "27017")
    if not connection and port.isdigit():
        connection = f"mongodb://{host}:{int(port)}/"
    auth_text = "enabled" if auth_enabled else "not initialized"
    tls_text = "disabled"
    compass_uri = get_windows_native_mongo_uri(loopback=False) if os.name == "nt" else connection
    login_hint = (
        "Enter the MongoDB admin credentials to unlock the web manager."
        if auth_enabled else
        "Authentication is not initialized on this MongoDB service. You can continue without credentials, or enter credentials if you enabled auth manually."
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>MongoDB Web</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0b1220;color:#e5eefc;padding:24px;margin:0}}
.card{{max-width:1280px;margin:0 auto;background:#111a2e;border:1px solid #243454;border-radius:16px;padding:24px}}
.muted{{color:#a9b9d5}}
.row{{margin:10px 0}}
.pill{{display:inline-block;padding:6px 10px;border-radius:999px;background:#1d4ed8;color:#fff;font-size:12px;margin-right:8px}}
a{{color:#93c5fd}}
code, pre{{background:#0a1020;padding:3px 6px;border-radius:6px;color:#dbeafe}}
.actions{{margin-top:18px;display:flex;gap:12px;flex-wrap:wrap}}
.btn{{display:inline-block;padding:10px 14px;border-radius:10px;text-decoration:none;background:#2563eb;color:#fff;border:0;cursor:pointer;font:inherit}}
.btn.secondary{{background:#334155}}
.btn.danger{{background:#b91c1c}}
.layout{{display:grid;grid-template-columns:260px 280px 1fr;gap:16px;margin-top:20px}}
.panel{{background:#0f172a;border:1px solid #22304a;border-radius:14px;padding:14px;min-height:420px}}
.panel h3{{margin:0 0 12px 0;font-size:16px}}
.list{{display:flex;flex-direction:column;gap:8px;max-height:420px;overflow:auto}}
.item{{padding:10px 12px;border-radius:10px;border:1px solid #243454;background:#111827;color:#e5eefc;cursor:pointer;text-align:left}}
.item.active{{border-color:#60a5fa;background:#13213c}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px 0}}
textarea{{width:100%;min-height:180px;background:#0a1020;color:#dbeafe;border:1px solid #22304a;border-radius:12px;padding:12px;font-family:Consolas,monospace}}
select,input{{background:#0a1020;color:#dbeafe;border:1px solid #22304a;border-radius:10px;padding:8px 10px}}
pre{{white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;padding:14px}}
.stack{{display:flex;flex-direction:column;gap:14px}}
.login-shell{{margin-top:20px;display:grid;grid-template-columns:minmax(320px,520px);justify-content:center}}
.login-panel{{min-height:auto}}
.hidden{{display:none}}
.status{{margin-top:10px;padding:10px 12px;border-radius:10px;border:1px solid #243454;background:#0a1020}}
.status.error{{border-color:#7f1d1d;color:#fecaca;background:#220c12}}
.status.ok{{border-color:#14532d;color:#bbf7d0;background:#0a1f17}}
.auth-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.auth-grid label{{display:flex;flex-direction:column;gap:6px}}
@media (max-width:1100px){{.layout{{grid-template-columns:1fr}}}}
@media (max-width:700px){{.auth-grid{{grid-template-columns:1fr}}}}
</style>
</head><body><div class="card">
<div class="pill">MongoDB</div><div class="pill">Windows Native</div><div class="pill">{html.escape(web_version)}</div>
<h2>MongoDB Web</h2>
<p class="muted">Windows native MongoDB management UI. Sign in on this page, then browse databases and collections, inspect documents, and run `mongosh` commands directly from the dashboard.</p>
<div class="row">Connection: <code>{html.escape(connection or "mongodb://localhost:27017/")}</code></div>
<div class="row">Compass URI: <code id="compassUri">{html.escape(compass_uri or "mongodb://admin:StrongPassword123@localhost:27017/admin?authSource=admin")}</code></div>
<div class="row">Version: <code>{html.escape(version or "unknown")}</code></div>
<div class="row">Authentication: <code>{html.escape(auth_text)}</code></div>
<div class="row">TLS/SSL: <code>{html.escape(tls_text)}</code></div>
<div class="actions">
<a class="btn" href="/">Back To Dashboard</a>
<a class="btn secondary" href="https://www.mongodb.com/try/download/compass" target="_blank" rel="noreferrer noopener">Download Compass</a>
<button class="btn secondary" id="copyCompass" type="button">Copy Compass URI</button>
<button class="btn secondary hidden" id="logoutMongo" type="button">Log Out</button>
</div>
<div class="login-shell" id="loginShell">
  <div class="panel login-panel">
    <h3>Login</h3>
    <p class="muted">{html.escape(login_hint)}</p>
    <div class="auth-grid">
      <label class="muted">Username
        <input id="mongoUser" type="text" autocomplete="username" value="admin">
      </label>
      <label class="muted">Password
        <input id="mongoPassword" type="password" autocomplete="current-password" value="StrongPassword123">
      </label>
    </div>
    <div class="toolbar">
      <button class="btn" id="loginMongo" type="button">Log In</button>
      <button class="btn secondary" id="continueMongo" type="button"{' style="display:none"' if auth_enabled else ''}>Continue Without Login</button>
    </div>
    <div class="status" id="loginStatus">{html.escape(login_hint)}</div>
  </div>
</div>
<div class="layout hidden" id="managerLayout">
  <div class="panel">
    <h3>Databases</h3>
    <div class="toolbar"><button class="btn secondary" id="refreshDbs" type="button">Refresh</button></div>
    <div class="list" id="dbList"><div class="muted">Loading...</div></div>
  </div>
  <div class="panel">
    <h3>Collections</h3>
    <div class="row muted" id="selectedDbLabel">Select a database.</div>
    <div class="list" id="collectionList"><div class="muted">No database selected.</div></div>
  </div>
  <div class="panel">
    <div class="stack">
      <div>
        <h3>Documents</h3>
        <div class="toolbar">
          <label class="muted">Limit <input id="docLimit" type="number" min="1" max="200" value="50"></label>
          <button class="btn secondary" id="refreshDocs" type="button">Load Documents</button>
        </div>
        <pre id="docOutput">Select a collection.</pre>
      </div>
      <div>
        <h3>Command Console</h3>
        <div class="toolbar">
          <label class="muted">Database <input id="commandDb" type="text" value="admin"></label>
          <button class="btn" id="runCommand" type="button">Run</button>
        </div>
        <textarea id="commandText">return db.runCommand({{ ping: 1 }});</textarea>
        <pre id="commandOutput">Run a command to manage MongoDB.</pre>
      </div>
    </div>
  </div>
</div>
<script>
const AUTH_STORAGE_KEY = 'mongo-native-auth-v1';
const state = {{ db: "", collection: "", auth: null }};
const dbList = document.getElementById("dbList");
const collectionList = document.getElementById("collectionList");
const selectedDbLabel = document.getElementById("selectedDbLabel");
const docOutput = document.getElementById("docOutput");
const commandOutput = document.getElementById("commandOutput");
const commandDb = document.getElementById("commandDb");
const commandText = document.getElementById("commandText");
const docLimit = document.getElementById("docLimit");
const loginShell = document.getElementById("loginShell");
const managerLayout = document.getElementById("managerLayout");
const loginStatus = document.getElementById("loginStatus");
const loginBtn = document.getElementById("loginMongo");
const continueBtn = document.getElementById("continueMongo");
const logoutBtn = document.getElementById("logoutMongo");
const mongoUser = document.getElementById("mongoUser");
const mongoPassword = document.getElementById("mongoPassword");
const authRequired = {str(auth_enabled).lower()};

function currentHeaders(extra) {{
  const headers = Object.assign({{ "X-Requested-With": "fetch" }}, extra || {{}});
  if (state.auth) {{
    headers["X-Mongo-User"] = state.auth.username || "";
    headers["X-Mongo-Password"] = state.auth.password || "";
  }}
  return headers;
}}

async function apiGet(url) {{
  const r = await fetch(url, {{ headers: currentHeaders() }});
  return await r.json();
}}
async function apiPost(url, body) {{
  const r = await fetch(url, {{
    method: "POST",
    headers: currentHeaders({{ "Content-Type": "application/x-www-form-urlencoded" }}),
    body: new URLSearchParams(body).toString()
  }});
  return await r.json();
}}
function pretty(value) {{
  return JSON.stringify(value, null, 2);
}}
function setLoginState(message, tone) {{
  loginStatus.textContent = message || '';
  loginStatus.className = 'status' + (tone === 'error' ? ' error' : (tone === 'ok' ? ' ok' : ''));
}}
function setLoggedIn(loggedIn) {{
  loginShell.classList.toggle('hidden', loggedIn);
  managerLayout.classList.toggle('hidden', !loggedIn);
  logoutBtn.classList.toggle('hidden', !loggedIn);
}}
function saveAuth() {{
  try {{
    if (state.auth) {{
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(state.auth));
    }} else {{
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
    }}
  }} catch (_err) {{}}
}}
function restoreAuth() {{
  try {{
    const raw = sessionStorage.getItem(AUTH_STORAGE_KEY) || '';
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return {{
      username: String(parsed.username || ''),
      password: String(parsed.password || '')
    }};
  }} catch (_err) {{
    return null;
  }}
}}
async function loadDatabases(initialPayload) {{
  dbList.innerHTML = '<div class="muted">Loading...</div>';
  const j = initialPayload || await apiGet('/api/mongo/native/overview');
  if (!j.ok) {{
    dbList.innerHTML = '<div class="muted">' + String(j.error || 'Failed to load databases.') + '</div>';
    return;
  }}
  const dbs = Array.isArray(j.databases) ? j.databases : [];
  if (!dbs.length) {{
    dbList.innerHTML = '<div class="muted">No databases found.</div>';
    return;
  }}
  dbList.innerHTML = '';
  dbs.forEach((item) => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'item' + (state.db === item.name ? ' active' : '');
    btn.textContent = item.name;
    btn.onclick = async () => {{
      state.db = item.name;
      state.collection = '';
      commandDb.value = item.name;
      await loadDatabases();
      await loadCollections();
    }};
    dbList.appendChild(btn);
  }});
}}
async function loadCollections() {{
  if (!state.db) {{
    selectedDbLabel.textContent = 'Select a database.';
    collectionList.innerHTML = '<div class="muted">No database selected.</div>';
    return;
  }}
  selectedDbLabel.textContent = 'Database: ' + state.db;
  collectionList.innerHTML = '<div class="muted">Loading...</div>';
  const j = await apiGet('/api/mongo/native/collections?db=' + encodeURIComponent(state.db));
  if (!j.ok) {{
    collectionList.innerHTML = '<div class="muted">' + String(j.error || 'Failed to load collections.') + '</div>';
    return;
  }}
  const cols = Array.isArray(j.collections) ? j.collections : [];
  if (!cols.length) {{
    collectionList.innerHTML = '<div class="muted">No collections found.</div>';
    return;
  }}
  collectionList.innerHTML = '';
  cols.forEach((item) => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'item' + (state.collection === item.name ? ' active' : '');
    btn.textContent = item.name;
    btn.onclick = async () => {{
      state.collection = item.name;
      await loadCollections();
      await loadDocuments();
    }};
    collectionList.appendChild(btn);
  }});
}}
async function loadDocuments() {{
  if (!state.db || !state.collection) {{
    docOutput.textContent = 'Select a collection.';
    return;
  }}
  docOutput.textContent = 'Loading...';
  const limit = Math.max(1, Math.min(200, Number(docLimit.value || 50)));
  const j = await apiGet('/api/mongo/native/documents?db=' + encodeURIComponent(state.db) + '&collection=' + encodeURIComponent(state.collection) + '&limit=' + encodeURIComponent(limit));
  if (!j.ok) {{
    docOutput.textContent = String(j.error || 'Failed to load documents.');
    return;
  }}
  docOutput.textContent = pretty(j.documents || []);
}}
async function runCommand() {{
  commandOutput.textContent = 'Running...';
  const j = await apiPost('/api/mongo/native/command', {{ db: commandDb.value || 'admin', script: commandText.value || '' }});
  if (!j.ok) {{
    commandOutput.textContent = String(j.error || 'Command failed.');
    return;
  }}
  commandOutput.textContent = pretty(j.result);
  await loadDatabases();
  if (state.db) await loadCollections();
}}
async function attemptLogin(username, password) {{
  state.auth = {{
    username: String(username || ''),
    password: String(password || '')
  }};
  setLoginState('Checking MongoDB credentials...', '');
  const j = await apiGet('/api/mongo/native/overview');
  if (!j.ok) {{
    state.auth = null;
    saveAuth();
    setLoggedIn(false);
    setLoginState(String(j.error || 'Login failed.'), 'error');
    return false;
  }}
  saveAuth();
  setLoggedIn(true);
  setLoginState(authRequired ? 'MongoDB login successful.' : 'Connected to MongoDB.', 'ok');
  await loadDatabases(j);
  return true;
}}
async function submitLogin() {{
  loginBtn.disabled = true;
  continueBtn.disabled = true;
  try {{
    await attemptLogin(mongoUser.value || '', mongoPassword.value || '');
  }} finally {{
    loginBtn.disabled = false;
    continueBtn.disabled = false;
  }}
}}
function logoutMongo() {{
  state.auth = null;
  state.db = '';
  state.collection = '';
  saveAuth();
  setLoggedIn(false);
  dbList.innerHTML = '<div class="muted">Log in to load databases.</div>';
  collectionList.innerHTML = '<div class="muted">No database selected.</div>';
  selectedDbLabel.textContent = 'Select a database.';
  docOutput.textContent = 'Select a collection.';
  commandOutput.textContent = 'Run a command to manage MongoDB.';
  setLoginState(authRequired ? 'Enter MongoDB credentials to continue.' : 'Continue without login or enter credentials.', '');
}}
document.getElementById('refreshDbs').onclick = loadDatabases;
document.getElementById('refreshDocs').onclick = loadDocuments;
document.getElementById('runCommand').onclick = runCommand;
loginBtn.onclick = submitLogin;
continueBtn.onclick = () => attemptLogin('', '');
logoutBtn.onclick = logoutMongo;
mongoPassword.addEventListener('keydown', (ev) => {{
  if (ev.key === 'Enter') {{
    ev.preventDefault();
    submitLogin();
  }}
}});
document.getElementById('copyCompass').onclick = async () => {{
  const text = document.getElementById('compassUri').textContent || '';
  try {{
    await navigator.clipboard.writeText(text);
  }} catch (_err) {{}}
}};
const savedAuth = restoreAuth();
if (savedAuth) {{
  mongoUser.value = savedAuth.username || mongoUser.value;
  mongoPassword.value = savedAuth.password || mongoPassword.value;
  attemptLogin(savedAuth.username || '', savedAuth.password || '');
}} else if (!authRequired) {{
  setLoginState('Authentication is optional here. Continue without login or enter credentials.', '');
}} else {{
  setLoginState('Enter MongoDB credentials to continue.', '');
}}
</script>
</div></body></html>"""

