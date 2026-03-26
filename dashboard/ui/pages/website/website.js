(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  // ── Engine definitions ──────────────────────────────────────────────────────
  // Ordered by priority (best first). Each engine defines OS support and
  // which code types it can run.  The UI filters by cfg.os and validates
  // compatibility against the selected website kind.
  const ALL_ENGINES = [
    {
      id: "docker",
      label: "Docker",
      color: "#1f2937",
      icon: "D",
      os: ["windows", "linux", "darwin"],
      supports: ["static", "flutter", "next-export", "nextjs", "php", "auto"],
      description: "Run in a Docker container. Supports all website types — Node.js, PHP, static, Next.js, and more. Auto-installs if needed.",
      installable: true,
    },
    {
      id: "nginx",
      label: "Nginx",
      color: "#009639",
      icon: "N",
      os: ["linux", "darwin"],
      supports: ["static", "flutter", "next-export", "php", "auto"],
      incompatible: { nextjs: "Next.js requires a Node.js runtime. Use Docker or Node.js engine instead." },
      description: "Lightweight, high-performance web server. Best for static sites and PHP on Linux/macOS. Auto-installs via package manager.",
      installable: true,
    },
    {
      id: "iis",
      label: "IIS",
      color: "#1d4ed8",
      icon: "I",
      os: ["windows"],
      supports: ["static", "flutter", "next-export", "auto"],
      incompatible: {
        nextjs: "Next.js requires a Node.js runtime. Use Docker or Node.js engine instead.",
        php: "PHP on IIS requires additional CGI setup. Use Docker or XAMPP instead.",
      },
      description: "Internet Information Services — Windows native web server. Best for static and exported sites on Windows.",
      installable: true,
    },
    {
      id: "nodejs",
      label: "Node.js",
      color: "#339933",
      icon: "JS",
      os: ["windows", "linux", "darwin"],
      supports: ["nextjs", "static", "next-export", "auto"],
      incompatible: { php: "PHP code cannot run on Node.js. Use Nginx, Docker, or XAMPP." },
      description: "Run with Node.js runtime. Required for Next.js SSR. Also serves static sites via a lightweight server.",
      installable: true,
    },
    {
      id: "kubernetes",
      label: "Kubernetes",
      color: "#326ce5",
      icon: "K",
      os: ["linux"],
      supports: ["static", "flutter", "next-export", "nextjs", "php", "auto"],
      description: "Deploy to a local Kubernetes cluster (K3s/MicroK8s). For production-grade orchestration and scaling.",
      installable: true,
    },
    {
      id: "pm2",
      label: "PM2",
      color: "#2B037A",
      icon: "PM",
      os: ["windows", "linux", "darwin"],
      supports: ["nextjs", "static", "next-export", "auto"],
      incompatible: { php: "PHP code cannot run under PM2. Use Nginx, Docker, or XAMPP." },
      description: "Node.js process manager with auto-restart, clustering, and monitoring. Great for Next.js in production.",
      installable: true,
    },
    {
      id: "service",
      label: "OS Service",
      color: "#0f766e",
      icon: "OS",
      os: ["windows", "linux", "darwin"],
      supports: ["static", "flutter", "next-export", "nextjs", "php", "auto"],
      description: "Run as a managed OS service (systemd/Windows Service/launchd). Built-in — no extra install needed.",
      installable: false,
    },
  ];

  // Code-type labels for user display
  const KIND_LABELS = {
    auto: "Auto-detect",
    static: "Static / HTML",
    "next-export": "Next.js Export",
    nextjs: "Next.js (SSR)",
    flutter: "Flutter Web",
    php: "PHP",
  };

  function WebsiteInner(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box,
      TextField, MenuItem, Select, FormControl, InputLabel,
      Paper, Chip, Tooltip, isServiceRunningStatus, formatServiceState,
      cfg, run, selectableIps, getDefaultSelectableIp, serviceBusy,
      websiteEditor, websiteInfo, websiteServices,
      iis, docker,
      isScopeLoading, loadWebsiteInfo, loadWebsiteServices,
      onServiceAction, openWebsiteRun,
      renderServiceStatus,
      renderServiceUrls, renderServicePorts, renderFolderIcon, renderEditServiceIcon,
      scopeErrors,
      defaultWebsiteDirForOs,
      setPage, setFileManagerPath,
    } = p;

    const websiteHost = selectableIps.includes(String(websiteEditor?.host || "").trim())
      ? String(websiteEditor?.host || "").trim()
      : getDefaultSelectableIp(selectableIps);

    // ── Form state ─────────────────────────────────────────────────────────
    const [siteName,   setSiteName]   = React.useState(websiteEditor?.name || "ServerInstallerWebsite");
    const [siteKind,   setSiteKind]   = React.useState(websiteEditor?.kind || "auto");
    const [bindIp,     setBindIp]     = React.useState(websiteHost);
    const [domainName, setDomainName] = React.useState(websiteEditor?.domain || "");
    const [port,       setPort]       = React.useState(websiteEditor?.port || "8088");
    const [httpsPort,  setHttpsPort]  = React.useState(websiteEditor?.https_port || "");
    const [source,     setSource]     = React.useState(websiteEditor?.source || defaultWebsiteDirForOs(cfg.os));
    const [engine,     setEngine]     = React.useState("auto");
    const formRef      = React.useRef(null);
    const hiddenTargetRef = React.useRef(null);

    // ── Engine detection state ────────────────────────────────────────────
    const [engineStatus, setEngineStatus] = React.useState({}); // { docker: {installed, version}, nginx: ... }
    const [engineChecking, setEngineChecking] = React.useState(false);

    // ── Port-check state ──────────────────────────────────────────────────
    const [portResults,   setPortResults]   = React.useState(null);
    const [portChecking,  setPortChecking]  = React.useState(false);

    // ── Folder-upload state ───────────────────────────────────────────────
    const [uploadBusy,    setUploadBusy]    = React.useState(false);
    const [uploadStatus,  setUploadStatus]  = React.useState(null);
    const [selectedFiles, setSelectedFiles] = React.useState([]);
    const folderInputRef  = React.useRef(null);

    // ── SSL cert list ─────────────────────────────────────────────────────
    const [certList,     setCertList]     = React.useState([]);
    const [selectedCert, setSelectedCert] = React.useState("self_signed");

    React.useEffect(() => {
      fetch("/api/ssl/list", { headers: { "X-Requested-With": "fetch" } })
        .then((r) => r.json())
        .then((j) => { if (j.ok) setCertList(j.certs || []); })
        .catch(() => {});
    }, []);

    // ── Check engine status on mount ──────────────────────────────────────
    React.useEffect(() => {
      setEngineChecking(true);
      fetch("/api/website/engines", { headers: { "X-Requested-With": "fetch" } })
        .then((r) => r.json())
        .then((j) => { if (j.ok) setEngineStatus(j.engines || {}); })
        .catch(() => {})
        .finally(() => setEngineChecking(false));
    }, []);

    React.useEffect(() => {
      if (!bindIp) { const d = getDefaultSelectableIp(selectableIps); if (d) setBindIp(d); }
    }, [selectableIps]);

    const kindOptions = ["auto", "static", "next-export", "nextjs", "flutter", "php"];

    const hasAnyPort = !!(port.trim() || httpsPort.trim());

    // ── Filter engines by OS ──────────────────────────────────────────────
    const osEngines = ALL_ENGINES.filter((e) => e.os.includes(cfg.os));

    // ── Check compatibility between engine and code type ─────────────────
    const getEngineCompat = (eng, kind) => {
      if (kind === "auto") return { ok: true };
      if (eng.incompatible && eng.incompatible[kind]) return { ok: false, reason: eng.incompatible[kind] };
      if (!eng.supports.includes(kind) && !eng.supports.includes("auto")) return { ok: false, reason: `${eng.label} does not support ${KIND_LABELS[kind] || kind} projects.` };
      return { ok: true };
    };

    // ── Auto-select best engine ──────────────────────────────────────────
    const resolvedEngine = React.useMemo(() => {
      if (engine !== "auto") return engine;
      // Pick best engine based on: installed status, code type compatibility, priority order
      for (const eng of osEngines) {
        const compat = getEngineCompat(eng, siteKind);
        if (!compat.ok) continue;
        const status = engineStatus[eng.id];
        if (status && status.installed) return eng.id;
      }
      // Fallback: first compatible engine
      for (const eng of osEngines) {
        const compat = getEngineCompat(eng, siteKind);
        if (compat.ok) return eng.id;
      }
      return "service";
    }, [engine, siteKind, osEngines, engineStatus]);

    const selectedEngineObj = osEngines.find((e) => e.id === resolvedEngine) || osEngines[osEngines.length - 1];
    const selectedCompat = getEngineCompat(selectedEngineObj, siteKind);

    // ── Map engine id to backend WEBSITE_TARGET ──────────────────────────
    const engineToTarget = (engId) => {
      const map = { docker: "docker", iis: "iis", nginx: "nginx", nodejs: "nodejs", kubernetes: "kubernetes", pm2: "pm2", service: "service" };
      return map[engId] || "service";
    };

    const handleDeploy = React.useCallback((e) => {
      if (!port.trim() && !httpsPort.trim()) {
        e.preventDefault();
        setPortResults({ _error: { label: "Ports", ok: false, error: "At least one port (HTTP or HTTPS) is required." } });
        return;
      }
      if (!selectedCompat.ok) {
        e.preventDefault();
        return;
      }
      const target = engineToTarget(resolvedEngine);
      if (hiddenTargetRef.current) hiddenTargetRef.current.value = target;
      if (!source.trim()) {
        const def = defaultWebsiteDirForOs(cfg.os);
        setSource(def);
      }
      run(e, "/run/website_deploy", `Deploy Website → ${selectedEngineObj.label}`, formRef.current);
    }, [run, source, cfg.os, port, httpsPort, resolvedEngine, selectedCompat, selectedEngineObj]);

    // ── Port conflict check ───────────────────────────────────────────────
    const checkPorts = React.useCallback(async () => {
      const toCheck = [
        port.trim()      ? { port: port.trim(),      label: "HTTP Port" }  : null,
        httpsPort.trim() ? { port: httpsPort.trim(), label: "HTTPS Port" } : null,
      ].filter(Boolean);
      if (!toCheck.length) return;
      setPortChecking(true);
      setPortResults(null);
      const results = {};
      await Promise.all(toCheck.map(async ({ port: p, label }) => {
        try {
          const fd = new FormData();
          fd.append("port", p);
          fd.append("protocol", "tcp");
          const r = await fetch("/api/system/port_check", {
            method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd,
          });
          const j = await r.json();
          results[p] = { label, ...j };
        } catch (ex) {
          results[p] = { label, ok: false, error: String(ex) };
        }
      }));
      setPortResults(results);
      setPortChecking(false);
    }, [port, httpsPort]);

    // ── Install engine ────────────────────────────────────────────────────
    const handleInstallEngine = React.useCallback((engineId) => {
      const fd = new FormData();
      fd.append("ENGINE_ID", engineId);
      // Use the run system to stream output
      run(null, "/run/website_engine_install", `Install ${engineId}`, fd);
    }, [run]);

    // ── Stage selected files ─────────────────────────────────────────────
    const handleFilesSelected = React.useCallback((event) => {
      const files = Array.from(event.target.files || []);
      event.target.value = "";
      setSelectedFiles(files);
      setUploadStatus(null);
    }, []);

    // ── Upload staged files ──────────────────────────────────────────────
    const handleFolderUpload = React.useCallback(async () => {
      const files = selectedFiles;
      if (!files.length) return;
      let targetDir = source.trim();
      if (!targetDir) {
        targetDir = defaultWebsiteDirForOs(cfg.os);
        setSource(targetDir);
      }
      const fileCount = files.length;
      const totalBytes = files.reduce((sum, f) => sum + Number(f.size || 0), 0);
      setUploadBusy(true);
      setUploadStatus(null);
      if (window.ServerInstallerTerminalHook) {
        window.ServerInstallerTerminalHook({
          open: true,
          state: "Uploading for: Website",
          line: `[${new Date().toLocaleTimeString()}] Upload started for Website (${fileCount} file(s), ${totalBytes} bytes)`,
        });
      }
      try {
        const fd = new FormData();
        fd.append("target", targetDir);
        files.forEach((f) => fd.append("files", f, f.webkitRelativePath || f.name));
        const r = await fetch("/api/files/upload", {
          method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd,
        });
        const j = await r.json();
        if (j.ok) {
          setSelectedFiles([]);
          const firstRel = (files[0]?.webkitRelativePath || "").replace(/\\/g, "/");
          const folderName = firstRel.split("/")[0];
          if (folderName) {
            const sep = targetDir.includes("/") ? "/" : "\\";
            const updated = targetDir.replace(/[\\/]$/, "") + sep + folderName;
            setSource(updated);
            targetDir = updated;
          }
          if (window.ServerInstallerTerminalHook) {
            window.ServerInstallerTerminalHook({
              open: true,
              state: "Uploading for: Website",
              line: `[${new Date().toLocaleTimeString()}] Upload completed. Server path: ${targetDir}`,
            });
          }
          setUploadStatus({ ok: true, text: "Upload completed successfully." });
        } else {
          throw new Error(j.error || "Upload failed.");
        }
      } catch (ex) {
        const message = String(ex);
        setUploadStatus({ ok: false, text: message });
        if (window.ServerInstallerTerminalHook) {
          window.ServerInstallerTerminalHook({
            open: true, state: "Error",
            line: `[${new Date().toLocaleTimeString()}] Upload failed: ${message}`,
          });
        }
      } finally {
        setUploadBusy(false);
      }
    }, [selectedFiles, source, cfg.os]);

    const openSourceInFileManager = React.useCallback(() => {
      const dir = source.trim();
      if (!dir || !setFileManagerPath || !setPage) return;
      setFileManagerPath(dir);
      setPage("files");
    }, [source, setFileManagerPath, setPage]);

    const websiteLoading = isScopeLoading("website");

    return (
      <Grid container spacing={2}>
        {/* ── Header ── */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
              <Typography variant="h6" fontWeight={800}>Website Deployment</Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Configuration form ── */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 2 }}>Website Configuration</Typography>
              <form ref={formRef}>
                <input ref={hiddenTargetRef} type="hidden" name="WEBSITE_TARGET" value={engineToTarget(resolvedEngine)} />
                <input type="hidden" name="WEBSITE_ENGINE" value={resolvedEngine} />
                <Stack spacing={2}>
                  <TextField
                    label="Website Name" size="small" fullWidth required
                    name="WEBSITE_SITE_NAME" value={siteName}
                    onChange={(e) => setSiteName(e.target.value)}
                  />
                  <FormControl size="small" fullWidth>
                    <InputLabel>Website Type</InputLabel>
                    <Select label="Website Type" name="WEBSITE_KIND" value={siteKind} onChange={(e) => { setSiteKind(e.target.value); setEngine("auto"); }}>
                      {kindOptions.map((k) => <MenuItem key={k} value={k}>{KIND_LABELS[k] || k}</MenuItem>)}
                    </Select>
                  </FormControl>

                  {/* ── Runtime Engine Selector ── */}
                  <Box>
                    <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Runtime Engine</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                      Select how your website will be served. Engines are ordered by recommendation. Incompatible engines are disabled.
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                      <Chip
                        label="Auto (Best Match)"
                        size="small"
                        variant={engine === "auto" ? "filled" : "outlined"}
                        onClick={() => setEngine("auto")}
                        sx={{
                          cursor: "pointer", fontWeight: 700,
                          ...(engine === "auto" ? { bgcolor: "#6d28d9", color: "#fff" } : {}),
                        }}
                      />
                      {osEngines.map((eng) => {
                        const compat = getEngineCompat(eng, siteKind);
                        const status = engineStatus[eng.id];
                        const installed = status && status.installed;
                        const isSelected = engine === eng.id;
                        return (
                          <Tooltip
                            key={eng.id}
                            title={!compat.ok ? compat.reason : (installed ? `${eng.label} ${status.version || ""} — Installed` : `${eng.label} — Not installed (will be auto-installed)`)}
                          >
                            <span>
                              <Chip
                                label={
                                  <Stack direction="row" spacing={0.5} alignItems="center">
                                    <span>{eng.label}</span>
                                    {installed && <span style={{ fontSize: 9, opacity: 0.7 }}>&#10003;</span>}
                                    {!installed && compat.ok && <span style={{ fontSize: 9, opacity: 0.5 }}>+</span>}
                                  </Stack>
                                }
                                size="small"
                                variant={isSelected ? "filled" : "outlined"}
                                disabled={!compat.ok}
                                onClick={() => { if (compat.ok) setEngine(eng.id); }}
                                sx={{
                                  cursor: compat.ok ? "pointer" : "not-allowed", fontWeight: 600,
                                  ...(isSelected ? { bgcolor: eng.color, color: "#fff", borderColor: eng.color } : { borderColor: compat.ok ? eng.color : "#e2e8f0", color: compat.ok ? eng.color : "#94a3b8" }),
                                }}
                              />
                            </span>
                          </Tooltip>
                        );
                      })}
                    </Stack>

                    {/* Selected engine info */}
                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, borderColor: selectedEngineObj.color + "44" }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                        <Chip
                          label={selectedEngineObj.icon}
                          size="small"
                          sx={{ bgcolor: selectedEngineObj.color, color: "#fff", fontWeight: 800, minWidth: 32, justifyContent: "center" }}
                        />
                        <Typography variant="subtitle2" fontWeight={800} sx={{ color: selectedEngineObj.color }}>
                          {selectedEngineObj.label}
                          {engine === "auto" && <Typography component="span" variant="caption" color="text.secondary"> (auto-selected)</Typography>}
                        </Typography>
                        {engineStatus[resolvedEngine]?.installed ? (
                          <Chip label={`Installed ${engineStatus[resolvedEngine].version || ""}`.trim()} size="small" color="success" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
                        ) : (
                          <Chip label="Not installed" size="small" color="warning" variant="outlined" sx={{ fontSize: 10, height: 20 }} />
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary">{selectedEngineObj.description}</Typography>
                      {!selectedCompat.ok && (
                        <Alert severity="error" sx={{ mt: 1, py: 0.25, fontSize: 12 }}>
                          {selectedCompat.reason}
                        </Alert>
                      )}
                      {!engineStatus[resolvedEngine]?.installed && selectedCompat.ok && selectedEngineObj.installable && (
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                          <Alert severity="info" sx={{ py: 0.25, fontSize: 12, flexGrow: 1 }}>
                            {selectedEngineObj.label} will be automatically installed during deployment.
                          </Alert>
                          <Button
                            size="small" variant="outlined"
                            disabled={serviceBusy}
                            onClick={() => handleInstallEngine(resolvedEngine)}
                            sx={{ textTransform: "none", flexShrink: 0, borderColor: selectedEngineObj.color, color: selectedEngineObj.color }}
                          >
                            Install Now
                          </Button>
                        </Stack>
                      )}
                    </Paper>
                  </Box>

                  <FormControl size="small" fullWidth required>
                    <InputLabel>Bind IP</InputLabel>
                    <Select label="Bind IP" name="WEBSITE_BIND_IP" value={bindIp} onChange={(e) => setBindIp(e.target.value)}
                      disabled={selectableIps.length === 0}>
                      {selectableIps.map((ip) => <MenuItem key={ip} value={ip}>{ip}</MenuItem>)}
                    </Select>
                  </FormControl>
                  <TextField
                    label="Domain Name (optional)" size="small" fullWidth
                    name="WEBSITE_DOMAIN" value={domainName}
                    onChange={(e) => setDomainName(e.target.value)}
                    placeholder="e.g. mysite.example.com"
                  />
                  {/* Ports row */}
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                    <TextField
                      label="HTTP Port" size="small" fullWidth
                      name="WEBSITE_PORT" value={port} placeholder="8088"
                      onChange={(e) => { setPort(e.target.value); setPortResults(null); }}
                      error={!hasAnyPort}
                    />
                    <TextField
                      label="HTTPS Port" size="small" fullWidth
                      name="WEBSITE_HTTPS_PORT" value={httpsPort} placeholder="8443"
                      onChange={(e) => { setHttpsPort(e.target.value); setPortResults(null); }}
                      error={!hasAnyPort}
                    />
                  </Stack>
                  {!hasAnyPort && (
                    <Alert severity="warning" sx={{ py: 0.25, fontSize: 12 }}>
                      At least one port (HTTP or HTTPS) is required.
                    </Alert>
                  )}

                  {/* SSL cert dropdown */}
                  {httpsPort.trim() && (
                    <FormControl size="small" fullWidth>
                      <InputLabel>SSL Certificate</InputLabel>
                      <Select
                        label="SSL Certificate"
                        name="WEBSITE_SSL_CERT"
                        value={selectedCert}
                        onChange={(e) => setSelectedCert(e.target.value)}
                      >
                        <MenuItem value="self_signed">Self-Signed (auto-generated)</MenuItem>
                        {certList.map((cert) => (
                          <MenuItem key={cert.name} value={cert.name}>
                            {cert.name}{cert.domain ? ` — ${cert.domain}` : ""}{cert.self_signed ? " (self-signed)" : ""}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  )}

                  {/* Port check */}
                  <Box>
                    <Button
                      size="small" variant="outlined"
                      disabled={portChecking || (!port.trim() && !httpsPort.trim())}
                      onClick={checkPorts}
                      sx={{ textTransform: "none", mb: portResults ? 1 : 0 }}
                    >
                      {portChecking ? "Checking ports..." : "Check Port Conflicts"}
                    </Button>
                    {portResults && Object.entries(portResults).map(([p, r]) => (
                      <Alert
                        key={p}
                        severity={r.in_use ? "error" : "success"}
                        sx={{ mb: 0.5, py: 0.25, fontSize: 12 }}
                      >
                        {r.label} {p}: {r.in_use
                          ? `IN USE — ${r.used_by || "another process"} (PID ${r.pid || "?"})`
                          : "available"}
                      </Alert>
                    ))}
                  </Box>

                  {/* Published Folder + Upload */}
                  <Stack spacing={1}>
                    <TextField
                      label="Published Folder or Path" size="small" fullWidth
                      name="WEBSITE_SOURCE" value={source}
                      placeholder={defaultWebsiteDirForOs(cfg.os)}
                      onChange={(e) => { setSource(e.target.value); setSelectedFiles([]); setUploadStatus(null); }}
                      helperText="Point to your built/published folder. The dashboard auto-detects the project type."
                    />
                    <input
                      ref={folderInputRef}
                      type="file"
                      style={{ display: "none" }}
                      webkitdirectory=""
                      multiple
                      onChange={handleFilesSelected}
                    />
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                      <Button
                        size="small" variant="outlined"
                        onClick={() => folderInputRef.current && folderInputRef.current.click()}
                        sx={{ textTransform: "none", flexShrink: 0 }}
                      >
                        Select Folder
                      </Button>
                      <Button
                        size="small" variant="contained"
                        disabled={uploadBusy || selectedFiles.length === 0}
                        onClick={handleFolderUpload}
                        sx={{ textTransform: "none", flexShrink: 0 }}
                      >
                        {uploadBusy ? "Uploading..." : `Upload${selectedFiles.length ? ` (${selectedFiles.length} files)` : ""}`}
                      </Button>
                      {selectedFiles.length > 0 && (
                        <Typography variant="caption" color="text.secondary">
                          {selectedFiles[0]?.webkitRelativePath?.split("/")[0] || "folder"} — {selectedFiles.length} file(s) ready
                        </Typography>
                      )}
                    </Stack>
                    {uploadStatus && (
                      <Alert
                        severity={uploadStatus.ok ? "success" : "error"}
                        sx={{ py: 0.5 }}
                        onClose={() => setUploadStatus(null)}
                      >
                        {uploadStatus.text}
                      </Alert>
                    )}
                  </Stack>

                  {/* Deploy button */}
                  <Button
                    variant="contained"
                    size="large"
                    disabled={serviceBusy || !bindIp || !hasAnyPort || !selectedCompat.ok}
                    onClick={handleDeploy}
                    sx={{
                      textTransform: "none", fontWeight: 800, borderRadius: 2, py: 1.2,
                      bgcolor: selectedEngineObj.color,
                      "&:hover": { bgcolor: selectedEngineObj.color, filter: "brightness(0.9)" },
                      "&:disabled": { bgcolor: "#e2e8f0" },
                    }}
                  >
                    Deploy to {selectedEngineObj.label}
                  </Button>
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Info card ── */}
        <Grid item xs={12} md={4}>
          <Stack spacing={2}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Auto-Detection</Typography>
                <Typography variant="body2">
                  The dashboard scans your source folder and auto-detects the project type:
                </Typography>
                <Box component="ul" sx={{ pl: 2, mt: 1, mb: 0 }}>
                  {[
                    ["Next.js", "package.json + .next"],
                    ["Flutter web", "build/web/index.html"],
                    ["PHP", ".php files"],
                    ["Static / exported", "index.html"],
                  ].map(([label, hint]) => (
                    <Box key={label} component="li" sx={{ mb: 0.5 }}>
                      <Typography variant="body2"><b>{label}</b> — {hint}</Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>Engine Status</Typography>
                {engineChecking ? (
                  <Typography variant="body2" color="text.secondary">Checking engines...</Typography>
                ) : (
                  <Stack spacing={0.5}>
                    {osEngines.map((eng) => {
                      const status = engineStatus[eng.id];
                      const installed = status && status.installed;
                      return (
                        <Stack key={eng.id} direction="row" alignItems="center" spacing={1}>
                          <Chip
                            label={eng.icon}
                            size="small"
                            sx={{ bgcolor: installed ? eng.color : "#e2e8f0", color: installed ? "#fff" : "#94a3b8", fontWeight: 800, minWidth: 28, justifyContent: "center", fontSize: 10 }}
                          />
                          <Typography variant="body2" sx={{ flexGrow: 1 }}>
                            {eng.label}
                          </Typography>
                          {installed ? (
                            <Chip label={status.version || "OK"} size="small" color="success" variant="outlined" sx={{ fontSize: 10, height: 18 }} />
                          ) : (
                            <Chip label="Not installed" size="small" variant="outlined" sx={{ fontSize: 10, height: 18, color: "#94a3b8" }} />
                          )}
                        </Stack>
                      );
                    })}
                  </Stack>
                )}
                <Box sx={{ mt: 1.5, pt: 1.5, borderTop: "1px solid #e8edf6" }}>
                  <Typography variant="body2">Managed sites: {Number(websiteInfo?.count || websiteServices.length || 0)}</Typography>
                </Box>
              </CardContent>
            </Card>
          </Stack>
        </Grid>

        {/* ── Service list ── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Websites</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                  variant="outlined"
                  disabled={!!websiteLoading}
                  onClick={() => Promise.all([loadWebsiteInfo.current(), loadWebsiteServices.current()])}
                  sx={{ textTransform: "none" }}
                >
                  Refresh
                </Button>
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {websiteServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No managed websites found yet.</Typography>
                )}
                {scopeErrors.website && <Alert severity="error" sx={{ mb: 1 }}>{scopeErrors.website}</Alert>}
                {websiteServices.map((svc) => {
                  const running = isServiceRunningStatus(svc.status, svc.sub_status);
                  const kindLabel = svc.kind || "service";
                  return (
                    <Paper key={`website-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                            <Typography variant="body2"><b>{svc.form_name || svc.name}</b></Typography>
                            <Chip label={kindLabel} size="small" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
                          </Stack>
                          {svc.image && (
                            <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>
                          )}
                          {typeof renderServiceUrls === "function" && renderServiceUrls(svc)}
                          {typeof renderServicePorts === "function" && renderServicePorts(svc)}
                        </Box>
                        {typeof renderServiceStatus === "function" && renderServiceStatus(svc)}
                        <Box sx={{ flexGrow: 1 }} />
                        {typeof renderFolderIcon === "function" && renderFolderIcon(svc)}
                        {typeof renderEditServiceIcon === "function" && renderEditServiceIcon(svc)}
                        {!!(svc.urls && svc.urls[0]) && (
                          <Button
                            size="small" variant="contained" disabled={serviceBusy}
                            onClick={() => window.open(svc.urls[0], "_blank", "noopener,noreferrer")}
                            sx={{ textTransform: "none" }}
                          >
                            Open
                          </Button>
                        )}
                        <Button
                          size="small" variant="outlined" disabled={serviceBusy}
                          onClick={() => openWebsiteRun(svc)}
                          sx={{ textTransform: "none" }}
                        >
                          Update Files
                        </Button>
                        <Button
                          size="small" variant="outlined"
                          color={running ? "error" : "success"}
                          disabled={!!serviceBusy}
                          onClick={() => onServiceAction(running ? "stop" : "start", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          {running ? "Stop" : "Start"}
                        </Button>
                        <Button
                          size="small" variant="outlined"
                          disabled={!!serviceBusy}
                          onClick={() => onServiceAction("restart", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          Restart
                        </Button>
                        <Button
                          size="small" variant="outlined" color="error"
                          disabled={!!serviceBusy}
                          onClick={() => onServiceAction("delete", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          Delete
                        </Button>
                      </Stack>
                    </Paper>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  }

  ns.pages.website = function renderWebsitePage(p) {
    return React.createElement(WebsiteInner, p);
  };
})();
