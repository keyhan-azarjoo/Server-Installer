(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.dotnet = function renderDotnetPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      NavCard,
      cfg, serviceBusy,
      dotnetServices, dockerServices,
      isScopeLoading, loadDotnetInfo, loadDotnetServices, loadDockerServices,
      hasStoppedServices, batchServiceAction, setPage,
      isServiceRunningStatus, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
    } = p;

    const dotnetDockerServices = (dockerServices || []).filter((s) => {
      const text = String(s.name || "") + " " + String(s.image || "");
      return /(dotnet|aspnet|dotnetapp)/i.test(text) && !/python/i.test(text);
    });
    const allServices = [...(dotnetServices || []), ...dotnetDockerServices];

    const serviceList = (svcs) => (
      <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 460px)", overflow: "auto" }}>
        {svcs.length === 0 && <Typography variant="body2" color="text.secondary">No DotNet-related services found.</Typography>}
        {svcs.map((svc) => (
          <Paper key={`dotnet-all-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
              <Box sx={{ minWidth: 250 }}>
                <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "service"})</Typography></Typography>
                {svc.image && <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>}
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
    );

    const _renderApiDocs = ns.renderApiDocs;
    const _apiDocData = ns.apiDocs && ns.apiDocs.dotnet;
    const apiDocsInline = _renderApiDocs && _apiDocData ? _renderApiDocs(p, _apiDocData) : null;

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="IIS" text="Install and deploy on IIS." onClick={() => setPage("dotnet-iis")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="Docker" text="Install and deploy on Docker." onClick={() => setPage("dotnet-docker")} />
          </Grid>
          <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
              <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>All DotNet Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button variant="outlined" disabled={isScopeLoading("dotnet") || isScopeLoading("docker")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current(), loadDockerServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                  {allServices.length > 0 && (
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(allServices) ? "success" : "error"}
                      disabled={serviceBusy}
                      onClick={() => batchServiceAction(allServices, "DotNet", hasStoppedServices(allServices) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(allServices) ? "Start All" : "Stop All"}
                    </Button>
                  )}
                </Stack>
                {serviceList(allServices)}
              </CardContent>
            </Card>
          </Grid>
          {apiDocsInline}
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
          <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
              <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>All DotNet Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button variant="outlined" disabled={isScopeLoading("dotnet") || isScopeLoading("docker")} onClick={() => Promise.all([loadDotnetInfo.current(), loadDotnetServices.current(), loadDockerServices.current()])} sx={{ textTransform: "none" }}>Refresh</Button>
                  {allServices.length > 0 && (
                    <Button
                      variant="outlined"
                      color={hasStoppedServices(allServices) ? "success" : "error"}
                      disabled={serviceBusy}
                      onClick={() => batchServiceAction(allServices, "DotNet", hasStoppedServices(allServices) ? "start" : "stop")}
                      sx={{ textTransform: "none" }}
                    >
                      {hasStoppedServices(allServices) ? "Start All" : "Stop All"}
                    </Button>
                  )}
                </Stack>
                {serviceList(allServices)}
              </CardContent>
            </Card>
          </Grid>
          {apiDocsInline}
        </Grid>
      );
    }
    return <Alert severity="info">macOS installer actions are not configured yet.</Alert>;
  };
})();
