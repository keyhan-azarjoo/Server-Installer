(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function DotnetIisInner(p) {
    const {
      Grid, Card, CardContent, Typography, Divider, ActionCard, Alert,
      Stack, Button, Box, Paper, Chip,
      cfg, run, serviceBusy,
      isServiceRunningStatus, onServiceAction,
      hasStoppedServices, batchServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon, renderEditServiceIcon,
    } = p;

    const [iisServices, setIisServices] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState("");

    const loadIisServices = React.useCallback(async () => {
      setLoading(true);
      setError("");
      try {
        const r = await fetch("/api/system/services?scope=dotnet", { headers: { "X-Requested-With": "fetch" } });
        const j = await r.json();
        if (j.ok && Array.isArray(j.services)) {
          const sites = j.services.filter((s) => String(s.kind || "").toLowerCase() === "iis_site");
          setIisServices(sites);
        } else {
          setError(j.error || "Failed to load services.");
        }
      } catch (ex) {
        setError("Could not reach the services API: " + String(ex));
      }
      setLoading(false);
    }, []);

    React.useEffect(() => { loadIisServices(); }, [loadIisServices]);

    if (cfg.os !== "windows") return null;

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <ActionCard title="Install IIS" description="Install IIS features and .NET prerequisites." action="/run/windows_setup_iis" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
        </Grid>
        <Grid item xs={12} md={4}>
          <ActionCard
            title="Deploy IIS"
            description="Deploy application to IIS. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/windows_iis"
            fields={[
              { name: "SiteName", label: "Site Name", defaultValue: "DotNetApp", required: true, placeholder: "DotNetApp" },
              { name: "DomainName", label: "Domain Name", placeholder: "e.g. myapp.example.com (optional)" },
              { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
              { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
            ]}
            onRun={run}
            color="#1e40af"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>IIS Deploy Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>Run <b>Install IIS</b> first to enable IIS features and the ASP.NET Core Module.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>Source Path or URL</b> — a published .NET folder, a <code>.zip</code> archive, or a GitHub URL.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>.NET Channel</b> — runtime version, e.g. <code>8.0</code> or <code>9.0</code>.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>HTTP Port</b> — leave empty to disable HTTP.</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><b>HTTPS Port</b> — leave empty to disable HTTPS.</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>IIS Sites</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={loading} onClick={loadIisServices} sx={{ textTransform: "none" }}>
                  {loading ? "Refreshing..." : "Refresh"}
                </Button>
                {iisServices.length > 0 && (
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(iisServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(iisServices, "IIS", hasStoppedServices(iisServices) ? "start" : "stop")}
                    sx={{ textTransform: "none" }}
                  >
                    {hasStoppedServices(iisServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              {error && <Alert severity="warning" sx={{ mt: 1, borderRadius: 2 }}>{error}</Alert>}
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {loading && iisServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">Loading IIS sites...</Typography>
                )}
                {!loading && iisServices.length === 0 && !error && (
                  <Typography variant="body2" color="text.secondary">No IIS sites deployed yet. Use "Deploy IIS" above to add one.</Typography>
                )}
                {iisServices.map((svc) => (
                  <Paper key={`iis-${svc.name}`} variant="outlined" sx={{ p: 1.5, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                          <Typography variant="body2" fontWeight={700}>{svc.name}</Typography>
                          <Chip label="IIS" size="small" color="primary" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
                        </Stack>
                        {svc.display_name && svc.display_name !== svc.name && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: "block", wordBreak: "break-all" }}>{svc.display_name}</Typography>
                        )}
                        {renderServiceUrls && renderServiceUrls(svc)}
                        {renderServicePorts && renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus && renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon && renderFolderIcon(svc)}
                      {renderEditServiceIcon && renderEditServiceIcon(svc)}
                      <Button
                        size="small" variant="outlined"
                        color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"}
                        disabled={serviceBusy}
                        onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)}
                        sx={{ textTransform: "none" }}
                      >
                        {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                      </Button>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
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
  }

  ns.pages["dotnet-iis"] = function renderDotnetIisPage(p) {
    return React.createElement(DotnetIisInner, p);
  };
})();
