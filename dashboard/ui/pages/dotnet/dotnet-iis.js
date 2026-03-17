(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-iis"] = function renderDotnetIisPage(p) {
    const { Grid, ActionCard, cfg, run } = p;

    if (cfg.os !== "windows") return null;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <ActionCard title="Install IIS" description="Install IIS features and .NET prerequisites." action="/run/windows_setup_iis" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title="Deploy IIS"
            description="Deploy application to IIS. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/windows_iis"
            fields={[
              { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
              { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP" },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS" },
            ]}
            onRun={run}
            color="#1e40af"
          />
        </Grid>
      </Grid>
    );
  };
})();
