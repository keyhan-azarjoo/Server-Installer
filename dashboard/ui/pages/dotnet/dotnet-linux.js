(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-linux"] = function renderDotnetLinuxPage(p) {
    const { Grid, ActionCard, cfg, run } = p;

    if (cfg.os !== "linux") return null;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <ActionCard title="Install Linux" description="Install Linux prerequisites." action="/run/linux_prereq" fields={[{ name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
        </Grid>
        <Grid item xs={12} md={6}>
          <ActionCard
            title="Deploy Linux"
            description="Deploy application on Linux. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/linux"
            fields={[
              { name: "DOTNET_CHANNEL", label: ".NET Channel", defaultValue: "8.0" },
              { name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true },
              { name: "DOMAIN_NAME", label: "Domain Name" },
              { name: "SERVICE_NAME", label: "Service Name", defaultValue: "dotnet-app" },
              { name: "SERVICE_PORT", label: "Service Internal Port", defaultValue: "5000" },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "80", placeholder: "Leave empty to skip HTTP" },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS" },
            ]}
            onRun={run}
          />
        </Grid>
      </Grid>
    );
  };
})();
