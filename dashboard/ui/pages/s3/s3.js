(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.s3 = function renderS3Page(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Button, Box, Stack, Paper, Chip,
      ActionCard, ActionIcon,
      cfg, run, selectableIps, getDefaultSelectableIp, serviceBusy,
      s3WindowsModeOptions, s3WindowsDockerSupported, s3WindowsDockerReason,
      s3ConsoleUrl, s3ApiUrl, s3LoginText, s3Services,
      isScopeLoading, loadS3Info, loadS3Services,
      hasStoppedServices, batchServiceAction, copyText,
      onServiceAction, isServiceRunningStatus,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      OpenCompassStyleIcon, TryOpenCompassIcon, CopyCompassIcon,
    } = p;

    const s3ExtraActions = (
      <>
        {!!s3ConsoleUrl && (
          <ActionIcon title="Open S3 Dashboard" disabled={serviceBusy} onClick={() => window.open(s3ConsoleUrl, "_blank", "noopener,noreferrer")} variant="contained" IconComp={OpenCompassStyleIcon} fallback="UI" />
        )}
        {!!s3ApiUrl && (
          <ActionIcon title="Open S3 API" disabled={serviceBusy} onClick={() => window.open(s3ApiUrl, "_blank", "noopener,noreferrer")} IconComp={TryOpenCompassIcon} fallback="API" />
        )}
        {!!s3LoginText && (
          <ActionIcon title="Copy S3 Login" onClick={() => copyText(s3LoginText, "S3 login details")} IconComp={CopyCompassIcon} fallback="CP" />
        )}
        <Button
          variant="outlined"
          color={hasStoppedServices(s3Services) ? "success" : "error"}
          disabled={serviceBusy || s3Services.length === 0}
          onClick={() => batchServiceAction(s3Services, "S3", hasStoppedServices(s3Services) ? "start" : "stop")}
          sx={{ textTransform: "none" }}
        >
          {hasStoppedServices(s3Services) ? "Start All S3" : "Stop All S3"}
        </Button>
      </>
    );

    const s3UrlDisplay = (!!s3ConsoleUrl || !!s3ApiUrl) ? (
      <Box sx={{ mb: 1 }}>
        {!!s3ConsoleUrl && <Typography variant="body2">Dashboard URL: {s3ConsoleUrl}</Typography>}
        {!!s3ApiUrl && <Typography variant="body2">API URL: {s3ApiUrl}</Typography>}
      </Box>
    ) : null;

    const s3Loading = isScopeLoading("s3");

    const s3ServiceList = (
      <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
        <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
            <Typography variant="h6" fontWeight={800}>S3 Services</Typography>
            <Box sx={{ flexGrow: 1 }} />
            {s3ExtraActions}
            <Button
              variant="outlined"
              disabled={!!s3Loading}
              onClick={() => Promise.all([loadS3Info.current(), loadS3Services.current()])}
              sx={{ textTransform: "none" }}
            >
              Refresh
            </Button>
          </Stack>
          <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
            {s3Services.length === 0 && (
              <Typography variant="body2" color="text.secondary">No S3-related services found.</Typography>
            )}
            {s3UrlDisplay}
            {s3Services.map((svc) => {
              const running = isServiceRunningStatus(svc.status, svc.sub_status);
              const kindLabel = svc.kind || "service";
              return (
                <Paper key={`s3-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                    <Box sx={{ minWidth: 250 }}>
                      <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                        <Typography variant="body2"><b>{svc.form_name || svc.name}</b></Typography>
                        <Chip label={kindLabel} size="small" variant="outlined" sx={{ fontSize: 11, height: 20 }} />
                      </Stack>
                      {svc.image && (
                        <Typography variant="caption" color="text.secondary">Image: {svc.image}</Typography>
                      )}
                      {typeof renderServiceUrls === "function" && renderServiceUrls(svc)}
                      {typeof renderServicePorts === "function" && renderServicePorts(svc)}
                    </Box>
                    {typeof renderServiceStatus === "function" && renderServiceStatus(svc)}
                    <Box sx={{ flexGrow: 1 }} />
                    {typeof renderFolderIcon === "function" && renderFolderIcon(svc)}
                    <Button
                      size="small"
                      variant="outlined"
                      color={running ? "error" : "success"}
                      disabled={!!serviceBusy}
                      onClick={() => onServiceAction(running ? "stop" : "start", svc)}
                      sx={{ textTransform: "none" }}
                    >
                      {running ? "Stop" : "Start"}
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      disabled={!!serviceBusy}
                      onClick={() => onServiceAction("delete", svc)}
                      sx={{ textTransform: "none" }}
                    >
                      Delete
                    </Button>
                  </Stack>
                </Paper>
              );
            })}
          </Box>
        </CardContent>
      </Card>
    );

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>S3-Compatible Object Storage</Typography>
                <Typography variant="body2">
                  MinIO provides Amazon S3-compatible object storage you can run locally. Store files, images, backups, and application data using the standard S3 API. Access your storage through the MinIO Console web UI or connect from any S3-compatible client or SDK.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={8}>
            <ActionCard
              title="Install S3 (Windows)"
              description="Choose IIS or Docker mode, host type (local/DNS/IP), and ports. Use a unique Instance Name to run multiple isolated S3 instances side by side. Leave HTTP Port or HTTPS Port empty to skip that protocol."
              action="/run/s3_windows"
              fields={[
                { name: "LOCALS3_INSTANCE_NAME", label: "Instance Name", defaultValue: "locals3", placeholder: "locals3", required: true },
                { name: "S3_MODE", label: "Mode", type: "select", options: s3WindowsModeOptions, defaultValue: "iis" },
                { name: "LOCALS3_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: getDefaultSelectableIp(selectableIps), required: true, placeholder: "Select IP" },
                { name: "LOCALS3_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
                { name: "LOCALS3_HTTPS_PORT", label: "HTTPS Port", defaultValue: "8443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
                { name: "LOCALS3_API_PORT", label: "MinIO API Port", defaultValue: "39000", required: true, placeholder: "39000", checkPort: true },
                { name: "LOCALS3_UI_PORT", label: "MinIO Console UI Port", defaultValue: "39001", required: true, placeholder: "39001", checkPort: true },
                { name: "LOCALS3_CONSOLE_PORT", label: "Console Proxy Port", defaultValue: "9443", required: true, placeholder: "9443", checkPort: true },
                { name: "LOCALS3_ROOT_USER", label: "S3 Username", defaultValue: "admin" },
                { name: "LOCALS3_ROOT_PASSWORD", label: "S3 Password", defaultValue: "StrongPassword123" },
              ]}
              onRun={run}
              color="#0f766e"
            />
            {!s3WindowsDockerSupported && (
              <Alert severity="warning" sx={{ mt: 1.5 }}>
                Docker mode is disabled on this Windows host. {s3WindowsDockerReason || "This machine is not currently usable for Linux-container Docker workloads."}
              </Alert>
            )}
          </Grid>
          <Grid item xs={12} md={4}>
            <ActionCard
              title="Stop S3 APIs (Windows)"
              description="Stop LocalS3 API/Console services (IIS site, task, and Docker containers)."
              action="/run/s3_windows_stop"
              fields={[]}
              onRun={run}
              color="#7f1d1d"
            />
          </Grid>
          <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
            {s3ServiceList}
          </Grid>
        </Grid>
      );
    }
    if (cfg.os === "linux" || cfg.os === "darwin") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>S3-Compatible Object Storage</Typography>
                <Typography variant="body2">
                  MinIO provides Amazon S3-compatible object storage you can run locally. Store files, images, backups, and application data using the standard S3 API. Access your storage through the MinIO Console web UI or connect from any S3-compatible client or SDK.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={8}>
            <ActionCard
              title="Install S3 (Linux/macOS)"
              description="Run local S3 installer. Choose OS (native nginx proxy) or Docker (MinIO + nginx containers). Use a unique Instance Name to run multiple isolated S3 instances side by side. Leave HTTP Port or HTTPS Port empty to skip that protocol."
              action="/run/s3_linux"
              fields={[
                { name: "LOCALS3_INSTANCE_NAME", label: "Instance Name", defaultValue: "locals3", placeholder: "locals3", required: true },
                { name: "LOCALS3_MODE", label: "Engine", type: "select", options: ["os", "docker"], defaultValue: "os" },
                { name: "LOCALS3_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: getDefaultSelectableIp(selectableIps), required: true, placeholder: "Select IP" },
                { name: "LOCALS3_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
                { name: "LOCALS3_HTTPS_PORT", label: "API HTTPS Port", defaultValue: "9443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
                { name: "LOCALS3_CONSOLE_PORT", label: "Console HTTPS Port", defaultValue: "18443", required: true, placeholder: "18443", checkPort: true },
                { name: "LOCALS3_API_PORT", label: "MinIO API Port (internal)", defaultValue: "9000", required: true, placeholder: "9000", checkPort: true },
                { name: "LOCALS3_UI_PORT", label: "MinIO Console UI Port (internal)", defaultValue: "9001", required: true, placeholder: "9001", checkPort: true },
                { name: "LOCALS3_ROOT_USER", label: "S3 Username", defaultValue: "admin" },
                { name: "LOCALS3_ROOT_PASSWORD", label: "S3 Password", defaultValue: "StrongPassword123" },
              ]}
              onRun={run}
              color="#1e40af"
            />
          </Grid>
          <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
            {s3ServiceList}
          </Grid>
        </Grid>
      );
    }
    return <Alert severity="info">S3 installer is not configured for this OS.</Alert>;
  };
})();
