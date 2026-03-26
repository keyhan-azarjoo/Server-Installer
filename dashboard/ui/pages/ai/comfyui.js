(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-comfyui"] = function renderComfyUIPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard, NavCard, TextField, FormControl, InputLabel, Select, MenuItem,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, formatServiceState, onServiceAction, IconOnlyAction, FolderIcon,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, setFileManagerPath,
    } = p;

    // Read comfyui state from the generic AI service state
    const comfyuiInfo = (p.comfyuiService) || {};
    const services = p.comfyuiPageServices || [];
    const loadInfo = p.loadComfyuiInfo;
    const loadServices = p.loadComfyuiServices;

    const httpUrl = String(comfyuiInfo.http_url || "").trim();
    const httpsUrl = String(comfyuiInfo.https_url || "").trim();
    const httpPort = String(comfyuiInfo.http_port || "8188").trim();
    const installed = !!comfyuiInfo.installed;
    const running = !!comfyuiInfo.running;
    const gpuInfo = comfyuiInfo.gpu || "";
    const bestUrl = httpsUrl || httpUrl || (installed ? `http://127.0.0.1:${httpPort}` : "");

    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));

    const commonFields = [
      { name: "COMFYUI_HOST_IP", label: "Host IP", type: "select", options: selectableIps, defaultValue: selectableIps[0] || "", required: true, placeholder: "Select IP" },
      { name: "COMFYUI_HTTP_PORT", label: "HTTP Port", defaultValue: httpPort || "8188", checkPort: true },
      { name: "COMFYUI_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: "", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "COMFYUI_DOMAIN", label: "Domain (optional)", defaultValue: comfyuiInfo.domain || "", placeholder: "e.g. comfyui.example.com" },
      { name: "COMFYUI_USERNAME", label: "Username (optional)", defaultValue: "", placeholder: "Leave empty for no auth" },
      { name: "COMFYUI_PASSWORD", label: "Password (optional)", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    return (
      <Grid container spacing={2}>
        {/* ── Description ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#7c3aed" }}>
                ComfyUI — Stable Diffusion Workflows
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Node-based Stable Diffusion UI for creating complex image generation workflows. Supports SDXL, ControlNet, LoRA, IP-Adapter, AnimateDiff, and hundreds of custom nodes.
              </Typography>
              <Alert severity="warning" sx={{ mt: 1, borderRadius: 2 }}>
                ComfyUI requires a GPU with 4+ GB VRAM for image generation. NVIDIA GPUs with CUDA are recommended. CPU mode is very slow.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Install Cards ── */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title={`Install ComfyUI — OS (${installOsLabel})`}
            description="Install ComfyUI as a managed OS service. Downloads the latest release and configures auto-start."
            action={cfg.os === "windows" ? "/run/comfyui_windows_os" : "/run/comfyui_unix_os"}
            fields={commonFields}
            onRun={run}
            color="#7c3aed"
          />
        </Grid>
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title="Install ComfyUI — Docker"
            description="Deploy ComfyUI in a Docker container with optional GPU passthrough."
            action="/run/comfyui_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>
        {cfg.os === "windows" && (
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Install ComfyUI — IIS"
              description="ComfyUI with IIS reverse proxy for HTTPS."
              action="/run/comfyui_windows_iis"
              fields={commonFields}
              onRun={run}
              color="#d97706"
            />
          </Grid>
        )}

        {/* ── Status ── */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#7c3aed" }}>ComfyUI Status</Typography>
              <Typography variant="body2">Installed: <Chip size="small" label={installed ? "Yes" : "No"} color={installed ? "success" : "default"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Running: <Chip size="small" label={running ? "Running" : "Stopped"} color={running ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
              <Typography variant="body2">Port: <b>{httpPort}</b></Typography>
              {httpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>URL: <a href={httpUrl} target="_blank" rel="noopener">{httpUrl}</a></Typography>}
              {gpuInfo && <Typography variant="body2">GPU: <b>{gpuInfo}</b></Typography>}
              {running && bestUrl && (
                <Button
                  variant="contained" size="small" sx={{ mt: 1, textTransform: "none", bgcolor: "#7c3aed" }}
                  onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}
                >
                  Open ComfyUI
                </Button>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* ── Services List ── */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6" fontWeight={800}>ComfyUI Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("comfyui")} onClick={() => { if (loadInfo?.current) loadInfo.current(); if (loadServices?.current) loadServices.current(); }} sx={{ textTransform: "none" }}>
                  {isScopeLoading("comfyui") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.comfyui && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.comfyui}</Alert>}
              {services.length === 0 && (
                <Typography variant="body2" color="text.secondary">No ComfyUI services deployed yet. Use an Install card above.</Typography>
              )}
              {services.map((svc) => (
                <Paper key={`comfyui-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
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
        {ns.renderApiDocs && ns.apiDocs && ns.apiDocs.comfyui && ns.renderApiDocs(p, ns.apiDocs.comfyui)}
      </Grid>
    );
  };
})();
