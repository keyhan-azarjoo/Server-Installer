(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["mongo-native"] = function renderMongoNativePage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard, ActionIcon,
      cfg, run, selectableIps, serviceBusy,
      mongo, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
    } = p;

    const nativeServices = (mongoDisplayServices || []).filter(
      (s) => String(s.kind || "").toLowerCase() !== "docker"
    );

    const commonFields = [
      { name: "LOCALMONGO_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
      { name: "LOCALMONGO_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
      { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "Leave empty to skip HTTPS", checkPort: true },
      { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017", checkPort: true },
      { name: "LOCALMONGO_WEB_PORT", label: "Web UI Port", defaultValue: "8081", placeholder: "8081" },
      { name: "LOCALMONGO_ADMIN_USER", label: "Admin User", defaultValue: "admin" },
      { name: "LOCALMONGO_ADMIN_PASSWORD", label: "Admin Password", type: "password", defaultValue: "StrongPassword123" },
      { name: "LOCALMONGO_UI_USER", label: "UI User", defaultValue: "admin" },
      { name: "LOCALMONGO_UI_PASSWORD", label: "UI Password", type: "password", defaultValue: "StrongPassword123" },
    ];

    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          {cfg.os === "windows" && (
            <ActionCard
              title="Install MongoDB (Windows)"
              description="Install MongoDB as a native Windows service. Leave HTTP or HTTPS Port empty to skip that protocol."
              action="/run/mongo_windows"
              fields={commonFields}
              onRun={run}
              color="#7c3aed"
            />
          )}
          {(cfg.os === "linux" || cfg.os === "darwin") && (
            <ActionCard
              title={`Install MongoDB (${cfg.os === "linux" ? "Linux" : "macOS"})`}
              description="Deploy MongoDB natively with a Compass-style web admin UI. Leave HTTP or HTTPS Port empty to skip that protocol."
              action="/run/mongo_unix"
              fields={commonFields}
              onRun={run}
              color="#7c3aed"
            />
          )}
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Status</Typography>
              <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "native"})` : "Not installed yet"}</Typography>
              {!!mongo.web_version && <Typography variant="body2">Web Version: {mongo.web_version}</Typography>}
              {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
              {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Native MongoDB Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                {!!mongoWebsiteUrl && (
                  <ActionIcon title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                )}
                <Button variant="outlined" disabled={isScopeLoading("mongo")} onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                  Refresh
                </Button>
                {nativeServices.length > 0 && (
                  <Button
                    variant="contained"
                    color={hasStoppedServices(nativeServices) ? "success" : "error"}
                    disabled={serviceBusy}
                    onClick={() => batchServiceAction(nativeServices, "MongoDB", hasStoppedServices(nativeServices) ? "start" : "stop")}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(nativeServices) ? "Start All" : "Stop All"}
                  </Button>
                )}
              </Stack>
              <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                {nativeServices.length === 0 && (
                  <Typography variant="body2" color="text.secondary">No native MongoDB services found. Install above to see services here.</Typography>
                )}
                {nativeServices.map((svc) => (
                  <Paper key={`mgn-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> <Typography component="span" variant="caption" color="text.secondary">({svc.kind || "service"})</Typography></Typography>
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status) || "-"} />
                      <Box sx={{ flexGrow: 1 }} />
                      <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
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
