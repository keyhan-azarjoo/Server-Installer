const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Drawer,
  FormControl, Grid, IconButton, InputLabel, LinearProgress, MenuItem, Paper, Select, Stack, TextField, Toolbar, Tooltip, Typography
} = MaterialUI;

const { ActionCard, NavCard } = (window.ServerInstallerUI && window.ServerInstallerUI.components) || {};
const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
const MuiIcons = window.MaterialUIIcons || {};
const DownloadCompassIcon = MuiIcons.DownloadRounded || MuiIcons.Download || null;
const CopyCompassIcon = MuiIcons.ContentCopyRounded || MuiIcons.ContentCopy || null;
const TryOpenCompassIcon = MuiIcons.OpenInNewRounded || MuiIcons.LaunchRounded || MuiIcons.OpenInNew || MuiIcons.Launch || null;
const OpenCompassStyleIcon = MuiIcons.LanguageRounded || MuiIcons.PublicRounded || MuiIcons.Language || MuiIcons.Public || null;
const RefreshSmallIcon = MuiIcons.RefreshRounded || MuiIcons.SyncRounded || MuiIcons.Refresh || null;
const StartAllIcon = MuiIcons.PlayArrowRounded || MuiIcons.PlayArrow || null;
const StopAllIcon = MuiIcons.StopRounded || MuiIcons.Stop || null;
const DRAWER_W = 250;
const DRAWER_MIN = 82;

