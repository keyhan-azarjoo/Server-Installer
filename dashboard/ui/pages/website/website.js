(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function WebsiteInner(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box,
      TextField, MenuItem, Select, FormControl, InputLabel,
      Paper, Chip, isServiceRunningStatus, formatServiceState,
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
    const [port,       setPort]       = React.useState(websiteEditor?.port || "8088");
    const [httpsPort,  setHttpsPort]  = React.useState(websiteEditor?.https_port || "");
    const [source,     setSource]     = React.useState(websiteEditor?.source || defaultWebsiteDirForOs(cfg.os));
    const formRef      = React.useRef(null);
    const hiddenTargetRef = React.useRef(null);

    // ── Port-check state ──────────────────────────────────────────────────
    const [portResults,   setPortResults]   = React.useState(null); // map port→{ok,used_by,...}
    const [portChecking,  setPortChecking]  = React.useState(false);

    // ── Folder-upload state ───────────────────────────────────────────────
    const [uploadBusy,    setUploadBusy]    = React.useState(false);
    const [uploadStatus,  setUploadStatus]  = React.useState(null); // {ok, text}
    const [selectedFiles, setSelectedFiles] = React.useState([]); // files staged for upload
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

    // Keep bindIp in sync if selectableIps loads
    React.useEffect(() => {
      if (!bindIp) { const d = getDefaultSelectableIp(selectableIps); if (d) setBindIp(d); }
    }, [selectableIps]);

    const kindOptions = ["auto", "static", "next-export", "nextjs", "flutter", "php"];

    const hasAnyPort = !!(port.trim() || httpsPort.trim());

    const handleDeploy = React.useCallback((e, target) => {
      if (!port.trim() && !httpsPort.trim()) {
        e.preventDefault();
        setPortResults({ _error: { label: "Ports", ok: false, error: "At least one port (HTTP or HTTPS) is required." } });
        return;
      }
      if (hiddenTargetRef.current) hiddenTargetRef.current.value = target;
      if (!source.trim()) {
        const def = defaultWebsiteDirForOs(cfg.os);
        setSource(def);
      }
      run(e, "/run/website_deploy", `Deploy Website → ${target}`, formRef.current);
    }, [run, source, cfg.os, port, httpsPort]);

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

    // ── Stage selected files (don't upload yet) ───────────────────────────
    const handleFilesSelected = React.useCallback((event) => {
      const files = Array.from(event.target.files || []);
      event.target.value = ""; // allow re-selecting same folder
      setSelectedFiles(files);
      setUploadStatus(null);
    }, []);

    // ── Upload staged files to server (using web terminal like other pages) ─
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
          // Update source path to include the uploaded subfolder name
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

    // ── Open source folder in file manager ────────────────────────────────
    const openSourceInFileManager = React.useCallback(() => {
      const dir = source.trim();
      if (!dir || !setFileManagerPath || !setPage) return;
      setFileManagerPath(dir);
      setPage("files");
    }, [source, setFileManagerPath, setPage]);

    // Target cards config
    const targets = [
      ...(cfg.os === "windows" && iis.installed ? [{
        target: "iis",
        label: "IIS",
        color: "#1d4ed8",
        desc: "Host as an IIS site. Best for static, exported Next.js, and Flutter web builds on Windows.",
        available: true,
      }] : []),
      {
        target: "service",
        label: cfg.os === "windows" ? "Windows Service" : (cfg.os === "darwin" ? "launchd" : "systemd Service"),
        color: "#0f766e",
        desc: cfg.os === "windows"
          ? "Run as a managed Windows service. Supports all website types."
          : "Run as a managed OS service via systemd/launchd. Supports all website types.",
        available: true,
      },
      {
        target: "docker",
        label: "Docker",
        color: "#1f2937",
        desc: docker.installed
          ? "Run in a Docker container. Supports all website types including Next.js, PHP, and Flutter."
          : "Docker will be installed automatically, then your site will be deployed as a container.",
        available: true,
      },
    ];

    const websiteLoading = isScopeLoading("website");

    return (
      <Grid container spacing={2}>
        {/* ── Configuration form ── */}
        <Grid item xs={12} md={8}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 2 }}>Website Configuration</Typography>
              <form ref={formRef}>
                {/* Hidden target field — overwritten per deploy button click */}
                <input ref={hiddenTargetRef} type="hidden" name="WEBSITE_TARGET" value="service" />
                <Stack spacing={2}>
                  <TextField
                    label="Website Name" size="small" fullWidth required
                    name="WEBSITE_SITE_NAME" value={siteName}
                    onChange={(e) => setSiteName(e.target.value)}
                  />
                  <FormControl size="small" fullWidth>
                    <InputLabel>Website Type</InputLabel>
                    <Select label="Website Type" name="WEBSITE_KIND" value={siteKind} onChange={(e) => setSiteKind(e.target.value)}>
                      {kindOptions.map((k) => <MenuItem key={k} value={k}>{k}</MenuItem>)}
                    </Select>
                  </FormControl>
                  <FormControl size="small" fullWidth required>
                    <InputLabel>Bind IP</InputLabel>
                    <Select label="Bind IP" name="WEBSITE_BIND_IP" value={bindIp} onChange={(e) => setBindIp(e.target.value)}
                      disabled={selectableIps.length === 0}>
                      {selectableIps.map((ip) => <MenuItem key={ip} value={ip}>{ip}</MenuItem>)}
                    </Select>
                  </FormControl>
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

                  {/* SSL cert dropdown — shown when HTTPS port is set */}
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

                  {/* Port check button + results */}
                  <Box>
                    <Button
                      size="small" variant="outlined"
                      disabled={portChecking || (!port.trim() && !httpsPort.trim())}
                      onClick={checkPorts}
                      sx={{ textTransform: "none", mb: portResults ? 1 : 0 }}
                    >
                      {portChecking ? "Checking ports…" : "Check Port Conflicts"}
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

                  {/* Published Folder + Select + Upload */}
                  <Stack spacing={1}>
                    <TextField
                      label="Published Folder or Path" size="small" fullWidth
                      name="WEBSITE_SOURCE" value={source}
                      placeholder={defaultWebsiteDirForOs(cfg.os)}
                      onChange={(e) => { setSource(e.target.value); setSelectedFiles([]); setUploadStatus(null); }}
                      helperText="Point to your built/published folder. The dashboard auto-detects the project type."
                    />
                    {/* hidden folder input */}
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
                        {uploadBusy ? "Uploading…" : `Upload${selectedFiles.length ? ` (${selectedFiles.length} files)` : ""}`}
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
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Info card (description only) ── */}
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
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
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2">Managed sites: {Number(websiteInfo?.count || websiteServices.length || 0)}</Typography>
                <Typography variant="body2">IIS: {iis.installed ? "Installed" : "Not installed"}</Typography>
                <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "available"})` : "Not installed"}</Typography>
              </Box>
              <Box sx={{ mt: 2, pt: 2, borderTop: "1px solid #e8edf6" }}>
                <Typography variant="body2" color="text.secondary">
                  Use <b>Select Folder</b> to pick your built output from your local machine, then <b>Upload</b> to send it to the server path set in Published Folder.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Deploy target buttons ── */}
        {targets.map(({ target, label, color, desc, available, unavailableReason }) => (
          <Grid key={target} item xs={12} md={4}>
            <Card sx={{ borderRadius: 3, border: `1px solid ${available ? color + "44" : "#e2e8f0"}`, height: "100%", opacity: available ? 1 : 0.7 }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5, color: available ? color : "#94a3b8" }}>
                  Deploy → {label}
                </Typography>
                <Typography variant="body2" sx={{ mb: 2, color: "text.secondary", minHeight: 40 }}>{desc}</Typography>
                {!available && unavailableReason && (
                  <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>{unavailableReason}</Alert>
                )}
                <Button
                  variant="contained"
                  disabled={serviceBusy || !available || !bindIp || !hasAnyPort}
                  onClick={(e) => handleDeploy(e, target)}
                  sx={{
                    textTransform: "none", bgcolor: color, fontWeight: 700,
                    "&:hover": { bgcolor: color, filter: "brightness(0.9)" },
                    "&:disabled": { bgcolor: "#e2e8f0" },
                  }}
                >
                  Deploy to {label}
                </Button>
              </CardContent>
            </Card>
          </Grid>
        ))}

        {/* ── Service list (inline) ── */}
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
                        {/* ── Name + Kind ── */}
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

                        {/* ── Status dot ── */}
                        {typeof renderServiceStatus === "function" && renderServiceStatus(svc)}

                        <Box sx={{ flexGrow: 1 }} />

                        {/* ── Folder icon ── */}
                        {typeof renderFolderIcon === "function" && renderFolderIcon(svc)}

                        {/* ── Edit icon ── */}
                        {typeof renderEditServiceIcon === "function" && renderEditServiceIcon(svc)}

                        {/* ── Open URL (website-specific) ── */}
                        {!!(svc.urls && svc.urls[0]) && (
                          <Button
                            size="small" variant="contained" disabled={serviceBusy}
                            onClick={() => window.open(svc.urls[0], "_blank", "noopener,noreferrer")}
                            sx={{ textTransform: "none" }}
                          >
                            Open
                          </Button>
                        )}

                        {/* ── Update Files (website-specific) ── */}
                        <Button
                          size="small" variant="outlined" disabled={serviceBusy}
                          onClick={() => openWebsiteRun(svc)}
                          sx={{ textTransform: "none" }}
                        >
                          Update Files
                        </Button>

                        {/* ── Start / Stop ── */}
                        <Button
                          size="small"
                          variant="outlined"
                          color={running ? "error" : "success"}
                          disabled={!!serviceBusy}
                          onClick={() => onServiceAction(running ? "stop" : "start", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          {running ? "Stop" : "Start"}
                        </Button>

                        {/* ── Restart ── */}
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={!!serviceBusy}
                          onClick={() => onServiceAction("restart", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          Restart
                        </Button>

                        {/* ── Delete ── */}
                        <Button
                          size="small"
                          variant="outlined"
                          color="error"
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
