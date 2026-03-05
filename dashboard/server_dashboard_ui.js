const {
  Alert, AppBar, Box, Button, Card, CardContent, CssBaseline, Divider, Drawer,
  FormControl, Grid, IconButton, InputLabel, List, ListItemButton, ListItemIcon,
  ListItemText, MenuItem, Select, Stack, TextField, Toolbar, Typography, Paper
} = MaterialUI;

const Icons = (typeof window !== "undefined" && window.MaterialUIIcons) ? window.MaterialUIIcons : {};
const MenuIcon = Icons.Menu || (() => React.createElement("span", null, "☰"));
const DashboardIcon = Icons.Dashboard || (() => React.createElement("span", null, "•"));
const BuildIcon = Icons.Build || (() => React.createElement("span", null, "•"));
const RocketIcon = Icons.RocketLaunch || (() => React.createElement("span", null, "•"));
const TerminalIcon = Icons.Terminal || (() => React.createElement("span", null, "•"));
const ChevronLeft = Icons.ChevronLeft || (() => React.createElement("span", null, "<"));
const ChevronRight = Icons.ChevronRight || (() => React.createElement("span", null, ">"));

const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
const DRAWER_W = 280;
const DRAWER_MIN = 78;

function fieldsToForm(fields) {
  return fields.map((f) => {
    if (f.type === "select") {
      return (
        <FormControl fullWidth size="small" key={f.name} sx={{ mb: 1.5 }}>
          <InputLabel>{f.label}</InputLabel>
          <Select name={f.name} defaultValue={f.defaultValue} label={f.label}>
            {(f.options || []).map((opt) => <MenuItem key={opt} value={opt}>{opt}</MenuItem>)}
          </Select>
        </FormControl>
      );
    }
    return (
      <TextField
        key={f.name}
        size="small"
        fullWidth
        name={f.name}
        label={f.label}
        defaultValue={f.defaultValue || ""}
        placeholder={f.placeholder || ""}
        required={!!f.required}
        sx={{ mb: 1.5 }}
      />
    );
  });
}

