const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Dialog, DialogActions, DialogContent, DialogTitle, Drawer,
  FormControl, Grid, IconButton, InputLabel, LinearProgress, MenuItem, Paper, Select, Stack, TextField, Toolbar, Tooltip, Typography
} = MaterialUI;

const { ActionCard, NavCard } = (window.ServerInstallerUI && window.ServerInstallerUI.components) || {};
const { core = {}, utils = {}, actions = {} } = window.ServerInstallerUI || {};
const {
  cfg = { os: "windows", os_label: "Windows", message: "" },
  DownloadCompassIcon,
  CopyCompassIcon,
  TryOpenCompassIcon,
  OpenCompassStyleIcon,
  RefreshSmallIcon,
  StartAllIcon,
  StopAllIcon,
  DRAWER_W = 250,
  DRAWER_MIN = 82,
} = core;
const {
  clampPercent,
  defaultNotebookDirForOs,
  defaultPythonApiDirForOs,
  defaultWebsiteDirForOs,
  extractLabeledUrl,
  formatBytes,
  formatUptime,
  getSelectableIps,
  uniqUrls,
} = utils;
const {
  ActionIcon,
  formatServiceState,
  IconOnlyAction,
  isServiceRunningStatus,
  MiniMetric,
} = actions;

function App() {
  const isMobile = MaterialUI.useMediaQuery("(max-width:1100px)");
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [page, setPage] = React.useState("home");
  const [termText, setTermText] = React.useState("Ready. Click Start to run and stream output.");
  const [termState, setTermState] = React.useState("Idle");
  const [runError, setRunError] = React.useState("");
  const [termOpen, setTermOpen] = React.useState(false);
  const [termMin, setTermMin] = React.useState(false);
  const [termPos, setTermPos] = React.useState({ x: null, y: null });
  const [infoMessage, setInfoMessage] = React.useState("");
  const [systemInfo, setSystemInfo] = React.useState(null);
  const [systemErr, setSystemErr] = React.useState("");
  const [loadingSystem, setLoadingSystem] = React.useState(true);
  const [portValue, setPortValue] = React.useState("8090");
  const [portProtocol, setPortProtocol] = React.useState("tcp");
  const [portBusy, setPortBusy] = React.useState(false);
  const [serviceBusy, setServiceBusy] = React.useState(false);
  const [scopeLoading, setScopeLoading] = React.useState({ all: false, mongo: false, s3: false, dotnet: false, docker: false, proxy: false, python: false, website: false });
  const [scopeErrors, setScopeErrors] = React.useState({ all: "", mongo: "", s3: "", dotnet: "", docker: "", proxy: "", python: "", website: "" });
  const [serviceFilter, setServiceFilter] = React.useState("");
  const [services, setServices] = React.useState([]);
  const [mongoPageServices, setMongoPageServices] = React.useState([]);
  const [s3PageServices, setS3PageServices] = React.useState([]);
  const [dotnetPageServices, setDotnetPageServices] = React.useState([]);
  const [dockerPageServices, setDockerPageServices] = React.useState([]);
  const [proxyPageServices, setProxyPageServices] = React.useState([]);
  const [pythonPageServices, setPythonPageServices] = React.useState([]);
  const [websitePageServices, setWebsitePageServices] = React.useState([]);
  const [mongoInfoState, setMongoInfoState] = React.useState(null);
  const [s3InfoState, setS3InfoState] = React.useState(null);
  const [dotnetInfoState, setDotnetInfoState] = React.useState(null);
  const [dockerInfoState, setDockerInfoState] = React.useState(null);
  const [proxyInfoState, setProxyInfoState] = React.useState(null);
  const [pythonInfoState, setPythonInfoState] = React.useState(null);
  const [websiteInfoState, setWebsiteInfoState] = React.useState(null);
  const [pythonApiEditor, setPythonApiEditor] = React.useState(null);
  const [pythonApiEditorSeed, setPythonApiEditorSeed] = React.useState(0);
  const [updateSourceDlg, setUpdateSourceDlg] = React.useState(null);
  const [websiteEditor, setWebsiteEditor] = React.useState(null);
  const [websiteEditorSeed, setWebsiteEditorSeed] = React.useState(0);
  const [fileManagerPath, setFileManagerPath] = React.useState("");
  const [fileManagerData, setFileManagerData] = React.useState(null);
  const [fileManagerLoading, setFileManagerLoading] = React.useState(false);
  const [fileManagerError, setFileManagerError] = React.useState("");
  const [fileEditorPath, setFileEditorPath] = React.useState("");
  const [fileEditorContent, setFileEditorContent] = React.useState("");
  const [fileEditorMeta, setFileEditorMeta] = React.useState(null);
  const [fileEditorDirty, setFileEditorDirty] = React.useState(false);
  const [fileOpBusy, setFileOpBusy] = React.useState(false);
  const [netRate, setNetRate] = React.useState({ rxBps: 0, txBps: 0 });
  const prevNetRef = React.useRef(null);
  const pageHistoryRef = React.useRef(["home"]);
  const historyBackRef = React.useRef(false);
  const fileManagerInitRef = React.useRef(false);
  const drag = React.useRef({ active: false, sx: 0, sy: 0, bx: 0, by: 0 });
  const selectableIps = React.useMemo(() => getSelectableIps(systemInfo), [systemInfo]);

  React.useEffect(() => {
    const onMove = (e) => {
      if (!drag.current.active) return;
      setTermPos({
        x: Math.max(8, drag.current.bx + (e.clientX - drag.current.sx)),
        y: Math.max(8, drag.current.by + (e.clientY - drag.current.sy)),
      });
    };
    const onUp = () => { drag.current.active = false; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const append = (line) => setTermText((prev) => `${prev}\n${line}`);
  const setScopeLoadingFlag = React.useCallback((scope, value) => {
    setScopeLoading((prev) => ({ ...prev, [scope]: value }));
  }, []);
  const setScopeErrorText = React.useCallback((scope, value) => {
    setScopeErrors((prev) => ({ ...prev, [scope]: value }));
  }, []);
  const isScopeLoading = React.useCallback((scope) => !!scopeLoading?.[scope], [scopeLoading]);

  const loadSystem = React.useRef(async () => {});
  loadSystem.current = async () => {
    try {
      setScopeLoadingFlag("all", true);
      setSystemErr("");
      setScopeErrorText("all", "");
      const r = await fetch("/api/system/status?scope=all", { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      const st = j.status || null;
      if (st && st.network_totals && Number.isFinite(st.network_totals.rx_bytes) && Number.isFinite(st.network_totals.tx_bytes)) {
        const now = Date.now();
        const prev = prevNetRef.current;
        if (prev) {
          const dt = Math.max(1, (now - prev.ts) / 1000);
          const rxBps = Math.max(0, (st.network_totals.rx_bytes - prev.rx) / dt);
          const txBps = Math.max(0, (st.network_totals.tx_bytes - prev.tx) / dt);
          setNetRate({ rxBps, txBps });
        }
        prevNetRef.current = { rx: st.network_totals.rx_bytes, tx: st.network_totals.tx_bytes, ts: now };
      }
      setSystemInfo(st);
    } catch (err) {
      const msg = String(err);
      setSystemErr(msg);
      setScopeErrorText("all", msg);
    } finally {
      setScopeLoadingFlag("all", false);
      setLoadingSystem(false);
    }
  };

  const loadScopedStatus = React.useCallback(async (scope, setter) => {
    setScopeLoadingFlag(scope, true);
    setScopeErrorText(scope, "");
    try {
      const r = await fetch(`/api/system/status?scope=${encodeURIComponent(scope)}`, { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setter(j.status || null);
    } catch (err) {
      setScopeErrorText(scope, String(err));
      setter(null);
    } finally {
      setScopeLoadingFlag(scope, false);
    }
  }, [setScopeErrorText, setScopeLoadingFlag]);

  React.useEffect(() => {
    const generalPage = page === "home" || page === "sysinfo" || page === "ports" || page === "services";
    if (!generalPage) return undefined;
    loadSystem.current();
    const t = setInterval(() => loadSystem.current(), 10000);
    return () => clearInterval(t);
  }, [page, setScopeErrorText, setScopeLoadingFlag]);

  React.useEffect(() => {
    const history = pageHistoryRef.current;
    if (historyBackRef.current) {
      historyBackRef.current = false;
      if (history.length > 1) history.pop();
      if (history[history.length - 1] !== page) {
        history.push(page);
      }
      return;
    }
    if (history[history.length - 1] !== page) {
      history.push(page);
    }
  }, [page]);

  const loadServices = React.useRef(async () => {});
  const loadMongoServices = React.useRef(async () => {});
  const loadS3Services = React.useRef(async () => {});
  const loadDotnetServices = React.useRef(async () => {});
  const loadDockerServices = React.useRef(async () => {});
  const loadProxyServices = React.useRef(async () => {});
  const loadPythonServices = React.useRef(async () => {});
  const loadWebsiteServices = React.useRef(async () => {});
  const loadMongoInfo = React.useRef(async () => {});
  const loadS3Info = React.useRef(async () => {});
  const loadDotnetInfo = React.useRef(async () => {});
  const loadDockerInfo = React.useRef(async () => {});
  const loadProxyInfo = React.useRef(async () => {});
  const loadPythonInfo = React.useRef(async () => {});
  const loadWebsiteInfo = React.useRef(async () => {});

  const loadServiceScope = React.useCallback(async (scope, setter) => {
    setScopeLoadingFlag(scope, true);
    setScopeErrorText(scope, "");
    try {
      const r = await fetch(`/api/system/services?scope=${encodeURIComponent(scope)}`, { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setter(Array.isArray(j.services) ? j.services : []);
    } catch (err) {
      setScopeErrorText(scope, String(err));
      setter([]);
    } finally {
      setScopeLoadingFlag(scope, false);
    }
  }, [setScopeErrorText, setScopeLoadingFlag]);

  loadServices.current = async () => {
    setScopeLoadingFlag("all", true);
    setScopeErrorText("all", "");
    try {
      const r = await fetch("/api/system/services?scope=all", { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setServices(Array.isArray(j.services) ? j.services : []);
    } catch (err) {
      setScopeErrorText("all", String(err));
      setServices([]);
    } finally {
      setScopeLoadingFlag("all", false);
    }
  };

  loadMongoServices.current = async () => loadServiceScope("mongo", setMongoPageServices);
  loadS3Services.current = async () => loadServiceScope("s3", setS3PageServices);
  loadDotnetServices.current = async () => loadServiceScope("dotnet", setDotnetPageServices);
  loadDockerServices.current = async () => loadServiceScope("docker", setDockerPageServices);
  loadProxyServices.current = async () => loadServiceScope("proxy", setProxyPageServices);
  loadPythonServices.current = async () => loadServiceScope("python", setPythonPageServices);
  loadWebsiteServices.current = async () => loadServiceScope("website", setWebsitePageServices);
  loadMongoInfo.current = async () => loadScopedStatus("mongo", setMongoInfoState);
  loadS3Info.current = async () => loadScopedStatus("s3", setS3InfoState);
  loadDotnetInfo.current = async () => loadScopedStatus("dotnet", setDotnetInfoState);
  loadDockerInfo.current = async () => loadScopedStatus("docker", setDockerInfoState);
  loadProxyInfo.current = async () => loadScopedStatus("proxy", setProxyInfoState);
  loadPythonInfo.current = async () => loadScopedStatus("python", setPythonInfoState);
  loadWebsiteInfo.current = async () => loadScopedStatus("website", setWebsiteInfoState);

  const refreshPageServices = React.useCallback((targetPage) => {
    if (targetPage === "services") return loadServices.current();
    if (targetPage === "mongo" || String(targetPage || "").startsWith("mongo-")) return loadMongoServices.current();
    if (targetPage === "s3") return loadS3Services.current();
    if (targetPage === "docker") return loadDockerServices.current();
    if (targetPage === "proxy") return loadProxyServices.current();
    if (targetPage === "python" || String(targetPage || "").startsWith("python-")) return loadPythonServices.current();
    if (targetPage === "website") return loadWebsiteServices.current();
    if (targetPage === "dotnet" || targetPage === "dotnet-docker" || targetPage === "dotnet-linux") return Promise.all([loadDotnetServices.current(), loadDockerServices.current()]);
    if (String(targetPage || "").startsWith("dotnet-")) return loadDotnetServices.current();
    return Promise.resolve();
  }, []);

  const refreshPageStatus = React.useCallback((targetPage) => {
    if (targetPage === "mongo" || String(targetPage || "").startsWith("mongo-")) return loadMongoInfo.current();
    if (targetPage === "s3") return loadS3Info.current();
    if (targetPage === "docker") return loadDockerInfo.current();
    if (targetPage === "proxy") return loadProxyInfo.current();
    if (targetPage === "python" || String(targetPage || "").startsWith("python-")) return loadPythonInfo.current();
    if (targetPage === "website") return loadWebsiteInfo.current();
    if (targetPage === "dotnet" || String(targetPage || "").startsWith("dotnet-")) return loadDotnetInfo.current();
    if (targetPage === "home" || targetPage === "api" || targetPage === "sysinfo" || targetPage === "ports" || targetPage === "services") return loadSystem.current();
    return Promise.resolve();
  }, []);

  const refreshPageContext = React.useCallback((targetPage) => {
    return Promise.all([refreshPageStatus(targetPage), refreshPageServices(targetPage)]);
  }, [refreshPageServices, refreshPageStatus]);

  React.useEffect(() => {
    if (page === "services" || page === "dotnet" || page === "s3" || page === "mongo" || String(page).startsWith("mongo-") || page === "docker" || page === "proxy" || page === "python" || page === "website" || String(page).startsWith("dotnet-") || String(page).startsWith("python-")) {
      refreshPageContext(page);
    }
  }, [page, refreshPageContext]);

  React.useEffect(() => {
    if (!(page === "services" || page === "dotnet" || page === "s3" || page === "mongo" || String(page).startsWith("mongo-") || page === "docker" || page === "proxy" || page === "python" || page === "website" || String(page).startsWith("dotnet-") || String(page).startsWith("python-"))) {
      return undefined;
    }
    const t = setInterval(() => {
      refreshPageContext(page);
    }, 10000);
    return () => clearInterval(t);
  }, [page, refreshPageContext]);

  React.useEffect(() => {
    const hook = (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (payload.open) setTermOpen(true);
      if (payload.state) setTermState(payload.state);
      if (payload.line) append(payload.line);
    };
    window.ServerInstallerTerminalHook = hook;
    return () => {
      if (window.ServerInstallerTerminalHook === hook) {
        delete window.ServerInstallerTerminalHook;
      }
    };
  }, []);

  const poll = async (jobId, title, offset = 0) => {
    try {
      const r = await fetch(`/job/${jobId}?offset=${offset}`, { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (j.output) append(j.output);
      const next = j.next_offset || offset;
      if (j.done) {
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code})`);
        if (title === "Dashboard Update") {
          if (Number(j.exit_code) === 0) {
            append("[INFO] Dashboard is restarting. Page will reload automatically in 15 seconds...");
            setInfoMessage("Dashboard updated. Reloading in 15 seconds...");
          } else {
            setRunError(`${title} failed (exit ${j.exit_code}). Check Web Terminal output for details.`);
            setInfoMessage("Dashboard update failed. Check the terminal for details.");
          }
          setTermState("Idle");
          setTimeout(() => window.location.reload(), 15000);
          return;
        }
        if (Number(j.exit_code) !== 0) {
          setRunError(`${title} failed (exit ${j.exit_code}). Check Web Terminal output for details.`);
        }
        setTermState("Idle");
        refreshPageContext(page);
        loadSystem.current();
        return;
      }
      setTimeout(() => poll(jobId, title, next), 300);
    } catch (err) {
      if (title === "Dashboard Update") {
        append(`Update triggered. Dashboard is restarting... (${err})`);
        setInfoMessage("Dashboard update started. Reloading in 15 seconds...");
        setTermState("Idle");
        setTimeout(() => window.location.reload(), 15000);
        return;
      }
      append(`Polling failed: ${err}`);
      setTermState("Error");
    }
  };

  const run = async (event, action, title, formElement = null) => {
    event.preventDefault();
    const formTarget = formElement || event.currentTarget || event.target;
    const body = new FormData(formTarget);
    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    const isS3Install = action === "/run/s3_linux" || action === "/run/s3_windows" || action === "/run/s3_windows_iis" || action === "/run/s3_windows_docker";
    const isMongoInstall = action === "/run/mongo_windows" || action === "/run/mongo_unix";
    const isPythonInstall = action === "/run/python_install";
    setRunError("");
    if (isS3Install) {
      const selectedIp = String(body.get("LOCALS3_HOST_IP") || "").trim();
      if (!selectedIp && selectableIps.length > 1) {
        const msg = "Select an IP address before starting S3 setup.";
        setRunError(msg);
        setInfoMessage(msg);
        setTermState("Error");
        append(msg);
        return;
      }
      const resolvedHost = selectedIp || (selectableIps.length === 1 ? selectableIps[0] : "localhost");
      body.set("LOCALS3_HOST", resolvedHost);
      if (selectedIp) {
        body.set("LOCALS3_HOST_IP", selectedIp);
      }
      if (action === "/run/s3_linux" && !String(body.get("LOCALS3_CONSOLE_PORT") || "").trim()) {
        body.set("LOCALS3_CONSOLE_PORT", "9443");
      }

      // Strict pre-check: do not start if port is owned by another app.
      const p = String(body.get("LOCALS3_HTTPS_PORT") || "").trim();
      if (p && cfg.os !== "windows") {
        const fd = new FormData();
        fd.append("port", p);
        fd.append("protocol", "tcp");
        const chk = await fetch("/api/system/port_check", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
        const pj = await chk.json();
        if (pj.ok && pj.busy && !pj.managed_owner) {
          const busyMsg = `S3 HTTPS port ${p} is already in use by another service. Choose a different port.`;
          setRunError(busyMsg);
          setInfoMessage(busyMsg);
          append(`[${new Date().toLocaleTimeString()}] ${title} cancelled (${busyMsg})`);
          setTermState("Idle");
          return;
        }
        if (pj.ok && pj.busy && pj.managed_owner) {
          const ownMsg = `Port ${p} is used by existing S3 (${pj.owner_hint || "managed service"}). Proceeding to update/reclaim on the same port.`;
          setInfoMessage(ownMsg);
          append(ownMsg);
        }
      }
    }
    if (isMongoInstall) {
      const selectedIp = String(body.get("LOCALMONGO_HOST_IP") || "").trim();
      if (!selectedIp && selectableIps.length > 1) {
        const msg = "Select an IP address before starting MongoDB setup.";
        setRunError(msg);
        setInfoMessage(msg);
        setTermState("Error");
        append(msg);
        return;
      }
      if (selectedIp) {
        body.set("LOCALMONGO_HOST", selectedIp);
      } else if (selectableIps.length === 1) {
        body.set("LOCALMONGO_HOST", selectableIps[0]);
      }
    }
    try {
      const r = await fetch(action, { method: "POST", headers: { "X-Requested-With": "fetch" }, body });
      const j = await r.json();
      if (!j.job_id) {
        append(j.output || "No output.");
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code ?? 1})`);
        if (Number(j.exit_code ?? 1) !== 0) {
          setRunError(`${title} failed (exit ${j.exit_code ?? 1}). ${String(j.output || "").slice(0, 200)}`);
        }
        setTermState("Idle");
        refreshPageContext(page);
        loadSystem.current();
        return;
      }
      poll(j.job_id, title, 0);
    } catch (err) {
      append(`Request failed: ${err}`);
      setRunError(`${title} request failed: ${err}`);
      setTermState("Error");
    }
  };

  const runDashboardUpdate = async () => {
    const title = "Dashboard Update";
    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    setRunError("");
    try {
      const r = await fetch("/run/dashboard_update", { method: "POST", headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.job_id) {
        append(j.output || "No output.");
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code ?? 1})`);
        if (Number(j.exit_code ?? 1) !== 0) {
          setRunError(`${title} failed (exit ${j.exit_code ?? 1}). ${String(j.output || "").slice(0, 200)}`);
        }
        setTermState("Idle");
        loadSystem.current();
        return;
      }
      poll(j.job_id, title, 0);
    } catch (err) {
      // Update restarts the dashboard process; the fetch can fail mid-flight.
      append(`Update triggered. Dashboard is restarting... (${err})`);
      setInfoMessage("Dashboard update started. If the page disconnects, refresh in a few seconds.");
      setTermState("Idle");
      setTimeout(() => window.location.reload(), 4000);
    }
  };

  const runPythonInstallWithCurrentSettings = async () => {
    const title = `Python Installer (${cfg.os === "windows" ? "Windows" : "Linux/macOS"})`;
    const body = new FormData();
    const selectedHost = String(pythonService.host || "").trim() || (selectableIps.length === 1 ? selectableIps[0] : "");
    const selectedVersion = String(pythonService.requested_version || pythonService.python_version || "3.12").trim() || "3.12";
    const selectedPort = String(pythonService.jupyter_port || "8888").trim() || "8888";
    const selectedNotebookDir = String(
      pythonService.notebook_dir || pythonService.default_notebook_dir || defaultNotebookDirForOs(cfg.os)
    ).trim() || defaultNotebookDirForOs(cfg.os);
    body.set("PYTHON_VERSION", selectedVersion);
    body.set("PYTHON_INSTALL_JUPYTER", "1");
    body.set("PYTHON_JUPYTER_PORT", selectedPort);
    body.set("PYTHON_NOTEBOOK_DIR", selectedNotebookDir);
    if (selectedHost) body.set("PYTHON_HOST_IP", selectedHost);

    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    setRunError("");
    try {
      const r = await fetch("/run/python_install", { method: "POST", headers: { "X-Requested-With": "fetch" }, body });
      const j = await r.json();
      if (!j.job_id) {
        append(j.output || "No output.");
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code ?? 1})`);
        if (Number(j.exit_code ?? 1) !== 0) {
          setRunError(`${title} failed (exit ${j.exit_code ?? 1}). ${String(j.output || "").slice(0, 200)}`);
        }
        setTermState("Idle");
        refreshPageContext(page);
        loadSystem.current();
        return;
      }
      poll(j.job_id, title, 0);
    } catch (err) {
      append(`Request failed: ${err}`);
      setRunError(`${title} request failed: ${err}`);
      setTermState("Error");
    }
  };

  const goBack = () => {
    if (page === "home") return;
    const history = pageHistoryRef.current;
    const previousPage = history.length > 1 ? history[history.length - 2] : "home";
    historyBackRef.current = true;
    setPage(previousPage || "home");
  };

  const headerTitle = (() => {
    if (page === "home") return "Dashboard";
    if (page === "api") return "API";
    if (page === "dotnet") return "DotNet";
    if (page === "s3") return "S3";
    if (page === "mongo") return "MongoDB";
    if (page === "mongo-native") return "MongoDB > Native";
    if (page === "mongo-docker") return "MongoDB > Docker";
    if (page === "docker") return "Docker";
    if (page === "proxy") return "Proxy";
    if (page === "python") return "Python";
    if (page === "website") return "Websites";
    if (page === "ssl") return "SSL & Certificates";
    if (page === "files") return "File Manager";
    if (page === "python-api") return "Python > API";
    if (page === "python-system") return "Python > OS Service";
    if (page === "python-docker") return "Python > Docker";
    if (page === "python-iis") return "Python > IIS";
    if (page === "sysinfo") return "SysInfo";
    if (page === "ports") return "Port Management";
    if (page === "services") return "Service Manager";
    if (page === "dotnet-iis") return "DotNet > IIS";
    if (page === "dotnet-docker") return "DotNet > Docker";
    if (page === "dotnet-linux") return "DotNet > Linux";
    return "Dashboard";
  })();

  const onPortAction = async (action) => {
    if (!portValue) return;
    setPortBusy(true);
    try {
      const fd = new FormData();
      fd.append("action", action);
      fd.append("port", String(portValue).trim());
      fd.append("protocol", portProtocol);
      const r = await fetch("/api/system/port", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.message || "Port action failed.");
      setInfoMessage(j.message || `Port ${action} done.`);
      loadSystem.current();
    } catch (err) {
      setInfoMessage(`Port ${action} failed: ${err}`);
    } finally {
      setPortBusy(false);
    }
  };

  const onServicePortAction = async (svc, portItem, action) => {
    if (!portItem || !portItem.port) return;
    setServiceBusy(true);
    try {
      const fd = new FormData();
      fd.append("action", action);
      fd.append("port", String(portItem.port));
      fd.append("protocol", portItem.protocol || "tcp");
      const r = await fetch("/api/system/port", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.message || "Port action failed.");
      setInfoMessage(j.message || `Port ${action} completed.`);
    } catch (err) {
      setInfoMessage(`Port ${action} failed: ${err}`);
    } finally {
      setServiceBusy(false);
    }
  };

  const renderServiceUrls = (svc) => {
    const urls = Array.isArray(svc?.urls) ? svc.urls : [];
    if (urls.length === 0) return null;
    return (
      <Box sx={{ mt: 0.6 }}>
        {urls.map((u) => (
          <Stack key={`${svc.name}-${u}`} direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.4 }}>
            <Typography variant="caption" sx={{ display: "block", color: "text.secondary", wordBreak: "break-all" }}>{u}</Typography>
            <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => window.open(u, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none", minWidth: 56 }}>Open</Button>
          </Stack>
        ))}
      </Box>
    );
  };

  const renderServicePorts = () => null;

  const onServiceAction = async (action, svc) => {
    if (!svc || !svc.name) return;
    if (action === "stop" || action === "delete") {
      const prompt = action === "delete" && String(svc.kind || "").toLowerCase() === "python_version"
        ? `Do you want to hide detected Python '${svc.detail || svc.sub_status || svc.name}' from the dashboard?`
        : `Do you want to ${action === "delete" ? "delete" : "stop"} '${svc.name}'?`;
      const ok = window.confirm(prompt);
      if (!ok) return;
    }
    setServiceBusy(true);
    try {
      const body = new URLSearchParams();
      body.set("action", action);
      body.set("name", svc.name);
      body.set("kind", svc.kind || "service");
      body.set("detail", svc.detail || svc.sub_status || "");
      const r = await fetch("/api/system/service", {
        method: "POST",
        headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.message || "Service action failed.");
      setInfoMessage(j.message || `${action} completed.`);
      await Promise.all([
        loadServices.current(),
        loadMongoInfo.current(),
        loadMongoServices.current(),
        loadS3Info.current(),
        loadS3Services.current(),
        loadProxyInfo.current(),
        loadProxyServices.current(),
        loadPythonInfo.current(),
        loadPythonServices.current(),
        loadWebsiteInfo.current(),
        loadWebsiteServices.current(),
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
        loadDockerInfo.current(),
        loadDockerServices.current(),
      ]);
      loadSystem.current();
    } catch (err) {
      setInfoMessage(`Service ${action} failed: ${err}`);
    } finally {
      setServiceBusy(false);
    }
  };

  const stopServicesBatch = async (items, label) => {
    const isRunning = (svc) => /running|active|up/i.test(String(svc?.status || ""));
    const list = (items || []).filter((x) => x && x.name && isRunning(x));
    if (list.length === 0) {
      setInfoMessage(`No running ${label} services found to stop.`);
      return;
    }
    const ok = window.confirm(`Do you want to stop all running ${label} services (${list.length})?`);
    if (!ok) return;
    setServiceBusy(true);
    try {
      let okCount = 0;
      let failCount = 0;
      const failed = [];
      for (const svc of list) {
        try {
          const body = new URLSearchParams();
          body.set("action", "stop");
          body.set("name", svc.name);
          body.set("kind", svc.kind || "service");
          body.set("detail", svc.detail || svc.sub_status || "");
          const r = await fetch("/api/system/service", {
            method: "POST",
            headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
            body: body.toString(),
          });
          const j = await r.json();
          if (j.ok) okCount += 1;
          else { failCount += 1; failed.push(`${svc.name}: ${j.message || "failed"}`); }
        } catch (_) {
          failCount += 1;
          failed.push(`${svc.name}: request failed`);
        }
      }
      if (failed.length > 0) {
        setInfoMessage(`Stop ${label}: ${okCount} success, ${failCount} failed. ${failed.slice(0, 3).join(" | ")}`);
      } else {
        setInfoMessage(`Stop ${label}: ${okCount} success, ${failCount} failed.`);
      }
      await Promise.all([
        loadServices.current(),
        loadMongoInfo.current(),
        loadMongoServices.current(),
        loadS3Info.current(),
        loadS3Services.current(),
        loadProxyInfo.current(),
        loadProxyServices.current(),
        loadPythonInfo.current(),
        loadPythonServices.current(),
        loadWebsiteInfo.current(),
        loadWebsiteServices.current(),
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
        loadDockerInfo.current(),
        loadDockerServices.current(),
      ]);
      loadSystem.current();
    } finally {
      setServiceBusy(false);
    }
  };

  const batchServiceAction = async (items, label, action) => {
    const isRunning = (svc) => /running|active|up/i.test(String(svc?.status || ""));
    const list = (items || []).filter((x) => x && x.name && (action === "start" ? !isRunning(x) : isRunning(x)));
    if (list.length === 0) {
      setInfoMessage(`No ${action === "start" ? "stopped" : "running"} ${label} services found to ${action}.`);
      return;
    }
    const ok = window.confirm(`Do you want to ${action} all ${label} services (${list.length})?`);
    if (!ok) return;
    setServiceBusy(true);
    try {
      let okCount = 0;
      let failCount = 0;
      const failed = [];
      for (const svc of list) {
        try {
          const body = new URLSearchParams();
          body.set("action", action);
          body.set("name", svc.name);
          body.set("kind", svc.kind || "service");
          body.set("detail", svc.detail || svc.sub_status || "");
          const r = await fetch("/api/system/service", {
            method: "POST",
            headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
            body: body.toString(),
          });
          const j = await r.json();
          if (j.ok) okCount += 1;
          else { failCount += 1; failed.push(`${svc.name}: ${j.message || "failed"}`); }
        } catch (_) {
          failCount += 1;
          failed.push(`${svc.name}: request failed`);
        }
      }
      if (failed.length > 0) {
        setInfoMessage(`${actionLabel(action)} ${label}: ${okCount} success, ${failCount} failed. ${failed.slice(0, 3).join(" | ")}`);
      } else {
        setInfoMessage(`${actionLabel(action)} ${label}: ${okCount} success, ${failCount} failed.`);
      }
      await Promise.all([
        loadServices.current(),
        loadMongoInfo.current(),
        loadMongoServices.current(),
        loadS3Info.current(),
        loadS3Services.current(),
        loadProxyInfo.current(),
        loadProxyServices.current(),
        loadPythonInfo.current(),
        loadPythonServices.current(),
        loadWebsiteInfo.current(),
        loadWebsiteServices.current(),
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
        loadDockerInfo.current(),
        loadDockerServices.current(),
      ]);
      loadSystem.current();
    } finally {
      setServiceBusy(false);
    }
  };

  const hasStoppedServices = React.useCallback((items) => {
    return (items || []).some((svc) => !isServiceRunningStatus(svc?.status, svc?.sub_status));
  }, []);

  const onProxyServiceAction = async (action, svc) => {
    if (!svc?.name) return;
    if (action === "stop" || action === "delete") {
      const verb = action === "delete" ? "delete" : "stop";
      const ok = window.confirm(`Do you want to ${verb} '${svc.name}'?`);
      if (!ok) return;
    }
    setServiceBusy(true);
    try {
      const body = new URLSearchParams();
      body.set("action", action);
      body.set("name", svc.name);
      const r = await fetch("/api/proxy/service", {
        method: "POST",
        headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.message || "Proxy service action failed.");
      setInfoMessage(j.message || `${action} completed.`);
      await Promise.all([loadProxyInfo.current(), loadProxyServices.current()]);
    } catch (err) {
      setInfoMessage(`Proxy ${action} failed: ${err}`);
    } finally {
      setServiceBusy(false);
    }
  };

  const actionLabel = (action) => {
    if (action === "autostart_on") return "Auto-start ON";
    if (action === "autostart_off") return "Auto-start OFF";
    return action.charAt(0).toUpperCase() + action.slice(1);
  };

  const openPythonApiRun = React.useCallback((svc) => {
    if (!svc) return;
    const targetPage = svc.target_page || (svc.kind === "docker" ? "python-docker" : (svc.kind === "iis_site" ? "python-iis" : "python-system"));
    setPythonApiEditor({
      targetPage,
      name: String(svc.form_name || svc.name || "").trim(),
      host: String(svc.host || "").trim(),
      port: String(svc.port_value || (Array.isArray(svc.ports) && svc.ports[0] ? svc.ports[0].port : "") || "").trim(),
      source: String(svc.project_path || "").trim(),
      mainFile: String(svc.main_file || svc.detail || "").trim(),
      serviceLog: String(svc.service_log || "").trim(),
    });
    setPythonApiEditorSeed((prev) => prev + 1);
    setPage(targetPage);
  }, [cfg.os]);

  const runPythonApiUpdateSource = React.useCallback(async (svc, sourcePath) => {
    const title = "Update API Files";
    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started for ${svc.form_name || svc.name}`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    setRunError("");
    try {
      const fd = new FormData();
      fd.append("service_name", svc.form_name || svc.name);
      fd.append("source_path", sourcePath);
      const r = await fetch("/run/python_api_update_source", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.job_id) {
        append(j.output || "No output.");
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code ?? 1})`);
        if (Number(j.exit_code ?? 1) !== 0) setRunError(`${title} failed. Check terminal output.`);
        setTermState("Idle");
        Promise.all([loadPythonInfo.current(), loadPythonServices.current()]);
        return;
      }
      poll(j.job_id, title, 0);
    } catch (err) {
      append(`Error: ${err}`);
      setTermState("Error");
    }
  }, []);

  const startNewPythonApiDeployment = React.useCallback((targetPage) => {
    setPythonApiEditor(null);
    setPythonApiEditorSeed((prev) => prev + 1);
    setPage(targetPage);
  }, []);

  const openWebsiteRun = React.useCallback((svc) => {
    if (!svc) return;
    setWebsiteEditor({
      name: String(svc.form_name || svc.name || "").trim(),
      host: String(svc.host || "").trim(),
      port: String(svc.port_value || (Array.isArray(svc.ports) && svc.ports[0] ? svc.ports[0].port : "") || "").trim(),
      source: String(svc.project_path || svc.deploy_root || "").trim(),
      kind: String(svc.kind_value || "auto").trim(),
      target: String(svc.target_value || "service").trim(),
    });
    setWebsiteEditorSeed((prev) => prev + 1);
    setPage("website");
  }, []);

  const startNewWebsiteDeployment = React.useCallback(() => {
    setWebsiteEditor(null);
    setWebsiteEditorSeed((prev) => prev + 1);
    setPage("website");
  }, []);

  const renderPythonApiRunsCard = React.useCallback(() => (
    <Grid item xs={12}>
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
            <Typography variant="h6" fontWeight={800}>API Runs</Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button variant="outlined" disabled={isScopeLoading("python")} onClick={() => Promise.all([loadPythonInfo.current(), loadPythonServices.current()])} sx={{ textTransform: "none" }}>
              Refresh
            </Button>
          </Stack>
          <Box sx={{ mt: 1.2, maxHeight: 360, overflow: "auto" }}>
            {pythonApiRuns.length === 0 && <Typography variant="body2">No Python API runs found yet.</Typography>}
            {pythonApiRuns.map((svc) => (
              <Paper key={`python-api-run-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Box sx={{ minWidth: 280 }}>
                    <Typography variant="body2"><b>{svc.form_name || svc.name}</b> ({svc.kind})</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                      Project: {svc.project_path || "-"}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                      Main file: {svc.main_file || "-"}
                    </Typography>
                    {!!svc.service_log && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", wordBreak: "break-all" }}>
                        Runtime log: {svc.service_log}
                      </Typography>
                    )}
                    {renderServiceUrls(svc)}
                    {renderServicePorts(svc)}
                  </Box>
                  <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                  <Box sx={{ flexGrow: 1 }} />
                  <Button size="small" variant="contained" disabled={serviceBusy} onClick={() => setUpdateSourceDlg({ svc, path: "" })} sx={{ textTransform: "none" }}>
                    Update Files
                  </Button>
                  {svc.manageable !== false && (
                    <>
                      <Button
                        size="small"
                        variant="outlined"
                        color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"}
                        disabled={serviceBusy}
                        onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)}
                        sx={{ textTransform: "none" }}
                      >
                        {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                      </Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>
                        Restart
                      </Button>
                    </>
                  )}
                  {svc.deletable && (
                    <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>
                      Delete
                    </Button>
                  )}
                </Stack>
              </Paper>
            ))}
          </Box>
        </CardContent>
      </Card>
    </Grid>
  ), [isScopeLoading, openPythonApiRun, onServiceAction, pythonApiRuns, renderServicePorts, renderServiceUrls, serviceBusy]);

  const software = systemInfo?.software || {};
  const mongoStatusInfo = mongoInfoState || systemInfo || {};
  const dotnetStatusInfo = dotnetInfoState || systemInfo || {};
  const dockerStatusInfo = dockerInfoState || systemInfo || {};
  const proxyStatusInfo = proxyInfoState || systemInfo || {};
  const pythonStatusInfo = pythonInfoState || systemInfo || {};
  const websiteStatusInfo = websiteInfoState || systemInfo || {};
  const mongoSoftware = mongoStatusInfo?.software || {};
  const dotnetSoftware = dotnetStatusInfo?.software || {};
  const dockerSoftware = dockerStatusInfo?.software || {};
  const proxySoftware = proxyStatusInfo?.software || {};
  const pythonSoftware = pythonStatusInfo?.software || {};
  const websiteSoftware = websiteStatusInfo?.software || {};
  const dotnet = dotnetSoftware.dotnet || software.dotnet || {};
  const docker = dockerSoftware.docker || software.docker || {};
  const mongoDocker = mongoSoftware.docker || software.docker || {};
  const iis = software.iis || {};
  const mongo = mongoSoftware.mongo || software.mongo || {};
  const proxy = proxySoftware.proxy || software.proxy || {};
  const pythonService = pythonSoftware.python_service || software.python_service || {};
  const websiteInfo = websiteSoftware.website || software.website || {};
  const listeningPorts = systemInfo?.listening_ports || [];
  const cpuPercent = clampPercent(systemInfo?.cpu_usage_percent ?? ((systemInfo?.load?.["1m"] && systemInfo?.cpu_count) ? (systemInfo.load["1m"] / systemInfo.cpu_count) * 100 : 0));
  const memoryPercent = clampPercent(systemInfo?.memory?.used_percent);
  const netBps = (netRate.rxBps || 0) + (netRate.txBps || 0);
  const netPercent = clampPercent((netBps / (20 * 1024 * 1024)) * 100);

  const apiAddressList = React.useMemo(() => {
    const ips = systemInfo?.ips || [];
    const portSet = new Set((listeningPorts || []).map((p) => Number(p.port)));
    const common = [80, 443, 2375, 2376, 5000, 5001, 8080, 8090, 8443, 9000];
    const found = common.filter((p) => portSet.has(p));
    const urls = [];
    ips.forEach((ip) => {
      found.forEach((p) => {
        if (p === 80) urls.push(`http://${ip}`);
        else if (p === 443) urls.push(`https://${ip}`);
        else urls.push(`http://${ip}:${p}`);
      });
    });
    urls.push(`${window.location.origin}/api/system/status`);
    return Array.from(new Set(urls));
  }, [systemInfo, listeningPorts]);

  const filteredServices = React.useMemo(() => {
    const q = (serviceFilter || "").trim().toLowerCase();
    if (!q) return services;
    return services.filter((s) => {
      const n = String(s.name || "").toLowerCase();
      const d = String(s.display_name || "").toLowerCase();
      const k = String(s.kind || "").toLowerCase();
      const st = String(s.status || "").toLowerCase();
      return n.includes(q) || d.includes(q) || k.includes(q) || st.includes(q);
    });
  }, [services, serviceFilter]);

  const dotnetServices = React.useMemo(() => {
    const patt = /(dotnet|aspnet|kestrel|w3svc|iis|api)/i;
    return (dotnetPageServices || []).filter((s) => {
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [dotnetPageServices]);

  const s3Services = React.useMemo(() => {
    const patt = /(locals3|minio|nginx|s3)/i;
    return (s3PageServices || []).filter((s) => {
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [s3PageServices]);

  const mongoServices = React.useMemo(() => {
    const patt = /(localmongo|mongodb|mongo-express|mongod)/i;
    return (mongoPageServices || []).filter((s) => {
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [mongoPageServices]);
  const proxyServices = React.useMemo(() => {
    return Array.isArray(proxyPageServices) ? proxyPageServices : [];
  }, [proxyPageServices]);
  const pythonServices = React.useMemo(() => {
    return Array.isArray(pythonPageServices) ? pythonPageServices : [];
  }, [pythonPageServices]);
  const websiteServices = React.useMemo(() => {
    return Array.isArray(websitePageServices) ? websitePageServices : [];
  }, [websitePageServices]);
  const pythonInstalledRuntimes = React.useMemo(() => {
    return pythonServices.filter((svc) => ["python_installation", "python_version"].includes(String(svc?.kind || "").toLowerCase()));
  }, [pythonServices]);
  const pythonRuntimeServices = React.useMemo(() => {
    return pythonServices.filter((svc) => !["python_installation", "python_version"].includes(String(svc?.kind || "").toLowerCase()));
  }, [pythonServices]);
  const pythonApiRuns = React.useMemo(() => {
    return pythonRuntimeServices.filter((svc) => !!svc?.python_api);
  }, [pythonRuntimeServices]);
  const dockerServices = React.useMemo(() => {
    const patt = /(docker|dockerd|containerd|com\.docker\.service|docker desktop service|docker engine)/i;
    return (dockerPageServices || []).filter((s) => {
      if (String(s?.kind || "").toLowerCase() === "docker") return true;
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [dockerPageServices]);
  const mongoDisplayServices = React.useMemo(() => {
    if ((mongoServices || []).length > 0) return mongoServices;
    const hasMongoSignal = !!(
      mongo.installed ||
      mongo.connection_string ||
      mongo.server_version ||
      mongo.web_version ||
      mongo.https_url
    );
    if (!hasMongoSignal) return [];
    let fallbackPort = 27017;
    try {
      const raw = String(mongo.connection_string || "").trim();
      const hostPart = raw.replace(/^mongodb:\/\//, "").replace(/\/.*$/, "").trim();
      const portText = hostPart.includes(":") ? hostPart.split(":").pop() : "27017";
      if (/^\d+$/.test(portText)) fallbackPort = Number(portText);
    } catch (_) {}
    const fallbackUrl = mongo.https_url ? String(mongo.https_url).trim() : (mongo.web_version === "native-service" ? "/mongo/native-ui" : "");
    return [{
      kind: cfg.os === "windows" ? "service" : "docker",
      name: cfg.os === "windows" ? "LocalMongoDB" : "localmongo-mongodb",
      display_name: mongo.server_version ? `MongoDB ${mongo.server_version}` : "MongoDB",
      status: "running",
      sub_status: "running",
      autostart: true,
      urls: fallbackUrl ? [fallbackUrl] : [],
      ports: fallbackPort ? [{ port: fallbackPort, protocol: "tcp" }] : [],
    }];
  }, [cfg.os, mongo.connection_string, mongo.https_url, mongo.installed, mongo.server_version, mongo.web_version, mongoServices]);

  const clientOs = React.useMemo(() => {
    const raw = `${navigator.userAgent || ""} ${(navigator.platform || "")}`.toLowerCase();
    if (raw.includes("win")) return "windows";
    if (raw.includes("mac")) return "macos";
    if (raw.includes("linux")) return "linux";
    return "unknown";
  }, []);

  const mongoCompassDownloadUrl = React.useMemo(() => {
    if (clientOs === "windows") return "https://www.mongodb.com/try/download/compass";
    if (clientOs === "macos") return "https://www.mongodb.com/try/download/compass";
    if (clientOs === "linux") return "https://www.mongodb.com/try/download/compass";
    return "https://www.mongodb.com/try/download/compass";
  }, [clientOs]);
  const mongoCompassUri = React.useMemo(() => {
    const buildMongoUri = (baseHost) => {
      const authority = String(baseHost || "").trim().replace(/\/+$/, "");
      const normalized = !authority ? "localhost:27017" : (
        /^\[[^\]]+\](?::\d+)?$/.test(authority)
          ? (/\]:\d+$/.test(authority) ? authority : `${authority}:27017`)
          : (/:\d+$/.test(authority) ? authority : `${authority}:27017`)
      );
      const user = encodeURIComponent("admin");
      const pass = encodeURIComponent("StrongPassword123");
      return `mongodb://${user}:${pass}@${normalized}/admin?authSource=admin`;
    };
    if (mongo.connection_string) {
      try {
        const raw = String(mongo.connection_string).trim();
        const hostPart = raw.replace(/^mongodb:\/\//, "").replace(/\/.*$/, "").trim();
        if (hostPart) return buildMongoUri(hostPart);
      } catch (_) {}
    }
    if (mongo.host) {
      return buildMongoUri(String(mongo.host).trim());
    }
    const host = (
      mongoStatusInfo?.public_ip ||
      (mongoStatusInfo?.ips || []).find((ip) => !String(ip).startsWith("127.")) ||
      systemInfo?.public_ip ||
      (systemInfo?.ips || []).find((ip) => !String(ip).startsWith("127.")) ||
      "localhost"
    );
    return buildMongoUri(host);
  }, [mongo.connection_string, mongo.host, mongoStatusInfo, systemInfo]);
  const mongoServiceUrls = React.useMemo(() => uniqUrls((mongoDisplayServices || []).flatMap((svc) => svc?.urls || [])), [mongoDisplayServices]);
  const mongoWebsiteUrl = React.useMemo(() => {
    if (mongo.https_url) return String(mongo.https_url).trim();
    if (cfg.os === "windows" && mongo.web_version === "native-service") return "/mongo/native-ui";
    return mongoServiceUrls.find((url) => /^https?:\/\//i.test(String(url || ""))) || "";
  }, [cfg.os, mongo.https_url, mongo.web_version, mongoServiceUrls]);
  const s3WindowsDockerSupported = cfg.os !== "windows" ? true : cfg.s3_windows_docker_supported !== false;
  const s3WindowsDockerReason = String(cfg.s3_windows_docker_reason || "").trim();
  const s3WindowsModeOptions = React.useMemo(() => (
    s3WindowsDockerSupported ? ["iis", "docker"] : ["iis"]
  ), [s3WindowsDockerSupported]);
  const windowsAdminRequired = cfg.os === "windows" && !systemInfo?.is_admin;
  const windowsAdminReason = windowsAdminRequired
    ? "Run the dashboard as Administrator before installing or managing the Windows proxy stack."
    : "";

  const s3ServiceUrls = React.useMemo(() => uniqUrls((s3Services || []).flatMap((svc) => svc?.urls || [])), [s3Services]);
  const s3ConsoleUrl = React.useMemo(() => {
    const fromTerminal = (
      extractLabeledUrl(termText, "Console URL") ||
      extractLabeledUrl(termText, "MinIO Console") ||
      extractLabeledUrl(termText, "LAN Console")
    );
    if (fromTerminal) return fromTerminal;
    return s3ServiceUrls.find((url) => /:(9443|10443|11443|12443|13443|18443|8444)(\/|$)/.test(url)) || "";
  }, [s3ServiceUrls, termText]);
  const s3ApiUrl = React.useMemo(() => {
    const fromTerminal = (
      extractLabeledUrl(termText, "API URL") ||
      extractLabeledUrl(termText, "S3 API / Share links") ||
      extractLabeledUrl(termText, "LAN S3 API")
    );
    if (fromTerminal) return fromTerminal;
    return s3ServiceUrls.find((url) => url !== s3ConsoleUrl) || s3ServiceUrls[0] || "";
  }, [s3ConsoleUrl, s3ServiceUrls, termText]);
  const s3LoginText = React.useMemo(() => {
    if (!s3ConsoleUrl && !s3ApiUrl) return "";
    return [
      `Console: ${s3ConsoleUrl || "-"}`,
      `API: ${s3ApiUrl || "-"}`,
      "Username: admin",
      "Password: StrongPassword123",
    ].join("\n");
  }, [s3ApiUrl, s3ConsoleUrl]);
  const dockerServiceUrls = React.useMemo(() => uniqUrls((dockerServices || []).flatMap((svc) => svc?.urls || [])), [dockerServices]);
  const dockerDaemonPorts = React.useMemo(() => {
    const direct = (systemInfo?.listening_ports || [])
      .filter((p) => {
        const port = Number(p?.port);
        return port === 2375 || port === 2376;
      })
      .map((p) => ({ port: Number(p.port), protocol: String(p.protocol || p.proto || "tcp").toLowerCase() }));
    const fallback = [];
    (dockerServices || []).forEach((svc) => {
      (svc?.ports || []).forEach((p) => {
        const port = Number(p?.port);
        if (port === 2375 || port === 2376) fallback.push({ port, protocol: String(p.protocol || "tcp").toLowerCase() });
      });
    });
    return uniqUrls([...direct, ...fallback].map((item) => `${item.protocol}:${item.port}`)).map((key) => {
      const [protocol, portText] = key.split(":");
      return { protocol, port: Number(portText) };
    });
  }, [dockerServices, systemInfo]);
  const dockerManageEndpoints = React.useMemo(() => {
    const hosts = uniqUrls([
      ...(selectableIps || []),
      dockerStatusInfo?.public_ip,
      systemInfo?.public_ip,
    ].filter(Boolean));
    const values = [];
    dockerDaemonPorts.forEach((item) => {
      const scheme = Number(item.port) === 2376 ? "https" : "tcp";
      hosts.forEach((host) => {
        values.push(`${scheme}://${host}:${item.port}`);
      });
    });
    return values;
  }, [dockerDaemonPorts, dockerStatusInfo?.public_ip, selectableIps, systemInfo?.public_ip]);
  const dockerConnectionHelp = React.useMemo(() => {
    if (dockerManageEndpoints.length > 0) {
      return `Docker remote API detected. Use one of these endpoints in Docker CLI/IDE.`;
    }
    return "Docker remote API port is not open. If you enable Docker TCP API on 2375 or 2376, the dashboard will show IP-based endpoints here.";
  }, [dockerManageEndpoints]);

  const launchCompassProtocol = React.useCallback((uri) => {
    if (!uri) return;
    window.location.href = uri;
  }, []);

  const copyText = async (text, label) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const tmp = document.createElement("textarea");
        tmp.value = text;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand("copy");
        document.body.removeChild(tmp);
      }
      setInfoMessage(`${label} copied.`);
    } catch (err) {
      setInfoMessage(`Could not copy ${label}: ${err}`);
    }
  };

  const loadFileManager = React.useCallback(async (targetPath = fileManagerPath) => {
    setFileManagerLoading(true);
    setFileManagerError("");
    try {
      const query = targetPath ? `?path=${encodeURIComponent(targetPath)}` : "";
      const r = await fetch(`/api/files/list${query}`, { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setFileManagerData(j);
      setFileManagerPath(j.path || "");
    } catch (err) {
      setFileManagerError(String(err));
      setFileManagerData(null);
    } finally {
      setFileManagerLoading(false);
    }
  }, [fileManagerPath]);

  const openFileInEditor = React.useCallback(async (targetPath) => {
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("path", targetPath);
      const r = await fetch("/api/files/read", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setFileEditorPath(j.path || targetPath);
      setFileEditorContent(j.content || "");
      setFileEditorMeta(j);
      setFileEditorDirty(false);
      setInfoMessage(`Opened ${j.path || targetPath}`);
    } catch (err) {
      setInfoMessage(`Could not open file: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, []);

  const saveFileEditor = React.useCallback(async () => {
    if (!fileEditorPath) return;
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("path", fileEditorPath);
      fd.append("content", fileEditorContent);
      const r = await fetch("/api/files/write", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setFileEditorDirty(false);
      setInfoMessage(`Saved ${fileEditorPath}`);
      loadFileManager(fileManagerPath);
    } catch (err) {
      setInfoMessage(`Save failed: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, [fileEditorContent, fileEditorPath, fileManagerPath, loadFileManager]);

  const createFolderInCurrentPath = React.useCallback(async () => {
    const folderName = window.prompt("New folder name:");
    if (!folderName) return;
    const separator = cfg.os === "windows" ? "\\" : "/";
    const nextPath = fileManagerPath
      ? `${String(fileManagerPath).replace(/[\\/]+$/, "")}${separator}${folderName}`
      : folderName;
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("path", nextPath);
      const r = await fetch("/api/files/mkdir", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setInfoMessage(`Created folder ${nextPath}`);
      loadFileManager(fileManagerPath);
    } catch (err) {
      setInfoMessage(`Create folder failed: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, [cfg.os, fileManagerPath, loadFileManager]);

  const createFileInCurrentPath = React.useCallback(async () => {
    const fileName = window.prompt("New file name:");
    if (!fileName) return;
    const separator = cfg.os === "windows" ? "\\" : "/";
    const nextPath = fileManagerPath
      ? `${String(fileManagerPath).replace(/[\\/]+$/, "")}${separator}${fileName}`
      : fileName;
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("path", nextPath);
      fd.append("content", "");
      const r = await fetch("/api/files/write", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setInfoMessage(`Created file ${nextPath}`);
      await loadFileManager(fileManagerPath);
      await openFileInEditor(nextPath);
    } catch (err) {
      setInfoMessage(`Create file failed: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, [cfg.os, fileManagerPath, loadFileManager, openFileInEditor]);

  const renameFileManagerPath = React.useCallback(async (sourcePath) => {
    const currentName = String(sourcePath || "").split(/[\\/]/).pop() || "";
    const nextName = window.prompt("Rename to:", currentName);
    if (!nextName || nextName === currentName) return;
    const nextPath = String(sourcePath).replace(/[\\/][^\\/]+$/, `${cfg.os === "windows" ? "\\" : "/"}${nextName}`);
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("source", sourcePath);
      fd.append("target", nextPath);
      const r = await fetch("/api/files/rename", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      if (fileEditorPath === sourcePath) {
        setFileEditorPath(nextPath);
      }
      setInfoMessage(`Renamed to ${nextPath}`);
      loadFileManager(fileManagerPath);
    } catch (err) {
      setInfoMessage(`Rename failed: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, [cfg.os, fileEditorPath, fileManagerPath, loadFileManager]);

  const deleteFileManagerPath = React.useCallback(async (targetPath, isDir) => {
    const confirmed = window.confirm(`Delete ${isDir ? "folder" : "file"}?\n${targetPath}`);
    if (!confirmed) return;
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("path", targetPath);
      const r = await fetch("/api/files/delete", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      if (fileEditorPath === targetPath) {
        setFileEditorPath("");
        setFileEditorContent("");
        setFileEditorMeta(null);
        setFileEditorDirty(false);
      }
      setInfoMessage(`Deleted ${targetPath}`);
      loadFileManager(fileManagerPath);
    } catch (err) {
      setInfoMessage(`Delete failed: ${err}`);
    } finally {
      setFileOpBusy(false);
    }
  }, [fileEditorPath, fileManagerPath, loadFileManager]);

  const uploadIntoCurrentPath = React.useCallback(async (event) => {
    const files = Array.from(event.target.files || []);
    if (!fileManagerPath || files.length === 0) return;
    setFileOpBusy(true);
    try {
      const fd = new FormData();
      fd.append("target", fileManagerPath);
      files.forEach((file) => {
        fd.append("files", file, file.webkitRelativePath || file.name);
      });
      const r = await fetch("/api/files/upload", { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setInfoMessage(`Uploaded ${j.written?.length || files.length} item(s).`);
      loadFileManager(fileManagerPath);
    } catch (err) {
      setInfoMessage(`Upload failed: ${err}`);
    } finally {
      event.target.value = "";
      setFileOpBusy(false);
    }
  }, [fileManagerPath, loadFileManager]);

  React.useEffect(() => {
    if (page === "files" && !fileManagerInitRef.current) {
      fileManagerInitRef.current = true;
      loadFileManager(fileManagerPath);
    } else if (page !== "files") {
      fileManagerInitRef.current = false;
    }
  }, [fileManagerPath, loadFileManager, page]);

  const tryOpenCompass = () => {
    try {
      launchCompassProtocol(mongoCompassUri);
      if (clientOs === "windows") {
        setInfoMessage("Trying to open Compass on Windows using the registered mongodb:// handler.");
      } else if (clientOs === "macos") {
        setInfoMessage("Trying to open Compass on macOS using the registered mongodb:// handler.");
      } else if (clientOs === "linux") {
        setInfoMessage("Trying to open Compass on Linux using the registered mongodb:// handler.");
      } else {
        setInfoMessage("Trying to open Compass using the registered mongodb:// handler.");
      }
    } catch (err) {
      setInfoMessage(`Could not launch Compass: ${err}`);
    }
  };

  const promptOpenMongoWebsite = React.useCallback(() => {
    if (!mongoWebsiteUrl) return;
    if (cfg.os === "windows" && mongo.web_version === "native-service") {
      window.open(mongoWebsiteUrl, "_blank", "noopener,noreferrer");
      return;
    }
    const username = window.prompt("MongoDB web username:", "admin");
    if (username === null) return;
    const password = window.prompt("MongoDB web password:", "StrongPassword123");
    if (password === null) return;
    try {
      const target = new URL(mongoWebsiteUrl, window.location.origin);
      if (/^https?:$/i.test(target.protocol)) {
        target.username = username;
        target.password = password;
      }
      window.open(target.toString(), "_blank", "noopener,noreferrer");
    } catch (_) {
      window.open(mongoWebsiteUrl, "_blank", "noopener,noreferrer");
    }
  }, [cfg.os, mongo.web_version, mongoWebsiteUrl]);

  const commonProps = {
    // MUI components
    Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Dialog, DialogActions,
    DialogContent, DialogTitle, Drawer, FormControl, Grid, IconButton, InputLabel,
    LinearProgress, MenuItem, Paper, Select, Stack, TextField, Toolbar, Tooltip, Typography,
    // Shared components
    ActionCard, NavCard,
    // Config
    cfg,
    // Icons
    DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
    RefreshSmallIcon, StartAllIcon, StopAllIcon,
    // Utilities
    clampPercent, defaultNotebookDirForOs, defaultPythonApiDirForOs, defaultWebsiteDirForOs,
    extractLabeledUrl, formatBytes, formatUptime, getSelectableIps, uniqUrls,
    // Actions
    ActionIcon, formatServiceState, IconOnlyAction, isServiceRunningStatus, MiniMetric,
    // App state
    page, setPage,
    systemInfo, systemErr, loadingSystem,
    selectableIps,
    isMobile, mobileOpen, setMobileOpen,
    collapsed, setCollapsed,
    termText, termState, runError, termOpen, termMin, termPos,
    infoMessage, setInfoMessage,
    portValue, setPortValue, portProtocol, setPortProtocol, portBusy,
    serviceBusy,
    scopeLoading, scopeErrors,
    serviceFilter, setServiceFilter,
    services, mongoPageServices, s3PageServices, dotnetPageServices,
    dockerPageServices, proxyPageServices, pythonPageServices, websitePageServices,
    mongoInfoState, s3InfoState, dotnetInfoState, dockerInfoState,
    proxyInfoState, pythonInfoState, websiteInfoState,
    pythonApiEditor, pythonApiEditorSeed,
    updateSourceDlg, setUpdateSourceDlg,
    websiteEditor, websiteEditorSeed,
    fileManagerPath, setFileManagerPath,
    fileManagerData, setFileManagerData,
    fileManagerLoading, fileManagerError,
    fileEditorPath, fileEditorContent, fileEditorMeta, fileEditorDirty,
    fileOpBusy,
    netRate,
    // Derived/computed state
    software, mongoStatusInfo, dotnetStatusInfo, dockerStatusInfo, proxyStatusInfo,
    pythonStatusInfo, websiteStatusInfo,
    mongoSoftware, dotnetSoftware, dockerSoftware, proxySoftware, pythonSoftware, websiteSoftware,
    dotnet, docker, mongoDocker, iis, mongo, proxy, pythonService, websiteInfo,
    listeningPorts, cpuPercent, memoryPercent, netBps, netPercent,
    apiAddressList, filteredServices,
    dotnetServices, s3Services, mongoServices, proxyServices, pythonServices, websiteServices,
    dockerServices,
    pythonInstalledRuntimes, pythonRuntimeServices, pythonApiRuns,
    mongoDisplayServices, mongoCompassDownloadUrl, mongoCompassUri,
    mongoServiceUrls, mongoWebsiteUrl,
    s3WindowsDockerSupported, s3WindowsDockerReason, s3WindowsModeOptions,
    windowsAdminRequired, windowsAdminReason,
    s3ServiceUrls, s3ConsoleUrl, s3ApiUrl, s3LoginText,
    dockerServiceUrls, dockerDaemonPorts, dockerManageEndpoints, dockerConnectionHelp,
    clientOs,
    // Refs
    loadSystem, loadServices, loadMongoServices, loadS3Services, loadDotnetServices,
    loadDockerServices, loadProxyServices, loadPythonServices, loadWebsiteServices,
    loadMongoInfo, loadS3Info, loadDotnetInfo, loadDockerInfo, loadProxyInfo,
    loadPythonInfo, loadWebsiteInfo,
    // Callbacks and handlers
    append, setScopeLoadingFlag, setScopeErrorText, isScopeLoading,
    loadScopedStatus, loadServiceScope,
    refreshPageServices, refreshPageStatus, refreshPageContext,
    poll, run, runDashboardUpdate, runPythonInstallWithCurrentSettings,
    goBack, onPortAction, onServicePortAction,
    renderServiceUrls, renderServicePorts,
    onServiceAction, stopServicesBatch, batchServiceAction, hasStoppedServices,
    onProxyServiceAction, actionLabel,
    openPythonApiRun, runPythonApiUpdateSource,
    startNewPythonApiDeployment, openWebsiteRun, startNewWebsiteDeployment,
    renderPythonApiRunsCard,
    launchCompassProtocol, copyText, tryOpenCompass, promptOpenMongoWebsite,
    loadFileManager, openFileInEditor, saveFileEditor,
    createFolderInCurrentPath, createFileInCurrentPath,
    renameFileManagerPath, deleteFileManagerPath, uploadIntoCurrentPath,
    setFileEditorContent, setFileEditorDirty,
  };

  const renderPage = () => {
    const pageRenderer = (window.ServerInstallerUI && window.ServerInstallerUI.pages) ? window.ServerInstallerUI.pages[page] : null;
    if (pageRenderer) {
      // Use React.createElement so each page function gets its own fiber node and
      // can use hooks without violating the Rules of Hooks (hook count per component
      // must be stable, but differs between pages).
      return React.createElement(pageRenderer, commonProps);
    }
    return <Alert severity="info">No actions available for this page on {cfg.os_label}.</Alert>;
  };


  const sidebar = (
    <Box sx={{ height: "100%", background: "linear-gradient(180deg,#081726,#132d4b)", color: "#deebff", p: 1.5, display: "flex", flexDirection: "column" }}>
      <Stack direction="row" alignItems="center" sx={{ px: 1, pb: 1.5, pt: 1 }}>
        {!collapsed && (
          <Box>
            <Typography variant="h6" fontWeight={800}>Server Installer</Typography>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>Control Panel</Typography>
          </Box>
        )}
      </Stack>
      {!collapsed && <Chip label={cfg.os_label} size="small" sx={{ mb: 1.5, ml: 1, bgcolor: "rgba(96,165,250,.2)", color: "#dbeafe", border: "1px solid rgba(147,197,253,.45)" }} />}
      <Button fullWidth variant={page === "home" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }} onClick={() => { setPage("home"); if (isMobile) setMobileOpen(false); }}>
        {collapsed ? "Home" : "Dashboard Home"}
      </Button>
      <Button
        fullWidth
        variant={page === "ssl" ? "contained" : "outlined"}
        sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, mt: 1, color: page === "ssl" ? undefined : "#dbeafe", borderColor: "rgba(219,234,254,.35)" }}
        onClick={() => { setPage("ssl"); if (isMobile) setMobileOpen(false); }}
      >
        {collapsed ? "SSL" : "SSL & Certificates"}
      </Button>
      <Button
        fullWidth
        variant={page === "files" ? "contained" : "outlined"}
        sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, mt: 1, color: page === "files" ? undefined : "#dbeafe", borderColor: "rgba(219,234,254,.35)" }}
        onClick={() => { setPage("files"); setFileManagerData(null); if (isMobile) setMobileOpen(false); }}
      >
        {collapsed ? "Files" : "File Manager"}
      </Button>
      <Box sx={{ flexGrow: 1 }} />
      <Button
        fullWidth
        variant="outlined"
        sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, mt: 1, color: "#dbeafe", borderColor: "rgba(219,234,254,.35)" }}
        onClick={runDashboardUpdate}
      >
        {collapsed ? "Update" : "Update Dashboard"}
      </Button>
    </Box>
  );

  const mainMargin = isMobile ? 0 : (collapsed ? DRAWER_MIN : DRAWER_W);
  const termStyle = termPos.x === null ? { right: 16, bottom: 16 } : { left: termPos.x, top: termPos.y };

  const updateSourceDialog = updateSourceDlg ? (
    <Dialog open onClose={() => setUpdateSourceDlg(null)} maxWidth="sm" fullWidth>
      <DialogTitle>Update Files — {updateSourceDlg.svc.form_name || updateSourceDlg.svc.name}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1.5, color: "text.secondary" }}>
          Enter the path to the source folder on this server. All files in that folder will replace the current deployed files and the service will be restarted.
        </Typography>
        <TextField
          fullWidth
          size="small"
          label="Source folder path on server"
          placeholder="/home/user/my-project"
          value={updateSourceDlg.path}
          onChange={(e) => setUpdateSourceDlg((prev) => ({ ...prev, path: e.target.value }))}
          autoFocus
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setUpdateSourceDlg(null)} sx={{ textTransform: "none" }}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!updateSourceDlg.path.trim()}
          onClick={() => {
            const { svc, path } = updateSourceDlg;
            setUpdateSourceDlg(null);
            runPythonApiUpdateSource(svc, path.trim());
          }}
          sx={{ textTransform: "none" }}
        >
          Update
        </Button>
      </DialogActions>
    </Dialog>
  ) : null;

  return (
    <Box sx={{ display: "flex", minHeight: "100%" }}>
      <CssBaseline />
      {updateSourceDialog}
      <AppBar position="fixed" sx={{ zIndex: 1300, ml: `${mainMargin}px`, width: `calc(100% - ${mainMargin}px)`, background: "linear-gradient(90deg,#081726,#1a3f66)", transition: "all .2s ease" }}>
        <Toolbar sx={{ gap: 1 }}>
          <IconButton color="inherit" onClick={() => isMobile ? setMobileOpen(true) : setCollapsed((v) => !v)} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
              <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
            </svg>
          </IconButton>
          <Box sx={{ ml: 0.5 }}>
            <Typography variant="h6" fontWeight={800}>{headerTitle}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.9 }}>Detected OS: {cfg.os_label}</Typography>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Stack direction="row" spacing={0.5}>
            <IconButton size="small" sx={{ border: "1px solid rgba(219,234,254,.35)", color: "#dbeafe" }} onClick={() => setPage("sysinfo")} title="SysInfo">
              <Typography variant="caption" sx={{ fontSize: 10, fontWeight: 700 }}>SI</Typography>
            </IconButton>
            <IconButton size="small" sx={{ border: "1px solid rgba(219,234,254,.35)", color: "#dbeafe" }} onClick={() => setPage("ports")} title="Port Management">
              <Typography variant="caption" sx={{ fontSize: 10, fontWeight: 700 }}>PM</Typography>
            </IconButton>
            <IconButton size="small" sx={{ border: "1px solid rgba(219,234,254,.35)", color: "#dbeafe" }} onClick={() => { setPage("services"); loadServices.current(); }} title="Service Manager">
              <Typography variant="caption" sx={{ fontSize: 10, fontWeight: 700 }}>SV</Typography>
            </IconButton>
            <IconButton size="small" sx={{ border: "1px solid rgba(219,234,254,.35)", color: "#dbeafe" }} onClick={() => { setPage("files"); setFileManagerData(null); }} title="File Manager">
              <Typography variant="caption" sx={{ fontSize: 10, fontWeight: 700 }}>FM</Typography>
            </IconButton>
            <Button size="small" variant="outlined" sx={{ color: "#dbeafe", borderColor: "rgba(219,234,254,.35)", textTransform: "none" }} onClick={() => { window.location.href = "/logout"; }}>
              Logout
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>

      <Drawer
        variant={isMobile ? "temporary" : "permanent"}
        open={isMobile ? mobileOpen : true}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        PaperProps={{ sx: { width: isMobile ? DRAWER_W : (collapsed ? DRAWER_MIN : DRAWER_W), transition: "width .2s ease", borderRight: "1px solid rgba(15,23,42,.15)", overflowX: "hidden" } }}
      >
        {sidebar}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, mt: "64px", p: { xs: 2, md: 3 }, ml: `${mainMargin}px`, transition: "margin .2s ease", display: "flex", flexDirection: "column", minHeight: "calc(100vh - 64px)" }}>
        {cfg.message && <Alert severity="success" sx={{ mb: 2 }}>{cfg.message}</Alert>}
        {infoMessage && <Alert severity="info" sx={{ mb: 2 }} onClose={() => setInfoMessage("")}>{infoMessage}</Alert>}
        {runError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setRunError("")}>{runError}</Alert>}
        {systemErr && <Alert severity="error" sx={{ mb: 2 }}>{systemErr}</Alert>}

        <Grid container spacing={1.2} sx={{ mb: 1.5 }}>
          <Grid item xs={12} md={4}>
            <MiniMetric label="CPU" valueText={`${cpuPercent.toFixed(1)}%`} percent={cpuPercent} color="#2563eb" />
          </Grid>
          <Grid item xs={12} md={4}>
            <MiniMetric label="Memory" valueText={`${memoryPercent.toFixed(1)}%`} percent={memoryPercent} color="#0891b2" />
          </Grid>
          <Grid item xs={12} md={4}>
            <MiniMetric label="Network" valueText={`${formatBytes(netRate.rxBps + netRate.txBps)}/s`} percent={netPercent} color="#0f766e" />
          </Grid>
        </Grid>

        <Stack spacing={2} sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
          {page !== "home" && (
            <Stack direction="row" justifyContent="flex-start">
              <Button variant="outlined" sx={{ textTransform: "none" }} onClick={goBack}>Back</Button>
            </Stack>
          )}
          <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
            {renderPage()}
          </Box>
        </Stack>
      </Box>

      {termOpen && (
        <Paper elevation={14} sx={{ position: "fixed", zIndex: 1500, width: termMin ? 320 : { xs: "calc(100vw - 16px)", sm: 700 }, maxWidth: "calc(100vw - 16px)", borderRadius: 2, border: "1px solid #1f2937", overflow: "hidden", ...termStyle }}>
          <Box
            sx={{ px: 1.5, py: 1, cursor: "move", background: "#111827", color: "#dbeafe", borderBottom: "1px solid #1f2937", display: "flex", alignItems: "center", justifyContent: "space-between" }}
            onMouseDown={(e) => {
              const rect = e.currentTarget.parentElement.getBoundingClientRect();
              drag.current.active = true;
              drag.current.sx = e.clientX;
              drag.current.sy = e.clientY;
              drag.current.bx = rect.left;
              drag.current.by = rect.top;
              setTermPos({ x: rect.left, y: rect.top });
            }}
          >
            <Box>
              <Typography variant="subtitle2" fontWeight={700}>Web Terminal</Typography>
              <Typography variant="caption" sx={{ color: "#93c5fd" }}>{termState}</Typography>
            </Box>
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="outlined" sx={{ color: "#dbeafe", borderColor: "#334155", minWidth: 80 }} onClick={() => setTermMin((v) => !v)}>
                {termMin ? "Expand" : "Minimize"}
              </Button>
              <Button size="small" variant="outlined" color="error" sx={{ minWidth: 72 }} onClick={() => setTermOpen(false)}>
                Close
              </Button>
            </Stack>
          </Box>
          {!termMin && (
            <Box sx={{ height: 330, overflow: "auto", background: "#0d1117", color: "#c9d1d9", p: 1.5 }}>
              <div className="terminal-log">{termText}</div>
            </Box>
          )}
        </Paper>
      )}
    </Box>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
