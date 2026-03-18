(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.docker = function renderDockerPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard,
      cfg, run, serviceBusy,
      docker, dockerServices, dockerServiceUrls, dockerManageEndpoints, dockerConnectionHelp,
      isScopeLoading, loadDockerInfo, loadDockerServices,
      hasStoppedServices, batchServiceAction, copyText,
      isServiceRunningStatus, formatServiceState, onServiceAction,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      scopeErrors,
    } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          {cfg.os === "windows" ? (
            <ActionCard
              title="Install Docker (Windows)"
              description="Install Docker only on Windows."
              action="/run/windows_docker_engine"
              fields={[]}
              onRun={run}
              color="#1f2937"
            />
          ) : (
            <ActionCard
              title="Install Docker (Linux)"
              description="Install Docker Engine on Linux/macOS-compatible hosts."
              action="/run/linux_setup_docker"
              fields={[]}
              onRun={run}
              color="#1f2937"
            />
          )}
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Docker Engine</Typography>
              <Typography variant="body2">Installed: {docker.installed ? "Yes" : "No"}</Typography>
              <Typography variant="body2">CLI: {docker.version || "-"}</Typography>
              <Typography variant="body2">Engine: {docker.server_version || "-"}</Typography>
              <Typography variant="body2">Running: {docker.running ? "Yes" : "No"}</Typography>
              <Typography variant="body2">OS Type: {docker.os_type || "-"}</Typography>
              <Typography variant="body2" sx={{ mt: 1.5 }}>
                For app deployment, use the existing DotNet Docker page.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Docker Management</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Button variant="outlined" disabled={isScopeLoading("docker")} onClick={() => Promise.all([loadDockerInfo.current(), loadDockerServices.current()])} sx={{ textTransform: "none" }}>
                  {isScopeLoading("docker") ? "Refreshing..." : "Refresh"}
                </Button>
                <Button
                  variant="outlined"
                  color={hasStoppedServices(dockerServices) ? "success" : "error"}
                  disabled={serviceBusy || dockerServices.length === 0}
                  onClick={() => batchServiceAction(dockerServices, "Docker", hasStoppedServices(dockerServices) ? "start" : "stop")}
                  sx={{ textTransform: "none" }}
                >
                  {hasStoppedServices(dockerServices) ? "Start All Docker" : "Stop All Docker"}
                </Button>
              </Stack>
              {scopeErrors.docker && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.docker}</Alert>}
              <Box sx={{ mt: 1.25 }}>
                <Typography variant="body2">{dockerConnectionHelp}</Typography>
                {dockerManageEndpoints.map((endpoint) => (
                  <Stack key={endpoint} direction="row" spacing={0.75} alignItems="center" sx={{ mt: 0.75 }}>
                    <Typography variant="caption" sx={{ color: "text.secondary", wordBreak: "break-all" }}>{endpoint}</Typography>
                    <Button size="small" variant="outlined" onClick={() => copyText(endpoint, "Docker endpoint")} sx={{ textTransform: "none", minWidth: 56 }}>
                      Copy
                    </Button>
                  </Stack>
                ))}
                {dockerManageEndpoints.length === 0 && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                    Common Docker remote ports: `2375` (plain TCP) and `2376` (TLS).
                  </Typography>
                )}
              </Box>
              {!!dockerServiceUrls.length && (
                <Box sx={{ mt: 1.5 }}>
                  {dockerServiceUrls.map((u) => (
                    <Stack key={u} direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.4 }}>
                      <Typography variant="caption" sx={{ color: "text.secondary", wordBreak: "break-all" }}>{u}</Typography>
                      <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => window.open(u, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none", minWidth: 56 }}>
                        Open
                      </Button>
                    </Stack>
                  ))}
                </Box>
              )}
              <Box sx={{ mt: 1.5, flexGrow: 1, minHeight: "calc(100vh - 420px)", overflow: "auto" }}>
                {dockerServices.length === 0 && <Typography variant="body2">No Docker services or containers found.</Typography>}
                {dockerServices.map((svc) => {
                  const running = isServiceRunningStatus(svc.status, svc.sub_status);
                  const autostart = !!svc.autostart;
                  const deleteDisabled = serviceBusy || (String(svc.kind || "").toLowerCase() !== "docker");
                  return (
                    <Paper key={`${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 280 }}>
                          <Typography variant="body2" fontWeight={700}>{svc.name}</Typography>
                          <Typography variant="caption" color="text.secondary">{svc.display_name || "-"}</Typography>
                        </Box>
                        <Chip size="small" label={svc.kind || "service"} />
                        {renderServiceStatus(svc)}
                        <Chip size="small" color={autostart ? "primary" : "default"} label={autostart ? "autostart:on" : "autostart:off"} />
                        <Box sx={{ flexGrow: 1 }} />
                        {renderFolderIcon(svc)}
                        <Button
                          size="small"
                          variant="outlined"
                          color={running ? "error" : "success"}
                          disabled={serviceBusy}
                          onClick={() => onServiceAction(running ? "stop" : "start", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          {running ? "Stop" : "Start"}
                        </Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>Restart</Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy || autostart} onClick={() => onServiceAction("autostart_on", svc)} sx={{ textTransform: "none" }}>Auto-start ON</Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy || !autostart} onClick={() => onServiceAction("autostart_off", svc)} sx={{ textTransform: "none" }}>Auto-start OFF</Button>
                        <Button size="small" variant="outlined" color="error" disabled={deleteDisabled} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>Delete</Button>
                      </Stack>
                      {renderServiceUrls(svc)}
                      {renderServicePorts(svc)}
                    </Paper>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };
})();
