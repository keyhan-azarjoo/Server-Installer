(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function WebsiteInner(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      TextField, MenuItem, Select, FormControl, InputLabel,
      ActionCard,
      cfg, run, selectableIps, serviceBusy,
      websiteEditor, websiteEditorSeed, websiteInfo, websiteServices,
      iis, docker,
      isScopeLoading, loadWebsiteInfo, loadWebsiteServices,
      onServiceAction, openWebsiteRun,
      isServiceRunningStatus, formatServiceState, renderServiceStatus,
      renderServiceUrls, renderServicePorts, renderFolderIcon,
      scopeErrors,
      defaultWebsiteDirForOs,
      setPage, setFileManagerPath,
    } = p;

    const websiteHost = selectableIps.includes(String(websiteEditor?.host || "").trim())
      ? String(websiteEditor?.host || "").trim()
      : (selectableIps.length === 1 ? selectableIps[0] : "");

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
    const [uploadBusy,   setUploadBusy]   = React.useState(false);
    const [uploadStatus, setUploadStatus] = React.useState(null); // {ok, text}

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
      if (!bindIp && selectableIps.length === 1) setBindIp(selectableIps[0]);
    }, [selectableIps]);

    const kindOptions = ["auto", "static", "next-export", "nextjs", "flutter", "php"];

    const handleDeploy = React.useCallback((e, target) => {
      if (hiddenTargetRef.current) hiddenTargetRef.current.value = target;
      run(e, "/run/website_deploy", `Deploy Website → ${target}`, formRef.current);
    }, [run]);

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

    // ── Folder / files upload to source path ─────────────────────────────
    const handleFolderUpload = React.useCallback(async (event) => {
      const files = Array.from(event.target.files || []);
      // reset input so same selection re-triggers onChange
      event.target.value = "";
      if (!files.length) return;
      const targetDir = source.trim();
      if (!targetDir) {
        setUploadStatus({ ok: false, text: "Set a Published Folder path first." });
        return;
      }
      setUploadBusy(true);
      setUploadStatus(null);
      try {
        const fd = new FormData();
        fd.append("target", targetDir);
        files.forEach((f) => fd.append("files", f, f.webkitRelativePath || f.name));
        const r = await fetch("/api/files/upload", {
          method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd,
        });
        const j = await r.json();
        setUploadStatus({
          ok: j.ok,
          text: j.ok
            ? `Uploaded ${j.written ?? files.length} file(s) to ${targetDir}.`
            : (j.error || "Upload failed."),
        });
      } catch (ex) {
        setUploadStatus({ ok: false, text: String(ex) });
      } finally {
        setUploadBusy(false);
      }
    }, [source]);

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
        desc: "Run in a Docker container. Supports all website types including Next.js, PHP, and Flutter.",
        available: docker.installed,
        unavailableReason: "Docker is not installed on this host.",
      },
    ];

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
                      label="HTTP Port" size="small" fullWidth required
                      name="WEBSITE_PORT" value={port} placeholder="8088"
                      onChange={(e) => { setPort(e.target.value); setPortResults(null); }}
                    />
                    <TextField
                      label="HTTPS Port (optional)" size="small" fullWidth
                      name="WEBSITE_HTTPS_PORT" value={httpsPort} placeholder="8443"
                      onChange={(e) => { setHttpsPort(e.target.value); setPortResults(null); }}
                    />
                  </Stack>

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

                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="flex-start">
                    <TextField
                      label="Published Folder or Path" size="small" fullWidth
                      name="WEBSITE_SOURCE" value={source}
                      placeholder={defaultWebsiteDirForOs(cfg.os)}
                      onChange={(e) => setSource(e.target.value)}
                      helperText="Point to your built/published folder. The dashboard auto-detects the project type."
                    />
                    <Button
                      size="small" variant="outlined"
                      onClick={openSourceInFileManager}
                      disabled={!source.trim()}
                      sx={{ textTransform: "none", flexShrink: 0, mt: 0.5 }}
                    >
                      Open Folder
                    </Button>
                  </Stack>
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Grid>

        {/* ── Info + Upload card ── */}
        <Grid item xs={12} md={4}>
          <Stack spacing={2} sx={{ height: "100%" }}>
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
                <Typography variant="body2" sx={{ mt: 1.5 }}>
                  Managed sites: {Number(websiteInfo?.count || websiteServices.length || 0)}
                </Typography>
                <Typography variant="body2">IIS: {iis.installed ? "Installed" : "Not installed"}</Typography>
                <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "available"})` : "Not installed"}</Typography>
              </CardContent>
            </Card>

            {/* ── Upload files to source folder ── */}
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 0.5 }}>Upload to Source Folder</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Upload your built files directly to the Published Folder on the server. Select a folder or individual files from your local machine.
                </Typography>
                {uploadStatus && (
                  <Alert
                    severity={uploadStatus.ok ? "success" : "error"}
                    sx={{ mb: 1.5, py: 0.5 }}
                    onClose={() => setUploadStatus(null)}
                  >
                    {uploadStatus.text}
                  </Alert>
                )}
                {!source.trim() && (
                  <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
                    Set a Published Folder path above before uploading.
                  </Alert>
                )}
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button
                    component="label"
                    variant="contained"
                    size="small"
                    disabled={uploadBusy || !source.trim()}
                    sx={{ textTransform: "none", fontWeight: 700 }}
                  >
                    {uploadBusy ? "Uploading…" : "Upload Folder"}
                    <input
                      hidden type="file"
                      webkitdirectory=""
                      multiple
                      onChange={handleFolderUpload}
                    />
                  </Button>
                  <Button
                    component="label"
                    variant="outlined"
                    size="small"
                    disabled={uploadBusy || !source.trim()}
                    sx={{ textTransform: "none" }}
                  >
                    Upload Files
                    <input
                      hidden type="file"
                      multiple
                      onChange={handleFolderUpload}
                    />
                  </Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                  Target: {source.trim() || "(not set)"}
                </Typography>
              </CardContent>
            </Card>
          </Stack>
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
                  disabled={serviceBusy || !available || !bindIp}
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

        {/* ── Service list ── */}
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Websites</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("website")} onClick={() => Promise.all([loadWebsiteInfo.current(), loadWebsiteServices.current()])} sx={{ textTransform: "none" }}>
                  Refresh
                </Button>
              </Stack>
              {scopeErrors.website && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.website}</Alert>}
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {websiteServices.length === 0 && <Typography variant="body2">No managed websites found yet.</Typography>}
                {websiteServices.map((svc) => (
                  <Paper key={`website-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 280 }}>
                        <Typography variant="body2"><b>{svc.form_name || svc.name}</b> ({svc.stack_label || "website"})</Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                          Target: {svc.target_value || svc.kind || "-"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                          Source: {svc.project_path || "-"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                          Publish Folder: {svc.publish_rel || "."}
                        </Typography>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {!!(svc.urls && svc.urls[0]) && (
                        <Button size="small" variant="contained" disabled={serviceBusy} onClick={() => window.open(svc.urls[0], "_blank", "noopener,noreferrer")} sx={{ textTransform: "none" }}>
                          Open
                        </Button>
                      )}
                      {renderFolderIcon(svc)}
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => openWebsiteRun(svc)} sx={{ textTransform: "none" }}>
                        Update Files
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"}
                        disabled={serviceBusy}
                        onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)}
                        sx={{ textTransform: "none" }}
                      >
                        {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                      </Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>
                        Restart
                      </Button>
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>
                        Delete
                      </Button>
                    </Stack>
                  </Paper>
                ))}
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
