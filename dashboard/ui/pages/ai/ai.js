(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-ml"] = function renderAiMlPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Alert,
      NavCard,
      cfg, serviceBusy,
      isScopeLoading,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage,
    } = p;

    return (
      <Grid container spacing={2}>
        {/* ── Page Description Card ─────────────────────────────────────────── */}
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
                Ensure your server meets the VRAM/RAM requirements for the models you plan to deploy.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Service NavCards ───────────────────────────────────────────────── */}
        <Grid item xs={12} md={6}>
          <NavCard
            title="Ollama"
            text="Run large language models locally. Supports GPU acceleration."
            onClick={() => setPage("ai-ollama")}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard
            title="Text Generation WebUI"
            text="Web UI for running LLMs with various backends."
            onClick={() => setPage("ai-tgwui")}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard
            title="ComfyUI"
            text="Node-based Stable Diffusion UI."
            onClick={() => setPage("ai-comfyui")}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard
            title="Custom Model"
            text="Deploy any AI model as a managed service."
            onClick={() => setPage("ai-custom")}
          />
        </Grid>

        {/* ── AI Services List ──────────────────────────────────────────────── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>AI & ML Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                  type="button"
                  variant="outlined"
                  disabled={isScopeLoading("ai")}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                >
                  {isScopeLoading("ai") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 460px)", overflow: "auto" }}>
                <Typography variant="body2" color="text.secondary">
                  No AI services deployed yet.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };
})();
