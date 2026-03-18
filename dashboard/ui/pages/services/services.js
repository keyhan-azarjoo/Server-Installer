(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.services = function renderServicesPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, TextField, Button, Box, Alert, Paper, Chip,
      serviceFilter, setServiceFilter, isScopeLoading, loadServices,
      scopeErrors, filteredServices, serviceBusy,
      isServiceRunningStatus, formatServiceState, onServiceAction, actionLabel,
      renderServiceUrls, renderServicePorts, renderServiceStatus, renderFolderIcon,
      renderStartupTypeDropdown, renderEditServiceIcon,
      setPage, setFileManagerPath,
    } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Managed Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <TextField size="small" label="Filter" value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} sx={{ minWidth: 260 }} />
                <Button variant="outlined" disabled={isScopeLoading("all")} onClick={() => loadServices.current()} sx={{ textTransform: "none" }}>
                  {isScopeLoading("all") ? "Refreshing..." : "Refresh"}
                </Button>
              </Stack>
              {scopeErrors.all && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.all}</Alert>}
              <Box sx={{ mt: 1.5, flexGrow: 1, minHeight: "calc(100vh - 380px)", overflow: "auto" }}>
                {filteredServices.length === 0 && <Typography variant="body2">No services found.</Typography>}
                {filteredServices.map((svc) => {
                  const status = String(svc.status || "");
                  return (
                    <Paper key={`${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                        <Box sx={{ minWidth: 280 }}>
                          <Typography variant="body2" fontWeight={700}>{svc.name}</Typography>
                          <Typography variant="caption" color="text.secondary">{svc.display_name || "-"}</Typography>
                        </Box>
                        <Chip size="small" label={svc.kind || "service"} />
                        {renderServiceStatus(svc)}
                        <Box sx={{ flexGrow: 1 }} />
                        {renderStartupTypeDropdown(svc)}
                        {renderFolderIcon(svc)}
                        {renderEditServiceIcon(svc)}
                        <Button
                          size="small"
                          variant="outlined"
                          color={isServiceRunningStatus(status, svc.sub_status) ? "error" : "success"}
                          disabled={serviceBusy}
                          onClick={() => onServiceAction(isServiceRunningStatus(status, svc.sub_status) ? "stop" : "start", svc)}
                          sx={{ textTransform: "none" }}
                        >
                          {isServiceRunningStatus(status, svc.sub_status) ? "Stop" : "Start"}
                        </Button>
                        <Button size="small" variant="outlined" disabled={serviceBusy} onClick={() => onServiceAction("restart", svc)} sx={{ textTransform: "none" }}>{actionLabel("restart")}</Button>
                        <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>{actionLabel("delete")}</Button>
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
