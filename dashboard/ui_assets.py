import html
import json
import pathlib


DASHBOARD_UI_SCRIPTS = [
    "/static/ui/core.js",
    "/static/ui/utils.js",
    "/static/ui/actions.js",
    "/static/ui/components.js",
    "/static/ui/file-manager.js",
    "/static/ui/pages/home/home.js",
    "/static/ui/pages/api/api.js",
    "/static/ui/pages/sysinfo/sysinfo.js",
    "/static/ui/pages/ports/ports.js",
    "/static/ui/pages/services/services.js",
    "/static/ui/pages/s3/s3.js",
    "/static/ui/pages/mongo/mongo.js",
    "/static/ui/pages/mongo/mongo-native.js",
    "/static/ui/pages/mongo/mongo-docker.js",
    "/static/ui/pages/docker/docker.js",
    "/static/ui/pages/proxy/proxy.js",
    "/static/ui/pages/dotnet/dotnet.js",
    "/static/ui/pages/dotnet/dotnet-iis.js",
    "/static/ui/pages/dotnet/dotnet-docker.js",
    "/static/ui/pages/dotnet/dotnet-linux.js",
    "/static/ui/pages/python/python.js",
    "/static/ui/pages/python/python-api.js",
    "/static/ui/pages/python/python-system.js",
    "/static/ui/pages/python/python-docker.js",
    "/static/ui/pages/python/python-iis.js",
    "/static/ui/pages/website/website.js",
    "/static/ui/pages/ssl/ssl.js",
    "/static/ui/pages/files/files.js",
    "/static/ui/app.js",
]


def render_login_page(message=""):
    msg = f'<div class="alert">{html.escape(message)}</div>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Server Installer Login</title>
