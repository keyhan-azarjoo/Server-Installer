(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.mongo = function renderMongoPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard, ActionIcon,
      cfg, run, selectableIps, serviceBusy,
      mongo, mongoDocker, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
      RefreshSmallIcon, StartAllIcon, StopAllIcon,
    } = p;

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <ActionCard
              title="Install MongoDB (Windows)"
              description="Install MongoDB as a native Windows service."
              action="/run/mongo_windows"
              fields={[
                { name: "LOCALMONGO_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "443, 9445..." },
                { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017" },
                { name: "LOCALMONGO_WEB_PORT", label: "Local Web UI Port", defaultValue: "8081", placeholder: "8081" },
                { name: "LOCALMONGO_ADMIN_USER", label: "MongoDB Admin User", defaultValue: "admin" },
                { name: "LOCALMONGO_ADMIN_PASSWORD", label: "MongoDB Admin Password", type: "password", defaultValue: "StrongPassword123" },
                { name: "LOCALMONGO_UI_USER", label: "Web UI User", defaultValue: "admin" },
                { name: "LOCALMONGO_UI_PASSWORD", label: "Web UI Password", type: "password", defaultValue: "StrongPassword123" },
              ]}
              onRun={run}
              color="#7c3aed"
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Requirements</Typography>
                <Typography variant="body2">Windows service: native `mongod` install</Typography>
                <Typography variant="body2">Docker: optional, not required</Typography>
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
                  <Typography variant="h6" fontWeight={800}>MongoDB Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                  <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                  <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                  {!!mongoWebsiteUrl && (
                    <ActionIcon title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                  )}
                  <Button
                    type="button"
                    variant="outlined"
                    disabled={isScopeLoading("mongo")}
                    onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])}
                    startIcon={RefreshSmallIcon ? <RefreshSmallIcon fontSize="small" /> : null}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    Refresh
                  </Button>
                  <Button
                    type="button"
                    variant="contained"
                    color={hasStoppedServices(mongoDisplayServices) ? "success" : "error"}
                    disabled={serviceBusy || mongoDisplayServices.length === 0}
                    onClick={() => batchServiceAction(mongoDisplayServices, "MongoDB", hasStoppedServices(mongoDisplayServices) ? "start" : "stop")}
                    startIcon={(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon) ? React.createElement(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon, { fontSize: "small" }) : null}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(mongoDisplayServices) ? "Start All" : "Stop All"}
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                  {mongoDisplayServices.length === 0 && <Typography variant="body2">No MongoDB-related services found.</Typography>}
                  {mongoDisplayServices.map((svc) => (
                    <Paper key={`mongo-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                          {renderServiceUrls(svc)}
                          {renderServicePorts(svc)}
                        </Box>
                        <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
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
    if (cfg.os === "linux" || cfg.os === "darwin") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <ActionCard
              title={`Install MongoDB (${cfg.os === "linux" ? "Linux" : "macOS"})`}
              description="Deploy MongoDB with a Compass-style web admin UI behind HTTPS."
              action="/run/mongo_unix"
              fields={[
                { name: "LOCALMONGO_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: selectableIps.length === 1 ? selectableIps[0] : "", required: true, placeholder: "Select IP" },
                { name: "LOCALMONGO_HTTPS_PORT", label: "HTTPS Port", defaultValue: "9445", placeholder: "443, 9445..." },
                { name: "LOCALMONGO_MONGO_PORT", label: "MongoDB Port", defaultValue: "27017", placeholder: "27017" },
                { name: "LOCALMONGO_WEB_PORT", label: "Local Web UI Port", defaultValue: "8081", placeholder: "8081" },
                { name: "LOCALMONGO_ADMIN_USER", label: "MongoDB Admin User", defaultValue: "admin" },
                { name: "LOCALMONGO_ADMIN_PASSWORD", label: "MongoDB Admin Password", type: "password", defaultValue: "StrongPassword123" },
                { name: "LOCALMONGO_UI_USER", label: "Web UI User", defaultValue: "admin" },
                { name: "LOCALMONGO_UI_PASSWORD", label: "Web UI Password", type: "password", defaultValue: "StrongPassword123" },
              ]}
              onRun={run}
              color="#7c3aed"
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Requirements</Typography>
                <Typography variant="body2">Docker: {mongoDocker.installed ? `Installed (${mongoDocker.version || "unknown"})` : (cfg.os === "linux" ? "Will be installed if missing" : "Docker Desktop must be running")}</Typography>
                <Typography variant="body2">HTTPS Proxy: Built into Mongo setup</Typography>
                <Typography variant="body2">MongoDB: {mongo.installed ? `Installed (${mongo.server_version || "docker"})` : "Not installed yet"}</Typography>
                {!!mongoWebsiteUrl && <Typography variant="body2" sx={{ mt: 1 }}>HTTPS URL: {mongoWebsiteUrl}</Typography>}
                {!!mongo.connection_string && <Typography variant="body2">Connection: {mongo.connection_string}</Typography>}
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>MongoDB Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
                  <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                  <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                  {!!mongoWebsiteUrl && (
                    <ActionIcon title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                  )}
                  <Button
                    type="button"
                    variant="outlined"
                    disabled={isScopeLoading("mongo")}
                    onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])}
                    startIcon={RefreshSmallIcon ? <RefreshSmallIcon fontSize="small" /> : null}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    Refresh
                  </Button>
                  <Button
                    type="button"
                    variant="contained"
                    color={hasStoppedServices(mongoDisplayServices) ? "success" : "error"}
                    disabled={serviceBusy || mongoDisplayServices.length === 0}
                    onClick={() => batchServiceAction(mongoDisplayServices, "MongoDB", hasStoppedServices(mongoDisplayServices) ? "start" : "stop")}
                    startIcon={(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon) ? React.createElement(hasStoppedServices(mongoDisplayServices) ? StartAllIcon : StopAllIcon, { fontSize: "small" }) : null}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(mongoDisplayServices) ? "Start All" : "Stop All"}
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                  {mongoDisplayServices.length === 0 && <Typography variant="body2">No MongoDB-related services found.</Typography>}
                  {mongoDisplayServices.map((svc) => (
                    <Paper key={`mongo-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 250 }}>
                          <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                          {renderServiceUrls(svc)}
                          {renderServicePorts(svc)}
                        </Box>
                        <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
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
    return <Alert severity="info">MongoDB installer is not configured for this OS.</Alert>;
  };
})();
