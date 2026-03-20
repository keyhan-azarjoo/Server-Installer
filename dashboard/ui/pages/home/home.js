(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // ── Platform Services page ────────────────────────────────────────────────
  ns.pages["platform-services"] = function renderPlatformServicesPage(p) {
    const { Grid, Card, CardContent, Typography, Divider, NavCard, setPage, startNewWebsiteDeployment, setFileManagerData } = p;
    return (
      <Grid container spacing={2}>
        {/* ── Page description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>Platform Services</Typography>
              <Typography variant="body2" color="text.secondary">
                Install, deploy, and manage all server services from one place. Choose a service category below to get started.
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Section 1: Running Services ── */}
        <Grid item xs={12}>
          <Typography variant="overline" fontWeight={700} sx={{ ml: 0.5, letterSpacing: 1, color: "#475569" }}>Running Services</Typography>
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="DotNet APIs" text="Deploy ASP.NET / .NET Core APIs via Docker, OS service, or IIS." onClick={() => setPage("dotnet")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python APIs" text="Deploy Python APIs via Docker, OS service, or IIS." onClick={() => setPage("python-api")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="S3 Storage" text="Install MinIO S3-compatible object storage via Docker, OS service, or IIS." onClick={() => setPage("s3")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="MongoDB" text="Install MongoDB with a Compass-style web admin UI via Docker or OS service." onClick={() => setPage("mongo")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python & Jupyter" text="Install Python runtime and Jupyter notebooks. Manage kernels and runtime services." onClick={() => setPage("python")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Websites" text="Deploy static sites, Flutter web, Next.js exports via Docker, OS service, or IIS." onClick={() => startNewWebsiteDeployment()} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Proxy" text="Install and manage the multi-layer proxy/VPN stack." onClick={() => setPage("proxy")} outlined />
        </Grid>

        {/* ── Section 2: Tools & Infrastructure ── */}
        <Grid item xs={12} sx={{ mt: 1 }}>
          <Typography variant="overline" fontWeight={700} sx={{ ml: 0.5, letterSpacing: 1, color: "#475569" }}>Tools & Infrastructure</Typography>
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="Files" text="Browse, upload, edit, and manage server files." onClick={() => { setPage("files"); setFileManagerData(null); }} outlined />
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="Docker" text="Install Docker and manage containers, images, and logs." onClick={() => setPage("docker")} outlined />
        </Grid>
        <Grid item xs={12} md={4}>
          <NavCard title="SSL & Certificates" text="Manage TLS certificates: Let's Encrypt, custom certs, and service assignment." onClick={() => setPage("ssl")} outlined />
        </Grid>
      </Grid>
    );
  };

  // ── AI & ML Services page ─────────────────────────────────────────────────
  ns.pages["ai-ml"] = function renderAiMlPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Alert,
      NavCard, cfg, setPage,
    } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#6d28d9" }}>
                AI & ML Services
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Deploy and manage AI models, inference servers, and machine learning workloads on your server.
              </Typography>
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                <b>Supported frameworks:</b> Ollama, vLLM, llama.cpp, Text Generation WebUI, ComfyUI
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                Most AI/ML workloads benefit from a dedicated GPU. CPU-only inference is supported but will be significantly slower for large models.
              </Alert>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Ollama" text="Run large language models locally. Supports GPU acceleration." onClick={() => setPage("ai-ollama")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Text Generation WebUI" text="Web UI for running LLMs with various backends." onClick={() => setPage("ai-tgwui")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="ComfyUI" text="Node-based Stable Diffusion UI." onClick={() => setPage("ai-comfyui")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Custom Model" text="Deploy any AI model as a managed service." onClick={() => setPage("ai-custom")} outlined />
        </Grid>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>AI & ML Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>Refresh</Button>
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: 200, overflow: "auto" }}>
                <Typography variant="body2" color="text.secondary">No AI services deployed yet.</Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  // ── Logs page ───────────────────────────────────────────────────────────────
  function LogsPageInner(p) {
    const { Box, Button, Card, CardContent, Typography, Stack, Paper, Tooltip, termText, copyText } = p;
    const [autoScroll, setAutoScroll] = React.useState(true);
    const [cleared, setCleared] = React.useState(false);
    const [clearedAt, setClearedAt] = React.useState("");
    const scrollRef = React.useRef(null);
    const displayText = cleared ? "" : (termText || "");

    React.useEffect(() => {
      if (cleared && termText !== clearedAt) setCleared(false);
    }, [termText, cleared, clearedAt]);

    React.useEffect(() => {
      if (autoScroll && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [displayText, autoScroll]);

    const isEmpty = !displayText || displayText.trim() === "" || displayText.trim() === "Ready. Click Start to run and stream output.";

    return (
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
            <Typography variant="h6" fontWeight={800} sx={{ flexGrow: 1 }}>System Logs</Typography>
            <Tooltip title={autoScroll ? "Auto-scroll is ON" : "Auto-scroll is OFF"}>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: "0.85rem", userSelect: "none" }}>
                <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} style={{ accentColor: "#2563eb", width: 16, height: 16, cursor: "pointer" }} />
                Auto-scroll
              </label>
            </Tooltip>
            <Button size="small" variant="outlined" disabled={isEmpty} onClick={() => { if (copyText) copyText(displayText, "Logs"); else navigator.clipboard?.writeText(displayText); }} sx={{ textTransform: "none" }}>Copy</Button>
            <Button size="small" variant="outlined" color="error" disabled={isEmpty} onClick={() => { setCleared(true); setClearedAt(termText || ""); }} sx={{ textTransform: "none" }}>Clear</Button>
          </Stack>
          <Paper ref={scrollRef} elevation={0} sx={{
            bgcolor: "#0d1117", borderRadius: 2, border: "1px solid #30363d", p: 2,
            minHeight: "calc(100vh - 340px)", maxHeight: "calc(100vh - 340px)",
            overflowY: "auto", overflowX: "auto",
            fontFamily: "'Cascadia Code','Fira Code','Consolas','Monaco',monospace",
            fontSize: "0.85rem", lineHeight: 1.6, color: "#c9d1d9",
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {isEmpty
              ? <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "calc(100vh - 400px)", color: "#484f58" }}>
                  <Typography variant="h6" sx={{ color: "#8b949e", mb: 1, fontWeight: 600 }}>No logs captured yet</Typography>
                  <Typography variant="body2" sx={{ color: "#484f58" }}>Logs will appear here when you run services or commands.</Typography>
                </Box>
              : displayText
            }
          </Paper>
        </CardContent>
      </Card>
    );
  }
  ns.pages.logs = function renderLogsPage(p) {
    return React.createElement(LogsPageInner, p);
  };

  // ── Home page ─────────────────────────────────────────────────────────────
  ns.pages.home = function renderHomePage(p) {
    const { Card, CardContent, Typography, Grid, Button, Box, setPage } = p;

    const categories = [
      {
        title: "Platform Services",
        subtitle: "Infrastructure & Deployment",
        description: "Install and manage APIs, Docker, S3 storage, MongoDB, Proxy, Python, Websites, SSL certificates, and file management tools.",
        page: "platform-services",
        color: "#1e40af",
        bg: "linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%)",
        border: "#bfdbfe",
      },
      {
        title: "AI & ML Services",
        subtitle: "Machine Learning & Intelligence",
        description: "Deploy and manage AI models, machine learning pipelines, inference servers, and data science workloads.",
        page: "ai-ml",
        color: "#6d28d9",
        bg: "linear-gradient(135deg,#f5f3ff 0%,#ede9fe 100%)",
        border: "#c4b5fd",
      },
    ];

    return (
      <Grid container spacing={3} sx={{ mt: 1 }}>
        {categories.map((cat) => (
          <Grid item xs={12} md={6} key={cat.page}>
            <Card
              sx={{
                borderRadius: 4,
                border: `1.5px solid ${cat.border}`,
                background: cat.bg,
                height: "100%",
                display: "flex",
                flexDirection: "column",
                boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
                transition: "box-shadow 0.2s",
                "&:hover": { boxShadow: "0 6px 24px rgba(0,0,0,0.12)" },
              }}
            >
              <CardContent sx={{ flexGrow: 1, p: 3, display: "flex", flexDirection: "column" }}>
                <Typography variant="overline" fontWeight={800} sx={{ color: cat.color, letterSpacing: 1.2, fontSize: 11 }}>
                  {cat.subtitle}
                </Typography>
                <Typography variant="h5" fontWeight={900} sx={{ color: cat.color, mt: 0.5, mb: 1.5 }}>
                  {cat.title}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1, mb: 3, lineHeight: 1.7 }}>
                  {cat.description}
                </Typography>
                <Button
                  variant="contained"
                  fullWidth
                  onClick={() => setPage(cat.page)}
                  sx={{
                    textTransform: "none",
                    fontWeight: 800,
                    borderRadius: 2.5,
                    py: 1.2,
                    fontSize: 15,
                    bgcolor: cat.color,
                    "&:hover": { bgcolor: cat.color, filter: "brightness(1.1)" },
                  }}
                >
                  Open {cat.title}
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };
})();
