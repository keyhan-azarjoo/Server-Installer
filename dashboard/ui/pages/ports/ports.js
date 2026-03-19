(() => {
  const ns = window.ServerInstallerUI = window.ServerInstallerUI || {};
  ns.pages = ns.pages || {};

  ns.pages.ports = function renderPortsPage(p) {
    const {
      Grid, Card, CardContent, Typography, Stack, TextField, FormControl, InputLabel,
      Select, MenuItem, Button, Box, Chip, Paper, Tooltip, Dialog, DialogTitle,
      DialogContent, DialogActions, Divider,
      portValue, setPortValue, portProtocol, setPortProtocol, portBusy,
      onPortAction, closeListeningPort,
      listeningPorts, managedPortSet, isScopeLoading, loadSystem,
    } = p;

    const [searchText, setSearchText] = React.useState("");
    const [selectedPort, setSelectedPort] = React.useState(null);

    // Known OS/system process names (Windows + Linux)
    const SYSTEM_PROC_NAMES = React.useMemo(() => new Set([
      // Windows OS processes
      "svchost","system","lsass","services","wininit","smss","csrss","winlogon",
      "ntoskrnl","wslhost","vmmem","msmpeng","idle","registry","spoolsv","dwm",
      "fontdrvhost","audiodg","taskhostw","runtimebroker","searchindexer","msiexec",
      // Linux/macOS system daemons
      "systemd","init","kthreadd","kernel","rpcbind","dbus-daemon","rpc.statd",
      "sshd","systemd-resolved","systemd-networkd","avahi-daemon","cups","cupsd",
      "chronyd","ntpd","rsyslogd","syslog-ng","crond","cron","atd","dnsmasq",
      "NetworkManager","wpa_supplicant","ModemManager","bluetoothd","polkitd",
      "udevd","systemd-udevd","irqbalance","acpid","thermald","fwupd",
      "mdnsresponder","configd","launchd","netbiosd","discoveryd",
    ]), []);

    const isSystemPort = React.useCallback((item) => {
      const processes = (Array.isArray(item.processes) && item.processes.length > 0)
        ? item.processes : (item.process ? [item.process] : []);
      if (processes.length === 0) return item.port < 1024;
      return processes.every((p) =>
        SYSTEM_PROC_NAMES.has(p.toLowerCase().trim()) ||
        SYSTEM_PROC_NAMES.has(p.toLowerCase().replace(/\.exe$/i, "").trim())
      );
    }, [SYSTEM_PROC_NAMES]);

    // Deduplicate by proto+port
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

    // Filter rows by search text
    const filteredRows = React.useMemo(() => {
      const q = searchText.trim().toLowerCase();
      if (!q) return portRows;
      return portRows.filter((item) => {
        const procs = Array.isArray(item.processes) && item.processes.length > 0
          ? item.processes
          : (item.process ? [item.process] : []);
        return (
          String(item.port).includes(q) ||
          String(item.proto || "").toLowerCase().includes(q) ||
          procs.some((n) => n.toLowerCase().includes(q))
        );
      });
    }, [portRows, searchText]);

    const installerRows = React.useMemo(() => filteredRows.filter((r) => managedPortSet && managedPortSet.has(r.port)), [filteredRows, managedPortSet]);
    const userRows      = React.useMemo(() => filteredRows.filter((r) => !(managedPortSet && managedPortSet.has(r.port)) && !isSystemPort(r)), [filteredRows, managedPortSet, isSystemPort]);
    const systemRows    = React.useMemo(() => filteredRows.filter((r) => !(managedPortSet && managedPortSet.has(r.port)) && isSystemPort(r)), [filteredRows, managedPortSet, isSystemPort]);

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
                  inputProps={{ maxLength: 5, autoComplete: "off", "data-lpignore": "true", "data-form-type": "other" }}
                  autoComplete="off"
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
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <TextField
                    size="small"
                    placeholder="Filter by port or process…"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    inputProps={{ autoComplete: "off", "data-lpignore": "true", "data-form-type": "other" }}
                    sx={{ width: 220 }}
                  />
                  <Chip label={`${filteredRows.length}${searchText ? ` / ${portRows.length}` : ""} total`} size="small" />
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
                {filteredRows.length === 0 && (
                  <Typography variant="body2" sx={{ px: 1.5, py: 1, color: "text.secondary" }}>
                    {searchText ? "No ports match your filter." : "No listening ports found."}
                  </Typography>
                )}

                {/* Render a group of port rows */}
                {[
                  { label: "Installer Services", rows: installerRows, color: "#7c3aed", bg: "#f5f3ff" },
                  { label: "Application Ports",  rows: userRows,      color: "#1e40af", bg: "#eff6ff" },
                  { label: "System Ports",        rows: systemRows,    color: "#6b7280", bg: "#f9fafb" },
                ].map(({ label, rows, color, bg }) => rows.length === 0 ? null : (
                  <Box key={label} sx={{ mb: 1.5 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, mb: 0.75 }}>
                      <Typography variant="caption" fontWeight={800} sx={{ color, textTransform: "uppercase", letterSpacing: 0.6 }}>
                        {label}
                      </Typography>
                      <Chip label={rows.length} size="small" sx={{ height: 18, fontSize: 11, bgcolor: bg, color, fontWeight: 700 }} />
                    </Box>
                    {rows.map((item) => {
                      const proto = String(item.proto || "").toLowerCase();
                      const isTcp = proto.startsWith("tcp");
                      const processes = (Array.isArray(item.processes) && item.processes.length > 0)
                        ? item.processes : (item.process ? [item.process] : []);
                      const pids = (Array.isArray(item.pids) && item.pids.length > 0)
                        ? item.pids : (item.pid ? [item.pid] : []);
                      return (
                        <Paper
                          key={`${proto}-${item.port}`}
                          variant="outlined"
                          onClick={() => setSelectedPort(item)}
                          sx={{
                            display: "grid",
                            gridTemplateColumns: "64px 72px 1fr 140px 72px",
                            gap: 1, px: 1.5, py: 0.75, mb: 0.4, borderRadius: 1.5,
                            alignItems: "center", cursor: "pointer",
                            "&:hover": { bgcolor: bg },
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
                            onClick={(e) => { e.stopPropagation(); closeListeningPort(item.port, proto); }}
                            sx={{ textTransform: "none", fontSize: 11, minWidth: 58, px: 1 }}
                          >
                            Close
                          </Button>
                        </Paper>
                      );
                    })}
                  </Box>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Port detail dialog */}
        {selectedPort && (() => {
          const item = selectedPort;
          const proto = String(item.proto || "").toLowerCase();
          const processes = (Array.isArray(item.processes) && item.processes.length > 0)
            ? item.processes
            : (item.process ? [item.process] : []);
          const pids = (Array.isArray(item.pids) && item.pids.length > 0)
            ? item.pids
            : (item.pid ? [item.pid] : []);
          return (
            <Dialog open onClose={() => setSelectedPort(null)} maxWidth="xs" fullWidth>
              <DialogTitle sx={{ fontWeight: 800, pb: 1 }}>
                Port {item.port} — {proto.toUpperCase()}
              </DialogTitle>
              <DialogContent sx={{ pt: 0 }}>
                <Stack spacing={1.5}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>PROTOCOL</Typography>
                    <Typography variant="body2">{proto.toUpperCase()}</Typography>
                  </Box>
                  <Divider />
                  <Box>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>PORT</Typography>
                    <Typography variant="body2" fontWeight={700}>{item.port}</Typography>
                  </Box>
                  <Divider />
                  <Box>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>
                      {processes.length === 1 ? "PROCESS" : "PROCESSES"}
                    </Typography>
                    {processes.length > 0
                      ? processes.map((name, i) => (
                          <Typography key={i} variant="body2">{name}</Typography>
                        ))
                      : <Typography variant="body2" color="text.secondary">—</Typography>
                    }
                  </Box>
                  <Divider />
                  <Box>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>
                      {pids.length === 1 ? "PID" : "PIDs"}
                    </Typography>
                    {pids.length > 0
                      ? <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{pids.join(", ")}</Typography>
                      : <Typography variant="body2" color="text.secondary">—</Typography>
                    }
                  </Box>
                  {item.state && (
                    <>
                      <Divider />
                      <Box>
                        <Typography variant="caption" color="text.secondary" fontWeight={700}>STATE</Typography>
                        <Typography variant="body2">{item.state}</Typography>
                      </Box>
                    </>
                  )}
                </Stack>
              </DialogContent>
              <DialogActions sx={{ px: 3, pb: 2 }}>
                <Button
                  variant="outlined"
                  color="error"
                  disabled={portBusy}
                  onClick={() => { setSelectedPort(null); closeListeningPort(item.port, proto); }}
                  sx={{ textTransform: "none" }}
                >
                  Close Port
                </Button>
                <Button onClick={() => setSelectedPort(null)} sx={{ textTransform: "none" }}>Dismiss</Button>
              </DialogActions>
            </Dialog>
          );
        })()}
      </Grid>
    );
  };
})();
