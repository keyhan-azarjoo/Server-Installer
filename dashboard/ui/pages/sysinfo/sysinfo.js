(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  function SysinfoInner(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Chip, Select, MenuItem, FormControl, InputLabel,
      systemInfo, dotnet, docker, iis, mongo, pythonService, proxy,
      apiAddressList, formatBytes, formatUptime, run,
    } = p;

    const [dashCert, setDashCert] = React.useState(null);
    const [certMode, setCertMode] = React.useState("self-signed");
    const [certName, setCertName] = React.useState("");

    React.useEffect(() => {
      fetch("/api/dashboard/cert")
        .then((r) => r.json())
        .then((d) => {
          if (d.ok) {
            setDashCert(d);
            setCertMode(d.mode || "self-signed");
            setCertName(d.name || "");
          }
        })
        .catch(() => {});
    }, []);

    function handleApplyCert(e) {
      const form = document.createElement("form");
      const modeField = document.createElement("input");
      modeField.name = "CERT_MODE"; modeField.value = certMode;
      form.appendChild(modeField);
      if (certMode === "managed") {
        const nameField = document.createElement("input");
        nameField.name = "CERT_NAME"; nameField.value = certName;
        form.appendChild(nameField);
      }
      run(e, "/run/dashboard_apply_cert", "Apply Dashboard Certificate", form);
    }

    const managedCerts = (dashCert && dashCert.managed_certs) || [];
    const certInfo = (dashCert && dashCert.cert_info) || {};
    const expiryStr = certInfo.not_after ? new Date(certInfo.not_after * 1000).toLocaleDateString() : null;
    const isExpired = certInfo.not_after && certInfo.not_after * 1000 < Date.now();
    const isExpiringSoon = certInfo.not_after && !isExpired && (certInfo.not_after * 1000 - Date.now()) < 30 * 24 * 3600 * 1000;

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>System</Typography>
              <Typography variant="body2">Host: {systemInfo?.hostname || "-"}</Typography>
              <Typography variant="body2">OS: {systemInfo?.os || "-"} {systemInfo?.os_release || ""}</Typography>
              <Typography variant="body2">Platform: {systemInfo?.platform || "-"}</Typography>
              <Typography variant="body2">Machine: {systemInfo?.machine || "-"}</Typography>
              <Typography variant="body2">Processor: {systemInfo?.processor || "-"}</Typography>
              <Typography variant="body2">CPU Cores: {systemInfo?.cpu_count || "-"}</Typography>
              <Typography variant="body2">Memory: {formatBytes(systemInfo?.memory?.used_bytes)} / {formatBytes(systemInfo?.memory?.total_bytes)} ({systemInfo?.memory?.used_percent ?? "-"}%)</Typography>
              <Typography variant="body2">Uptime: {formatUptime(systemInfo?.uptime_seconds)}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Installed Software</Typography>
              <Typography variant="body2">.NET: {dotnet.installed ? `Installed (${dotnet.version || "unknown"})` : "Not installed"}</Typography>
              {!!(dotnet.sdks && dotnet.sdks.length) && <Typography variant="body2">SDKs: {dotnet.sdks.slice(0, 6).join(" | ")}</Typography>}
              <Typography variant="body2">Docker: {docker.installed ? `Installed (${docker.version || "unknown"})` : "Not installed"}</Typography>
              {!!docker.server_version && <Typography variant="body2">Docker Engine: {docker.server_version}</Typography>}
              <Typography variant="body2">IIS: {iis.installed ? `Installed (${iis.service || "unknown"})` : "Not installed"}</Typography>
              <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not installed"}</Typography>
              {!!mongo.web_version && <Typography variant="body2">Mongo Web UI: {mongo.web_version}</Typography>}
              {!!mongo.https_url && <Typography variant="body2">Mongo HTTPS: {mongo.https_url}</Typography>}
              <Typography variant="body2">Python: {pythonService.installed ? `Installed (${pythonService.python_version || "managed"})` : "Not installed"}</Typography>
              <Typography variant="body2">Jupyter: {pythonService.jupyter_installed ? (pythonService.jupyter_running ? "Running" : "Installed") : "Not installed"}</Typography>
              <Typography variant="body2">Proxy: {proxy.installed ? `Installed (${proxy.layer || proxy.mode || "proxy"})` : "Not installed"}</Typography>
              {!!proxy.panel_url && <Typography variant="body2">Proxy Panel: {proxy.panel_url}</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>API Addresses</Typography>
              {(apiAddressList.length > 0) ? apiAddressList.map((u) => (
                <Typography key={u} variant="body2">{u}</Typography>
              )) : <Typography variant="body2">No API address detected.</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1.5 }}>Dashboard HTTPS Certificate</Typography>
              {dashCert ? (
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Chip
                      size="small"
                      color={isExpired ? "error" : isExpiringSoon ? "warning" : "success"}
                      label={dashCert.mode === "managed" ? `Real CA: ${dashCert.name}` : "Self-Signed"}
                    />
                    {certInfo.subject && <Typography variant="body2" color="text.secondary">Subject: {certInfo.subject}</Typography>}
                    {expiryStr && (
                      <Typography variant="body2" color={isExpired ? "error" : isExpiringSoon ? "warning.main" : "text.secondary"}>
                        Expires: {expiryStr}{isExpired ? " (EXPIRED)" : isExpiringSoon ? " (expiring soon)" : ""}
                      </Typography>
                    )}
                  </Stack>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ xs: "stretch", sm: "center" }}>
                    <FormControl size="small" sx={{ minWidth: 180 }}>
                      <InputLabel>Certificate Type</InputLabel>
                      <Select value={certMode} label="Certificate Type" onChange={(e) => { setCertMode(e.target.value); setCertName(""); }}>
                        <MenuItem value="self-signed">Self-Signed (auto)</MenuItem>
                        <MenuItem value="managed" disabled={managedCerts.length === 0}>Real CA (managed)</MenuItem>
                      </Select>
                    </FormControl>
                    {certMode === "managed" && (
                      <FormControl size="small" sx={{ minWidth: 200 }}>
                        <InputLabel>Select Certificate</InputLabel>
                        <Select value={certName} label="Select Certificate" onChange={(e) => setCertName(e.target.value)}>
                          {managedCerts.map((c) => (
                            <MenuItem key={c.name} value={c.name}>{c.domain || c.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    )}
                    <Button
                      variant="contained"
                      size="small"
                      disabled={certMode === "managed" && !certName}
                      onClick={handleApplyCert}
                      sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }}
                    >
                      Apply &amp; Restart Dashboard
                    </Button>
                  </Stack>
                  {certMode === "self-signed" && (
                    <Typography variant="caption" color="text.secondary">
                      A self-signed certificate is generated automatically. Browsers will show a security warning — you can safely proceed or import the CA into your browser.
                    </Typography>
                  )}
                  {certMode === "managed" && managedCerts.length === 0 && (
                    <Typography variant="caption" color="warning.main">
                      No managed certificates found. Go to SSL &amp; Certificates to import or request a real CA certificate first.
                    </Typography>
                  )}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">Loading certificate info...</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  }

  // Wrap in React.createElement so hooks inside SysinfoInner have their own fiber
  // and work correctly regardless of whether app.js calls pages directly or via createElement.
  ns.pages.sysinfo = function renderSysinfoPage(p) {
    return React.createElement(SysinfoInner, p);
  };
})();