<style>
:root{{
  --bg:#f4f8fc;
  --panel:#ffffff;
  --ink:#0f172a;
  --muted:#475569;
  --line:#d9e4f2;
  --brand:#0f766e;
  --brand-deep:#115e59;
  --brand-soft:#dff7f3;
  --danger:#b42318;
  --danger-bg:#fff1f1;
}}
*{{box-sizing:border-box}}
body{{
  margin:0;
  min-height:100vh;
  font-family:"Segoe UI",Tahoma,Arial,sans-serif;
  color:var(--ink);
  background:
    radial-gradient(circle at top left, rgba(15,118,110,.18), transparent 28%),
    radial-gradient(circle at bottom right, rgba(37,99,235,.14), transparent 24%),
    linear-gradient(135deg, #eef5fb 0%, #f8fbff 45%, #eef7f5 100%);
}}
.shell{{
  min-height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:32px 20px;
}}
.frame{{
  width:min(1080px, 100%);
  display:grid;
  grid-template-columns:1.08fr .92fr;
  background:rgba(255,255,255,.78);
  border:1px solid rgba(217,228,242,.95);
  border-radius:28px;
  overflow:hidden;
  box-shadow:0 28px 80px rgba(15,23,42,.16);
  backdrop-filter:blur(14px);
}}
.hero{{
  position:relative;
  padding:56px 48px;
  background:
    linear-gradient(160deg, rgba(15,118,110,.94), rgba(14,89,118,.9)),
    linear-gradient(135deg, #0f766e, #1d4ed8);
  color:#fff;
}}
.hero::before,
.hero::after{{
  content:"";
  position:absolute;
  border-radius:999px;
  background:rgba(255,255,255,.09);
}}
.hero::before{{width:260px;height:260px;top:-80px;right:-60px}}
.hero::after{{width:220px;height:220px;bottom:-110px;left:-90px}}
.eyebrow{{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:7px 12px;
  border:1px solid rgba(255,255,255,.18);
  border-radius:999px;
  background:rgba(255,255,255,.08);
  font-size:12px;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.hero h1{{
  margin:18px 0 14px;
  font-size:40px;
  line-height:1.06;
}}
.hero p{{
  margin:0;
  max-width:520px;
  color:rgba(255,255,255,.84);
  font-size:16px;
  line-height:1.7;
}}
.points{{margin:32px 0 0;padding:0;list-style:none;display:grid;gap:14px}}
.points li{{
  padding:14px 16px;
  border-radius:16px;
  background:rgba(255,255,255,.1);
  border:1px solid rgba(255,255,255,.12);
  line-height:1.5;
}}
.points strong{{display:block;margin-bottom:4px;font-size:14px}}
.card{{
  padding:48px 42px;
  background:linear-gradient(180deg, rgba(255,255,255,.96), rgba(252,253,255,.92));
  display:flex;
  align-items:center;
}}
.card-inner{{width:min(420px, 100%);margin:0 auto}}
.kicker{{
  margin:0 0 10px;
  color:var(--brand);
  font-size:12px;
  font-weight:700;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.card h2{{margin:0 0 10px;font-size:32px;line-height:1.1}}
.lead{{margin:0 0 26px;color:var(--muted);line-height:1.65}}
.alert{{
  margin:0 0 18px;
  padding:12px 14px;
  border-radius:14px;
  border:1px solid rgba(180,35,24,.14);
  background:var(--danger-bg);
  color:var(--danger);
  font-size:14px;
}}
form{{display:grid;gap:16px}}
.field{{display:grid;gap:8px}}
label{{font-size:14px;font-weight:700;color:#1e293b}}
input{{
  width:100%;
  padding:14px 16px;
  border:1px solid var(--line);
  border-radius:14px;
  background:#fff;
  color:var(--ink);
  font-size:15px;
  outline:none;
  transition:border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}}
input:focus{{
  border-color:rgba(15,118,110,.55);
  box-shadow:0 0 0 4px rgba(15,118,110,.12);
  transform:translateY(-1px);
}}
input::placeholder{{color:#94a3b8}}
.password-wrap{{position:relative}}
.password-wrap input{{padding-right:84px}}
.password-toggle{{
  position:absolute;
  right:10px;
  top:50%;
  transform:translateY(-50%);
  min-width:62px;
  background:#fff;
  color:#0f172a;
  border:1px solid var(--line);
  padding:7px 10px;
  border-radius:10px;
  font-size:12px;
  font-weight:700;
  cursor:pointer;
}}
.password-toggle:hover{{background:#f8fafc}}
.submit{{
  margin-top:4px;
  padding:14px 18px;
  border:0;
  border-radius:14px;
  background:linear-gradient(135deg, var(--brand), var(--brand-deep));
  color:#fff;
  font-size:15px;
  font-weight:700;
  letter-spacing:.01em;
  cursor:pointer;
  box-shadow:0 14px 28px rgba(15,118,110,.22);
  transition:transform .18s ease, box-shadow .18s ease, filter .18s ease;
}}
.submit:hover{{transform:translateY(-1px);box-shadow:0 18px 34px rgba(15,118,110,.28);filter:saturate(1.05)}}
.footnote{{margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.6}}
.meta{{
  margin-top:16px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  flex-wrap:wrap;
}}
.credit{{
  margin:0;
  color:#64748b;
  font-size:12px;
  line-height:1.5;
}}
.github-link{{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:7px 10px;
  border-radius:999px;
  border:1px solid var(--line);
  background:#fff;
  color:#334155;
  font-size:12px;
  font-weight:700;
  text-decoration:none;
  transition:border-color .18s ease, background .18s ease, color .18s ease;
}}
.github-link:hover{{
  border-color:rgba(15,118,110,.35);
  background:#f8fffe;
  color:var(--brand-deep);
}}
@media (max-width: 900px) {{
  .frame{{grid-template-columns:1fr}}
  .hero{{padding:36px 28px}}
  .card{{padding:34px 24px 36px}}
  .hero h1{{font-size:32px}}
}}
</style></head>
<body><div class="shell"><div class="frame">
<section class="hero">
  <div class="eyebrow">Secure Remote Access</div>
  <h1>Server Installer Dashboard</h1>
  <p>Manage IIS, .NET hosting, S3 services, and Mongo deployments from one place with a cleaner, safer remote sign-in experience.</p>
  <ul class="points">
    <li><strong>System-backed authentication</strong>Use this machine's operating system account to access the dashboard remotely.</li>
    <li><strong>Operational visibility</strong>Track service state, resource usage, and installer output from a single control surface.</li>
    <li><strong>Built for administration</strong>Fast access to the tools you need without exposing a separate dashboard password store.</li>
  </ul>
</section>
<section class="card">
  <div class="card-inner">
    <p class="kicker">Administrator Sign In</p>
    <h2>Open the dashboard</h2>
    <p class="lead">Remote access requires the OS username and password for this computer.</p>
    {msg}
    <form method="post" action="/login" autocomplete="on">
      <div class="field">
        <label for="username">Server Username</label>
        <input id="username" name="username" placeholder="DOMAIN\\username or local account" autocomplete="username" required>
      </div>
      <div class="field">
        <label for="password">Server Password</label>
        <div class="password-wrap">
          <input id="password" type="password" name="password" autocomplete="current-password" placeholder="Enter your OS password" required>
          <button type="button" class="password-toggle" data-password-toggle>Show</button>
        </div>
      </div>
      <button type="submit" class="submit">Open Dashboard</button>
    </form>
    <p class="footnote">Localhost access does not require this sign-in screen. This login is only for remote dashboard access.</p>
    <div class="meta">
      <p class="credit">Created by Keyhan Azarjoo</p>
      <a class="github-link" href="https://github.com/keyhan-azarjoo/Server-Installer" target="_blank" rel="noopener noreferrer">Project GitHub</a>
    </div>
  </div>
</section>
</div></div>
<script>
document.querySelectorAll('[data-password-toggle]').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var wrap = btn.closest('.password-wrap');
    var input = wrap ? wrap.querySelector('input[type="password"], input[type="text"]') : null;
    if (!input) return;
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.textContent = show ? 'Hide' : 'Show';
  }});
}});
var firstInput = document.getElementById('username');
if (firstInput) firstInput.focus();
</script>
</body></html>"""


def render_dashboard_page(config, script_paths=None, dashboard_root=None):
    # All dashboard scripts are inlined as script content so Babel processes them
    # synchronously in document order. External src= scripts are fetched asynchronously
    # by Babel standalone, creating a race where app.js can evaluate before
    # components.js has set window.ServerInstallerUI.components, causing NavCard/
    # ActionCard to be undefined everywhere.  Inline scripts have no fetch step and
    # are guaranteed to run in order before ReactDOM.render fires.
    static_prefix = "/static/ui/"
    script_tags_list = []
    for path in (script_paths or DASHBOARD_UI_SCRIPTS):
        inlined = False
        if dashboard_root and path.startswith(static_prefix):
            rel = path[len(static_prefix):]  # e.g. "core.js" or "pages/home/home.js"
            file_path = pathlib.Path(dashboard_root) / "ui" / rel
            try:
                content = file_path.read_text(encoding="utf-8")
                script_tags_list.append(
                    f'  <script type="text/babel">\n{content}\n  </script>'
                )
                inlined = True
            except Exception:
                pass
        if not inlined:
            script_tags_list.append(
                f'  <script type="text/babel" src="{html.escape(path)}"></script>'
            )
    script_tags = "\n".join(script_tags_list)
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Server Installer Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    html, body, #root { height: 100%; margin: 0; }
    body { font-family: "Manrope", "Segoe UI", sans-serif; background: #eef3fb; }
    .terminal-log { white-space: pre-wrap; word-break: break-word; font-family: Consolas, monospace; font-size: 12px; }
  </style>
  <script>window.__APP_CONFIG__ = __CONFIG__;</script>
  <script crossorigin src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://cdn.jsdelivr.net/npm/react-dom@18/umd/react-dom.production.min.js"></script>
  <script crossorigin src="https://cdn.jsdelivr.net/npm/@mui/material@5.16.14/umd/material-ui.production.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@mui/icons-material@5.16.14/umd/material-icons.production.min.js" onerror="window.MaterialIcons=window.MaterialIcons||{};"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@4.19.0/css/xterm.css">
  <script src="https://cdn.jsdelivr.net/npm/xterm@4.19.0/lib/xterm.js" onerror="window.__xtermFailed=true"></script>
  <script>if(window.__xtermFailed||!window.Terminal)document.write('<scr'+'ipt src="https://cdnjs.cloudflare.com/ajax/libs/xterm/4.19.0/xterm.min.js"><\/'+'script>');</script>
  <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.7.0/lib/xterm-addon-fit.js" onerror="window.__fitFailed=true"></script>
  <script>if(window.__fitFailed||!window.FitAddon)document.write('<scr'+'ipt src="https://unpkg.com/xterm-addon-fit@0.7.0/lib/xterm-addon-fit.js"><\/'+'script>');</script>
  <script>window.MaterialUIIcons = window.MaterialIcons || {};</script>
</head>
<body>
  <div id="root"></div>
__SCRIPTS__
</body>
</html>""".replace("__CONFIG__", json.dumps(config)).replace("__SCRIPTS__", script_tags)


def render_output_page(title, output, code):
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Consolas,monospace;background:#0d1117;color:#c9d1d9;padding:16px}}a{{color:#58a6ff}}</style>
</head><body><h2>{html.escape(title)} (exit {code})</h2><pre>{html.escape(output)}</pre><a href="/">Back</a></body></html>"""


def render_mongo_native_ui(connection, version, web_version, auth_enabled, auth_text, tls_text, compass_uri, login_hint):
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
    <div class="status" id="authStatus">Use the MongoDB admin username and password configured on this server.</div>
  </div>
</div>
<div class="layout hidden" id="mongoLayout">
  <section class="panel">
    <h3>Databases</h3>
    <div class="toolbar">
      <button class="btn secondary" id="refreshOverview" type="button">Refresh</button>
    </div>
    <div id="databaseList" class="list"></div>
  </section>
  <section class="panel">
    <h3>Collections</h3>
    <div class="toolbar">
      <button class="btn secondary" id="refreshCollections" type="button">Refresh</button>
    </div>
    <div id="collectionList" class="list"></div>
  </section>
  <section class="panel">
    <h3>Documents And Shell</h3>
    <div class="stack">
      <div>
        <div class="toolbar">
          <button class="btn secondary" id="refreshDocuments" type="button">Load Documents</button>
        </div>
        <pre id="documentsOutput">Pick a collection to inspect documents.</pre>
      </div>
      <div>
        <div class="toolbar">
          <input id="mongoScript" type="text" value="db.adminCommand({ ping: 1 })">
          <button class="btn" id="runScript" type="button">Run Script</button>
        </div>
        <pre id="scriptOutput">Shell results will appear here.</pre>
      </div>
    </div>
  </section>
</div>
<script>
const state = {{
  auth: null,
  overview: [],
  selectedDb: "",
  collections: [],
  selectedCollection: "",
}};

const authStatus = document.getElementById("authStatus");
const loginShell = document.getElementById("loginShell");
const mongoLayout = document.getElementById("mongoLayout");
const logoutMongo = document.getElementById("logoutMongo");
const databaseList = document.getElementById("databaseList");
const collectionList = document.getElementById("collectionList");
const documentsOutput = document.getElementById("documentsOutput");
const scriptOutput = document.getElementById("scriptOutput");
const scriptInput = document.getElementById("mongoScript");

function setStatus(text, isError) {{
  authStatus.textContent = text;
  authStatus.className = "status" + (isError ? " error" : " ok");
}}

function credentialHeaders() {{
  if (!state.auth) return {{}};
  return {{
    "X-Mongo-Username": state.auth.username || "",
    "X-Mongo-Password": state.auth.password || "",
  }};
}}

async function getJson(url, options) {{
  const res = await fetch(url, {{
    ...options,
    headers: {{
      "X-Requested-With": "fetch",
      ...(options && options.headers ? options.headers : {{}}),
      ...credentialHeaders(),
    }},
  }});
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}}

function renderList(target, items, current, onClick, labelSelector) {{
  target.innerHTML = "";
  if (!items.length) {{
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No items found.";
    target.appendChild(empty);
    return;
  }}
  items.forEach((item) => {{
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "item" + (item === current ? " active" : "");
    btn.textContent = labelSelector(item);
    btn.addEventListener("click", () => onClick(item));
    target.appendChild(btn);
  }});
}}

async function loadOverview() {{
  const data = await getJson("/api/mongo/native/overview");
  state.overview = Array.isArray(data.databases) ? data.databases : [];
  renderList(databaseList, state.overview, state.selectedDb, async (name) => {{
    state.selectedDb = name;
    await loadCollections();
  }}, (name) => name);
}}

async function loadCollections() {{
  if (!state.selectedDb) {{
    state.collections = [];
    renderList(collectionList, [], "", () => {{}}, (name) => name);
    return;
  }}
  const data = await getJson(`/api/mongo/native/collections?database=${encodeURIComponent(state.selectedDb)}`);
  state.collections = Array.isArray(data.collections) ? data.collections : [];
  renderList(collectionList, state.collections, state.selectedCollection, async (name) => {{
    state.selectedCollection = name;
    await loadDocuments();
  }}, (name) => name);
}}

async function loadDocuments() {{
  if (!state.selectedDb || !state.selectedCollection) {{
    documentsOutput.textContent = "Pick a collection to inspect documents.";
    return;
  }}
  const data = await getJson(`/api/mongo/native/documents?database=${encodeURIComponent(state.selectedDb)}&collection=${encodeURIComponent(state.selectedCollection)}`);
  documentsOutput.textContent = JSON.stringify(data.documents || [], null, 2);
}}

async function runScript() {{
  const fd = new FormData();
  fd.append("script", scriptInput.value || "");
  const res = await fetch("/api/mongo/native/run", {{
    method: "POST",
    headers: {{
      "X-Requested-With": "fetch",
      ...credentialHeaders(),
    }},
    body: fd,
  }});
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Script failed");
  scriptOutput.textContent = String(data.output || "");
}}

async function login(username, password) {{
  state.auth = {{ username, password }};
  await loadOverview();
  loginShell.classList.add("hidden");
  mongoLayout.classList.remove("hidden");
  logoutMongo.classList.remove("hidden");
  setStatus("Connected to MongoDB.", false);
}}

document.getElementById("copyCompass").addEventListener("click", async () => {{
  const value = document.getElementById("compassUri").textContent || "";
  try {{
    await navigator.clipboard.writeText(value);
    alert("Compass URI copied.");
  }} catch (_) {{
    alert(value);
  }}
}});

document.getElementById("loginMongo").addEventListener("click", async () => {{
  const username = document.getElementById("mongoUser").value || "";
  const password = document.getElementById("mongoPassword").value || "";
  try {{
    await login(username, password);
  }} catch (err) {{
    setStatus(String(err), true);
  }}
}});

const continueMongoBtn = document.getElementById("continueMongo");
if (continueMongoBtn) {{
  continueMongoBtn.addEventListener("click", async () => {{
    try {{
      await login("", "");
    }} catch (err) {{
      setStatus(String(err), true);
    }}
  }});
}}

logoutMongo.addEventListener("click", () => {{
  state.auth = null;
  loginShell.classList.remove("hidden");
  mongoLayout.classList.add("hidden");
  logoutMongo.classList.add("hidden");
  setStatus("Logged out.", false);
}});

document.getElementById("refreshOverview").addEventListener("click", () => loadOverview().catch((err) => setStatus(String(err), true)));
document.getElementById("refreshCollections").addEventListener("click", () => loadCollections().catch((err) => setStatus(String(err), true)));
document.getElementById("refreshDocuments").addEventListener("click", () => loadDocuments().catch((err) => setStatus(String(err), true)));
document.getElementById("runScript").addEventListener("click", () => runScript().catch((err) => setStatus(String(err), true)));
</script>
</div></body></html>"""
