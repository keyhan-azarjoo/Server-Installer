(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.dotnet = function renderDotnetPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      NavCard,
      cfg, serviceBusy,
      dotnetServices,
      isScopeLoading, loadDotnetInfo, loadDotnetServices,
      hasStoppedServices, batchServiceAction, setPage,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
    } = p;

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="IIS" text="Install and deploy on IIS." onClick={() => setPage("dotnet-iis")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="Docker" text="Install and deploy on Docker." onClick={() => setPage("dotnet-docker")} />
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>DotNet Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button variant="outlined" disabled={isScopeLoading("dotnet")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(dotnetServices) ? "success" : "error"}
                    disabled={serviceBusy || dotnetServices.length === 0}
                    onClick={() => batchServiceAction(dotnetServices, "DotNet", hasStoppedServices(dotnetServices) ? "start" : "stop")}
                    sx={{ textTransform: "none" }}
                  >
                    {hasStoppedServices(dotnetServices) ? "Start All DotNet" : "Stop All DotNet"}
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                  {dotnetServices.length === 0 && <Typography variant="body2">No DotNet-related services found.</Typography>}
                  {dotnetServices.map((svc) => (
                    <Paper key={`dotnet-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                          {renderServiceUrls(svc)}
                          {renderServicePorts(svc)}
                        </Box>
                        <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
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
    if (cfg.os === "linux") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="Linux" text="Install and deploy on Linux." onClick={() => setPage("dotnet-linux")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="Docker" text="Install and deploy on Docker (Linux)." onClick={() => setPage("dotnet-docker")} />
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>DotNet Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button variant="outlined" disabled={isScopeLoading("dotnet")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(dotnetServices) ? "success" : "error"}
                    disabled={serviceBusy || dotnetServices.length === 0}
                    onClick={() => batchServiceAction(dotnetServices, "DotNet", hasStoppedServices(dotnetServices) ? "start" : "stop")}
                    sx={{ textTransform: "none" }}
                  >
                    {hasStoppedServices(dotnetServices) ? "Start All DotNet" : "Stop All DotNet"}
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 300, overflow: "auto" }}>
                  {dotnetServices.length === 0 && <Typography variant="body2">No DotNet-related services found.</Typography>}
                  {dotnetServices.map((svc) => (
                    <Paper key={`dotnet-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                          {renderServiceUrls(svc)}
                          {renderServicePorts(svc)}
                        </Box>
                        <Chip size="small" color={/running|active|up/i.test(String(svc.status || "")) ? "success" : "default"} label={svc.status || "-"} />
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
    return <Alert severity="info">macOS installer actions are not configured yet.</Alert>;
  };
})();
