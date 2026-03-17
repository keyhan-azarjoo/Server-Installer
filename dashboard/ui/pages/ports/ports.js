(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.ports = function renderPortsPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, TextField, FormControl, InputLabel, Select, MenuItem, Button, Box,
      portValue, setPortValue, portProtocol, setPortProtocol, portBusy, onPortAction,
      listeningPorts,
    } = p;
    return (
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Port Management</Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                <TextField size="small" label="Port" value={portValue} onChange={(e) => setPortValue(e.target.value)} sx={{ width: 140 }} />
                <FormControl size="small" sx={{ width: 130 }}>
                  <InputLabel>Protocol</InputLabel>
                  <Select label="Protocol" value={portProtocol} onChange={(e) => setPortProtocol(e.target.value)}>
                    <MenuItem value="tcp">TCP</MenuItem>
                    <MenuItem value="udp">UDP</MenuItem>
                  </Select>
                </FormControl>
                <Button variant="contained" disabled={portBusy} onClick={() => onPortAction("open")} sx={{ textTransform: "none" }}>Open Port</Button>
                <Button variant="outlined" disabled={portBusy} onClick={() => onPortAction("close")} sx={{ textTransform: "none" }}>Close Port</Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1 }}>Open/Listening Ports</Typography>
              <Box sx={{ maxHeight: 340, overflow: "auto" }}>
                {listeningPorts.length === 0 && <Typography variant="body2">No listening ports found.</Typography>}
                {listeningPorts.slice(0, 500).map((p, idx) => (
                  <Typography key={`${p.proto}-${p.port}-${idx}`} variant="body2">
                    {String(p.proto || "").toUpperCase()}:{p.port} {p.pid ? `(pid ${p.pid})` : ""} {p.process ? ` ${p.process}` : ""}
                  </Typography>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };
})();
