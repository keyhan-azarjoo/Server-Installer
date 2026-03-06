const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Drawer,
  FormControl, Grid, IconButton, InputLabel, List, ListItemButton, ListItemText,
  MenuItem, Select, Stack, TextField, Toolbar, Typography, Paper
} = MaterialUI;

const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
const DRAWER_W = 270;
const DRAWER_MIN = 84;

function Field({ field }) {
  if (field.type === "select") {
    return (
      <FormControl fullWidth size="small" sx={{ mb: 1.5 }}>
        <InputLabel>{field.label}</InputLabel>
        <Select name={field.name} defaultValue={field.defaultValue} label={field.label}>
          {(field.options || []).map((opt) => (
            <MenuItem key={opt} value={opt}>{opt}</MenuItem>
          ))}
        </Select>
      </FormControl>
    );
  }
  return (
    <TextField
      fullWidth
      size="small"
      name={field.name}
      label={field.label}
      defaultValue={field.defaultValue || ""}
      placeholder={field.placeholder || ""}
      required={!!field.required}
      sx={{ mb: 1.5 }}
    />
  );
}

function ActionFormCard({ title, description, action, fields, onRun, color }) {
  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 28px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box component="form" onSubmit={(e) => onRun(e, action, title)}>
          {(fields || []).map((f) => <Field key={f.name} field={f} />)}
          <Button type="submit" variant="contained" fullWidth sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, bgcolor: color || "#1d4ed8" }}>
            Start
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

function PlaceholderCard({ title, description, onClick }) {
  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Button variant="outlined" fullWidth sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }} onClick={onClick}>
          Start
        </Button>
      </CardContent>
    </Card>
  );
}

