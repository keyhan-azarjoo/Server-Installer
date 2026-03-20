(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // ── Platform Services page ────────────────────────────────────────────────
  ns.pages["platform-services"] = function renderPlatformServicesPage(p) {
    const { Grid, NavCard, setPage, startNewWebsiteDeployment, setFileManagerData } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <NavCard title="API" text="Open DotNet and Python API installer/deployment pages." onClick={() => setPage("api")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Docker" text="Install Docker and manage Docker services/containers." onClick={() => setPage("docker")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="S3" text="Open S3 installer pages." onClick={() => setPage("s3")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="MongoDB" text="Install MongoDB with a Compass-style web admin UI." onClick={() => setPage("mongo")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Proxy" text="Install and manage the multi-layer proxy stack." onClick={() => setPage("proxy")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python" text="Install Python and manage Jupyter notebooks, kernels, and runtime services." onClick={() => setPage("python")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Websites" text="Deploy and manage exported static websites, Flutter web builds, and Next export output on IIS." onClick={() => startNewWebsiteDeployment()} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Files" text="Browse, upload, edit, rename, download, and delete files across the server filesystem." onClick={() => { setPage("files"); setFileManagerData(null); }} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="SSL & Certificates" text="Manage TLS certificates: get free Let's Encrypt certs, upload your own CA-signed certs, and assign them to IIS, nginx, or any service." onClick={() => setPage("ssl")} outlined />
        </Grid>
      </Grid>
    );
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
