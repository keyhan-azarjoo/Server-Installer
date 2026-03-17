(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["python-api"] = function renderPythonApiPage(p) {
    const {
      Grid, NavCard,
      cfg, startNewPythonApiDeployment, renderPythonApiRunsCard,
    } = p;

    const pythonApiTargets = [];
    pythonApiTargets.push(
      <Grid item xs={12} md={6} key="python-system">
        <NavCard
          title="API as OS service"
          text={cfg.os === "windows" ? "Run a Python API app as a Windows service." : "Run a Python API app as an OS service."}
          onClick={() => startNewPythonApiDeployment("python-system")}
        />
      </Grid>
    );
    pythonApiTargets.push(
      <Grid item xs={12} md={6} key="python-docker">
        <NavCard
          title="Docker"
          text="Use the Docker target for a containerized Python API app."
          onClick={() => startNewPythonApiDeployment("python-docker")}
          outlined
        />
      </Grid>
    );
    if (cfg.os === "windows") {
      pythonApiTargets.push(
        <Grid item xs={12} md={6} key="python-iis">
          <NavCard
            title="IIS"
            text="Use the IIS target for Python API hosting on Windows."
            onClick={() => startNewPythonApiDeployment("python-iis")}
            outlined
          />
        </Grid>
      );
    }
    return (
      <Grid container spacing={2}>
        {pythonApiTargets}
        {renderPythonApiRunsCard()}
      </Grid>
    );
  };
})();
