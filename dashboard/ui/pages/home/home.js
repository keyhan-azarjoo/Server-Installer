(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

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
