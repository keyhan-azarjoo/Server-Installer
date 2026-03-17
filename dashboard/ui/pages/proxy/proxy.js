(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.proxy = function renderProxyPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip,
      ActionCard,
      cfg, run, selectableIps, serviceBusy,
      proxy, proxyServices, systemInfo,
      isScopeLoading, loadProxyInfo, loadProxyServices,
      hasStoppedServices, batchServiceAction, onProxyServiceAction,
      isServiceRunningStatus, formatServiceState,
      windowsAdminRequired, windowsAdminReason,
    } = p;

    if (cfg.os === "windows" || cfg.os === "linux") {
      const panelUrl = String(proxy.panel_url || "").trim();
      const panelHostMatch = panelUrl.match(/^https?:\/\/([^/:]+)/i);
      const proxyHost = String((panelHostMatch && panelHostMatch[1]) || selectableIps[0] || "").trim();
      const layerOptions = [
        "layer3-basic",
        "layer4-nginx",
        "layer6-stunnel",
        "layer7-v2ray-vless",
        "layer7-v2ray-vmess",
        "layer7-real-domain",
        "layer7-iran-optimized",
      ];
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <ActionCard
              title={`Install Proxy (${cfg.os === "windows" ? "Windows" : "Linux"})`}
              description={cfg.os === "windows" ? "Run the Linux proxy stack inside WSL with persistent keepalive + autostart." : "Install the proxy stack locally from the vendored project copy."}
              action={cfg.os === "windows" ? "/run/proxy_windows" : "/run/proxy_linux"}
              fields={[
                { name: "PROXY_LAYER", label: "Layer", type: "select", options: layerOptions, defaultValue: proxy.layer || "layer3-basic", required: true },
                { name: "PROXY_DOMAIN", label: "Domain", placeholder: "Required for real-domain / iran-optimized layers" },
                { name: "PROXY_EMAIL", label: "Email", placeholder: "Required for real-domain / iran-optimized layers" },
                { name: "PROXY_DUCKDNS_TOKEN", label: "DuckDNS Token", placeholder: "Optional unless using DuckDNS", trailingAction: { label: "Open DuckDNS", href: "https://www.duckdns.org/" } },
                { name: "PROXY_PANEL_PORT", label: "Proxy Dashboard Port", defaultValue: String((proxy.panel_url || "").match(/:(\d+)\s*$/)?.[1] || "8443"), required: true, placeholder: "8443" },
                ...(selectableIps.length > 0 ? [{ name: "PROXY_HOST_IP", label: "Select IP", type: "select", options: selectableIps, defaultValue: proxyHost, required: true, placeholder: "Select IP" }] : []),
                ...(cfg.os === "windows" ? [{ name: "PROXY_WSL_DISTRO", label: "WSL Distro", defaultValue: proxy.distro || "Ubuntu" }] : []),
              ]}
              onRun={run}
              color="#1d4ed8"
              runDisabled={windowsAdminRequired}
              runDisabledReason={windowsAdminReason}
            />
          </Grid>
          <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
                <CardContent>
                  <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Current State</Typography>
                  {cfg.os === "windows" && (
                    <Typography variant="body2">Dashboard Admin: {systemInfo?.is_admin ? "Yes" : "No"}</Typography>
                  )}
                  <Typography variant="body2">Mode: {proxy.mode || (cfg.os === "windows" ? "wsl" : "native")}</Typography>
                {!!proxy.layer && <Typography variant="body2">Layer: {proxy.layer}</Typography>}
                {!!proxy.distro && <Typography variant="body2">WSL Distro: {proxy.distro}</Typography>}
                {!!panelUrl && <Typography variant="body2" sx={{ mt: 1 }}>Panel URL: {panelUrl}</Typography>}
                {!!panelUrl && (
                  <Button
                    variant="contained"
                    size="small"
                    sx={{ mt: 1, textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                    onClick={() => window.open(panelUrl, "_blank", "noopener,noreferrer")}
                  >
                    Open Proxy Panel
                  </Button>
                )}
                <Typography variant="body2">Source: vendored local copy of the proxy project</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>Proxy Services</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  {!!panelUrl && (
                    <Button variant="contained" disabled={serviceBusy} onClick={() => window.open(panelUrl, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                      Open Proxy Panel
                    </Button>
                  )}
                  <Button
                    variant="outlined"
                    color={hasStoppedServices(proxyServices) ? "success" : "error"}
                    disabled={serviceBusy || proxyServices.length === 0}
                    onClick={() => batchServiceAction(proxyServices, "Proxy", hasStoppedServices(proxyServices) ? "start" : "stop")}
                    sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}
                  >
                    {hasStoppedServices(proxyServices) ? "Start All Proxy" : "Stop All Proxy"}
                  </Button>
                  <Button variant="outlined" disabled={isScopeLoading("proxy")} onClick={() => Promise.all([loadProxyInfo.current(), loadProxyServices.current()])} sx={{ textTransform: "none", borderRadius: 2, fontWeight: 700 }}>
                    Refresh
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, maxHeight: 320, overflow: "auto" }}>
                  {proxyServices.length === 0 && <Typography variant="body2">No proxy services detected yet.</Typography>}
                  {proxyServices.map((svc) => {
                    const deleteDisabled = serviceBusy || !["proxy-panel", "ServerInstaller-ProxyWSL"].includes(String(svc.name || ""));
                    return (
                      <Paper key={`proxy-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 260 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind || "service"})</Typography>
                            <Typography variant="caption" color="text.secondary">{svc.display_name || "-"}</Typography>
                          </Box>
                          <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                          <Box sx={{ flexGrow: 1 }} />
                          <Button size="small" variant="outlined" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "error" : "success"} disabled={serviceBusy} onClick={() => onProxyServiceAction(isServiceRunningStatus(svc.status, svc.sub_status) ? "stop" : "start", svc)} sx={{ textTransform: "none" }}>
                            {isServiceRunningStatus(svc.status, svc.sub_status) ? "Stop" : "Start"}
                          </Button>
                          <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onProxyServiceAction("restart", svc)} sx={{ textTransform: "none" }}>
                            Restart
                          </Button>
                          <Button size="small" variant="outlined" color="error" disabled={deleteDisabled} onClick={() => onProxyServiceAction("delete", svc)} sx={{ textTransform: "none" }}>
                            Delete
                          </Button>
                        </Stack>
                      </Paper>
                    );
                  })}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      );
    }
    return <Alert severity="info">Proxy installer is currently configured for Linux hosts and Windows via WSL.</Alert>;
  };
})();