function ActionCard({ title, description, action, buttonText, fields, onRun, color }) {
  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 12px 30px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box component="form" onSubmit={(e) => onRun(e, action, title)}>
          {fieldsToForm(fields)}
          <Button
            type="submit"
            variant="contained"
            fullWidth
            sx={{ mt: 0.5, borderRadius: 2, textTransform: "none", fontWeight: 700, bgcolor: color || "#1d4ed8" }}
          >
            {buttonText}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

function App() {
  const isMobile = MaterialUI.useMediaQuery("(max-width:1100px)");
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [view, setView] = React.useState("home");
  const [termText, setTermText] = React.useState("Ready. Click any installer button to run and stream output here.");
  const [termState, setTermState] = React.useState("Idle");
  const [termMin, setTermMin] = React.useState(false);
  const [termOpen, setTermOpen] = React.useState(false);
  const [termPos, setTermPos] = React.useState({ x: null, y: null });
  const drag = React.useRef({ active: false, sx: 0, sy: 0, bx: 0, by: 0 });

  const navItems = React.useMemo(() => {
    if (cfg.os === "windows") return [
      { id: "home", label: "Dashboard", icon: <DashboardIcon /> },
      { id: "win-setup", label: "Windows Setup", icon: <BuildIcon /> },
      { id: "win-deploy", label: "Windows Deploy", icon: <RocketIcon /> },
    ];
    if (cfg.os === "linux") return [
      { id: "home", label: "Dashboard", icon: <DashboardIcon /> },
      { id: "linux", label: "Linux Deploy", icon: <RocketIcon /> },
    ];
    return [
      { id: "home", label: "Dashboard", icon: <DashboardIcon /> },
      { id: "macos", label: "macOS", icon: <BuildIcon /> },
    ];
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

  const drawer = (
    <Box sx={{ height: "100%", background: "linear-gradient(180deg,#0b1f3a,#14345b)", color: "#deebff", p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1, pb: 2, pt: 1 }}>
        {!collapsed && <Typography variant="h6" fontWeight={800}>DotNet Installer</Typography>}
        {!isMobile && (
          <IconButton sx={{ color: "#deebff" }} onClick={() => setCollapsed((v) => !v)}>
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </IconButton>
        )}
      </Stack>
      <List sx={{ pt: 0 }}>
        {navItems.map((n) => (
          <ListItemButton
            key={n.id}
            selected={view === n.id}
            onClick={() => { setView(n.id); if (isMobile) setMobileOpen(false); }}
            sx={{
              mb: 0.5, borderRadius: 2, color: "#e5edff",
              "&.Mui-selected": { backgroundColor: "#1d4ed8", color: "#fff" },
              "&:hover": { backgroundColor: "rgba(255,255,255,.12)" }
            }}
          >
            <ListItemIcon sx={{ color: "inherit", minWidth: 36 }}>{n.icon}</ListItemIcon>
            {!collapsed && <ListItemText primary={n.label} primaryTypographyProps={{ fontSize: 14, fontWeight: 600 }} />}
          </ListItemButton>
        ))}
      </List>
    </Box>
  );

  const mainMargin = isMobile ? 0 : (collapsed ? DRAWER_MIN : DRAWER_W);
  const termStyle = termPos.x === null ? { right: 16, bottom: 16 } : { left: termPos.x, top: termPos.y };

  return (
    <Box sx={{ display: "flex", minHeight: "100%" }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          zIndex: 1300,
          ml: `${mainMargin}px`,
          width: `calc(100% - ${mainMargin}px)`,
          background: "linear-gradient(90deg,#0b1f3a,#244a7a)",
          transition: "all .2s ease",
        }}
      >
        <Toolbar>
          <IconButton color="inherit" onClick={() => isMobile ? setMobileOpen(true) : setCollapsed((v) => !v)}>
            <MenuIcon />
          </IconButton>
          <Box sx={{ ml: 1 }}>
            <Typography variant="h6" fontWeight={800}>Server Installer Control Center</Typography>
            <Typography variant="caption" sx={{ opacity: 0.9 }}>Detected OS: {cfg.os_label}</Typography>
          </Box>
        </Toolbar>
      </AppBar>

      <Drawer
        variant={isMobile ? "temporary" : "permanent"}
        open={isMobile ? mobileOpen : true}
        onClose={() => setMobileOpen(false)}
        ModalProps={{ keepMounted: true }}
        PaperProps={{
          sx: {
            width: isMobile ? DRAWER_W : (collapsed ? DRAWER_MIN : DRAWER_W),
            transition: "width .2s ease",
            borderRight: "1px solid rgba(15,23,42,.15)",
            overflowX: "hidden",
          }
        }}
      >
        {drawer}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, mt: "64px", p: { xs: 2, md: 3 }, ml: `${mainMargin}px`, transition: "margin .2s ease" }}>
        {cfg.message && <Alert severity="success" sx={{ mb: 2 }}>{cfg.message}</Alert>}
        {view === "home" && (
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 30px rgba(15,23,42,.07)" }}>
            <CardContent>
              <Typography variant="h5" fontWeight={800} sx={{ mb: 1 }}>Dashboard</Typography>
              <Typography color="text.secondary">Select an installer section from the sidebar. Live command output appears in the web terminal box.</Typography>
            </CardContent>
          </Card>
        )}

        {cfg.os === "windows" && view === "win-setup" && (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <ActionCard
                title="Windows IIS Stack Setup"
                description="Install IIS features and .NET prerequisites only."
                action="/run/windows_setup_iis"
                buttonText="Install IIS Stack"
                fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
                onRun={run}
                color="#0f766e"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <ActionCard
                title="Windows Docker Stack Setup"
                description="Install Docker prerequisites and runtime."
                action="/run/windows_setup_docker"
                buttonText="Install Docker Stack"
                fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
                onRun={run}
                color="#1f2937"
              />
            </Grid>
          </Grid>
        )}

        {cfg.os === "windows" && view === "win-deploy" && (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <ActionCard
                title="Windows Combined Deploy"
                description="Deploy to IIS or Docker using one form."
                action="/run/windows"
                buttonText="Run Combined Deploy"
                onRun={run}
                fields={[
                  { name: "DeploymentMode", label: "Deployment Mode", type: "select", defaultValue: "IIS", options: ["IIS", "Docker"] },
                  { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                  { name: "SourceValue", label: "Source Path or URL", required: true, placeholder: "D:\\app\\published or https://..." },
                  { name: "DomainName", label: "Domain Name" },
                  { name: "SiteName", label: "Site Name", defaultValue: "DotNetApp" },
                  { name: "SitePort", label: "HTTP Port", defaultValue: "80" },
                  { name: "HttpsPort", label: "HTTPS Port", defaultValue: "443" },
                  { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" },
                ]}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <Stack spacing={2}>
                <ActionCard
                  title="Windows IIS Deploy"
                  description="Deploy directly to IIS."
                  action="/run/windows_iis"
                  buttonText="Deploy to IIS"
                  onRun={run}
                  color="#1e40af"
                  fields={[
                    { name: "SourceValue", label: "Source Path or URL", required: true },
                    { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                  ]}
                />
                <ActionCard
                  title="Windows Docker Deploy"
                  description="Deploy directly to Docker."
                  action="/run/windows_docker"
                  buttonText="Deploy to Docker"
                  onRun={run}
                  color="#334155"
                  fields={[
                    { name: "SourceValue", label: "Source Path or URL", required: true },
                    { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                    { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" },
                  ]}
                />
              </Stack>
            </Grid>
          </Grid>
        )}

        {cfg.os === "linux" && view === "linux" && (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <ActionCard
                title="Linux Combined Deploy"
                description="Deploy app and configure service."
                action="/run/linux"
                buttonText="Run Linux Deploy"
                onRun={run}
                fields={[
                  { name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" },
                  { name: "SOURCE_VALUE", label: "Source Path or URL", required: true, placeholder: "/srv/app or https://..." },
                  { name: "DOMAIN_NAME", label: "Domain Name" },
                  { name: "SERVICE_NAME", label: "Service Name", defaultValue: "dotnet-app" },
                  { name: "SERVICE_PORT", label: "Service Port", defaultValue: "5000" },
                  { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80" },
                  { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443" },
                ]}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <ActionCard
                title="Linux Prerequisites"
                description="Install runtime and required packages."
                action="/run/linux_prereq"
                buttonText="Install Linux Prerequisites"
                onRun={run}
                color="#0f766e"
                fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]}
              />
            </Grid>
          </Grid>
        )}

        {cfg.os === "darwin" && view === "macos" && (
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>macOS Support</Typography>
              <Typography color="text.secondary">macOS installer actions are not configured yet.</Typography>
            </CardContent>
          </Card>
        )}
      </Box>

      {termOpen && (
        <Paper
          elevation={14}
          sx={{
            position: "fixed",
            zIndex: 1500,
            width: termMin ? 320 : { xs: "calc(100vw - 16px)", sm: 680 },
            maxWidth: "calc(100vw - 16px)",
            borderRadius: 2,
            border: "1px solid #1f2937",
            overflow: "hidden",
            ...termStyle,
          }}
        >
          <Box
            sx={{
              px: 1.5, py: 1, cursor: "move", background: "#111827", color: "#dbeafe",
              borderBottom: "1px solid #1f2937", display: "flex", alignItems: "center", justifyContent: "space-between"
            }}
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
            <Stack direction="row" spacing={1} alignItems="center">
              <TerminalIcon fontSize="small" />
              <Box>
                <Typography variant="subtitle2" fontWeight={700}>Web Terminal</Typography>
                <Typography variant="caption" sx={{ color: "#93c5fd" }}>{termState}</Typography>
              </Box>
            </Stack>
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
