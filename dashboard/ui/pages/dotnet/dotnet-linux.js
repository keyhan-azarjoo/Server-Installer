(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-linux"] = function renderDotnetLinuxPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard, Divider,
      cfg, run, serviceBusy,
      dotnetServices,
      isScopeLoading, loadDotnetServices,
      hasStoppedServices, batchServiceAction,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      setPage, setFileManagerPath,
    } = p;

    if (cfg.os !== "linux") return null;

    const linuxServices = (dotnetServices || []).filter((s) => String(s.kind || "").toLowerCase() !== "docker");

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            title="Deploy Linux"
            description="Deploy application on Linux. .NET and prerequisites are installed automatically. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/linux"
            fields={[
              { name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" },
              { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true },
              { name: "DOMAIN_NAME", label: "Domain Name" },
              { name: "SERVICE_NAME", label: "Service Name", defaultValue: "dotnet-app" },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
            ]}
            onRun={run}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Linux Deploy Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><b>.NET Channel</b> — runtime version to install, e.g. <code>8.0</code> or <code>9.0</code>. .NET and nginx are installed automatically if not present.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>Source Path or URL</b> — local folder, a <code>.zip</code>/<code>.tar.gz</code> archive, or a GitHub repo URL.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>Domain Name</b> — public domain for the site (e.g. <code>app.example.com</code>). Leave empty to use the server IP. If a domain is set, a port already in use by another service will be shared as a new nginx virtual host.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>Service Name</b> — the systemd service name. Redeploying the same name replaces the app files and restarts the service.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>HTTP Port</b> — serve plain HTTP on this port. Leave empty to disable HTTP.</Typography>
              <Typography variant="body2"><b>HTTPS Port</b> — serve HTTPS (TLS) on this port. Leave empty to disable HTTPS.</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Linux .NET Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("dotnet")} onClick={() => loadDotnetServices.current()} sx={{ textTransform: "none" }}>Refresh</Button>
                {linuxServices.length > 0 && (
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(linuxServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(linuxServices, "DotNet", hasStoppedServices(linuxServices) ? "start" : "stop")}
                    sx={{ textTransform: "none" }}
                  >
                    {hasStoppedServices(linuxServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {linuxServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No Linux .NET services found. Deploy an app above to see services here.</Typography>
                )}
                {linuxServices.map((svc) => (
                  <Paper key={`linux-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "service"})</Typography></Typography>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon(svc)}
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
                      <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
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
