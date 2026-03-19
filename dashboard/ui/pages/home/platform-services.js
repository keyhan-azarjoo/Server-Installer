(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["platform-services"] = function renderPlatformServicesPage(p) {
    const { Grid, NavCard, setPage, startNewWebsiteDeployment, setFileManagerData } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <NavCard title="API" text="Open DotNet and Python API installer/deployment pages." onClick={() => setPage("api")} />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Docker" text="Install Docker and manage Docker services/containers." onClick={() => setPage("docker")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="S3" text="Open S3 installer pages." onClick={() => setPage("s3")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="MongoDB" text="Install MongoDB with a Compass-style web admin UI." onClick={() => setPage("mongo")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Proxy" text="Install and manage the multi-layer proxy stack." onClick={() => setPage("proxy")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Python" text="Install Python and manage Jupyter notebooks, kernels, and runtime services." onClick={() => setPage("python")} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Websites" text="Deploy and manage exported static websites, Flutter web builds, and Next export output on IIS." onClick={() => startNewWebsiteDeployment()} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="Files" text="Browse, upload, edit, rename, download, and delete files across the server filesystem." onClick={() => { setPage("files"); setFileManagerData(null); }} outlined />
        </Grid>
        <Grid item xs={12} md={6}>
          <NavCard title="SSL & Certificates" text="Manage TLS certificates: get free Let's Encrypt certs, upload your own CA-signed certs, and assign them to IIS, nginx, or any service." onClick={() => setPage("ssl")} outlined />
        </Grid>
      </Grid>
    );
  };
})();
