(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-tgwui"] = function renderTgwuiPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard, NavCard, TextField, FormControl, InputLabel, Select, MenuItem,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, formatServiceState, onServiceAction, IconOnlyAction, FolderIcon,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, setFileManagerPath,
    } = p;

    // Read tgwui state from the generic AI service state
    const tgwuiInfo = (p.tgwuiService) || {};
    const services = p.tgwuiPageServices || [];
    const loadInfo = p.loadTgwuiInfo;
    const loadServices = p.loadTgwuiServices;

    const httpUrl = String(tgwuiInfo.http_url || "").trim();
    const httpsUrl = String(tgwuiInfo.https_url || "").trim();
    const httpPort = String(tgwuiInfo.http_port || "7860").trim();
    const installed = !!tgwuiInfo.installed;
    const running = !!tgwuiInfo.running;
    const deployMode = String(tgwuiInfo.deploy_mode || "").trim();
    const httpsPort = String(tgwuiInfo.https_port || "").trim();
    const bestUrl = httpsUrl || httpUrl || (installed && httpsPort ? `https://127.0.0.1:${httpsPort}` : installed ? `http://127.0.0.1:${httpPort}` : "");

    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

    const commonFields = [
      { name: "TGWUI_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "TGWUI_HTTP_PORT", label: "HTTP Port", defaultValue: httpPort || "7860", checkPort: true },
      { name: "TGWUI_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "TGWUI_DOMAIN", label: "Domain (optional)", defaultValue: tgwuiInfo.domain || "", placeholder: "e.g. tgwui.example.com" },
      { name: "TGWUI_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "TGWUI_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    return (
      <Grid container spacing={2}>
        {/* ── Description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#7c3aed" }}>
                Text Generation WebUI
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Oobabooga's Text Generation WebUI — a Gradio-based interface for running LLMs with multiple backends
                (transformers, GPTQ, GGUF, ExLlama, AutoAWQ). Supports chat, notebook, and API modes.
              </Typography>
              <Alert severity="warning" sx={{ mt: 1, borderRadius: 2 }}>
                Text Generation WebUI requires a GPU with 8+ GB VRAM for most models. CPU-only mode is supported but
                significantly slower. NVIDIA GPUs with CUDA support are recommended for best performance.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Install Cards ── */}
        <Grid item xs={12} md={6}>
          <ActionCard
            title={`Install Text Generation WebUI — OS (${installOsLabel})`}
            description="Install Text Generation WebUI as a managed OS service. Clones the repository and configures auto-start."
            action={cfg.os === "windows" ? "/run/tgwui_windows_os" : "/run/tgwui_unix_os"}
            fields={commonFields}
            onRun={run}
            color="#7c3aed"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title="Install Text Generation WebUI — Docker"
            description="Deploy Text Generation WebUI in a Docker container with optional GPU passthrough."
            action="/run/tgwui_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>

        {/* ── Status ── */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#7c3aed" }}>Text Generation WebUI Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Port: <b>{httpPort}</b></Typography>
              {deployMode && <Typography variant="body2">Deploy mode: <b>{deployMode}</b></Typography>}
              {httpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>URL: <a href={httpUrl} target="_blank" rel="noopener">{httpUrl}</a></Typography>}
              {running && bestUrl && (
                <Button
                  variant="contained" size="small" sx={{ mt: 1, textTransform: "none", bgcolor: "#7c3aed" }}
                  onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}
                >
                  Open WebUI
                </Button>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* ── Info Panel ── */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>About Text Generation WebUI</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Text Generation WebUI (oobabooga) provides a full-featured Gradio interface for loading and interacting
                with large language models. It supports many model formats and backends including:
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                {["Transformers", "GPTQ", "GGUF / llama.cpp", "ExLlamaV2", "AutoAWQ", "HQQ", "TensorRT-LLM"].map((b) => (
                  <Chip key={b} label={b} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                ))}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                The WebUI includes chat, notebook, and default (raw completion) modes. It also exposes an OpenAI-compatible
                API endpoint for programmatic access. Models can be downloaded directly from Hugging Face within the interface.
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Services List ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>Text Generation WebUI Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("tgwui")} onClick={() => { if (loadInfo?.current) loadInfo.current(); if (loadServices?.current) loadServices.current(); }} sx={{ textTransform: "none" }}>
                  {isScopeLoading("tgwui") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.tgwui && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.tgwui}</Alert>}
              {services.length === 0 && (
                <Typography variant="body2" color="text.secondary">No Text Generation WebUI services deployed yet. Use an Install card above.</Typography>
              )}
              {services.map((svc) => (
                <Paper key={`tgwui-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Box sx={{ minWidth: 250 }}>
                      <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                      {renderServiceUrls(svc)}
                      {renderServicePorts(svc)}
                    </Box>
                    {renderServiceStatus(svc)}
                    <Box sx={{ flexGrow: 1 }} />
                    {renderFolderIcon(svc)}
                    {svc.manageable !== false && (
                      <>
                        <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                          {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                        </Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                      </>
                    )}
                    {svc.deletable && (
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                    )}
                  </Stack>
                </Paper>
              ))}
            </CardContent>
          </Card>
        </Grid>

        {/* ── API Docs ── */}
        {ns.renderApiDocs && ns.apiDocs && ns.apiDocs.tgwui && ns.renderApiDocs(p, ns.apiDocs.tgwui)}
      </Grid>
    );
  };
})();
