(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["mongo-docker"] = function renderMongoDockerPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard, ActionIcon,
      cfg, run, serviceBusy,
      mongo, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
    } = p;

    if (cfg.os !== "linux" && cfg.os !== "darwin") return null;

    const dockerServices = (mongoDisplayServices || []).filter(
      (s) => String(s.kind || "").toLowerCase() === "docker"
    );

    // Group Docker services by instance prefix
    function groupDockerServices(svcs) {
      const groups = {};
      svcs.forEach((svc) => {
        const raw = String(svc.name || "");
        const key = raw.includes("-") ? raw.split("-").slice(0, -1).join("-") || raw : raw;
        if (!groups[key]) groups[key] = [];
        groups[key].push(svc);
      });
      return groups;
    }

    const groups = groupDockerServices(dockerServices);

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            title="Deploy MongoDB (Docker)"
            description="Run MongoDB and mongo-express web UI in Docker containers. Leave HTTP or HTTPS Port empty to skip that protocol."
            action="/run/mongo_docker"
            fields={[
              { name: "LOCALMONGO_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "Leave empty to skip HTTPS", checkPort: true },
              { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017", checkPort: true },
              { name: "LOCALMONGO_WEB_PORT", label: "Web UI Port (internal)", defaultValue: "8081", placeholder: "8081" },
              { name: "LOCALMONGO_ADMIN_USER", label: "Admin User", defaultValue: "admin" },
              { name: "LOCALMONGO_ADMIN_PASSWORD", label: "Admin Password", type: "password", defaultValue: "StrongPassword123" },
              { name: "LOCALMONGO_UI_USER", label: "UI User", defaultValue: "admin" },
              { name: "LOCALMONGO_UI_PASSWORD", label: "UI Password", type: "password", defaultValue: "StrongPassword123" },
            ]}
            onRun={run}
            color="#166534"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Status</Typography>
              <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not deployed yet"}</Typography>
              {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
              {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Docker MongoDB Containers</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                <Button variant="outlined" disabled={isScopeLoading("mongo")} onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                  Refresh
                </Button>
                {dockerServices.length > 0 && (
                  <Button
                    variant="contained"
                    color={hasStoppedServices(dockerServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(dockerServices, "MongoDB", hasStoppedServices(dockerServices) ? "start" : "stop")}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(dockerServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              <Box sx={{ mt: 1.2, maxHeight: 400, overflow: "auto" }}>
                {dockerServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No Docker MongoDB containers found. Deploy above to see containers here.</Typography>
                )}
                {Object.entries(groups).map(([groupKey, svcs]) => (
                  <Paper key={groupKey} variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2, border: "1px solid #dbe5f6" }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} sx={{ mb: 1 }}>
                      <Typography variant="subtitle2" fontWeight={700} sx={{ flexGrow: 1 }}>{groupKey}</Typography>
                      <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                      <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                      {!!mongoWebsiteUrl && (
                        <ActionIcon title="Open UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                      )}
                      <Button size="small" variant="outlined" color={hasStoppedServices(svcs) ? "success" : "error"} disabled={serviceBusy} onClick={() => batchServiceAction(svcs, "MongoDB", hasStoppedServices(svcs) ? "start" : "stop")} sx={{ textTransform: "none", fontSize: 12 }}>
                        {hasStoppedServices(svcs) ? "Start Group" : "Stop Group"}
                      </Button>
                    </Stack>
                    {svcs.map((svc) => (
                      <Paper key={`mgd-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 0.75, borderRadius: 1.5, bgcolor: "#f8faff" }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 200 }}>
                            <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "docker"})</Typography></Typography>
                            {svc.image && <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>}
                            {renderServiceUrls(svc)}
                            {renderServicePorts(svc)}
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status) || "-"} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                            {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                          </Button>
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                        </Stack>
                      </Paper>
                    ))}
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