function formatBytes(v) {
  const n = Number(v || 0);
  if (!n || n < 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let size = n;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatUptime(v) {
  const sec = Number(v || 0);
  if (!sec) return "-";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

function clampPercent(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function isSelectableHostIp(ip) {
  const value = String(ip || "").trim();
  if (!value) return false;
  if (value.includes(":")) return false;
  if (value.startsWith("127.")) return false;
  if (value.startsWith("169.254.")) return false;
  if (value.startsWith("172.")) return false;
  if (value === "0.0.0.0") return false;
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(value);
}

function getSelectableIps(systemInfo) {
  const values = [];
  const pushIp = (ip) => {
    if (!isSelectableHostIp(ip)) return;
    if (!values.includes(ip)) values.push(ip);
  };
  (systemInfo?.ips || []).forEach(pushIp);
  pushIp(systemInfo?.public_ip);
  return values;
}

function trimDetectedUrl(value) {
  return String(value || "").trim().replace(/[),.;]+$/, "");
}

function extractLabeledUrl(text, label) {
  const source = String(text || "");
  const safeLabel = String(label || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${safeLabel}\\s*:\\s*(https?:\\/\\/\\S+)`, "i"));
  return match ? trimDetectedUrl(match[1]) : "";
}

function uniqUrls(items) {
  const values = [];
  (items || []).forEach((item) => {
    const url = trimDetectedUrl(item);
    if (!url || values.includes(url)) return;
    values.push(url);
  });
  return values;
}

function MiniMetric({ label, valueText, percent, color }) {
  return (
    <Paper variant="outlined" sx={{ p: 1, borderRadius: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.3 }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="caption" fontWeight={700}>{valueText}</Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={clampPercent(percent)}
        sx={{
          height: 5,
          borderRadius: 3,
          bgcolor: "rgba(15,23,42,.08)",
          "& .MuiLinearProgress-bar": { bgcolor: color || "#2563eb" },
        }}
      />
    </Paper>
  );
}

function ActionIcon({ title, onClick, disabled, color = "primary", variant = "outlined", IconComp, fallback }) {
  return (
    <Tooltip title={title}>
      <span>
        <Button
          type="button"
          color={color}
          variant={variant}
          disabled={disabled}
          onClick={onClick}
          aria-label={title}
          startIcon={IconComp ? <IconComp fontSize="small" /> : null}
          sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
        >
          {title}
          {!IconComp && fallback ? ` ${fallback}` : ""}
        </Button>
      </span>
    </Tooltip>
  );
}

function IconOnlyAction({ title, onClick, disabled, color = "default", variant = "outlined", IconComp, fallback }) {
  const showFallback = !IconComp && !!fallback;
  return (
    <Tooltip title={title}>
      <span>
        <IconButton
          type="button"
          color={color}
          disabled={disabled}
          onClick={onClick}
          aria-label={title}
          size="small"
          sx={{
            border: "1px solid",
            borderColor: variant === "contained" ? "transparent" : "rgba(37,99,235,.22)",
            bgcolor: variant === "contained" ? "primary.main" : "transparent",
            color: variant === "contained" ? "#fff" : "inherit",
            borderRadius: 2,
            px: showFallback ? 1 : 0.8,
            minWidth: showFallback ? 40 : "auto",
            "&:hover": {
              bgcolor: variant === "contained" ? "primary.dark" : "rgba(37,99,235,.08)",
            },
          }}
        >
          {IconComp ? <IconComp fontSize="small" /> : (
            showFallback ? <Typography component="span" variant="caption" fontWeight={800}>{fallback}</Typography> : null
          )}
        </IconButton>
      </span>
    </Tooltip>
  );
}

function isServiceRunningStatus(status, subStatus = "") {
  const primary = String(status || "").trim();
  const secondary = String(subStatus || "").trim();
  if (/running|up/i.test(secondary)) return true;
  if (/dead|failed|inactive|exited/i.test(secondary)) return false;
  return /running|active|up/i.test(primary);
}

function formatServiceState(status, subStatus = "") {
  const primary = String(status || "").trim();
  const secondary = String(subStatus || "").trim();
  if (primary && secondary && primary.toLowerCase() !== secondary.toLowerCase()) {
    return `${primary}/${secondary}`;
  }
  return primary || secondary || "-";
}

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
  const [scopeLoading, setScopeLoading] = React.useState({ all: false, mongo: false, s3: false, dotnet: false });
  const [scopeErrors, setScopeErrors] = React.useState({ all: "", mongo: "", s3: "", dotnet: "" });
  const [serviceFilter, setServiceFilter] = React.useState("");
  const [services, setServices] = React.useState([]);
  const [mongoPageServices, setMongoPageServices] = React.useState([]);
  const [s3PageServices, setS3PageServices] = React.useState([]);
  const [dotnetPageServices, setDotnetPageServices] = React.useState([]);
  const [mongoInfoState, setMongoInfoState] = React.useState(null);
  const [s3InfoState, setS3InfoState] = React.useState(null);
  const [dotnetInfoState, setDotnetInfoState] = React.useState(null);
  const [netRate, setNetRate] = React.useState({ rxBps: 0, txBps: 0 });
  const prevNetRef = React.useRef(null);
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

  const loadServices = React.useRef(async () => {});
  const loadMongoServices = React.useRef(async () => {});
  const loadS3Services = React.useRef(async () => {});
  const loadDotnetServices = React.useRef(async () => {});
  const loadMongoInfo = React.useRef(async () => {});
  const loadS3Info = React.useRef(async () => {});
  const loadDotnetInfo = React.useRef(async () => {});

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
  loadMongoInfo.current = async () => loadScopedStatus("mongo", setMongoInfoState);
  loadS3Info.current = async () => loadScopedStatus("s3", setS3InfoState);
  loadDotnetInfo.current = async () => loadScopedStatus("dotnet", setDotnetInfoState);

  const refreshPageServices = React.useCallback((targetPage) => {
    if (targetPage === "services") return loadServices.current();
    if (targetPage === "mongo") return loadMongoServices.current();
    if (targetPage === "s3") return loadS3Services.current();
    if (targetPage === "dotnet" || String(targetPage || "").startsWith("dotnet-")) return loadDotnetServices.current();
    return Promise.resolve();
  }, []);

  const refreshPageStatus = React.useCallback((targetPage) => {
    if (targetPage === "mongo") return loadMongoInfo.current();
    if (targetPage === "s3") return loadS3Info.current();
    if (targetPage === "dotnet" || String(targetPage || "").startsWith("dotnet-")) return loadDotnetInfo.current();
    if (targetPage === "home" || targetPage === "sysinfo" || targetPage === "ports" || targetPage === "services") return loadSystem.current();
    return Promise.resolve();
  }, []);

  const refreshPageContext = React.useCallback((targetPage) => {
    return Promise.all([refreshPageStatus(targetPage), refreshPageServices(targetPage)]);
  }, [refreshPageServices, refreshPageStatus]);

  React.useEffect(() => {
    if (page === "services" || page === "dotnet" || page === "s3" || page === "mongo" || String(page).startsWith("dotnet-")) {
      refreshPageContext(page);
    }
  }, [page, refreshPageContext]);

  React.useEffect(() => {
    if (!(page === "services" || page === "dotnet" || page === "s3" || page === "mongo" || String(page).startsWith("dotnet-"))) {
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
        setInfoMessage("Dashboard update started. If the page disconnects, refresh in a few seconds.");
        setTermState("Idle");
        setTimeout(() => window.location.reload(), 4000);
        return;
      }
      append(`Polling failed: ${err}`);
      setTermState("Error");
    }
  };

  const run = async (event, action, title) => {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    const isS3Install = action === "/run/s3_linux" || action === "/run/s3_windows" || action === "/run/s3_windows_iis" || action === "/run/s3_windows_docker";
    setRunError("");
    if (isS3Install) {
      const selectedIp = String(body.get("LOCALS3_HOST_IP") || "").trim();
      const resolvedHost = selectedIp || selectableIps[0] || "localhost";
      body.set("LOCALS3_HOST", resolvedHost);
      if (selectedIp) {
        body.set("LOCALS3_HOST_IP", selectedIp);
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
        refreshPageStatus(page);
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

  const goBack = () => {
    if (page === "home") return;
    if (page === "dotnet" || page === "s3" || page === "mongo" || page === "sysinfo" || page === "ports" || page === "services") setPage("home");
    else if (page.startsWith("dotnet-")) setPage("dotnet");
    else setPage("home");
  };

  const headerTitle = (() => {
    if (page === "home") return "Dashboard";
    if (page === "dotnet") return "DotNet";
    if (page === "s3") return "S3";
    if (page === "mongo") return "MongoDB";
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

  const renderServicePorts = (svc) => {
    const ports = Array.isArray(svc?.ports) ? svc.ports : [];
    if (ports.length === 0) return null;
    return (
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} sx={{ mt: 0.6 }}>
        {ports.map((p) => (
          <Stack key={`${svc.name}-${p.port}-${p.protocol}`} direction="row" spacing={0.5} alignItems="center">
            <Chip size="small" label={`${p.protocol || "tcp"}:${p.port}`} />
            <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServicePortAction(svc, p, "open")} sx={{ textTransform: "none" }}>Open</Button>
            <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServicePortAction(svc, p, "close")} sx={{ textTransform: "none" }}>Close</Button>
          </Stack>
        ))}
      </Stack>
    );
  };

  const onServiceAction = async (action, svc) => {
    if (!svc || !svc.name) return;
    if (action === "stop" || action === "delete") {
      const label = action === "delete" ? "delete" : "stop";
      const ok = window.confirm(`Do you want to ${label} '${svc.name}'?`);
      if (!ok) return;
    }
    setServiceBusy(true);
    try {
      const body = new URLSearchParams();
      body.set("action", action);
      body.set("name", svc.name);
      body.set("kind", svc.kind || "service");
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
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
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
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
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
        loadDotnetInfo.current(),
        loadDotnetServices.current(),
      ]);
      loadSystem.current();
    } finally {
      setServiceBusy(false);
    }
  };

  const hasStoppedServices = React.useCallback((items) => {
    return (items || []).some((svc) => !isServiceRunningStatus(svc?.status, svc?.sub_status));
  }, []);

  const actionLabel = (action) => {
    if (action === "autostart_on") return "Auto-start ON";
    if (action === "autostart_off") return "Auto-start OFF";
    return action.charAt(0).toUpperCase() + action.slice(1);
  };

  const software = systemInfo?.software || {};
  const mongoStatusInfo = mongoInfoState || systemInfo || {};
  const dotnetStatusInfo = dotnetInfoState || systemInfo || {};
  const mongoSoftware = mongoStatusInfo?.software || {};
  const dotnetSoftware = dotnetStatusInfo?.software || {};
  const dotnet = dotnetSoftware.dotnet || software.dotnet || {};
  const docker = software.docker || {};
  const mongoDocker = mongoSoftware.docker || software.docker || {};
  const iis = software.iis || {};
  const mongo = mongoSoftware.mongo || software.mongo || {};
  const listeningPorts = systemInfo?.listening_ports || [];
  const cpuPercent = clampPercent(systemInfo?.cpu_usage_percent ?? ((systemInfo?.load?.["1m"] && systemInfo?.cpu_count) ? (systemInfo.load["1m"] / systemInfo.cpu_count) * 100 : 0));
  const memoryPercent = clampPercent(systemInfo?.memory?.used_percent);
  const netBps = (netRate.rxBps || 0) + (netRate.txBps || 0);
  const netPercent = clampPercent((netBps / (20 * 1024 * 1024)) * 100);

  const apiAddressList = React.useMemo(() => {
    const ips = systemInfo?.ips || [];
    const portSet = new Set((listeningPorts || []).map((p) => Number(p.port)));
    const common = [80, 443, 5000, 5001, 8080, 8090, 8443, 9000];
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

  const s3ServiceUrls = React.useMemo(() => uniqUrls((s3Services || []).flatMap((svc) => svc?.urls || [])), [s3Services]);
  const s3ConsoleUrl = React.useMemo(() => {
    const fromTerminal = extractLabeledUrl(termText, "Console URL");
    if (fromTerminal) return fromTerminal;
    return s3ServiceUrls.find((url) => /:(9443|10443|18443|8444)(\/|$)/.test(url)) || "";
  }, [s3ServiceUrls, termText]);
  const s3ApiUrl = React.useMemo(() => {
    const fromTerminal = extractLabeledUrl(termText, "API URL");
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

  const renderPage = () => {
    if (page === "home") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="DotNet" text="Open .NET installer/deployment pages." onClick={() => setPage("dotnet")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="S3" text="Open S3 installer pages." onClick={() => setPage("s3")} outlined />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="MongoDB" text="Install MongoDB with a Compass-style web admin UI." onClick={() => setPage("mongo")} outlined />
          </Grid>
        </Grid>
      );
    }

    if (page === "sysinfo") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>System</Typography>
                <Typography variant="body2">Host: {systemInfo?.hostname || "-"}</Typography>
                <Typography variant="body2">OS: {systemInfo?.os || "-"} {systemInfo?.os_release || ""}</Typography>
                <Typography variant="body2">Platform: {systemInfo?.platform || "-"}</Typography>
                <Typography variant="body2">Machine: {systemInfo?.machine || "-"}</Typography>
                <Typography variant="body2">Processor: {systemInfo?.processor || "-"}</Typography>
                <Typography variant="body2">CPU Cores: {systemInfo?.cpu_count || "-"}</Typography>
                <Typography variant="body2">Memory: {formatBytes(systemInfo?.memory?.used_bytes)} / {formatBytes(systemInfo?.memory?.total_bytes)} ({systemInfo?.memory?.used_percent ?? "-"}%)</Typography>
                <Typography variant="body2">Uptime: {formatUptime(systemInfo?.uptime_seconds)}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Installed Software</Typography>
                <Typography variant="body2">.NET: {dotnet.installed ? `Installed (${dotnet.version || "unknown"})` : "Not installed"}</Typography>
                {!!(dotnet.sdks && dotnet.sdks.length) && <Typography variant="body2">SDKs: {dotnet.sdks.slice(0, 6).join(" | ")}</Typography>}
                <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "unknown"})` : "Not installed"}</Typography>
                {!!docker.server_version && <Typography variant="body2">Docker Engine: {docker.server_version}</Typography>}
                <Typography variant="body2">IIS: {iis.installed ? `Installed (${iis.service || "unknown"})` : "Not installed"}</Typography>
                <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not installed"}</Typography>
                {!!mongo.web_version && <Typography variant="body2">Mongo Web UI: {mongo.web_version}</Typography>}
                {!!mongo.https_url && <Typography variant="body2">Mongo HTTPS: {mongo.https_url}</Typography>}
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>API Addresses</Typography>
                {(apiAddressList.length > 0) ? apiAddressList.map((u) => (
                  <Typography key={u} variant="body2">{u}</Typography>
                )) : <Typography variant="body2">No API address detected.</Typography>}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      );
    }

    if (page === "ports") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Port Management</Typography>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                  <TextField size="small" label="Port" value={portValue} onChange={(e) => setPortValue(e.target.value)} sx={{ width: 140 }} />
                  <FormControl size="small" sx={{ width: 130 }}>
                    <InputLabel>Protocol</InputLabel>
                    <Select label="Protocol" value={portProtocol} onChange={(e) => setPortProtocol(e.target.value)}>
                      <MenuItem value="tcp">TCP</MenuItem>
                      <MenuItem value="udp">UDP</MenuItem>
                    </Select>
                  </FormControl>
                  <Button variant="contained" disabled={portBusy} onClick={() => onPortAction("open")} sx={{ textTransform: "none" }}>Open Port</Button>
                  <Button variant="outlined" disabled={portBusy} onClick={() => onPortAction("close")} sx={{ textTransform: "none" }}>Close Port</Button>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Open/Listening Ports</Typography>
                <Box sx={{ maxHeight: 340, overflow: "auto" }}>
                  {listeningPorts.length === 0 && <Typography variant="body2">No listening ports found.</Typography>}
                  {listeningPorts.slice(0, 500).map((p, idx) => (
                    <Typography key={`${p.proto}-${p.port}-${idx}`} variant="body2">
                      {String(p.proto || "").toUpperCase()}:{p.port} {p.pid ? `(pid ${p.pid})` : ""} {p.process ? ` ${p.process}` : ""}
                    </Typography>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      );
    }

    if (page === "services") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>Managed Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <TextField size="small" label="Filter" value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} sx={{ minWidth: 260 }} />
                  <Button variant="outlined" disabled={isScopeLoading("all")} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>
                    {isScopeLoading("all") ? "Refreshing..." : "Refresh"}
                  </Button>
                </Stack>
                {scopeErrors.all && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.all}</Alert>}
                <Box sx={{ mt: 1.5, maxHeight: 520, overflow: "auto" }}>
                  {filteredServices.length === 0 && <Typography variant="body2">No services found.</Typography>}
                  {filteredServices.map((svc) => {
                    const status = String(svc.status || "");
                    const stopDisabled = serviceBusy || /stopped|inactive|exited|dead/i.test(status);
                    const autostart = !!svc.autostart;
                    return (
                      <Paper key={`${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 280 }}>
                            <Typography variant="body2" fontWeight={700}>{svc.name}</Typography>
                            <Typography variant="caption" color="text.secondary">{svc.display_name || "-"}</Typography>
                          </Box>
                          <Chip size="small" label={svc.kind || "service"} />
                          <Chip size="small" color={isServiceRunningStatus(status, svc.sub_status) ? "success" : "default"} label={formatServiceState(status, svc.sub_status)} />
                          <Chip size="small" color={autostart ? "primary" : "default"} label={autostart ? "autostart:on" : "autostart:off"} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button
                            size="small"
                            variant="outlined"
                            color={isServiceRunningStatus(status, svc.sub_status) ? "error" : "success"}
                            disabled={serviceBusy}
                            onClick={() => onServiceAction(isServiceRunningStatus(status, svc.sub_status) ? "stop" : "start", svc)}
                            sx={{ textTransform: "none" }}
                          >
                            {isServiceRunningStatus(status, svc.sub_status) ? "Stop" : "Start"}
                          </Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>{actionLabel("restart")}</Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy || autostart} onClick={() => onServiceAction("autostart_on", svc)} sx={{ textTransform: "none" }}>{actionLabel("autostart_on")}</Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy || !autostart} onClick={() => onServiceAction("autostart_off", svc)} sx={{ textTransform: "none" }}>{actionLabel("autostart_off")}</Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>{actionLabel("delete")}</Button>
                        </Stack>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Paper>
                    );
                  })}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      );
    }

    if (page === "s3") {
      if (cfg.os === "windows") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={8}>
              <ActionCard
                title="Install S3 (Windows)"
                description="Choose IIS or Docker mode, host type (local/DNS/IP), and ports."
                action="/run/s3_windows"
                fields={[
                  { name: "S3_MODE", label: "Mode", type: "select", options: ["iis", "docker"], defaultValue: "iis" },
                  { name: "LOCALS3_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                  { name: "LOCALS3_HTTPS_PORT", label: "S3 HTTPS Port", defaultValue: "8443", placeholder: "443, 8443, 9443..." },
                  { name: "LOCALS3_API_PORT", label: "MinIO API Port (optional)", placeholder: "9000" },
                  { name: "LOCALS3_UI_PORT", label: "MinIO Console UI Port (optional)", placeholder: "9001" },
                  { name: "LOCALS3_CONSOLE_PORT", label: "Console Proxy Port (optional)", placeholder: "9443 or 10443..." },
                  { name: "LOCALS3_ROOT_USER", label: "S3 Username", defaultValue: "admin" },
                  { name: "LOCALS3_ROOT_PASSWORD", label: "S3 Password", defaultValue: "StrongPassword123" },
                ]}
                onRun={run}
                color="#0f766e"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <ActionCard
                title="Stop S3 APIs (Windows)"
                description="Stop LocalS3 API/Console services (IIS site, task, and Docker containers)."
                action="/run/s3_windows_stop"
                fields={[]}
                onRun={run}
                color="#7f1d1d"
              />
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>S3 Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    {!!s3ConsoleUrl && (
                      <ActionIcon title="Open S3 Dashboard" disabled={serviceBusy} onClick={() => window.open(s3ConsoleUrl, "_blank", "noopener,noreferrer")} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                    )}
                    {!!s3ApiUrl && (
                      <ActionIcon title="Open S3 API" disabled={serviceBusy} onClick={() => window.open(s3ApiUrl, "_blank", "noopener,noreferrer")} IconComp={TryOpenCompassIcon} fallback="API" />
                    )}
                    {!!s3LoginText && (
                      <ActionIcon title="Copy S3 Login" onClick={() => copyText(s3LoginText, "S3 login details")} IconComp={CopyCompassIcon} fallback="CP" />
                    )}
                    <Button variant="outlined" disabled={isScopeLoading("s3")} onClick={() => Promise.all([loadS3Info.current(), loadS3Services.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(s3Services) ? "success" : "error"}
                      disabled={serviceBusy || s3Services.length === 0}
                      onClick={() => batchServiceAction(s3Services, "S3", hasStoppedServices(s3Services) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(s3Services) ? "Start All S3" : "Stop All S3"}
                    </Button>
                  </Stack>
                  {(!!s3ConsoleUrl || !!s3ApiUrl) && (
                    <Box sx={{ mt: 1 }}>
                      {!!s3ConsoleUrl && <Typography variant="body2">Dashboard URL: {s3ConsoleUrl}</Typography>}
                      {!!s3ApiUrl && <Typography variant="body2">API URL: {s3ApiUrl}</Typography>}
                    </Box>
                  )}
                  <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                    {s3Services.length === 0 && <Typography variant="body2">No S3-related services found.</Typography>}
                    {s3Services.map((svc) => (
                      <Paper key={`s3-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      if (cfg.os === "linux" || cfg.os === "darwin") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={8}>
              <ActionCard
                title="Install S3 (Linux/macOS)"
                description="Run local S3 installer with selectable host and ports."
                action="/run/s3_linux"
                fields={[
                  { name: "LOCALS3_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                  { name: "LOCALS3_HTTPS_PORT", label: "S3 HTTPS Port", defaultValue: "8443", placeholder: "443, 8443, 9443..." },
                  { name: "LOCALS3_API_PORT", label: "MinIO API Port (optional)", placeholder: "9000" },
                  { name: "LOCALS3_UI_PORT", label: "MinIO Console UI Port (optional)", placeholder: "9001" },
                  { name: "LOCALS3_ROOT_USER", label: "S3 Username", defaultValue: "admin" },
                  { name: "LOCALS3_ROOT_PASSWORD", label: "S3 Password", defaultValue: "StrongPassword123" },
                ]}
                onRun={run}
                color="#1e40af"
              />
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>S3 Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    {!!s3ConsoleUrl && (
                      <ActionIcon title="Open S3 Dashboard" disabled={serviceBusy} onClick={() => window.open(s3ConsoleUrl, "_blank", "noopener,noreferrer")} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                    )}
                    {!!s3ApiUrl && (
                      <ActionIcon title="Open S3 API" disabled={serviceBusy} onClick={() => window.open(s3ApiUrl, "_blank", "noopener,noreferrer")} IconComp={TryOpenCompassIcon} fallback="API" />
                    )}
                    {!!s3LoginText && (
                      <ActionIcon title="Copy S3 Login" onClick={() => copyText(s3LoginText, "S3 login details")} IconComp={CopyCompassIcon} fallback="CP" />
                    )}
                    <Button variant="outlined" disabled={isScopeLoading("s3")} onClick={() => Promise.all([loadS3Info.current(), loadS3Services.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(s3Services) ? "success" : "error"}
                      disabled={serviceBusy || s3Services.length === 0}
                      onClick={() => batchServiceAction(s3Services, "S3", hasStoppedServices(s3Services) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(s3Services) ? "Start All S3" : "Stop All S3"}
                    </Button>
                  </Stack>
                  {(!!s3ConsoleUrl || !!s3ApiUrl) && (
                    <Box sx={{ mt: 1 }}>
                      {!!s3ConsoleUrl && <Typography variant="body2">Dashboard URL: {s3ConsoleUrl}</Typography>}
                      {!!s3ApiUrl && <Typography variant="body2">API URL: {s3ApiUrl}</Typography>}
                    </Box>
                  )}
                  <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                    {s3Services.length === 0 && <Typography variant="body2">No S3-related services found.</Typography>}
                    {s3Services.map((svc) => (
                      <Paper key={`s3-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      return <Alert severity="info">S3 installer is not configured for this OS.</Alert>;
    }

    if (page === "mongo") {
      if (cfg.os === "windows") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={8}>
              <ActionCard
                title="Install MongoDB (Windows)"
                description="Install MongoDB as a native Windows service."
                action="/run/mongo_windows"
                fields={[
                  { name: "LOCALMONGO_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                  { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "443, 9445..." },
                  { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017" },
                  { name: "LOCALMONGO_WEB_PORT", label: "Local Web UI Port", defaultValue: "8081", placeholder: "8081" },
                  { name: "LOCALMONGO_ADMIN_USER", label: "MongoDB Admin User", defaultValue: "admin" },
                  { name: "LOCALMONGO_ADMIN_PASSWORD", label: "MongoDB Admin Password", type: "password", defaultValue: "StrongPassword123" },
                  { name: "LOCALMONGO_UI_USER", label: "Web UI User", defaultValue: "admin" },
                  { name: "LOCALMONGO_UI_PASSWORD", label: "Web UI Password", type: "password", defaultValue: "StrongPassword123" },
                ]}
                onRun={run}
                color="#7c3aed"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Requirements</Typography>
                  <Typography variant="body2">Windows service: native `mongod` install</Typography>
                  <Typography variant="body2">Docker: optional, not required</Typography>
                  <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "native"})` : "Not installed yet"}</Typography>
                  {!!mongo.web_version && <Typography variant="body2">Web Version: {mongo.web_version}</Typography>}
                  {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
                  {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>MongoDB Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    <IconOnlyAction title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                    <IconOnlyAction title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                    <IconOnlyAction title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                    {!!mongoWebsiteUrl && (
                      <IconOnlyAction title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                    )}
                    <Button
                      type="button"
                      variant="outlined"
                      disabled={isScopeLoading("mongo")}
                      onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])}
                      startIcon={RefreshSmallIcon ? <RefreshSmallIcon fontSize="small" /> : null}
                      sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                    >
                      Refresh
                    </Button>
                    <Button
                      type="button"
                      variant="contained"
                      color={hasStoppedServices(mongoDisplayServices) ? "success" : "error"}
                      disabled={serviceBusy || mongoDisplayServices.length === 0}
                      onClick={() => batchServiceAction(mongoDisplayServices, "MongoDB", hasStoppedServices(mongoDisplayServices) ? "start" : "stop")}
                      startIcon={(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon) ? React.createElement(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon, { fontSize: "small" }) : null}
                      sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                    >
                      {hasStoppedServices(mongoDisplayServices) ? "Start All" : "Stop All"}
                    </Button>
                  </Stack>
                  <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                    {mongoDisplayServices.length === 0 && <Typography variant="body2">No MongoDB-related services found.</Typography>}
                    {mongoDisplayServices.map((svc) => (
                      <Paper key={`mongo-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      if (cfg.os === "linux" || cfg.os === "darwin") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={8}>
              <ActionCard
                title={`Install MongoDB (${cfg.os === "linux" ? "Linux" : "macOS"})`}
                description="Deploy MongoDB with a Compass-style web admin UI behind HTTPS."
                action="/run/mongo_unix"
                fields={[
                  { name: "LOCALMONGO_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                  { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "443, 9445..." },
                  { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017" },
                  { name: "LOCALMONGO_WEB_PORT", label: "Local Web UI Port", defaultValue: "8081", placeholder: "8081" },
                  { name: "LOCALMONGO_ADMIN_USER", label: "MongoDB Admin User", defaultValue: "admin" },
                  { name: "LOCALMONGO_ADMIN_PASSWORD", label: "MongoDB Admin Password", type: "password", defaultValue: "StrongPassword123" },
                  { name: "LOCALMONGO_UI_USER", label: "Web UI User", defaultValue: "admin" },
                  { name: "LOCALMONGO_UI_PASSWORD", label: "Web UI Password", type: "password", defaultValue: "StrongPassword123" },
                ]}
                onRun={run}
                color="#7c3aed"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Requirements</Typography>
                  <Typography variant="body2">Docker: {mongoDocker.installed ? `Installed (${mongoDocker.version || "unknown"})` : (cfg.os === "linux" ? "Will be installed if missing" : "Docker Desktop must be running")}</Typography>
                  <Typography variant="body2">HTTPS Proxy: Built into Mongo setup</Typography>
                  <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not installed yet"}</Typography>
                  {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
                  {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>MongoDB Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    <IconOnlyAction title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                    <IconOnlyAction title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                    <IconOnlyAction title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                    {!!mongoWebsiteUrl && (
                      <IconOnlyAction title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                    )}
                    <Button
                      type="button"
                      variant="outlined"
                      disabled={isScopeLoading("mongo")}
                      onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])}
                      startIcon={RefreshSmallIcon ? <RefreshSmallIcon fontSize="small" /> : null}
                      sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                    >
                      Refresh
                    </Button>
                    <Button
                      type="button"
                      variant="contained"
                      color={hasStoppedServices(mongoDisplayServices) ? "success" : "error"}
                      disabled={serviceBusy || mongoDisplayServices.length === 0}
                      onClick={() => batchServiceAction(mongoDisplayServices, "MongoDB", hasStoppedServices(mongoDisplayServices) ? "start" : "stop")}
                      startIcon={(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon) ? React.createElement(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon, { fontSize: "small" }) : null}
                      sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                    >
                      {hasStoppedServices(mongoDisplayServices) ? "Start All" : "Stop All"}
                    </Button>
                  </Stack>
                  <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                    {mongoDisplayServices.length === 0 && <Typography variant="body2">No MongoDB-related services found.</Typography>}
                    {mongoDisplayServices.map((svc) => (
                      <Paper key={`mongo-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      return <Alert severity="info">MongoDB installer is not configured for this OS.</Alert>;
    }

    if (page === "dotnet") {
      if (cfg.os === "windows") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <NavCard title="IIS" text="Install and deploy on IIS." onClick={() => setPage("dotnet-iis")} />
            </Grid>
            <Grid item xs={12} md={6}>
              <NavCard title="Docker" text="Install and deploy on Docker." onClick={() => setPage("dotnet-docker")} />
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>DotNet Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    <Button variant="outlined" disabled={isScopeLoading("dotnet")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(dotnetServices) ? "success" : "error"}
                      disabled={serviceBusy || dotnetServices.length === 0}
                      onClick={() => batchServiceAction(dotnetServices, "DotNet", hasStoppedServices(dotnetServices) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(dotnetServices) ? "Start All DotNet" : "Stop All DotNet"}
                    </Button>
                  </Stack>
                  <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                    {dotnetServices.length === 0 && <Typography variant="body2">No DotNet-related services found.</Typography>}
                    {dotnetServices.map((svc) => (
                      <Paper key={`dotnet-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      if (cfg.os === "linux") {
        return (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <NavCard title="Linux" text="Install and deploy on Linux." onClick={() => setPage("dotnet-linux")} />
            </Grid>
            <Grid item xs={12} md={6}>
              <NavCard title="Docker" text="Install and deploy on Docker (Linux)." onClick={() => setPage("dotnet-docker")} />
            </Grid>
            <Grid item xs={12}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Typography variant="h6" fontWeight={800}>DotNet Services</Typography>
                    <Box sx={{ flexGrow: 1 }} />
                    <Button variant="outlined" disabled={isScopeLoading("dotnet")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(dotnetServices) ? "success" : "error"}
                      disabled={serviceBusy || dotnetServices.length === 0}
                      onClick={() => batchServiceAction(dotnetServices, "DotNet", hasStoppedServices(dotnetServices) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(dotnetServices) ? "Start All DotNet" : "Stop All DotNet"}
                    </Button>
                  </Stack>
                  <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                    {dotnetServices.length === 0 && <Typography variant="body2">No DotNet-related services found.</Typography>}
                    {dotnetServices.map((svc) => (
                      <Paper key={`dotnet-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 250 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
                          <Box sx={{ flexGrow: 1 }} />
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        );
      }
      return <Alert severity="info">macOS installer actions are not configured yet.</Alert>;
    }

    if (cfg.os === "windows" && page === "dotnet-iis") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install IIS" description="Install IIS features and .NET prerequisites." action="/run/windows_setup_iis" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy IIS" description="Deploy application to IIS." action="/run/windows_iis" fields={[{ name: "SourceValue", label: "Source Path or URL", enableUpload: true }, { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#1e40af" />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "windows" && page === "dotnet-docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker prerequisites and .NET runtime." action="/run/windows_setup_docker" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy Docker" description="Deploy application to Docker." action="/run/windows_docker" fields={[{ name: "SourceValue", label: "Source Path or URL", enableUpload: true }, { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }, { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" }]} onRun={run} color="#334155" />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "linux" && page === "dotnet-linux") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Linux" description="Install Linux prerequisites." action="/run/linux_prereq" fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy Linux" description="Deploy application on Linux." action="/run/linux" fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }, { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true }, { name: "DOMAIN_NAME", label: "Domain Name" }, { name: "SERVICE_NAME", label: "Service Name", defaultValue: "dotnet-app" }, { name: "SERVICE_PORT", label: "Service Port", defaultValue: "5000" }, { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80" }, { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443" }]} onRun={run} />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "linux" && page === "dotnet-docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker Engine on Linux." action="/run/linux_setup_docker" fields={[]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy Docker" description="Build and run Docker container for uploaded/published app." action="/run/linux_docker" fields={[{ name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true }, { name: "DOCKER_HOST_PORT", label: "Docker Host Port", defaultValue: "8080" }]} onRun={run} color="#334155" />
          </Grid>
        </Grid>
      );
    }

    return <Alert severity="info">No actions available for this page.</Alert>;
  };

  const sidebar = (
    <Box sx={{ height: "100%", background: "linear-gradient(180deg,#081726,#132d4b)", color: "#deebff", p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1, pb: 1.5, pt: 1 }}>
        {!collapsed && (
          <Box>
            <Typography variant="h6" fontWeight={800}>Server Installer</Typography>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>Control Panel</Typography>
          </Box>
        )}
        {!isMobile && (
          <Button size="small" variant="outlined" onClick={() => setCollapsed((v) => !v)} sx={{ color: "#deebff", borderColor: "rgba(219,234,254,.35)", textTransform: "none", minWidth: 74 }}>
            {collapsed ? "Expand" : "Collapse"}
          </Button>
        )}
      </Stack>
      {!collapsed && <Chip label={cfg.os_label} size="small" sx={{ mb: 1.5, ml: 1, bgcolor: "rgba(96,165,250,.2)", color: "#dbeafe", border: "1px solid rgba(147,197,253,.45)" }} />}
      <Button fullWidth variant={page === "home" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }} onClick={() => { setPage("home"); if (isMobile) setMobileOpen(false); }}>
        {collapsed ? "Home" : "Dashboard Home"}
      </Button>
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

  return (
    <Box sx={{ display: "flex", minHeight: "100%" }}>
      <CssBaseline />
      <AppBar position="fixed" sx={{ zIndex: 1300, ml: `${mainMargin}px`, width: `calc(100% - ${mainMargin}px)`, background: "linear-gradient(90deg,#081726,#1a3f66)", transition: "all .2s ease" }}>
        <Toolbar sx={{ gap: 1 }}>
          <IconButton color="inherit" onClick={() => isMobile ? setMobileOpen(true) : setCollapsed((v) => !v)}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>|||</span>
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

      <Box component="main" sx={{ flexGrow: 1, mt: "64px", p: { xs: 2, md: 3 }, ml: `${mainMargin}px`, transition: "margin .2s ease" }}>
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

        <Stack spacing={2}>
          {page !== "home" && (
            <Stack direction="row" justifyContent="flex-start">
              <Button variant="outlined" sx={{ textTransform: "none" }} onClick={goBack}>Back</Button>
            </Stack>
          )}
          {renderPage()}
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