function App() {
  const isMobile = MaterialUI.useMediaQuery("(max-width:1100px)");
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [moduleTab, setModuleTab] = React.useState("dotnet");
  const [stackTab, setStackTab] = React.useState("iis");
  const [termText, setTermText] = React.useState("Ready. Click Start to run and stream output.");
  const [termState, setTermState] = React.useState("Idle");
  const [termOpen, setTermOpen] = React.useState(false);
  const [termMin, setTermMin] = React.useState(false);
  const [termPos, setTermPos] = React.useState({ x: null, y: null });
  const [infoMessage, setInfoMessage] = React.useState("");
  const drag = React.useRef({ active: false, sx: 0, sy: 0, bx: 0, by: 0 });

  React.useEffect(() => {
    if (cfg.os === "windows") setStackTab("iis");
    else if (cfg.os === "linux") setStackTab("linux");
    else setStackTab("macos");
  }, []);

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
    const body = new URLSearchParams(new FormData(event.currentTarget)).toString();
    append("============================================================");
    append(`[${new Date().toLocaleTimeString()}] ${title} started`);
    setTermState(`Running: ${title}`);
    setTermOpen(true);
    setTermMin(false);
    try {
      const r = await fetch(action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch", "Content-Type": "application/x-www-form-urlencoded" },
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

  const moduleCards = (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
          <CardContent>
            <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>DotNet</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Open .NET installation/deployment operations.</Typography>
            <Button fullWidth variant="contained" sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setModuleTab("dotnet")}>Open DotNet</Button>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
          <CardContent>
            <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>S3</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Open S3 section (empty page).</Typography>
            <Button fullWidth variant="outlined" sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setModuleTab("s3")}>Open S3</Button>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const dotnetStacks = (() => {
    if (cfg.os === "windows") {
      return (
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <Button variant={stackTab === "iis" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setStackTab("iis")}>IIS</Button>
          <Button variant={stackTab === "docker" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setStackTab("docker")}>Docker</Button>
        </Stack>
      );
    }
    if (cfg.os === "linux") {
      return (
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <Button variant={stackTab === "linux" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setStackTab("linux")}>Linux</Button>
          <Button variant={stackTab === "docker" ? "contained" : "outlined"} sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => setStackTab("docker")}>Docker</Button>
        </Stack>
      );
    }
    return (
      <Alert severity="info">macOS installer actions are not configured yet.</Alert>
    );
  })();

  const dotnetActions = (() => {
    if (cfg.os === "windows" && stackTab === "iis") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Install IIS"
              description="Install IIS features and .NET prerequisites."
              action="/run/windows_setup_iis"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#0f766e"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Deploy IIS"
              description="Deploy app directly to IIS."
              action="/run/windows_iis"
              fields={[
                { name: "SourceValue", label: "Source Path or URL", required: true },
                { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
              ]}
              onRun={run}
              color="#1e40af"
            />
          </Grid>
        </Grid>
      );
    }
    if (cfg.os === "windows" && stackTab === "docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Install Docker"
              description="Install Docker prerequisites and .NET runtime."
              action="/run/windows_setup_docker"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#1f2937"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Deploy Docker"
              description="Deploy app directly to Docker."
              action="/run/windows_docker"
              fields={[
                { name: "SourceValue", label: "Source Path or URL", required: true },
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
    if (cfg.os === "linux" && stackTab === "linux") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Install Linux"
              description="Install runtime and Linux prerequisites."
              action="/run/linux_prereq"
              fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]}
              onRun={run}
              color="#0f766e"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionFormCard
              title="Deploy Linux"
              description="Deploy .NET application on Linux."
              action="/run/linux"
              fields={[
                { name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" },
                { name: "SOURCE_VALUE", label: "Source Path or URL", required: true, placeholder: "/srv/app or https://..." },
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
    if (cfg.os === "linux" && stackTab === "docker") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <PlaceholderCard
              title="Install Docker (Linux)"
              description="Reserved action. Backend endpoint is not implemented yet."
              onClick={() => setInfoMessage("Install Docker (Linux) is not implemented yet.")}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <PlaceholderCard
              title="Deploy Docker (Linux)"
              description="Reserved action. Backend endpoint is not implemented yet."
              onClick={() => setInfoMessage("Deploy Docker (Linux) is not implemented yet.")}
            />
          </Grid>
        </Grid>
      );
    }
    return <Alert severity="info">No actions available for this platform.</Alert>;
  })();

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
      {!collapsed && (
        <Chip label={cfg.os_label} size="small" sx={{ mb: 1.5, ml: 1, bgcolor: "rgba(96,165,250,.2)", color: "#dbeafe", border: "1px solid rgba(147,197,253,.45)" }} />
      )}
      <List sx={{ pt: 0 }}>
        <ListItemButton selected={moduleTab === "dotnet"} onClick={() => { setModuleTab("dotnet"); if (isMobile) setMobileOpen(false); }} sx={{ mb: 0.5, borderRadius: 2, color: "#e5edff", "&.Mui-selected": { backgroundColor: "#1d4ed8", color: "#fff" }, "&:hover": { backgroundColor: "rgba(255,255,255,.12)" } }}>
          {!collapsed && <ListItemText primary="DotNet" primaryTypographyProps={{ fontSize: 14, fontWeight: 700 }} />}
          {collapsed && <Typography sx={{ fontSize: 12, fontWeight: 700 }}>NET</Typography>}
        </ListItemButton>
        <ListItemButton selected={moduleTab === "s3"} onClick={() => { setModuleTab("s3"); if (isMobile) setMobileOpen(false); }} sx={{ mb: 0.5, borderRadius: 2, color: "#e5edff", "&.Mui-selected": { backgroundColor: "#1d4ed8", color: "#fff" }, "&:hover": { backgroundColor: "rgba(255,255,255,.12)" } }}>
          {!collapsed && <ListItemText primary="S3" primaryTypographyProps={{ fontSize: 14, fontWeight: 700 }} />}
          {collapsed && <Typography sx={{ fontSize: 12, fontWeight: 700 }}>S3</Typography>}
        </ListItemButton>
      </List>
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
            <Typography variant="h6" fontWeight={800}>Server Installer Panel</Typography>
            <Typography variant="caption" sx={{ opacity: 0.9 }}>Detected OS: {cfg.os_label}</Typography>
          </Box>
        </Toolbar>
      </AppBar>

      <Drawer variant={isMobile ? "temporary" : "permanent"} open={isMobile ? mobileOpen : true} onClose={() => setMobileOpen(false)} ModalProps={{ keepMounted: true }} PaperProps={{ sx: { width: isMobile ? DRAWER_W : (collapsed ? DRAWER_MIN : DRAWER_W), transition: "width .2s ease", borderRight: "1px solid rgba(15,23,42,.15)", overflowX: "hidden" } }}>
        {sidebar}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, mt: "64px", p: { xs: 2, md: 3 }, ml: `${mainMargin}px`, transition: "margin .2s ease" }}>
        {cfg.message && <Alert severity="success" sx={{ mb: 2 }}>{cfg.message}</Alert>}
        {infoMessage && <Alert severity="info" sx={{ mb: 2 }} onClose={() => setInfoMessage("")}>{infoMessage}</Alert>}

        <Stack spacing={2}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h5" fontWeight={800}>Modules</Typography>
              <Typography variant="body2" color="text.secondary">DotNet | S3</Typography>
            </CardContent>
          </Card>

          {moduleCards}

          {moduleTab === "dotnet" && (
            <Stack spacing={2}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>DotNet</Typography>
                  {dotnetStacks}
                </CardContent>
              </Card>
              {dotnetActions}
            </Stack>
          )}

          {moduleTab === "s3" && (
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>S3</Typography>
                <Typography variant="body2" color="text.secondary">Empty page.</Typography>
              </CardContent>
            </Card>
          )}
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
