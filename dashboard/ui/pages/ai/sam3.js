(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-sam3"] = function renderAiSam3Page(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard, NavCard,
      cfg, run, selectableIps, serviceBusy,
      isScopeLoading, scopeErrors,
      isServiceRunningStatus, formatServiceState, onServiceAction, IconOnlyAction, FolderIcon,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setInfoMessage, setFileManagerPath,
      sam3Service, sam3PageServices,
      loadSam3Info, loadSam3Services,
    } = p;

    const sam3 = sam3Service || {};
    const services = sam3PageServices || [];
    const httpUrl = String(sam3.http_url || "").trim();
    const httpsUrl = String(sam3.https_url || "").trim();
    const httpPort = String(sam3.http_port || "").trim();
    const httpsPort = String(sam3.https_port || "").trim();
    const hostIp = String(sam3.host || "").trim();
    const device = String(sam3.device || "cpu").trim();
    const modelReady = !!sam3.model_downloaded;
    const deployMode = String(sam3.deploy_mode || "os").trim();
    const authEnabled = !!sam3.auth_enabled;
    const authUser = String(sam3.auth_username || "").trim();
    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));
    const modelPath = String(sam3.model_path || "").trim();
    const modelDir = String(sam3.model_dir || sam3.default_model_dir || "").trim();
    const installDir = String(sam3.install_dir || "").trim();
    const openInFiles = (dir) => { if (dir && setFileManagerPath) { setFileManagerPath(dir); setPage("files"); } };

    // Build GPU options - only show if GPU is actually detected
    const hasGpu = sam3.detected_gpu_type && sam3.detected_gpu_type !== "cpu" && sam3.detected_gpu_type !== "";
    const detectedGpusList = (sam3.detected_gpus && Array.isArray(sam3.detected_gpus))
      ? sam3.detected_gpus.filter((g) => g.type && g.type !== "cpu")
      : [];
    const hasDetectedGpus = detectedGpusList.length > 0 || hasGpu;

    const gpuFields = [];
    if (hasDetectedGpus) {
      const gpuOptions = [{ label: "Auto-detect", value: "auto" }];
      detectedGpusList.forEach((gpu) => {
        if (gpu.type === "cuda") gpuOptions.push({ label: `NVIDIA: ${gpu.name} (${gpu.vram_gb} GB)`, value: "cuda" });
        else if (gpu.type === "rocm") gpuOptions.push({ label: `AMD: ${gpu.name}`, value: "rocm" });
        else if (gpu.type === "mps") gpuOptions.push({ label: `Apple Silicon: ${gpu.name}`, value: "mps" });
        else if (gpu.type === "tpu") gpuOptions.push({ label: "Google TPU", value: "tpu" });
      });
      if (hasGpu && detectedGpusList.length === 0) {
        if (sam3.detected_gpu_type === "cuda") gpuOptions.push({ label: `NVIDIA: ${sam3.detected_gpu_name || "GPU"}`, value: "cuda" });
        else if (sam3.detected_gpu_type === "rocm") gpuOptions.push({ label: `AMD: ${sam3.detected_gpu_name || "GPU"}`, value: "rocm" });
        else if (sam3.detected_gpu_type === "mps") gpuOptions.push({ label: `Apple: ${sam3.detected_gpu_name || "Silicon"}`, value: "mps" });
        else if (sam3.detected_gpu_type === "tpu") gpuOptions.push({ label: "Google TPU", value: "tpu" });
      }
      gpuOptions.push({ label: "CPU Only", value: "cpu" });
      gpuFields.push({
        name: "SAM3_GPU_DEVICE",
        label: "GPU / Accelerator",
        type: "select",
        options: gpuOptions.map((o) => o.value),
        optionLabels: gpuOptions.reduce((acc, o) => { acc[o.value] = o.label; return acc; }, {}),
        defaultValue: device || "auto",
      });
    }

    // Common fields for all install modes
    const commonFields = [
      {
        name: "SAM3_HOST_IP",
        label: "Host IP",
        type: "select",
        options: selectableIps,
        defaultValue: hostIp,
        required: true,
        disabled: selectableIps.length === 0,
        placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
      },
      { name: "SAM3_HTTP_PORT", label: "HTTP Port (optional)", defaultValue: httpPort || "5000", checkPort: true, placeholder: "Leave empty to skip HTTP" },
      { name: "SAM3_HTTPS_PORT", label: "HTTPS Port (optional)", defaultValue: httpsPort || "5443", checkPort: true, certSelect: "SSL_CERT_NAME", placeholder: "Leave empty to skip HTTPS" },
      { name: "SAM3_DOMAIN", label: "Domain (optional)", defaultValue: sam3.domain || "", placeholder: "e.g. sam3.example.com" },
      ...gpuFields,
      { name: "SAM3_USERNAME", label: "Username", defaultValue: authUser || "", placeholder: "Leave empty for no auth" },
      { name: "SAM3_PASSWORD", label: "Password", type: "password", defaultValue: "", placeholder: "Leave empty for no auth" },
    ];

    // Best URL for "Open Dashboard" button
    const bestUrl = httpsUrl || httpUrl;

    return (
      <Grid container spacing={2}>
        {/* ── Page Description ──────────────────────────────────── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: "#6d28d9" }}>
                SAM3 - Segment Anything Model 3
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Deploy Meta's Segment Anything Model 3 for advanced object detection and segmentation.
                Supports text, point, bounding-box, and visual exemplar prompts. Includes video processing
                with object tracking, live camera detection, and multiple export formats.
              </Typography>
              <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                SAM3 requires ~4 GB disk space for the model file and benefits greatly from a dedicated GPU.
                CPU-only mode is supported but will be significantly slower. The model file (sam3.pt) can be
                downloaded after installation using the Download button below.
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Install SAM3 (OS Service) ────────────────────────── */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title={`Install SAM3 - OS (${installOsLabel})`}
            description="Install SAM3 as a managed OS service with systemd (Linux) or scheduled task (Windows). Includes Nginx HTTPS reverse proxy."
            action={cfg.os === "windows" ? "/run/sam3_windows_os" : "/run/sam3_linux_os"}
            fields={commonFields}
            onRun={run}
            color="#7c3aed"
          />
        </Grid>

        {/* ── Install SAM3 (Docker) ────────────────────────────── */}
        <Grid item xs={12} md={cfg.os === "windows" ? 4 : 6}>
          <ActionCard
            title="Install SAM3 - Docker"
            description="Deploy SAM3 as a Docker container with GPU passthrough. Requires Docker and nvidia-container-toolkit for GPU support."
            action="/run/sam3_docker"
            fields={commonFields}
            onRun={run}
            color="#0891b2"
          />
        </Grid>

        {/* ── Install SAM3 (IIS) - Windows Only ────────────────── */}
        {cfg.os === "windows" && (
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Install SAM3 - IIS"
              description="Install SAM3 with IIS reverse proxy. The service runs as an OS process with IIS forwarding HTTPS traffic."
              action="/run/sam3_windows_iis"
              fields={commonFields}
              onRun={run}
              color="#d97706"
            />
          </Grid>
        )}

        {/* ── Status Card ──────────────────────────────────────── */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, color: "#7c3aed" }}>SAM3 Status</Typography>
              <Typography variant="body2">Device: <b>{device}</b></Typography>
              <Typography variant="body2">Model: <Chip size="small" label={modelReady ? "Ready" : "Not Downloaded"} color={modelReady ? "success" : "warning"} sx={{ ml: 0.5 }} /></Typography>
              {sam3.installed && <Typography variant="body2">Deploy Mode: <b>{deployMode}</b></Typography>}
              {authEnabled && <Typography variant="body2">Auth: User: {authUser}</Typography>}
              {hostIp && <Typography variant="body2">Host: {hostIp}</Typography>}
              {httpPort && <Typography variant="body2">HTTP Port: {httpPort}</Typography>}
              {httpsPort && <Typography variant="body2">HTTPS Port: {httpsPort}</Typography>}
              {sam3.detected_gpu_name && <Typography variant="body2">GPU: {sam3.detected_gpu_name}</Typography>}
              {modelReady && !!modelDir && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}>
                  <IconOnlyAction title={`Open ${modelDir}`} IconComp={FolderIcon} fallback="folder" onClick={() => openInFiles(modelDir)} />
                  <Typography variant="body2" sx={{ wordBreak: "break-all", cursor: "pointer", "&:hover": { textDecoration: "underline", color: "#7c3aed" } }} onClick={() => openInFiles(modelDir)}>
                    {modelDir}
                  </Typography>
                </Box>
              )}
              {!!httpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>HTTP: <a href={httpUrl} target="_blank" rel="noopener">{httpUrl}</a></Typography>}
              {!!httpsUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>HTTPS: <a href={httpsUrl} target="_blank" rel="noopener">{httpsUrl}</a></Typography>}
            </CardContent>
          </Card>
        </Grid>

        {/* ── Download Model Card ──────────────────────────────── */}
        <Grid item xs={12} md={4}>
          <ActionCard
            title="Download SAM3 Model"
            description={modelReady
              ? "The SAM3 model is already downloaded. Click Start to re-download and replace."
              : "Download the SAM3 model file (~3.4 GB) to the server. Required before SAM3 can perform detections."
            }
            action="/run/sam3_download_model"
            fields={[
              { name: "SAM3_MODEL_URL", label: "Model Download URL", defaultValue: "https://huggingface.co/facebook/sam3/resolve/main/sam3.pt?download=true", placeholder: "https://...sam3.pt", required: true },
              { name: "SAM3_DL_TOKEN", label: "Auth Token (optional)", defaultValue: "", placeholder: "HuggingFace token or Bearer token if login required" },
              {
                name: "SAM3_REPLACE_MODEL",
                label: "Replace existing model?",
                type: "select",
                options: ["yes", "no"],
                defaultValue: "yes",
              },
            ]}
            onRun={run}
            color="#059669"
          />
          {modelReady && modelPath && (
            <Box sx={{ mt: 1, display: "flex", alignItems: "center", gap: 0.5 }}>
              <IconOnlyAction title={`Open ${modelDir}`} IconComp={FolderIcon} fallback="folder" onClick={() => openInFiles(modelDir)} />
              <Typography variant="caption" color="text.secondary" sx={{ wordBreak: "break-all", cursor: "pointer", "&:hover": { textDecoration: "underline" } }} onClick={() => openInFiles(modelDir)}>
                {modelPath}
              </Typography>
            </Box>
          )}
        </Grid>

        {/* ── SAM3 Services List ───────────────────────────────── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>SAM3 Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                {!!bestUrl && (
                  <Button variant="contained" disabled={serviceBusy || !modelReady} onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" } }}>
                    Open SAM3 Dashboard
                  </Button>
                )}
                <Button
                  variant="outlined"
                  disabled={isScopeLoading("sam3")}
                  onClick={() => { if (loadSam3Info && loadSam3Info.current) loadSam3Info.current(); if (loadSam3Services && loadSam3Services.current) loadSam3Services.current(); }}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                >
                  {isScopeLoading("sam3") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.sam3 && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.sam3}</Alert>}
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {services.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    No SAM3 services deployed yet. Use an Install card above to deploy SAM3.
                  </Typography>
                )}
                {services.map((svc) => (
                  <Paper key={`sam3-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                        {svc.display_name && <Typography variant="caption" color="text.secondary">{svc.display_name}</Typography>}
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon(svc)}
                      {svc.manageable !== false && (
                        <>
                          <Button
                            size="small"
                            variant="outlined"
                            color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"}
                            disabled={serviceBusy || (!modelReady && !isServiceRunningStatus(svc.status, svc.sub_status))}
                            onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)}
                            sx={{ textTransform: "none" }}
                          >
                            {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                          </Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy || !modelReady} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                        </>
                      )}
                      {svc.deletable && (
                        <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => {
                          const ok = window.confirm(`Do you want to delete SAM3 service '${svc.name}'?`);
                          if (!ok) return;
                          let detail = "";
                          if (modelReady) {
                            const delModel = window.confirm("Do you also want to delete the sam3.pt model file (~3.4 GB)?");
                            if (delModel) detail = "delete_model";
                          }
                          onServiceAction("delete", { ...svc, detail, _skipConfirm: true });
                        }} sx={{ textTransform: "none" }}>
                          Delete
                        </Button>
                      )}
                    </Stack>
                  </Paper>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        {ns.renderApiDocs && ns.apiDocs && ns.apiDocs.sam3 && ns.renderApiDocs(p, ns.apiDocs.sam3)}
      </Grid>
    );
  };
})();
