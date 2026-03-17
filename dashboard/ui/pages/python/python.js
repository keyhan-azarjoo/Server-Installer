(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.python = function renderPythonPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, Button, Box, Paper, Chip, Alert,
      ActionCard,
      cfg, run, selectableIps, serviceBusy,
      pythonService, pythonRuntimeServices, pythonInstalledRuntimes,
      isScopeLoading, loadPythonInfo, loadPythonServices,
      onServiceAction, runPythonInstallWithCurrentSettings,
      isServiceRunningStatus, formatServiceState,
      renderServiceUrls, renderServicePorts,
      scopeErrors,
      defaultNotebookDirForOs,
      setPage, setFileManagerPath,
    } = p;

    const pythonUrl = String(pythonService.jupyter_url || "").trim();
    const pythonPort = String(pythonService.jupyter_port || "8888").trim() || "8888";
    const pythonHost = String(pythonService.host || "").trim();
    const pythonNotebookDir = String(
      pythonService.notebook_dir || pythonService.default_notebook_dir || defaultNotebookDirForOs(cfg.os)
    ).trim();
    const installState = pythonService.installed
      ? `${pythonService.python_version || "installed"}`
      : "Not installed yet";
    const installOsLabel = cfg.os === "windows" ? "Windows" : (cfg.os === "linux" ? "Linux" : (cfg.os === "darwin" ? "macOS" : cfg.os_label));
    const commandShellLabel = cfg.os === "windows" ? "Windows cmd" : "shell";
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            title={`Install Python (${installOsLabel})`}
            description="Install the managed Python runtime and run Jupyter notebooks on this host. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/python_install"
            fields={[
              { name: "PYTHON_VERSION", label: "Python Version", type: "select", options: ["3.13", "3.12", "3.11", "3.10"], defaultValue: pythonService.requested_version || "3.12", required: true },
              {
                name: "PYTHON_HOST_IP",
                label: "Jupyter IP",
                type: "select",
                options: selectableIps,
                defaultValue: pythonHost,
                required: true,
                disabled: selectableIps.length === 0,
                placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
              },
              { name: "PYTHON_NOTEBOOK_DIR", label: "Notebook Directory", defaultValue: pythonNotebookDir, placeholder: defaultNotebookDirForOs(cfg.os) },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
            ]}
            onRun={run}
            color="#2563eb"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Managed Python</Typography>
              <Typography variant="body2">Interpreter: {installState}</Typography>
              <Typography variant="body2">Executable: {pythonService.python_executable || "-"}</Typography>
              <Typography variant="body2">Scripts: {pythonService.scripts_dir || "-"}</Typography>
              <Typography variant="body2">Notebook Directory: {pythonNotebookDir || "-"}</Typography>
              <Typography variant="body2">Jupyter: {pythonService.jupyter_installed ? "Installed" : "Not installed"}</Typography>
              <Typography variant="body2">Jupyter IP: {pythonHost || "-"}</Typography>
              <Typography variant="body2">Jupyter Port: {pythonPort || "-"}</Typography>
              <Typography variant="body2">Jupyter Status: {pythonService.jupyter_running ? "Running" : "Stopped"}</Typography>
              <Typography variant="body2">HTTPS: {pythonService.jupyter_https_enabled ? "Enabled" : "Disabled"}</Typography>
              <Typography variant="body2">Auth User: {pythonService.jupyter_username || "-"}</Typography>
              {!!pythonUrl && <Typography variant="body2" sx={{ mt: 1 }}>URL: {pythonUrl}</Typography>}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title={cfg.os === "windows" ? "Run Python CMD" : "Run Python Command"}
            description={`Send a ${commandShellLabel} command with the managed Python and Scripts directories placed first in PATH.`}
            action="/run/python_command"
            fields={[
              { name: "PYTHON_CMD", label: "Command", defaultValue: "python -m pip --version", required: true, placeholder: "python -m pip install requests" },
            ]}
            onRun={run}
            color="#0f766e"
          />
        </Grid>
        <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <Typography variant="h6" fontWeight={800}>Python Services</Typography>
                <Box sx={{ flexGrow: 1 }} />
                {!!pythonUrl && (
                  <Button variant="contained" disabled={serviceBusy} onClick={() => window.open(pythonUrl, "_blank", "noopener,noreferrer")} sx={{ textTransform: "none" }}>
                    Open Jupyter
                  </Button>
                )}
                <Button variant="outlined" disabled={isScopeLoading("python")} onClick={() => Promise.all([loadPythonInfo.current(), loadPythonServices.current()])} sx={{ textTransform: "none" }}>
                  Refresh
                </Button>
              </Stack>
              {scopeErrors.python && <Alert severity="error" sx={{ mt: 1 }}>{scopeErrors.python}</Alert>}
              <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                {pythonRuntimeServices.length === 0 && <Typography variant="body2">No managed Python runtime found yet.</Typography>}
                {pythonRuntimeServices.map((svc) => (
                  <Paper key={`python-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                      <Box sx={{ minWidth: 250 }}>
                        <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                        {svc.display_name && <Typography variant="caption" color="text.secondary">{svc.display_name}</Typography>}
                        {renderServiceUrls(svc)}
                        {renderServicePorts(svc)}
                      </Box>
                      <Chip size="small" color={isServiceRunningStatus(svc.status, svc.sub_status) ? "success" : "default"} label={formatServiceState(svc.status, svc.sub_status)} />
                      <Box sx={{ flexGrow: 1 }} />
                      {!!(svc.project_path && setFileManagerPath && setPage) && (
                        <Button size="small" variant="outlined" onClick={() => { setFileManagerPath(svc.project_path); setPage("files"); }} sx={{ textTransform: "none" }}>Open Folder</Button>
                      )}
                      {svc.manageable !== false && (
                        <>
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
                        </>
                      )}
                      {svc.deletable && (
                        <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>
                          Delete
                        </Button>
                      )}
                    </Stack>
                  </Paper>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        {cfg.os === "windows" && (
          <Grid item xs={12} sx={{ display: "flex", flexDirection: "column" }}>
            <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", display: "flex", flexDirection: "column", flexGrow: 1 }}>
              <CardContent sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflow: "hidden", "&:last-child": { pb: 2 } }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                  <Typography variant="h6" fontWeight={800}>Installed Pythons</Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Button variant="outlined" disabled={isScopeLoading("python")} onClick={() => Promise.all([loadPythonInfo.current(), loadPythonServices.current()])} sx={{ textTransform: "none" }}>
                    Refresh
                  </Button>
                </Stack>
                <Box sx={{ mt: 1.2, flexGrow: 1, minHeight: "calc(100vh - 520px)", overflow: "auto" }}>
                  {pythonInstalledRuntimes.length === 0 && <Typography variant="body2">No installed Python runtimes found.</Typography>}
                  {pythonInstalledRuntimes.map((svc) => {
                    const isManaged = String(svc.kind || "").toLowerCase() === "python_installation";
                    return (
                      <Paper key={`python-installed-${svc.kind}-${svc.name}`} variant="outlined" sx={{ p: 1, mb: 1, borderRadius: 2 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                          <Box sx={{ minWidth: 280 }}>
                            <Typography variant="body2"><b>{svc.name}</b> ({svc.kind})</Typography>
                            {svc.display_name && <Typography variant="caption" color="text.secondary">{svc.display_name}</Typography>}
                            <Typography variant="caption" sx={{ display: "block", color: "text.secondary", wordBreak: "break-all", mt: 0.5 }}>
                              {svc.detail || svc.sub_status || "-"}
                            </Typography>
                          </Box>
                          <Chip size="small" color="default" label="installed" />
                          <Box sx={{ flexGrow: 1 }} />
                          {isManaged && (
                            <Button size="small" variant="outlined" disabled={serviceBusy} onClick={runPythonInstallWithCurrentSettings} sx={{ textTransform: "none" }}>
                              Reinstall
                            </Button>
                          )}
                          <Button size="small" variant="outlined" color="error" disabled={serviceBusy} onClick={() => onServiceAction("delete", svc)} sx={{ textTransform: "none" }}>
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
        )}
      </Grid>
    );
  };
})();
