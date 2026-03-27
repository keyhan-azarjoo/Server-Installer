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

    // Best URL for "Open Dashboard" button — build from host+port if not set
    const computedHttpUrl = httpUrl || (httpPort ? `http://${hostIp || "127.0.0.1"}:${httpPort}` : "");
    const computedHttpsUrl = httpsUrl || (httpsPort ? `https://${hostIp || "127.0.0.1"}:${httpsPort}` : "");
    const bestUrl = computedHttpsUrl || computedHttpUrl;

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

        {/* ── API Documents Button (top) ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #7c3aed44", background: "linear-gradient(135deg, #7c3aed05 0%, #ffffff 100%)" }}>
            <CardContent sx={{ py: 2, "&:last-child": { pb: 2 } }}>
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Box sx={{ width: 6, height: 36, borderRadius: 3, bgcolor: "#7c3aed" }} />
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color: "#7c3aed" }}>SAM3 API Documentation</Typography>
                  <Typography variant="caption" color="text.secondary">16 API endpoints — detect, video, export, model info</Typography>
                </Box>
                <Chip label="16 endpoints" size="small" sx={{ bgcolor: "#7c3aed15", color: "#7c3aed", fontWeight: 700, border: "1px solid #7c3aed33" }} />
                <Button variant="contained" size="small" onClick={() => setPage("ai-sam3-api")} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" }, px: 3 }}>
                  API Documents
                </Button>
              </Stack>
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
              {!!computedHttpUrl && <Typography variant="body2" sx={{ mt: 0.5, wordBreak: "break-all" }}>HTTP: <a href={computedHttpUrl} target="_blank" rel="noopener">{computedHttpUrl}</a></Typography>}
              {!!computedHttpsUrl && <Typography variant="body2" sx={{ wordBreak: "break-all" }}>HTTPS: <a href={computedHttpsUrl} target="_blank" rel="noopener">{computedHttpsUrl}</a></Typography>}
              {!!bestUrl && (
                <Button variant="contained" size="small" sx={{ mt: 1.5, textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" } }} onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")}>
                  Open SAM3 Dashboard
                </Button>
              )}
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
                  <Button variant="contained" disabled={serviceBusy} onClick={() => window.open(bestUrl, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none", bgcolor: "#7c3aed", "&:hover": { bgcolor: "#6d28d9" } }}>
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
      </Grid>
    );
  };

  // ── SAM3 API Documentation Page ─────────────────────────────────────────────
  ns.pages["ai-sam3-api"] = function renderSam3ApiPage(p) {
    const { Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Tooltip, Alert, setPage, sam3Service, copyText } = p;
    const sam3 = sam3Service || {};
    const host = String(sam3.host || "").trim();
    const httpPort = String(sam3.http_port || "5000").trim();
    const httpsPort = String(sam3.https_port || "").trim();
    const urlHost = (host && host !== "0.0.0.0" && host !== "*") ? host : "{host}";
    const httpBase = "http://" + urlHost + ":" + httpPort;
    const httpsBase = httpsPort ? "https://" + urlHost + ":" + httpsPort : "";

    const MC = { GET: { bg: "#dcfce7", c: "#166534", b: "#86efac" }, POST: { bg: "#dbeafe", c: "#1e40af", b: "#93c5fd" }, DELETE: { bg: "#fee2e2", c: "#991b1b", b: "#fca5a5" } };
    const mc = (m) => MC[m] || { bg: "#f3f4f6", c: "#374151", b: "#d1d5db" };

    const doCopy = (text) => { if (copyText) copyText(text, "cURL"); else if (navigator.clipboard) navigator.clipboard.writeText(text); };

    const sections = [
      { name: "Image Detection", color: "#7c3aed", eps: [
        { m: "POST", p: "/detect", d: "Detect objects in an image using text prompts. Upload an image file and specify what objects to find.", body: 'multipart/form-data:\n  image: (file) JPEG/PNG image\n  prompt: (text) "person,car,dog"\n  threshold: (float) 0.0-1.0, default 0.3', res: '{\n  "detections": [\n    {\n      "label": "person",\n      "confidence": 0.95,\n      "bbox": [100, 50, 300, 400],\n      "mask": "base64-encoded-png..."\n    }\n  ]\n}' },
        { m: "POST", p: "/detect-point", d: "Segment the object at specific pixel coordinates. Click on the image to get the mask of that object. Use labels: 1 = foreground (select), 0 = background (exclude).", body: 'multipart/form-data:\n  image: (file) JPEG/PNG\n  points: (JSON) [[250, 300], [100, 100]]\n  labels: (JSON) [1, 0]', res: '{\n  "detections": [\n    { "mask": "base64...", "score": 0.98 }\n  ]\n}' },
        { m: "POST", p: "/detect-box", d: "Segment the object within a rectangular bounding box.", body: 'multipart/form-data:\n  image: (file) JPEG/PNG\n  box: (JSON) [x1, y1, x2, y2]', res: '{\n  "detections": [\n    { "mask": "base64...", "score": 0.97 }\n  ]\n}' },
        { m: "POST", p: "/detect-exemplar", d: "Find and segment objects similar to a visual example. Provide a cropped reference image of what to look for.", body: 'multipart/form-data:\n  image: (file) full image\n  exemplar: (file) cropped example', res: '{\n  "detections": [\n    { "mask": "base64...", "score": 0.92 }\n  ]\n}' },
        { m: "POST", p: "/detect-live", d: "Process a single camera/video frame for real-time detection. Optimized for low latency — send frames from a live feed.", body: 'multipart/form-data:\n  image: (file) frame\n  prompt: (text) objects to detect\n  threshold: (float) 0.0-1.0', res: '{\n  "detections": [...],\n  "processing_time_ms": 45\n}' },
      ]},
      { name: "Video Processing", color: "#0891b2", eps: [
        { m: "POST", p: "/upload-video", d: "Upload a video file for AI processing. Supports MP4, AVI, MOV formats. Returns a video_id for all subsequent video operations.", body: 'multipart/form-data:\n  video: (file) MP4/AVI/MOV', res: '{\n  "video_id": "abc123",\n  "frames": 300,\n  "fps": 30,\n  "duration": 10.0,\n  "width": 1920,\n  "height": 1080\n}' },
        { m: "GET", p: "/process-video/{video_id}?prompt={text}&threshold={float}", d: "Process the uploaded video with object detection. Returns a Server-Sent Events (SSE) stream with detection results for each frame.", res: 'text/event-stream:\n  data: { "frame": 1, "detections": [...] }\n  data: { "frame": 2, "detections": [...] }\n  ...' },
        { m: "GET", p: "/get-video/{video_id}", d: "Download the fully processed video with detection overlays (bounding boxes, labels) drawn on each frame.", res: "video/mp4 binary file download" },
        { m: "GET", p: "/get-frame/{video_id}/{frame_number}", d: "Get a specific processed frame as a JPEG image. Useful for previewing results.", res: "image/jpeg binary" },
        { m: "GET", p: "/track-object/{video_id}?x={x}&y={y}&frame={n}", d: "Track a selected object across all video frames. Click a point on a frame to select the object, then track it throughout the video. Returns SSE stream.", res: 'text/event-stream:\n  data: { "frame": 1, "bbox": [...], "mask": "..." }\n  ...' },
      ]},
      { name: "Export Results", color: "#059669", eps: [
        { m: "POST", p: "/export/mask", d: "Export a single detection mask as a transparent PNG image. Send the detection data from a /detect response.", body: 'JSON body with detection data from /detect response', res: "image/png binary (transparent mask)" },
        { m: "POST", p: "/export/masks-zip", d: "Export ALL detection masks as a ZIP archive. Each detection gets its own PNG file.", body: 'JSON body with detections array', res: "application/zip binary download" },
        { m: "POST", p: "/export/json", d: "Export all detections as a structured JSON file for programmatic use.", body: 'JSON body with detections array', res: "application/json file download" },
        { m: "POST", p: "/export/coco", d: "Export detections in COCO annotation format — standard format for training ML/AI models.", body: 'JSON body with detections array', res: "application/json (COCO annotation format)" },
      ]},
      { name: "Model & System Info", color: "#7c3aed", eps: [
        { m: "GET", p: "/model-info", d: "Get the current SAM3 model status including: model name, compute device (cpu/cuda/mps/tpu), whether the model is loaded, and VRAM usage.", res: '{\n  "model": "sam3",\n  "device": "cuda",\n  "loaded": true,\n  "vram_usage": "3.2 GB"\n}' },
        { m: "GET", p: "/", d: "Opens the SAM3 web dashboard — a visual interface for image detection, video processing, and result export. Open this URL in your browser.", res: "HTML page (SAM3 Dashboard UI)" },
      ]},
    ];

    return (
      <Grid container spacing={2}>
        {/* Header */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1.5px solid #7c3aed44" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={() => setPage("ai-sam3")} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700, borderColor: "#7c3aed", color: "#7c3aed" }}>
                  Back to SAM3
                </Button>
                <Typography variant="h5" fontWeight={900} sx={{ color: "#7c3aed", flexGrow: 1 }}>
                  SAM3 API Documentation
                </Typography>
                <Chip label="16 endpoints" size="small" sx={{ bgcolor: "#7c3aed15", color: "#7c3aed", fontWeight: 700, border: "1px solid #7c3aed33" }} />
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Complete API reference for SAM3 object detection & segmentation. All endpoints support both HTTP and HTTPS.
              </Typography>
              <Alert severity="info" sx={{ borderRadius: 2 }}>
                <b>HTTP:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpBase}</code>
                {httpsBase && <><br/><b>HTTPS:</b> <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>{httpsBase}</code></>}
                {!httpsBase && <><br/><b>HTTPS:</b> <span style={{ color: "#94a3b8" }}>Not configured — set HTTPS Port during install to enable</span></>}
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* Sections */}
        {sections.map((sec, si) => (
          <Grid item xs={12} key={si}>
            <Card sx={{ borderRadius: 3, border: "1px solid " + (sec.color || "#7c3aed") + "33" }}>
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
                  <Box sx={{ width: 5, height: 28, borderRadius: 3, bgcolor: sec.color || "#7c3aed" }} />
                  <Typography variant="h6" fontWeight={800} sx={{ color: sec.color || "#7c3aed", flexGrow: 1 }}>{sec.name}</Typography>
                  <Chip label={sec.eps.length + " endpoint" + (sec.eps.length > 1 ? "s" : "")} size="small" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
                </Stack>

                {sec.eps.map((ep, ei) => {
                  const cl = mc(ep.m);
                  return (
                    <Paper key={ei} variant="outlined" sx={{ p: 2, mb: 1.5, borderRadius: 2, "&:hover": { borderColor: (sec.color || "#7c3aed") + "66", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" } }}>
                      {/* Method + Paths (HTTP + HTTPS) */}
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "flex-start", md: "center" }}>
                        <Chip label={ep.m} size="small" sx={{ bgcolor: cl.bg, color: cl.c, border: "1px solid " + cl.b, fontWeight: 800, fontFamily: "monospace", minWidth: 70, justifyContent: "center" }} />
                        <Box sx={{ flexGrow: 1 }}>
                          <Typography sx={{ fontFamily: "'Cascadia Code','Fira Code','Consolas',monospace", fontWeight: 600, wordBreak: "break-all", fontSize: 14 }}>
                            {httpBase}{ep.p}
                          </Typography>
                          {httpsBase && (
                            <Typography sx={{ fontFamily: "'Cascadia Code','Fira Code','Consolas',monospace", fontWeight: 600, wordBreak: "break-all", fontSize: 13, color: "#059669", mt: 0.3 }}>
                              {httpsBase}{ep.p}
                            </Typography>
                          )}
                        </Box>
                        <Tooltip title="Copy cURL command">
                          <Button size="small" variant="outlined" onClick={() => doCopy("curl -X " + ep.m + " \"" + httpBase + ep.p + "\"")} sx={{ textTransform: "none", minWidth: 0, px: 1.5, fontSize: 11, borderColor: "#e2e8f0" }}>
                            cURL
                          </Button>
                        </Tooltip>
                      </Stack>

                      {/* Description */}
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1, lineHeight: 1.6 }}>{ep.d}</Typography>

                      {/* Request Body */}
                      {ep.body && (
                        <Box sx={{ mt: 1.5 }}>
                          <Typography variant="caption" fontWeight={700} sx={{ color: "#475569", display: "block", mb: 0.5 }}>Request Body:</Typography>
                          <Paper elevation={0} sx={{ p: 1.5, bgcolor: "#f8fafc", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", border: "1px solid #e2e8f0", lineHeight: 1.7 }}>
                            {ep.body}
                          </Paper>
                        </Box>
                      )}

                      {/* Response */}
                      {ep.res && (
                        <Box sx={{ mt: 1.5 }}>
                          <Typography variant="caption" fontWeight={700} sx={{ color: "#475569", display: "block", mb: 0.5 }}>Response:</Typography>
                          <Paper elevation={0} sx={{ p: 1.5, bgcolor: "#f0fdf4", borderRadius: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", border: "1px solid #dcfce7", lineHeight: 1.7 }}>
                            {ep.res}
                          </Paper>
                        </Box>
                      )}
                    </Paper>
                  );
                })}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };
})();
