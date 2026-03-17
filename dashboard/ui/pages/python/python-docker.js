(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["python-docker"] = function renderPythonDockerPage(p) {
    const {
      Grid, Card, CardContent, Typography,
      ActionCard,
      cfg, run, selectableIps,
      pythonApiEditor, pythonApiEditorSeed,
      renderPythonApiRunsCard,
      defaultPythonApiDirForOs,
    } = p;

    const dockerHost = selectableIps.includes(String(pythonApiEditor?.host || "").trim()) ? String(pythonApiEditor?.host || "").trim() : (selectableIps.length === 1 ? selectableIps[0] : "");
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <ActionCard
            key={`python-docker-${pythonApiEditorSeed}`}
            title="Deploy Python API to Docker"
            description="Build a Docker image from your Python API source and publish it. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/python_api_docker"
            fields={[
              { name: "PYTHON_API_CONTAINER_NAME", label: "Container Name", defaultValue: pythonApiEditor?.targetPage === "python-docker" ? (pythonApiEditor?.name || "serverinstaller-python-api") : "serverinstaller-python-api", required: true },
              {
                name: "PYTHON_API_HOST_IP",
                label: "Public IP",
                type: "select",
                options: selectableIps,
                defaultValue: dockerHost,
                required: true,
                disabled: selectableIps.length === 0,
                placeholder: selectableIps.length > 0 ? "Select IP" : "Loading IP addresses...",
              },
              { name: "PYTHON_API_HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP" },
              { name: "PYTHON_API_PORT", label: "HTTPS Port", defaultValue: pythonApiEditor?.targetPage === "python-docker" ? (pythonApiEditor?.port || "8443") : "8443", placeholder: "Leave empty to skip HTTPS" },
              { name: "PYTHON_API_SOURCE", label: "Project Path", defaultValue: pythonApiEditor?.targetPage === "python-docker" ? (pythonApiEditor?.source || "") : "", placeholder: defaultPythonApiDirForOs(cfg.os), enableUpload: true },
              { name: "PYTHON_API_MAIN_FILE", label: "Main File Name (optional)", defaultValue: pythonApiEditor?.targetPage === "python-docker" ? (pythonApiEditor?.mainFile || "") : "", placeholder: "main.py" },
            ]}
            onRun={run}
            color="#1f2937"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Docker Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTP Port</b> — expose plain HTTP on this port. Leave empty to disable HTTP.
              </Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <b>HTTPS Port</b> — expose HTTPS (TLS) on this port. Leave empty to disable HTTPS.
              </Typography>
              <Typography variant="body2">A container image is built from the uploaded or selected source.</Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>If a <code>requirements.txt</code> file exists, it is installed during image build.</Typography>
            </CardContent>
          </Card>
        </Grid>
        {renderPythonApiRunsCard()}
      </Grid>
    );
  };
})();
