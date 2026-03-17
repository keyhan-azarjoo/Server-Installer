(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["python-iis"] = function renderPythonIisPage(p) {
    const {
      Alert, Grid, Card, CardContent, Typography,
      ActionCard,
      cfg, run, selectableIps,
      pythonApiEditor, pythonApiEditorSeed,
      renderPythonApiRunsCard,
      defaultPythonApiDirForOs,
    } = p;

    if (cfg.os !== "windows") {
      return <Alert severity="info">Python IIS deployment is only available on Windows hosts.</Alert>;
    }
    const iisHost = selectableIps.includes(String(pythonApiEditor?.host || "").trim()) ? String(pythonApiEditor?.host || "").trim() : (selectableIps.length === 1 ? selectableIps[0] : "");
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            key={`python-iis-${pythonApiEditorSeed}`}
            title="Deploy Python API to IIS"
            description="Create an IIS-backed site for your Python API project. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/python_api_iis"
            fields={[
              { name: "PYTHON_API_SITE_NAME", label: "IIS Site Name", defaultValue: pythonApiEditor?.targetPage === "python-iis" ? (pythonApiEditor?.name || "ServerInstallerPythonApi") : "ServerInstallerPythonApi", required: true },
              {
                name: "PYTHON_API_HOST_IP",
                label: "Bind IP",
                type: "select",
                options: selectableIps,
                defaultValue: iisHost,
                required: true,
                disabled: selectableIps.length === 0,
                placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
              },
              { name: "PYTHON_API_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "PYTHON_API_PORT", label: "HTTPS Port", defaultValue: pythonApiEditor?.targetPage === "python-iis" ? (pythonApiEditor?.port || "8443") : "8443", placeholder: "Leave empty to skip HTTPS", checkPort: true },
              { name: "PYTHON_API_SOURCE", label: "Project Path", defaultValue: pythonApiEditor?.targetPage === "python-iis" ? (pythonApiEditor?.source || "") : "", placeholder: defaultPythonApiDirForOs(cfg.os), enableUpload: true },
              { name: "PYTHON_API_MAIN_FILE", label: "Main File Name (optional)", defaultValue: pythonApiEditor?.targetPage === "python-iis" ? (pythonApiEditor?.mainFile || "") : "", placeholder: "main.py" },
            ]}
            onRun={run}
            color="#1d4ed8"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>IIS Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTP Port</b> — IIS HTTP binding. Leave empty to skip HTTP.
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTPS Port</b> — IIS HTTPS binding (TLS termination). Leave empty to skip HTTPS.
              </Typography>
              <Typography variant="body2">IIS terminates TLS and proxies to the managed Python process.</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>Use this for Windows-hosted Python APIs that should sit behind an IIS site.</Typography>
            </CardContent>
          </Card>
        </Grid>
        {renderPythonApiRunsCard()}
      </Grid>
    );
  };
})();
