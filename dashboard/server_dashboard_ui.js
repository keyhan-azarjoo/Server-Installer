const {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CssBaseline, Drawer,
  FormControl, Grid, IconButton, InputLabel, List, ListItemButton, ListItemText,
  MenuItem, Select, Stack, TextField, Toolbar, Typography, Paper
} = MaterialUI;

const cfg = window.__APP_CONFIG__ || { os: "windows", os_label: "Windows", message: "" };
const DRAWER_W = 270;
const DRAWER_MIN = 78;
const APP_TITLE = "Server Installer Panel";

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

function ActionFormCard({ title, description, action, fields, buttonText, onRun, color }) {
  return (
    <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 28px rgba(15,23,42,.08)" }}>
      <CardContent>
        <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box component="form" onSubmit={(e) => onRun(e, action, title)}>
          {fields.map((f) => <Field key={f.name} field={f} />)}
          <Button
            type="submit"
            variant="contained"
            fullWidth
            sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2, bgcolor: color || "#1d4ed8" }}
          >
            {buttonText || "Start"}
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
  const [termText, setTermText] = React.useState("Ready. Click Start on any action page to run and stream output.");
  const [termState, setTermState] = React.useState("Idle");
  const [termMin, setTermMin] = React.useState(false);
  const [termOpen, setTermOpen] = React.useState(false);
  const [termPos, setTermPos] = React.useState({ x: null, y: null });
  const [infoMessage, setInfoMessage] = React.useState("");
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

  const openAction = (action) => {
    if (action === "install-iis" && cfg.os !== "windows") {
      setInfoMessage("Install IIS is available on Windows only.");
      return;
    }
    if (action === "install-docker-only" && cfg.os !== "windows") {
      setInfoMessage("Install Docker Only is available on Windows only.");
      return;
    }
    setView(action);
    if (isMobile) setMobileOpen(false);
  };

  const sidebar = (
    <Box sx={{ height: "100%", background: "linear-gradient(180deg,#081726,#132d4b)", color: "#deebff", p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1, pb: 1.5, pt: 1 }}>
        {!collapsed && (
          <Box>
            <Typography variant="h6" fontWeight={800}>{APP_TITLE}</Typography>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>Operations Center</Typography>
          </Box>
        )}
        {!isMobile && (
          <Button
            size="small"
            variant="outlined"
            onClick={() => setCollapsed((v) => !v)}
            sx={{ color: "#deebff", borderColor: "rgba(219,234,254,.35)", textTransform: "none", minWidth: 74 }}
          >
            {collapsed ? "Expand" : "Collapse"}
          </Button>
        )}
      </Stack>
      {!collapsed && (
        <Chip
          label={cfg.os_label}
          size="small"
          sx={{ mb: 1.5, ml: 1, bgcolor: "rgba(96,165,250,.2)", color: "#dbeafe", border: "1px solid rgba(147,197,253,.45)" }}
        />
      )}
      <List sx={{ pt: 0 }}>
        <ListItemButton
          selected={view === "home"}
          onClick={() => { setView("home"); if (isMobile) setMobileOpen(false); }}
          sx={{
            mb: 0.5, borderRadius: 2, color: "#e5edff",
            "&.Mui-selected": { backgroundColor: "#1d4ed8", color: "#fff" },
            "&:hover": { backgroundColor: "rgba(255,255,255,.12)" }
          }}
        >
          {!collapsed && <ListItemText primary="Dashboard" primaryTypographyProps={{ fontSize: 14, fontWeight: 700 }} />}
          {collapsed && <Typography sx={{ fontSize: 12, fontWeight: 700 }}>Home</Typography>}
        </ListItemButton>
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
          background: "linear-gradient(90deg,#081726,#1a3f66)",
          transition: "all .2s ease",
        }}
      >
        <Toolbar>
          <IconButton color="inherit" onClick={() => isMobile ? setMobileOpen(true) : setCollapsed((v) => !v)}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>|||</span>
          </IconButton>
          <Box sx={{ ml: 1 }}>
            <Typography variant="h6" fontWeight={800}>{APP_TITLE}</Typography>
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
        {sidebar}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, mt: "64px", p: { xs: 2, md: 3 }, ml: `${mainMargin}px`, transition: "margin .2s ease" }}>
        {cfg.message && <Alert severity="success" sx={{ mb: 2 }}>{cfg.message}</Alert>}
        {infoMessage && <Alert severity="info" sx={{ mb: 2 }} onClose={() => setInfoMessage("")}>{infoMessage}</Alert>}

        {view === "home" && (
          <Stack spacing={2}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", boxShadow: "0 10px 30px rgba(15,23,42,.07)" }}>
              <CardContent>
                <Typography variant="h5" fontWeight={800} sx={{ mb: 1 }}>Operations</Typography>
                <Typography color="text.secondary">Choose one function. This opens a dedicated page with details and a Start button.</Typography>
              </CardContent>
            </Card>
            <Grid container spacing={2}>
              <Grid item xs={12} md={3}>
                <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={800} sx={{ mb: 1 }}>Install IIS</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Open IIS setup page.</Typography>
                    <Button fullWidth variant="contained" sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => openAction("install-iis")}>
                      Open
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={800} sx={{ mb: 1 }}>Install Docker Only</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Open Docker setup page.</Typography>
                    <Button fullWidth variant="contained" sx={{ textTransform: "none", fontWeight: 700, bgcolor: "#0f766e" }} onClick={() => openAction("install-docker-only")}>
                      Open
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={800} sx={{ mb: 1 }}>Deploy .NET</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Open deployment page.</Typography>
                    <Button fullWidth variant="contained" sx={{ textTransform: "none", fontWeight: 700, bgcolor: "#1e40af" }} onClick={() => openAction("deploy-dotnet")}>
                      Open
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={800} sx={{ mb: 1 }}>Deploy S3</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Placeholder.</Typography>
                    <Button fullWidth variant="outlined" sx={{ textTransform: "none", fontWeight: 700 }} onClick={() => openAction("deploy-s3")}>
                      Open
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Stack>
        )}

        {view === "install-iis" && (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={800}>Install IIS</Typography>
              <Button variant="outlined" onClick={() => setView("home")} sx={{ textTransform: "none" }}>Back</Button>
            </Stack>
            <ActionFormCard
              title="Windows IIS Stack Setup"
              description="Install IIS features and .NET prerequisites."
              action="/run/windows_setup_iis"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              buttonText="Start"
              onRun={run}
              color="#0f766e"
            />
          </Stack>
        )}

        {view === "install-docker-only" && (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={800}>Install Docker Only</Typography>
              <Button variant="outlined" onClick={() => setView("home")} sx={{ textTransform: "none" }}>Back</Button>
            </Stack>
            <ActionFormCard
              title="Windows Docker Stack Setup"
              description="Install Docker prerequisites and .NET runtime."
              action="/run/windows_setup_docker"
              fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]}
              buttonText="Start"
              onRun={run}
              color="#1f2937"
            />
          </Stack>
        )}

        {view === "deploy-dotnet" && (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={800}>Deploy .NET</Typography>
              <Button variant="outlined" onClick={() => setView("home")} sx={{ textTransform: "none" }}>Back</Button>
            </Stack>

            {cfg.os === "windows" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <ActionFormCard
                    title="Windows Combined Deploy"
                    description="Deploy to IIS or Docker from one form."
                    action="/run/windows"
                    buttonText="Start"
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
                <Grid item xs={12} md={4}>
                  <ActionFormCard
                    title="Windows IIS Deploy"
                    description="Deploy directly to IIS."
                    action="/run/windows_iis"
                    buttonText="Start"
                    onRun={run}
                    color="#1e40af"
                    fields={[
                      { name: "SourceValue", label: "Source Path or URL", required: true },
                      { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                    ]}
                  />
                </Grid>
                <Grid item xs={12} md={4}>
                  <ActionFormCard
                    title="Windows Docker Deploy"
                    description="Deploy directly to Docker."
                    action="/run/windows_docker"
                    buttonText="Start"
                    onRun={run}
                    color="#334155"
                    fields={[
                      { name: "SourceValue", label: "Source Path or URL", required: true },
                      { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                      { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" },
                    ]}
                  />
                </Grid>
              </Grid>
            )}

            {cfg.os === "linux" && (
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <ActionFormCard
                    title="Linux Combined Deploy"
                    description="Deploy app and configure service."
                    action="/run/linux"
                    buttonText="Start"
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
                  <ActionFormCard
                    title="Linux Prerequisites"
                    description="Install runtime and required packages."
                    action="/run/linux_prereq"
                    buttonText="Start"
                    onRun={run}
                    color="#0f766e"
                    fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]}
                  />
                </Grid>
              </Grid>
            )}

            {cfg.os === "darwin" && (
              <Alert severity="info">macOS installer actions are not configured yet.</Alert>
            )}
          </Stack>
        )}

        {view === "deploy-s3" && (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={800}>Deploy S3</Typography>
              <Button variant="outlined" onClick={() => setView("home")} sx={{ textTransform: "none" }}>Back</Button>
            </Stack>
            <Alert severity="info">Deploy S3 is reserved and not implemented yet.</Alert>
          </Stack>
        )}
      </Box>

      {termOpen && (
        <Paper
          elevation={14}
          sx={{
            position: "fixed",
            zIndex: 1500,
            width: termMin ? 320 : { xs: "calc(100vw - 16px)", sm: 700 },
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
