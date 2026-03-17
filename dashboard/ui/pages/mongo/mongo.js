(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.mongo = function renderMongoPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      NavCard, ActionIcon,
      cfg, serviceBusy,
      mongo, mongoDocker, mongoWebsiteUrl, mongoDisplayServices,
      mongoCompassDownloadUrl, mongoCompassUri,
      isScopeLoading, loadMongoInfo, loadMongoServices,
      hasStoppedServices, batchServiceAction, copyText, tryOpenCompass, promptOpenMongoWebsite,
      isServiceRunningStatus, formatServiceState, onServiceAction, setPage,
      renderServiceUrls, renderServicePorts,
      DownloadCompassIcon, CopyCompassIcon, TryOpenCompassIcon, OpenCompassStyleIcon,
      RefreshSmallIcon, StartAllIcon, StopAllIcon,
    } = p;

    // Group services by instance: derive a group key from name prefix
    function groupServices(svcs) {
      const groups = {};
      (svcs || []).forEach((svc) => {
        const raw = String(svc.name || "");
        const key = raw.includes("-") ? raw.split("-").slice(0, -1).join("-") || raw : raw;
        if (!groups[key]) groups[key] = [];
        groups[key].push(svc);
      });
      return groups;
    }

    function renderServiceGroup(groupKey, svcs) {
      const allRunning = svcs.every((s) => isServiceRunningStatus(s.status, s.sub_status));
      const allStopped = svcs.every((s) => !isServiceRunningStatus(s.status, s.sub_status));
      const isDbGroup = svcs.some((s) => /(mongo|mongod|mongodb)/i.test(String(s.name || "").replace(/-?(web|ui|express)$/i, "")));
      return (
        <Paper key={groupKey} variant="outlined" sx={{ p: 1.5, mb: 1.5, borderRadius: 2, border: "1px solid #dbe5f6" }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }} sx={{ mb: 1 }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ flexGrow: 1 }}>{groupKey}</Typography>
            {isDbGroup && (
              <>
                <ActionIcon title="Copy Compass URI" onClick={() => copyText(mongoCompassUri, "Compass connection URI")} IconComp={CopyCompassIcon} fallback="CP" />
                <ActionIcon title="Try Open Compass" onClick={tryOpenCompass} IconComp={TryOpenCompassIcon} fallback="OP" />
                {!!mongoWebsiteUrl && (
                  <ActionIcon title="Open Compass-Style UI" disabled={serviceBusy} onClick={promptOpenMongoWebsite} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
                )}
              </>
            )}
            <Button
              size="small"
              variant="outlined"
              color={allStopped ? "success" : "error"}
              disabled={serviceBusy}
              onClick={() => batchServiceAction(svcs, "MongoDB", allStopped ? "start" : "stop")}
              sx={{ textTransform: "none", fontSize: 12 }}
            >
              {allStopped ? "Start All" : "Stop All"}
            </Button>
          </Stack>
          {svcs.map((svc) => (
            <Paper key={`mg-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 0.75, borderRadius: 1.5, bgcolor: "#f8faff" }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Box sx={{ minWidth: 200 }}>
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
        </Paper>
      );
    }

    const groups = groupServices(mongoDisplayServices);

    const servicePanel = (
      <Grid item xs={12}>
        <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
          <CardContent>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
              <Typography variant="h6" fontWeight={800}>MongoDB Services</Typography>
              <Box sx={{ flexGrow: 1 }} />
              <ActionIcon title="Download Compass" onClick={() => window.open(mongoCompassDownloadUrl, "_blank", "noopener,noreferrer")} IconComp={DownloadCompassIcon} fallback="DL" />
              <Button
                type="button"
                variant="outlined"
                disabled={isScopeLoading("mongo")}
                onClick={() => Promise.all([loadMongoInfo.current(), loadMongoServices.current()])}
                sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
              >
                Refresh
              </Button>
              {mongoDisplayServices.length > 0 && (
                <Button
                  type="button"
                  variant="contained"
                  color={hasStoppedServices(mongoDisplayServices) ? "success" : "error"}
                  disabled={serviceBusy || mongoDisplayServices.length === 0}
                  onClick={() => batchServiceAction(mongoDisplayServices, "MongoDB", hasStoppedServices(mongoDisplayServices) ? "start" : "stop")}
                  sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                >
                  {hasStoppedServices(mongoDisplayServices) ? "Start All" : "Stop All"}
                </Button>
              )}
            </Stack>
            <Box sx={{ mt: 1.2, maxHeight: 400, overflow: "auto" }}>
              {mongoDisplayServices.length === 0 && <Typography variant="body2" color="text.secondary">No MongoDB services found.</Typography>}
              {Object.entries(groups).map(([key, svcs]) => renderServiceGroup(key, svcs))}
            </Box>
          </CardContent>
        </Card>
      </Grid>
    );

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="Native" text="Install MongoDB as a Windows service." onClick={() => setPage("mongo-native")} />
          </Grid>
          {servicePanel}
        </Grid>
      );
    }
    if (cfg.os === "linux" || cfg.os === "darwin") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <NavCard title="Native" text="Install MongoDB natively with a Compass-style web UI." onClick={() => setPage("mongo-native")} />
          </Grid>
          <Grid item xs={12} md={6}>
            <NavCard title="Docker" text="Deploy MongoDB and web UI in Docker containers." onClick={() => setPage("mongo-docker")} />
          </Grid>
          {servicePanel}
        </Grid>
      );
    }
    return null;
  };
})();
