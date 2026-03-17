(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.sysinfo = function renderSysinfoPage(p) {
    const {
      Grid, Card, CardContent, Typography,
      systemInfo, dotnet, docker, iis, mongo, pythonService, proxy,
      apiAddressList, formatBytes, formatUptime,
    } = p;
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
      </Grid>
    );
  };
})();
