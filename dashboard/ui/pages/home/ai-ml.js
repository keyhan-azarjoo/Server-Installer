(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages["ai-ml"] = function renderAiMlPage(p) {
    const { Box, Typography } = p;
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 320, color: "text.secondary" }}>
        <Typography variant="h5" fontWeight={800} sx={{ mb: 1, color: "#6d28d9" }}>AI & ML Services</Typography>
        <Typography variant="body1" color="text.secondary">Coming soon.</Typography>
      </Box>
    );
  };
})();
