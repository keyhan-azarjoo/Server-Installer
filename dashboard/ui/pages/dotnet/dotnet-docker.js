(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-docker"] = function renderDotnetDockerPage(p) {
    const { Grid, ActionCard, cfg, run } = p;

    if (cfg.os === "windows") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker prerequisites and .NET runtime." action="/run/windows_setup_docker" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy Docker" description="Deploy application to Docker." action="/run/windows_docker" fields={[{ name: "SourceValue", label: "Source Path or URL", enableUpload: true }, { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }, { name: "DockerHostPort", label: "Docker Host Port", defaultValue: "8080" }]} onRun={run} color="#334155" />
          </Grid>
        </Grid>
      );
    }
    if (cfg.os === "linux") {
      return (
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <ActionCard title="Install Docker" description="Install Docker Engine on Linux." action="/run/linux_setup_docker" fields={[]} onRun={run} color="#1f2937" />
          </Grid>
          <Grid item xs={12} md={6}>
            <ActionCard title="Deploy Docker" description="Build and run Docker container for uploaded/published app." action="/run/linux_docker" fields={[{ name: "SOURCE_VALUE", label: "Source Path or URL", placeholder: "/srv/app or https://...", enableUpload: true }, { name: "DOCKER_HOST_PORT", label: "Docker Host Port", defaultValue: "8080" }]} onRun={run} color="#334155" />
          </Grid>
        </Grid>
      );
    }
    return null;
  };
})();
