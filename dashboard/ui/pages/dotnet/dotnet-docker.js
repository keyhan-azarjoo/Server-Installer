(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-docker"] = function renderDotnetDockerPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard,
      cfg, run, serviceBusy,
      dockerServices,
      isScopeLoading, loadDockerInfo, loadDockerServices,
      hasStoppedServices, batchServiceAction,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
    } = p;

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker prerequisites and .NET runtime." action="/run/windows_setup_docker" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy Docker"
              description="Deploy application to Docker. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
              action="/run/windows_docker"
              fields={[
                { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
                { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
                { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP", checkPort: true },
                { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true },
              ]}
              onRun={run}
              color="#334155"
            />
          </Grid>
        </Grid>
      );
    }
    if (cfg.os === "linux") {
      const dotnetDockerServices = (dockerServices || []).filter((s) => {
        const text = String(s.name || "") + " " + String(s.image || "");
        return /(dotnet|aspnet|dotnetapp)/i.test(text) && !/python/i.test(text);
      });
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker Engine on Linux." action="/run/linux_setup_docker" fields={[]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard
              title="Deploy Docker"
              description="Build and run Docker container for your .NET app. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
              action="/run/linux_docker"
              fields={[
                { name: "CONTAINER_NAME", label: "Container Name", defaultValue: "dotnetapp", required: true },
                { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true },
                { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP", checkPort: true },
                { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true },
              ]}
              onRun={run}
              color="#334155"
            />
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>Running .NET Docker Containers</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button
                    variant="outlined"
                    disabled={isScopeLoading("docker")}
                    onClick={() => Promise.all([loadDockerInfo.current(), loadDockerServices.current()])}
                    sx={{ textTransform: "none" }}
                  >
                    Refresh
                  </Button>
                  {dotnetDockerServices.length > 0 && (
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(dotnetDockerServices) ? "success" : "error"}
                      disabled={serviceBusy || dotnetDockerServices.length === 0}
                      onClick={() => batchServiceAction(dotnetDockerServices, "Docker", hasStoppedServices(dotnetDockerServices) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(dotnetDockerServices) ? "Start All" : "Stop All"}
                    </Button>
                  )}
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                  {dotnetDockerServices.length === 0 && (
                    <Typography variant="body2" color="text.secondary">No .NET Docker containers found. Deploy an app above to see containers here.</Typography>
                  )}
                  {dotnetDockerServices.map((svc) => (
                    <Paper key={`dd-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Typography variant="body2"><b>{svc.name}</b> ({svc.kind || "docker"})</Typography>
                          {svc.image && <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>}
                          {renderServiceUrls(svc)}
                          {renderServicePorts(svc)}
                        </Box>
                        <Chip
                          size="small"
                          color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"}
                          label={formatServiceState(svc.status, svc.sub_status) || "-"}
                        />
                        <Box sx={{ flexGrow: 1 }} />
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
    }
    return null;
  };
})();
