(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.ports = function renderPortsPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, TextField, FormControl, InputLabel,
      Select, MenuItem, Button, Box, Chip, Paper, Tooltip,
      portValue, setPortValue, portProtocol, setPortProtocol, portBusy,
      onPortAction, closeListeningPort,
      listeningPorts, isScopeLoading, loadSystem,
    } = p;

    // Deduplicate by proto+port in case backend still sends duplicates
    const portRows = React.useMemo(() => {
      const seen = {};
      (listeningPorts || []).forEach((item) => {
        const proto = String(item.proto || "").toLowerCase();
        const key = `${proto}:${item.port}`;
        if (!seen[key]) {
          seen[key] = { ...item, proto };
        } else {
          const existing = seen[key];
          const newNames = Array.isArray(item.processes) ? item.processes : (item.process ? [item.process] : []);
          const newPids  = Array.isArray(item.pids)      ? item.pids      : (item.pid     ? [item.pid]     : []);
          existing.processes = Array.from(new Set([...(existing.processes || []), ...newNames]));
          existing.pids      = Array.from(new Set([...(existing.pids      || []), ...newPids]));
          if (!existing.process && existing.processes[0]) existing.process = existing.processes[0];
          if (!existing.pid     && existing.pids[0])      existing.pid     = existing.pids[0];
        }
      });
      return Object.values(seen).sort((a, b) => a.port - b.port || a.proto.localeCompare(b.proto));
    }, [listeningPorts]);

    const tcpCount = portRows.filter((r) => r.proto.startsWith("tcp")).length;
    const udpCount = portRows.filter((r) => r.proto.startsWith("udp")).length;

    return (
      <Grid container spacing={2}>
        {/* Controls card */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent>
              <Typography variant="h6" fontWeight={800} sx={{ mb: 1.5 }}>Port Management</Typography>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ xs: "stretch", md: "center" }}>
                <TextField
                  size="small"
                  label="Port"
                  value={portValue}
                  onChange={(e) => setPortValue(e.target.value.replace(/\D/g, ""))}
                  inputProps={{ maxLength: 5 }}
                  sx={{ width: 120 }}
                />
                <FormControl size="small" sx={{ width: 120 }}>
                  <InputLabel>Protocol</InputLabel>
                  <Select label="Protocol" value={portProtocol} onChange={(e) => setPortProtocol(e.target.value)}>
                    <MenuItem value="tcp">TCP</MenuItem>
                    <MenuItem value="udp">UDP</MenuItem>
                  </Select>
                </FormControl>
                <Button
                  variant="contained"
                  color="success"
                  disabled={portBusy || !portValue}
                  onClick={() => onPortAction("open")}
                  sx={{ textTransform: "none" }}
                >
                  Open Port
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  disabled={portBusy || !portValue}
                  onClick={() => onPortAction("close")}
                  sx={{ textTransform: "none" }}
                >
                  Close Port
                </Button>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                  variant="outlined"
                  disabled={isScopeLoading("all")}
                  onClick={() => loadSystem.current()}
                  sx={{ textTransform: "none" }}
                >
                  {isScopeLoading("all") ? "Refreshing…" : "Refresh"}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Port list card */}
        <Grid item xs={12}>
          <Card sx={{ borderRadius: 3, border: "1px solid #dbe5f6" }}>
            <CardContent sx={{ "&:last-child": { pb: 2 } }}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ xs: "flex-start", sm: "center" }} sx={{ mb: 1.5 }}>
                <Typography variant="h6" fontWeight={800}>Open / Listening Ports</Typography>
                <Box sx={{ flexGrow: 1 }} />
                <Stack direction="row" spacing={0.75}>
                  <Chip label={`${portRows.length} total`} size="small" />
                  <Chip label={`TCP: ${tcpCount}`} size="small" color="primary" />
                  {udpCount > 0 && <Chip label={`UDP: ${udpCount}`} size="small" />}
                </Stack>
              </Stack>

              {/* Header */}
              <Box sx={{
                display: "grid",
                gridTemplateColumns: "64px 72px 1fr 140px 72px",
                gap: 1, px: 1.5, py: 0.5, mb: 0.5,
                borderBottom: "1px solid #e8edf6",
              }}>
                {["PROTO", "PORT", "PROCESS", "PID(S)", ""].map((h) => (
                  <Typography key={h} variant="caption" fontWeight={700} color="text.secondary">{h}</Typography>
                ))}
              </Box>

              <Box sx={{ maxHeight: "calc(100vh - 440px)", overflow: "auto" }}>
                {portRows.length === 0 && (
                  <Typography variant="body2" sx={{ px: 1.5, py: 1, color: "text.secondary" }}>
                    No listening ports found.
                  </Typography>
                )}
                {portRows.map((item) => {
                  const proto = String(item.proto || "").toLowerCase();
                  const isTcp = proto.startsWith("tcp");
                  const processes = (Array.isArray(item.processes) && item.processes.length > 0)
                    ? item.processes
                    : (item.process ? [item.process] : []);
                  const pids = (Array.isArray(item.pids) && item.pids.length > 0)
                    ? item.pids
                    : (item.pid ? [item.pid] : []);
                  return (
                    <Paper
                      key={`${proto}-${item.port}`}
                      variant="outlined"
                      sx={{
                        display: "grid",
                        gridTemplateColumns: "64px 72px 1fr 140px 72px",
                        gap: 1, px: 1.5, py: 0.75, mb: 0.4, borderRadius: 1.5,
                        alignItems: "center",
                        "&:hover": { bgcolor: "#f5f8ff" },
                      }}
                    >
                      <Box>
                        <Chip
                          label={proto.toUpperCase()}
                          size="small"
                          color={isTcp ? "primary" : "default"}
                          sx={{ fontSize: 11, height: 20, minWidth: 44 }}
                        />
                      </Box>
                      <Typography variant="body2" fontWeight={700}>{item.port}</Typography>
                      <Tooltip title={processes.join(", ")} placement="top" arrow>
                        <Typography
                          variant="body2"
                          sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        >
                          {processes.length > 0 ? processes.join(", ") : <span style={{ color: "#9ca3af" }}>—</span>}
                        </Typography>
                      </Tooltip>
                      <Typography variant="caption" color="text.secondary" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {pids.length > 0 ? pids.join(", ") : "—"}
                      </Typography>
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        disabled={portBusy}
                        onClick={() => closeListeningPort(item.port, proto)}
                        sx={{ textTransform: "none", fontSize: 11, minWidth: 58, px: 1 }}
                      >
                        Close
                      </Button>
                    </Paper>
                  );
                })}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };
})();
