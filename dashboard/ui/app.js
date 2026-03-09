const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Drawer,
  FormControl, Grid, IconButton, InputLabel, LinearProgress, MenuItem, Paper, Select, Stack, TextField, Toolbar, Typography
} = MaterialUI;

const { ActionCard, NavCard } = (window.ServerInstallerUI && window.ServerInstallerUI.components) || {};
const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
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
  const [servicesLoading, setServicesLoading] = React.useState(false);
  const [servicesErr, setServicesErr] = React.useState("");
  const [serviceFilter, setServiceFilter] = React.useState("");
  const [services, setServices] = React.useState([]);
  const [netRate, setNetRate] = React.useState({ rxBps: 0, txBps: 0 });
  const prevNetRef = React.useRef(null);
  const drag = React.useRef({ active: false, sx: 0, sy: 0, bx: 0, by: 0 });

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

  const loadSystem = React.useRef(async () => {});
  loadSystem.current = async () => {
    try {
      setSystemErr("");
      const r = await fetch("/api/system/status", { headers: { "X-Requested-With": "fetch" } });
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
      setSystemErr(String(err));
    } finally {
      setLoadingSystem(false);
    }
  };

  React.useEffect(() => {
    loadSystem.current();
    const t = setInterval(() => loadSystem.current(), 10000);
    return () => clearInterval(t);
  }, []);

  React.useEffect(() => {
    if (page === "services" || page === "dotnet" || page === "s3") {
      loadServices.current();
    }
  }, [page]);

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
        loadSystem.current();
        return;
      }
      setTimeout(() => poll(jobId, title, next), 300);
    } catch (err) {
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
      // Strict pre-check: do not start if port is owned by another app.
      const p = String(body.get("LOCALS3_HTTPS_PORT") || "").trim();
      if (p) {
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
      append(`Request failed: ${err}`);
      setRunError(`${title} request failed: ${err}`);
      setTermState("Error");
    }
  };

  const goBack = () => {
    if (page === "home") return;
    if (page === "dotnet" || page === "s3" || page === "sysinfo" || page === "ports" || page === "services") setPage("home");
    else if (page.startsWith("dotnet-")) setPage("dotnet");
    else setPage("home");
  };

  const headerTitle = (() => {
    if (page === "home") return "Dashboard";
    if (page === "dotnet") return "DotNet";
    if (page === "s3") return "S3";
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
          <Typography key={`${svc.name}-${u}`} variant="caption" sx={{ display: "block", color: "text.secondary" }}>{u}</Typography>
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

  const loadServices = React.useRef(async () => {});
  loadServices.current = async () => {
    setServicesLoading(true);
    setServicesErr("");
    try {
      const r = await fetch("/api/system/services", { headers: { "X-Requested-With": "fetch" } });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setServices(Array.isArray(j.services) ? j.services : []);
    } catch (err) {
      setServicesErr(String(err));
    } finally {
      setServicesLoading(false);
    }
  };

  const onServiceAction = async (action, svc) => {
    if (!svc || !svc.name) return;
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
      await loadServices.current();
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
      await loadServices.current();
      loadSystem.current();
    } finally {
      setServiceBusy(false);
    }
  };

  const actionLabel = (action) => {
    if (action === "autostart_on") return "Auto-start ON";
    if (action === "autostart_off") return "Auto-start OFF";
    return action.charAt(0).toUpperCase() + action.slice(1);
  };

  const software = systemInfo?.software || {};
  const dotnet = software.dotnet || {};
  const docker = software.docker || {};
  const iis = software.iis || {};
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
    return (services || []).filter((s) => {
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [services]);

  const s3Services = React.useMemo(() => {
    const patt = /(locals3|minio|nginx|s3)/i;
    return (services || []).filter((s) => {
      const text = `${s.name || ""} ${s.display_name || ""} ${s.status || ""}`;
      return patt.test(text);
    });
  }, [services]);

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
                  <Button variant="outlined" disabled={servicesLoading} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>
                    {servicesLoading ? "Refreshing..." : "Refresh"}
                  </Button>
                </Stack>
                {servicesErr && <Alert severity="error" sx={{ mt: 1 }}>{servicesErr}</Alert>}
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
                          <Chip size="small" color={/running|active|up/i.test(status) ? "success" : "default"} label={status || "-"} />
                          <Chip size="small" color={autostart ? "primary" : "default"} label={autostart ? "autostart:on" : "autostart:off"} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("start", svc)} sx={{ textTransform: "none" }}>{actionLabel("start")}</Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            disabled={stopDisabled}
                            onClick={() => onServiceAction("stop", svc)}
                            sx={{ textTransform: "none" }}
                          >
                            Stop
                          </Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>{actionLabel("restart")}</Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy || autostart} onClick={() => onServiceAction("autostart_on", svc)} sx={{ textTransform: "none" }}>{actionLabel("autostart_on")}</Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy || !autostart} onClick={() => onServiceAction("autostart_off", svc)} sx={{ textTransform: "none" }}>{actionLabel("autostart_off")}</Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>{actionLabel("delete")}</Button>
                        </Stack>
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
                  { name: "LOCALS3_HOST", label: "Host / Domain / IP", defaultValue: "", placeholder: "auto (public IP > local IP > localhost) or enter custom" },
                  { name: "LOCALS3_ENABLE_LAN", label: "LAN Access", type: "select", options: ["true", "false"], defaultValue: "true" },
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
                    <Button variant="outlined" disabled={servicesLoading} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button variant="outlined" color="error" disabled={serviceBusy || s3Services.length === 0} onClick={() => stopServicesBatch(s3Services, "S3")} sx={{ textTransform: "none" }}>Stop All S3</Button>
                  </Stack>
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
                          <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("stop", svc)} sx={{ textTransform: "none" }}>Stop</Button>
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
                  { name: "LOCALS3_HOST", label: "Host / Domain / IP", defaultValue: "", placeholder: "auto (public IP > local IP > localhost) or enter custom" },
                  { name: "LOCALS3_ENABLE_LAN", label: "LAN Access", type: "select", options: ["true", "false"], defaultValue: "true" },
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
            <Grid item xs={12} md={4}>
              <ActionCard
                title="Stop S3 APIs (Linux/macOS)"
                description="Stop LocalS3 MinIO and disable LocalS3 nginx endpoint."
                action="/run/s3_linux_stop"
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
                    <Button variant="outlined" disabled={servicesLoading} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button variant="outlined" color="error" disabled={serviceBusy || s3Services.length === 0} onClick={() => stopServicesBatch(s3Services, "S3")} sx={{ textTransform: "none" }}>Stop All S3</Button>
                  </Stack>
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
                          <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("stop", svc)} sx={{ textTransform: "none" }}>Stop</Button>
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
                    <Button variant="outlined" disabled={servicesLoading} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button variant="outlined" color="error" disabled={serviceBusy || dotnetServices.length === 0} onClick={() => stopServicesBatch(dotnetServices, "DotNet")} sx={{ textTransform: "none" }}>Stop All DotNet</Button>
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("stop", svc)} sx={{ textTransform: "none" }}>Stop</Button>
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
                    <Button variant="outlined" disabled={servicesLoading} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>Refresh</Button>
                    <Button variant="outlined" color="error" disabled={serviceBusy || dotnetServices.length === 0} onClick={() => stopServicesBatch(dotnetServices, "DotNet")} sx={{ textTransform: "none" }}>Stop All DotNet</Button>
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
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("stop", svc)} sx={{ textTransform: "none" }}>Stop</Button>
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
