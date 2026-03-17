(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["python-system"] = function renderPythonSystemPage(p) {
    const {
      Grid, Card, CardContent, Typography,
      ActionCard,
      cfg, run, selectableIps,
      pythonApiEditor, pythonApiEditorSeed,
      renderPythonApiRunsCard,
      defaultPythonApiDirForOs,
    } = p;

    const systemHost = selectableIps.includes(String(pythonApiEditor?.host || "").trim()) ? String(pythonApiEditor?.host || "").trim() : (selectableIps.length === 1 ? selectableIps[0] : "");
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            key={`python-system-${pythonApiEditorSeed}`}
            title="Deploy Python API as OS Service"
            description="Upload or point to your Python API project and publish it as a managed service. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/python_api_service"
            fields={[
              { name: "PYTHON_API_SERVICE_NAME", label: "Service Name", defaultValue: pythonApiEditor?.targetPage === "python-system" ? (pythonApiEditor?.name || "serverinstaller-python-api") : "serverinstaller-python-api", required: true },
              {
                name: "PYTHON_API_HOST_IP",
                label: "Bind IP",
                type: "select",
                options: selectableIps,
                defaultValue: systemHost,
                required: true,
                disabled: selectableIps.length === 0,
                placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
              },
              { name: "PYTHON_API_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP" },
              { name: "PYTHON_API_PORT", label: "HTTPS Port", defaultValue: pythonApiEditor?.targetPage === "python-system" ? (pythonApiEditor?.port || "8443") : "8443", placeholder: "Leave empty to skip HTTPS" },
              { name: "PYTHON_API_SOURCE", label: "Project Path", defaultValue: pythonApiEditor?.targetPage === "python-system" ? (pythonApiEditor?.source || "") : "", placeholder: defaultPythonApiDirForOs(cfg.os), enableUpload: true },
              { name: "PYTHON_API_MAIN_FILE", label: "Main File Name (optional)", defaultValue: pythonApiEditor?.targetPage === "python-system" ? (pythonApiEditor?.mainFile || "") : "", placeholder: "main.py" },
            ]}
            onRun={run}
            color="#0f766e"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>OS Service Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTP Port</b> — serve plain HTTP on this port. Leave empty to disable HTTP.
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTPS Port</b> — serve HTTPS (TLS) on this port. Leave empty to disable HTTPS.
              </Typography>
              <Typography variant="body2">Upload a folder or point to a folder path. If you leave Main File Name empty, the backend auto-detects <code>main.py</code>, <code>app.py</code>, and similar defaults.</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>Redeploying the same service name replaces the app files, recreates the virtual environment, reinstalls requirements, and updates the service.</Typography>
            </CardContent>
          </Card>
        </Grid>
        {renderPythonApiRunsCard()}
      </Grid>
    );
  };
})();
