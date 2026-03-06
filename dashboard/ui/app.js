const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Drawer,
  FormControl, Grid, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField, Toolbar, Typography
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

function App() {
  const isMobile = MaterialUI.useMediaQuery("(max-width:1100px)");
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [page, setPage] = React.useState("home");
  const [termText, setTermText] = React.useState("Ready. Click Start to run and stream output.");
  const [termState, setTermState] = React.useState("Idle");
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
      setSystemInfo(j.status || null);
    } catch (err) {
      setSystemErr(String(err));
    } finally {
      setLoadingSystem(false);
    }
  };

  React.useEffect(() => {
    loadSystem.current();
    const t = setInterval(() => loadSystem.current(), 15000);
    return () => clearInterval(t);
  }, []);

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
        setTermState("Idle");
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
    try {
      const r = await fetch(action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body,
      });
      const j = await r.json();
      if (!j.job_id) {
        append(j.output || "No output.");
        append(`[${new Date().toLocaleTimeString()}] ${title} finished (exit ${j.exit_code ?? 1})`);
        setTermState("Idle");
        return;
      }
      poll(j.job_id, title, 0);
    } catch (err) {
      append(`Request failed: ${err}`);
      setTermState("Error");
    }
  };

  const goBack = () => {
    if (page === "home") return;
    if (page === "dotnet") setPage("home");
    else if (page === "s3") setPage("home");
    else if (page.startsWith("dotnet-")) setPage("dotnet");
    else setPage("home");
  };

  const headerTitle = (() => {
    if (page === "home") return "Dashboard";
    if (page === "dotnet") return "DotNet";
    if (page === "s3") return "S3";
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

  const software = systemInfo?.software || {};
  const dotnet = software.dotnet || {};
  const docker = software.docker || {};
  const iis = software.iis || {};

  const renderPage = () => {
    if (page === "home") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="DotNet" text="Open .NET installer/deployment pages." onClick={() => setPage("dotnet")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="S3" text="Open S3 page (empty)." onClick={() => setPage("s3")} outlined />
          </Grid>
        </Grid>
      );
    }

    if (page === "s3") {
      return (
        <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
          <CardContent>
            <Typography variant="h6" fontWeight={800}>S3</Typography>
            <Typography variant="body2" color="text.secondary">Empty page.</Typography>
          </CardContent>
        </Card>
      );
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
          </Grid>
        );
      }
      return <Alert severity="info">macOS installer actions are not configured yet.</Alert>;
    }

    if (cfg.os === "windows" && page === "dotnet-iis") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Install IIS"
              description="Install IIS features and .NET prerequisites."
              action="/run/windows_setup_iis"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#0f766e"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy IIS"
              description="Deploy application to IIS."
              action="/run/windows_iis"
              fields={[
                { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
                { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
              ]}
              onRun={run}
              color="#1e40af"
            />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "windows" && page === "dotnet-docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Install Docker"
              description="Install Docker prerequisites and .NET runtime."
              action="/run/windows_setup_docker"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#1f2937"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy Docker"
              description="Deploy application to Docker."
              action="/run/windows_docker"
              fields={[
                { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
                { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" },
              ]}
              onRun={run}
              color="#334155"
            />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "linux" && page === "dotnet-linux") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Install Linux"
              description="Install Linux prerequisites."
              action="/run/linux_prereq"
              fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#0f766e"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy Linux"
              description="Deploy application on Linux."
              action="/run/linux"
              fields={[
                { name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" },
                { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true },
                { name: "DOMAIN_NAME", label: "Domain Name" },
                { name: "SERVICE_NAME", label: "Service Name", defaultValue: "dotnet-app" },
                { name: "SERVICE_PORT", label: "Service Port", defaultValue: "5000" },
                { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80" },
                { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443" },
              ]}
              onRun={run}
            />
          </Grid>
        </Grid>
      );
    }

    if (cfg.os === "linux" && page === "dotnet-docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Install Docker"
              description="Install Docker Engine on Linux."
              action="/run/linux_setup_docker"
              fields={[]}
              onRun={run}
              color="#1f2937"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy Docker"
              description="Build and run Docker container for uploaded/published app."
              action="/run/linux_docker"
              fields={[
                { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true },
                { name: "DOCKER_HOST_PORT", label: "Docker Host Port", defaultValue: "8080" },
              ]}
              onRun={run}
              color="#334155"
            />
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
            <Typography variant="caption" sx={{ opacity: 0.8 }}>Simple Dashboard</Typography>
          </Box>
        )}
        {!isMobile && (
          <Button size="small" variant="outlined" onClick={() => setCollapsed((v) => !v)} sx={{ color: "#deebff", borderColor: "rgba(219,234,254,.35)", textTransform: "none", minWidth: 74 }}>
            {collapsed ? "Expand" : "Collapse"}
          </Button>
        )}
      </Stack>
      {!collapsed && (
        <Chip label={cfg.os_label} size="small" sx={{ mb: 1.5, ml: 1, bgcolor: "rgba(96,165,250,.2)", color: "#dbeafe", border: "1px solid rgba(147,197,253,.45)" }} />
      )}
      <Button
        fullWidth
        variant={page === "home" ? "contained" : "outlined"}
        sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }}
        onClick={() => { setPage("home"); if (isMobile) setMobileOpen(false); }}
      >
        {collapsed ? "Home" : "Dashboard Home"}
      </Button>
    </Box>
  );

  const mainMargin = isMobile ? 0 : (collapsed ? DRAWER_MIN : DRAWER_W);
  const termStyle = termPos.x === null ? { right: 16, bottom: 16 } : { left: termPos.x, top: termPos.y };

  return (
    <Box sx={{ display: "flex", minHeight: "100%" }}>
      <CssBaseline />
      <AppBar position="fixed" sx={{ zIndex: 1300, ml: `${mainMargin}px`, width: `calc(100% - ${mainMargin}px)`, background: "linear-gradient(90deg,#081726,#1a3f66)", transition: "all .2s ease" }}>
        <Toolbar>
          <IconButton color="inherit" onClick={() => isMobile ? setMobileOpen(true) : setCollapsed((v) => !v)}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>|||</span>
          </IconButton>
          <Box sx={{ ml: 1 }}>
            <Typography variant="h6" fontWeight={800}>{headerTitle}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.9 }}>Detected OS: {cfg.os_label}</Typography>
          </Box>
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
        {systemErr && <Alert severity="error" sx={{ mb: 2 }}>{systemErr}</Alert>}

        <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", mb: 2 }}>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
              <Typography variant="h6" fontWeight={800}>Server Status</Typography>
              <Button variant="outlined" size="small" sx={{ textTransform: "none" }} onClick={() => loadSystem.current()} disabled={loadingSystem}>
                {loadingSystem ? "Loading..." : "Refresh"}
              </Button>
            </Stack>
            <Grid container spacing={1.5}>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 1.2 }}>
                  <Typography variant="caption" color="text.secondary">System</Typography>
                  <Typography variant="body2">Host: {systemInfo?.hostname || "-"}</Typography>
                  <Typography variant="body2">OS: {systemInfo?.os || "-"} {systemInfo?.os_release || ""}</Typography>
                  <Typography variant="body2">Machine: {systemInfo?.machine || "-"}</Typography>
                  <Typography variant="body2">Processor: {systemInfo?.processor || "-"}</Typography>
                  <Typography variant="body2">CPU: {systemInfo?.cpu_count || "-"}</Typography>
                  <Typography variant="body2">Memory: {formatBytes(systemInfo?.memory?.used_bytes)} / {formatBytes(systemInfo?.memory?.total_bytes)} ({systemInfo?.memory?.used_percent ?? "-"}%)</Typography>
                  <Typography variant="body2">Uptime: {formatUptime(systemInfo?.uptime_seconds)}</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 1.2 }}>
                  <Typography variant="caption" color="text.secondary">Installed Software</Typography>
                  <Typography variant="body2">.NET: {dotnet.installed ? `Installed (${dotnet.version || "unknown"})` : "Not installed"}</Typography>
                  {!!(dotnet.sdks && dotnet.sdks.length) && <Typography variant="body2">SDKs: {dotnet.sdks.slice(0, 3).join(" | ")}</Typography>}
                  <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "unknown"})` : "Not installed"}</Typography>
                  {!!docker.server_version && <Typography variant="body2">Docker Engine: {docker.server_version}</Typography>}
                  <Typography variant="body2">IIS: {iis.installed ? `Installed (${iis.service || "unknown"})` : "Not installed"}</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 1.2 }}>
                  <Typography variant="caption" color="text.secondary">Network</Typography>
                  <Typography variant="body2">IPs: {(systemInfo?.ips || []).join(", ") || "-"}</Typography>
                  <Typography variant="body2">Listening Ports: {(systemInfo?.listening_ports || []).length || 0}</Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <TextField size="small" label="Port" value={portValue} onChange={(e) => setPortValue(e.target.value)} sx={{ width: 110 }} />
                    <FormControl size="small" sx={{ width: 110 }}>
                      <InputLabel>Proto</InputLabel>
                      <Select label="Proto" value={portProtocol} onChange={(e) => setPortProtocol(e.target.value)}>
                        <MenuItem value="tcp">TCP</MenuItem>
                        <MenuItem value="udp">UDP</MenuItem>
                      </Select>
                    </FormControl>
                    <Button size="small" variant="contained" disabled={portBusy} onClick={() => onPortAction("open")} sx={{ textTransform: "none" }}>Open</Button>
                    <Button size="small" variant="outlined" disabled={portBusy} onClick={() => onPortAction("close")} sx={{ textTransform: "none" }}>Close</Button>
                  </Stack>
                </Paper>
              </Grid>
              <Grid item xs={12}>
                <Paper variant="outlined" sx={{ p: 1.2 }}>
                  <Typography variant="caption" color="text.secondary">Open Ports</Typography>
                  <Typography variant="body2" sx={{ mt: 0.5, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {(systemInfo?.listening_ports || []).slice(0, 60).map((p) => `${p.proto?.toUpperCase() || "?"}:${p.port}${p.pid ? ` (pid ${p.pid})` : ""}`).join(", ") || "-"}
                  </Typography>
                </Paper>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

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
