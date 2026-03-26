(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.api = function renderApiPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, NavCard,
      cfg, serviceBusy,
      dotnetServices, dockerServices, pythonApiRuns,
      isScopeLoading, loadDotnetServices, loadDotnetInfo, loadDockerServices, loadDockerInfo, loadPythonServices, loadPythonInfo,
      hasStoppedServices, batchServiceAction,
      isServiceRunningStatus, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon, renderEditServiceIcon,
      setPage,
    } = p;

    const allApiServices = [
      ...(dotnetServices || []),
      ...(dockerServices || []).filter(s => /(dotnet|aspnet|python)/i.test(String(s.name || "") + String(s.image || ""))),
      ...(pythonApiRuns || []),
    ];

    const kindLabel = (svc) => {
      if (svc.kind === "docker") return "Docker";
      if (svc.kind === "iis" || svc.kind === "windows-service") return "IIS";
      if (svc.kind === "systemd") return "Linux";
      if (svc.kind === "python" || svc.kind === "python-api") return "Python";
      return svc.kind || "service";
    };

    const kindColor = (svc) => {
      const k = kindLabel(svc);
      if (k === "Docker") return "info";
      if (k === "IIS" || k === "Linux") return "primary";
      if (k === "Python") return "success";
      return "default";
    };

    const refreshing = isScopeLoading("dotnet") || isScopeLoading("docker") || isScopeLoading("python");

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <NavCard title="DotNet" text="Open the existing .NET installer and deployment pages." onClick={() => setPage("dotnet")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python" text="Configure Python API service deployment separately from Jupyter notebooks." onClick={() => setPage("python-api")} outlined />
        </Grid>

        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>All API Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                  variant="outlined"
                  disabled={refreshing}
                  onClick={() => Promise.all([
                    loadDotnetInfo.current(), loadDotnetServices.current(),
                    loadDockerInfo.current(), loadDockerServices.current(),
                    loadPythonInfo.current(), loadPythonServices.current(),
                  ])}
                  sx={{ textTransform: "none" }}
                >
                  Refresh
                </Button>
                {allApiServices.length > 0 && (
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(allApiServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(allApiServices, "API", hasStoppedServices(allApiServices) ? "start" : "stop")}
                    sx={{ textTransform: "none" }}
                  >
                    {hasStoppedServices(allApiServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>

              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 460px)", overflow: "auto" }}>
                {allApiServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No API services found.</Typography>
                )}
                {allApiServices.map((svc) => (
                  <Paper key={`api-all-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2">
                          <b>{svc.name}</b>{" "}
                          <Chip label={kindLabel(svc)} color={kindColor(svc)} size="small" variant="outlined" sx={{ ml: 0.5 }} />
                        </Typography>
                        {svc.image && <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>}
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      {renderServiceStatus(svc)}
                      <Box sx={{ flexGrow: 1 }} />
                      {renderFolderIcon(svc)}
                      {typeof renderEditServiceIcon === "function" && renderEditServiceIcon(svc)}
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
  };
})();
