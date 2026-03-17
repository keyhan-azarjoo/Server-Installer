(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.api = function renderApiPage(p) {
    const { NavCard, setPage } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <NavCard title="DotNet" text="Open the existing .NET installer and deployment pages." onClick={() => setPage("dotnet")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python" text="Configure Python API service deployment separately from Jupyter notebooks." onClick={() => setPage("python-api")} outlined />
        </Grid>
      </Grid>
    );
  };
})();
