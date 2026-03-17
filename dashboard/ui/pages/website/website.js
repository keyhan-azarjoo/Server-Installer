(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.website = function renderWebsitePage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard,
      cfg, run, selectableIps, serviceBusy,
      websiteEditor, websiteEditorSeed, websiteInfo, websiteServices,
      iis, docker,
      isScopeLoading, loadWebsiteInfo, loadWebsiteServices,
      onServiceAction, openWebsiteRun,
      isServiceRunningStatus, formatServiceState,
      renderServiceUrls, renderServicePorts,
      scopeErrors,
      defaultWebsiteDirForOs,
    } = p;

    const websiteHost = selectableIps.includes(String(websiteEditor?.host || "").trim()) ? String(websiteEditor?.host || "").trim() : (selectableIps.length === 1 ? selectableIps[0] : "");
    const websiteTargetOptions = [];
    websiteTargetOptions.push("auto");
    websiteTargetOptions.push("service");
    if (cfg.os === "windows") websiteTargetOptions.push("iis");
    websiteTargetOptions.push("docker");
    const selectedTarget = websiteTargetOptions.includes(String(websiteEditor?.target || "").trim()) ? String(websiteEditor?.target || "").trim() : websiteTargetOptions[0];
    const websiteTargetLabel = selectedTarget === "auto"
      ? "Auto"
      : selectedTarget === "iis"
      ? "IIS"
      : (selectedTarget === "docker" ? "Docker" : (cfg.os === "windows" ? "OS Service (Windows)" : "OS Service"));
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            key={`website-${websiteEditorSeed}`}
            title={`Deploy Website to ${websiteTargetLabel}`}
            description="Upload or point to a website project. The dashboard inspects the files and chooses the correct runtime stack automatically."
            action="/run/website_deploy"
            fields={[
              { name: "WEBSITE_SITE_NAME", label: "Website Name", defaultValue: websiteEditor?.name || "ServerInstallerWebsite", required: true },
              {
                name: "WEBSITE_TARGET",
                label: "Run On",
                type: "select",
                options: websiteTargetOptions,
                defaultValue: selectedTarget,
                required: true,
              },
              {
                name: "WEBSITE_KIND",
                label: "Website Type",
                type: "select",
                options: ["auto", "static", "next-export", "nextjs", "flutter", "php"],
                defaultValue: websiteEditor?.kind || "auto",
                required: true,
              },
              {
                name: "WEBSITE_BIND_IP",
                label: "Bind IP",
                type: "select",
                options: selectableIps,
                defaultValue: websiteHost,
                required: true,
                disabled: selectableIps.length === 0,
                placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
              },
              { name: "WEBSITE_PORT", label: "HTTP Port", defaultValue: websiteEditor?.port || "8088", required: true, placeholder: "8088" },
              { name: "WEBSITE_SOURCE", label: "Published Folder or Path", defaultValue: websiteEditor?.source || defaultWebsiteDirForOs(cfg.os), placeholder: defaultWebsiteDirForOs(cfg.os), enableUpload: true },
            ]}
            onRun={run}
            color="#0f766e"
          />
          {cfg.os !== "windows" && (
            <Alert severity="info" sx={{ mt: 1.5 }}>
              IIS is only available on Windows. On this host you can deploy websites as an OS-managed service or Docker container.
            </Alert>
          )}
          {!docker.installed && (
            <Alert severity="info" sx={{ mt: 1.5 }}>
              Docker target requires Docker to be installed and running on the host.
            </Alert>
          )}
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Supported Builds</Typography>
              <Typography variant="body2">The dashboard inspects uploaded files and auto-detects static/exported sites, Flutter web, Next.js apps, and PHP apps.</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>Static/exported builds can run on IIS, Docker, or OS service. Next.js and PHP are routed to Docker or OS service because they need an application runtime.</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>Managed websites: {Number(websiteInfo?.count || websiteServices.length || 0)}</Typography>
              <Typography variant="body2">IIS: {iis.installed ? "Installed" : "Not installed"}</Typography>
              <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "available"})` : "Not installed"}</Typography>
              <Typography variant="body2">OS Target: {cfg.os === "windows" ? "Windows service" : (cfg.os === "darwin" ? "launchd" : "systemd")}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Websites</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("website")} onClick={() => Promise.all([loadWebsiteInfo.current(), loadWebsiteServices.current()])} sx={{ textTransform: "none" }}>
                  Refresh
                </Button>
              </Stack>
              {scopeErrors.website && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.website}</Alert>}
              <Box sx={{ mt: 1.2, maxHeight: 360, overflow: "auto" }}>
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
                      <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                      <Box sx={{ flexGrow: 1 }} />
                      {!!(svc.urls && svc.urls[0]) && (
                        <Button size="small" variant="contained" disabled={serviceBusy} onClick={() => window.open(svc.urls[0], "_blank", "noopener,noreferrer")} sx={{ textTransform: "none" }}>
                          Open
                        </Button>
                      )}
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
  };
})();
