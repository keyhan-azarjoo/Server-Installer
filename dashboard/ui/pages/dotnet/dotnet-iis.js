(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["dotnet-iis"] = function renderDotnetIisPage(p) {
    const { Grid, Card, CardContent, Typography, Divider, ActionCard, cfg, run } = p;

    if (cfg.os !== "windows") return null;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12} md={4}>
          <ActionCard title="Install IIS" description="Install IIS features and .NET prerequisites." action="/run/windows_setup_iis" fields={[{ name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" }]} onRun={run} color="#0f766e" />
        </Grid>
        <Grid item xs={12} md={4}>
          <ActionCard
            title="Deploy IIS"
            description="Deploy application to IIS. Leave HTTP Port or HTTPS Port empty to skip that protocol — at least one must be set."
            action="/run/windows_iis"
            fields={[
              { name: "SiteName", label: "Site Name", defaultValue: "DotNetApp", required: true, placeholder: "DotNetApp" },
              { name: "DomainName", label: "Domain Name", placeholder: "e.g. myapp.example.com (optional)" },
              { name: "SourceValue", label: "Source Path or URL", enableUpload: true },
              { name: "DotNetChannel", label: ".NET Channel", defaultValue: "8.0" },
              { name: "HTTP_PORT", label: "HTTP Port", defaultValue: "", placeholder: "Leave empty to skip HTTP", checkPort: true },
              { name: "HTTPS_PORT", label: "HTTPS Port", defaultValue: "443", placeholder: "Leave empty to skip HTTPS", checkPort: true, certSelect: "SSL_CERT_NAME" },
            ]}
            onRun={run}
            color="#1e40af"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6", height: "100%" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>IIS Deploy Target</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>Run <b>Install IIS</b> first to enable IIS features and the ASP.NET Core Module.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>Source Path or URL</b> — a published .NET folder, a <code>.zip</code> archive, or a GitHub URL. Point to your <code>publish</code> output directory.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>.NET Channel</b> — runtime version, e.g. <code>8.0</code> or <code>9.0</code>.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" sx={{ mb: 1 }}><b>HTTP Port</b> — serve plain HTTP on this port. Leave empty to disable HTTP.</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><b>HTTPS Port</b> — serve HTTPS (TLS) on this port. Leave empty to disable HTTPS.</Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2">Redeploying to the same site name updates the app pool and replaces application files without changing IIS bindings.</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };
})();
